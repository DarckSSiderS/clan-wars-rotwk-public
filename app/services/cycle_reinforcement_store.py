"""Persistence boundary for reserve/help aggregates; never commits caller work.

Lock order is always cycle -> aggregate. Write paths CAS both revisions and
flush in the caller transaction. initialize/load return INTERNAL records, not
API responses; read is the only viewer-safe projection. _resolve_interception
is a trusted worker boundary, never a public user command or request-body API.
"""

from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.core.time import as_utc
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord
from app.models.campaign import CampaignSeason
from app.models.clan import Clan, ClanMember, ClanMembershipPeriod
from app.models.cycle_battle import CycleTerritoryBattle
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.services.cycle_economy_store import CycleEconomyStore
from app.models.user import User
from app.services.campaign_cycle_service import CyclePhase
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_dispatch_route_service import CycleDispatchRouteService
from app.services.cycle_plan_service import CyclePlanService
from app.services import cycle_reinforcements as rules


_TYPES = {cls.__name__: cls for cls in (
    rules.PlayerIdentity, rules.ReserveUse, rules.Reserve, rules.Battle,
    rules.Ambush, rules.HelpRequest, rules.Dispatch, rules.CycleReinforcements,
)}


def _encode(value):
    if value is None or type(value) in (int, str):
        return value
    if isinstance(value, rules.Outcome):
        return {'type': 'outcome', 'value': value.value}
    if isinstance(value, UUID):
        return {'type': 'uuid', 'value': str(value)}
    if isinstance(value, datetime):
        return {'type': 'datetime', 'value': rules._time(value).isoformat()}
    if isinstance(value, Decimal):
        return {'type': 'decimal', 'value': str(rules._score(value))}
    if isinstance(value, (tuple, frozenset)):
        items = sorted(value, key=repr) if isinstance(value, frozenset) else value
        return {'type': 'frozenset' if isinstance(value, frozenset) else 'tuple',
                'items': [_encode(item) for item in items]}
    if is_dataclass(value) and type(value).__name__ in _TYPES and type(value) is _TYPES[type(value).__name__]:
        return {'type': type(value).__name__,
                'fields': {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    raise ValueError('Unsupported reinforcement JSON type')


def _decode(value, depth=0):
    if depth > 24:
        raise ValueError('Reinforcement JSON nesting exceeds schema')
    if value is None or type(value) in (str, int):
        return value
    if type(value) is not dict or type(value.get('type')) is not str:
        raise ValueError('Typed reinforcement JSON required')
    kind = value['type']
    if kind in ('uuid', 'datetime', 'decimal', 'outcome'):
        if set(value) != {'type', 'value'} or type(value['value']) is not str:
            raise ValueError('Invalid typed scalar')
        raw = value['value']
        if kind == 'uuid':
            return UUID(raw)
        if kind == 'datetime':
            return rules._time(datetime.fromisoformat(raw))
        if kind == 'decimal':
            return rules._score(raw)
        return rules.Outcome(raw)
    if kind in ('tuple', 'frozenset'):
        if set(value) != {'type', 'items'} or type(value['items']) is not list:
            raise ValueError('Invalid typed collection')
        items = tuple(_decode(item, depth + 1) for item in value['items'])
        if kind == 'frozenset':
            if len(frozenset(items)) != len(items):
                raise ValueError('Duplicate set member')
            return frozenset(items)
        return items
    cls = _TYPES.get(kind)
    if (cls is None or set(value) != {'type', 'fields'} or type(value['fields']) is not dict
            or set(value['fields']) != {f.name for f in fields(cls)}):
        raise ValueError('Unknown type or fields in reinforcement JSON')
    return cls(**{name: _decode(item, depth + 1) for name, item in value['fields'].items()})


def encode_state(state):
    if not isinstance(state, rules.CycleReinforcements):
        raise ValueError('Reinforcement aggregate required')
    return {'schema': 1, 'aggregate': _encode(state)}


def decode_state(payload):
    """Closed, versioned allowlist. No imports, executable data, or pickle."""
    try:
        if (type(payload) is not dict or set(payload) != {'schema', 'aggregate'}
                or type(payload['schema']) is not int or payload['schema'] != 1):
            raise ValueError('Unsupported reinforcement schema')
        result = _decode(payload['aggregate'])
        if not isinstance(result, rules.CycleReinforcements):
            raise ValueError('Reinforcement aggregate required')
        # Reject shape coercion (e.g. untyped timestamps/UUIDs/outcomes, wrong
        # collection tags, omitted current reserve history) on restore.
        if encode_state(result) != payload:
            raise ValueError('Noncanonical reinforcement state')
        return result
    except (TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError('Malformed reinforcement state') from error


class CycleReinforcementStore:
    def __init__(self):
        self.cycles = CampaignCycleStore()

    @staticmethod
    def _identities(db, user_ids):
        ids = set(user_ids)
        for user_id in ids:
            rules._positive(user_id)
        rows = db.query(ExternalPlayerIdentity).filter(
            ExternalPlayerIdentity.user_id.in_(ids),
            ExternalPlayerIdentity.source == 'bfmeladder',
            ExternalPlayerIdentity.verification_status == 'verified',
        ).all()
        try:
            result = {row.user_id: rules.PlayerIdentity(row.source, UUID(row.external_uuid)) for row in rows}
        except (TypeError, AttributeError, ValueError) as error:
            raise ValueError('Verified valid external UUID required') from error
        if set(result) != ids or len(set(result.values())) != len(result):
            raise ValueError('Unique verified external identity required for every player')
        return result

    def _plan_identities(self, db, plan, user_ids):
        ids = set(user_ids)
        for uid in ids:
            rules._positive(uid)
        snapshot = plan.snapshot or {}
        if 'player_identities' not in snapshot:
            # Explicit legacy-fixture fallback only. New production plans always
            # record verified source/UUID at reveal; never replace that map live.
            return self._identities(db, ids)
        mapping = snapshot['player_identities']
        if type(mapping) is not dict:
            raise ValueError('Frozen player identity map required')
        result = {}
        try:
            for uid in ids:
                item = mapping[str(uid)]
                if type(item) is not dict or set(item) != {'source', 'uuid'}:
                    raise ValueError('Complete frozen player identity required')
                if type(item['uuid']) is not str:
                    raise ValueError('Frozen UUID string required')
                result[uid] = rules.PlayerIdentity(item['source'], UUID(item['uuid']))
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError('Invalid frozen player identity map') from error
        if len(set(result.values())) != len(result):
            raise ValueError('Unique frozen player identities required')
        return result

    @staticmethod
    def _permission(db, clan_id, actor_user_id):
        rules._positive(clan_id)
        rules._positive(actor_user_id)
        clan = db.get(Clan, clan_id)
        members = db.query(ClanMember).filter_by(user_id=actor_user_id).all()
        if clan is None or clan.is_deleted or len(members) != 1 or members[0].clan_id != clan_id:
            raise PermissionError('Current clan membership required')
        return clan, members[0]

    def _actor(self, db, clan_id, actor_user_id):
        clan, member = self._permission(db, clan_id, actor_user_id)
        if clan.leader_id != actor_user_id and not member.is_warlord:
            raise PermissionError('Only head or voivode may request or dispatch')

    def _locked(self, db, cycle_id):
        cycle = self.cycles._locked(db, cycle_id)
        row = db.query(CycleReinforcementState).filter_by(cycle_id=cycle_id).with_for_update().populate_existing().one_or_none()
        if row is None:
            raise ValueError('Reinforcement state must be initialized')
        state, bindings = self._unpack(row, cycle)
        return cycle, row, state, bindings

    @staticmethod
    def _unpack(row, cycle):
        try:
            if type(row.payload) is not dict or set(row.payload) != {'state', 'bindings'}:
                raise ValueError('Malformed reinforcement record')
            state = decode_state(row.payload['state'])
            if state.number != cycle.number or state.battle_at != CampaignCycleStore.timeline(cycle).battle_at:
                raise ValueError('State belongs to a different cycle')
            bindings = {}
            if type(row.payload['bindings']) is not list:
                raise ValueError('Binding list required')
            for item in row.payload['bindings']:
                if type(item) is not dict or set(item) != {'user_id', 'clan_id', 'identity'}:
                    raise ValueError('Malformed frozen roster')
                rules._positive(item['user_id'])
                rules._positive(item['clan_id'])
                identity = _decode(item['identity'])
                if not isinstance(identity, rules.PlayerIdentity) or item['user_id'] in bindings:
                    raise ValueError('Invalid frozen player binding')
                bindings[item['user_id']] = (item['clan_id'], identity)
            if len({p for _, p in bindings.values()}) != len(bindings):
                raise ValueError('Ambiguous frozen player bindings')
            assigned = {p for r in (*state.reserves, *state.ambushes) for p in r.players}
            assigned.update(p for b in state.battles for p in b.ordinary_players)
            if not assigned <= {p for _, p in bindings.values()}:
                raise ValueError('Missing frozen player binding')
            return state, bindings
        except (TypeError, KeyError, AttributeError) as error:
            raise ValueError('Malformed reinforcement record') from error

    def _history(self, db, cycle, identities):
        history = set()
        prior_cycles = db.query(CampaignCycleRecord).filter(
            CampaignCycleRecord.season_id == cycle.season_id,
            CampaignCycleRecord.number < cycle.number,
            CampaignCycleRecord.orders_frozen_at.isnot(None),
        ).order_by(CampaignCycleRecord.number).all()
        for prior in prior_cycles:
            stored = db.query(CycleReinforcementState).filter_by(cycle_id=prior.id).one_or_none()
            prior_plans = db.query(CampaignCyclePlan).filter(
                CampaignCyclePlan.cycle_id == prior.id, CampaignCyclePlan.frozen_at.isnot(None)).all()
            reserve_ids = {o['user_id'] for plan in prior_plans for o in plan.orders if o['kind'] == 'reserve'}
            if stored is not None:
                previous, old_bindings = self._unpack(stored, prior)
                history.update(rules.ReserveUse(p, prior.number) for r in previous.reserves for p in r.players)
                reserve_ids.update(uid for uid, (_, p) in old_bindings.items()
                                   if any(p in r.players for r in previous.reserves))
            else:
                for plan in prior_plans:
                    selected = {o['user_id'] for o in plan.orders if o['kind'] == 'reserve'}
                    history.update(rules.ReserveUse(p, prior.number)
                                   for p in self._plan_identities(db, plan, selected).values())
            # Preserve restrictions by internal ID too if an identity is rebound.
            history.update(rules.ReserveUse(identities[uid], prior.number)
                           for uid in reserve_ids if uid in identities)
        return tuple(sorted(history, key=lambda h: (h.cycle, h.player.source, str(h.player.uuid))))

    @staticmethod
    def _validate_roster(db, roster, battle_at):
        for uid, clan_id in roster.items():
            periods = db.query(ClanMembershipPeriod).filter_by(user_id=uid).all()
            if periods:
                at_reveal = [p.clan_id for p in periods
                             if as_utc(p.started_at) <= battle_at
                             and (p.ended_at is None or battle_at < as_utc(p.ended_at))]
                valid = at_reveal == [clan_id]
            else:
                # Legacy rosters without interval backfill must still have a
                # unique DB member whose membership predates the reveal.
                members = db.query(ClanMember).filter_by(user_id=uid).all()
                valid = (len(members) == 1 and members[0].clan_id == clan_id
                         and as_utc(members[0].joined_at) <= battle_at)
            if not valid:
                raise ValueError('Frozen roster disagrees with DB membership at reveal')

    def initialize(self, db, *, cycle_id):
        cycle = self.cycles._locked(db, cycle_id)
        existing = db.query(CycleReinforcementState).filter_by(cycle_id=cycle_id).with_for_update().populate_existing().one_or_none()
        if existing is not None:
            self._unpack(existing, cycle)
            return existing
        if cycle.orders_frozen_at is None or not cycle.battles_registered or cycle.settled_at is not None:
            raise ValueError('Frozen plans and registered battles required before initialization')
        plans = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id).order_by(CampaignCyclePlan.clan_id).all()
        records = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).order_by(CycleTerritoryBattle.territory_id).all()
        roster = {}
        ordinary = {}
        for plan in plans:
            snapshot = plan.snapshot
            if (plan.frozen_at is None or type(snapshot) is not dict
                    or not {'level', 'member_ids', 'allied_clan_ids'} <= set(snapshot)):
                raise ValueError('Every plan requires a frozen snapshot')
            for uid in snapshot['member_ids']:
                rules._positive(uid)
                if uid in roster:
                    raise ValueError('Player belongs to multiple frozen rosters')
                roster[uid] = plan.clan_id
            for order in plan.orders:
                if order['user_id'] not in snapshot['member_ids']:
                    raise ValueError('Order player absent from frozen DB roster')
                if order['kind'] in ('attack', 'defend'):
                    ordinary.setdefault(order['territory_id'], {}).setdefault(plan.clan_id, []).append(order['user_id'])
                elif order['kind'] not in ('reserve', 'ambush'):
                    raise ValueError('Unknown frozen order')
        battle_at = self.cycles.timeline(cycle).battle_at
        self._validate_roster(db, roster, battle_at)
        identities = {}
        for plan in plans:
            identities.update(self._plan_identities(db, plan, plan.snapshot['member_ids']))
        if len(set(identities.values())) != len(identities):
            raise ValueError('Unique frozen identities required across all clans')
        reserves, ambushes, allies = [], [], set()
        for plan in plans:
            level = plan.snapshot['level']
            selected = tuple(identities[o['user_id']] for o in plan.orders if o['kind'] == 'reserve')
            if level == 0 and not selected:
                continue  # Deleted clan snapshot, never invent a capacity.
            reserves.append(rules.Reserve(plan.clan_id, level, selected))
            ambush_orders = [o for o in plan.orders if o['kind'] == 'ambush']
            if ambush_orders:
                if len({o['territory_id'] for o in ambush_orders}) != 1:
                    raise ValueError('Only one ambush territory per clan')
                target = ambush_orders[0]['territory_id']
                if not ordinary.get(target, {}).get(plan.clan_id):
                    raise ValueError('Ambush requires own ordinary squad')
                ambushes.append(rules.Ambush(plan.clan_id, target,
                    tuple(identities[o['user_id']] for o in ambush_orders)))
            allies.update(frozenset((plan.clan_id, other)) for other in plan.snapshot['allied_clan_ids'])
        battles = []
        if set(ordinary) != {b.territory_id for b in records}:
            raise ValueError('Registered battles do not match frozen orders')
        for record in records:
            expected = {clan: sorted(uids) for clan, uids in ordinary[record.territory_id].items()}
            if record.owner_clan_id is not None:
                expected.setdefault(record.owner_clan_id, [])
            actual = {s['clan_id']: sorted(s['user_ids']) for s in record.sides}
            if actual != expected or len(actual) != len(record.sides):
                raise ValueError('Registered battle sides do not match frozen orders')
            battles.append(rules.Battle(record.territory_id, tuple(actual),
                tuple(identities[uid] for uids in actual.values() for uid in uids)))
        state = rules.CycleReinforcements(cycle.number, self.cycles.timeline(cycle).battle_at,
            tuple(reserves), tuple(battles), frozenset(allies), self._history(db, cycle, identities), tuple(ambushes))
        payload = {'state': encode_state(state), 'bindings': [
            {'user_id': uid, 'clan_id': roster[uid], 'identity': _encode(identities[uid])} for uid in sorted(roster)]}
        self.cycles._bump(db, cycle)
        row = CycleReinforcementState(cycle_id=cycle_id, revision=1, payload=payload)
        db.add(row)
        db.flush()
        return row

    def _write(self, db, cycle, row, state, expected_revision):
        if expected_revision is not None and expected_revision != row.revision:
            raise CycleConflict('Reinforcement revision changed; refresh before retry')
        payload = {**row.payload, 'state': encode_state(state)}
        self.cycles._bump(db, cycle)
        changed = db.query(CycleReinforcementState).filter_by(id=row.id, revision=row.revision).update(
            {'payload': payload, 'revision': row.revision + 1}, synchronize_session=False)
        if changed != 1:
            raise CycleConflict('Concurrent reinforcement update; roll back transaction')
        db.refresh(row)
        db.flush()
        return row

    def _command_time(self, db, cycle, now):
        now = rules._time(now)
        season = db.get(CampaignSeason, cycle.season_id)
        if season is None or season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('An active cycle season is required')
        timeline = self.cycles.timeline(cycle)
        if (cycle.settled_at is not None or timeline.phase_at(now) != CyclePhase.BATTLE
                or not timeline.battle_at <= now < timeline.battle_at + timedelta(hours=24)):
            raise ValueError('New reinforcement commands require first 24 hours of battle')
        return now

    def request_help(self, db, *, cycle_id, request_id, clan_id, territory_id,
                     actor_user_id, now, expected_revision=None):
        from app.services.notification_service import NotificationService
        with CycleEconomyStore._atomic(db):
            cycle, row, state, _ = self._locked(db, cycle_id)
            self._actor(db, clan_id, actor_user_id)
            old = next((q for q in state.requests if q.id == request_id), None)
            updated = state.request_help(request_id, clan_id, territory_id,
                                         old.requested_at if old else self._command_time(db, cycle, now))
            if updated is state:
                return row
            result = self._write(db, cycle, row, updated, expected_revision)
            allies = {other for pair in state.alliances if clan_id in pair for other in pair if other != clan_id}
            requester = db.get(Clan, clan_id)
            territory = db.get(Territory, territory_id)
            for ally in db.query(Clan).filter(Clan.id.in_(allies), Clan.is_deleted.is_(False)):
                NotificationService().create_for_clan(db, clan_id=ally.id,
                    notification_type='cycle_help_requested', title='Союзнику нужна помощь',
                    message=f'Клан {requester.name} просит подкрепление на территорию {territory.name}.',
                    link_url=f'/campaign/cycles/{cycle_id}?territory={territory_id}',
                    entity_type='campaign_cycle', entity_id=cycle_id, commit=False)
            return result

    @staticmethod
    def _eligible(db, user_ids, sender, at, battle_at, bindings):
        eligible = set()
        for uid in user_ids:
            members = db.query(ClanMember).filter_by(user_id=uid).all()
            if (uid not in bindings or bindings[uid][0] != sender or len(members) != 1
                    or members[0].clan_id != sender or as_utc(members[0].joined_at) > battle_at):
                continue
            periods = db.query(ClanMembershipPeriod).filter_by(user_id=uid).all()
            if any(p.clan_id == sender and p.ended_at is not None
                   and battle_at <= as_utc(p.ended_at) <= at for p in periods):
                continue
            if periods and not any(p.clan_id == sender and as_utc(p.started_at) <= battle_at
                                   and (p.ended_at is None or as_utc(p.ended_at) > at) for p in periods):
                continue
            eligible.add(bindings[uid][1])
        return frozenset(eligible)

    def dispatch(self, db, *, cycle_id, dispatch_id, sender_clan_id, recipient_clan_id,
                 territory_id, player_user_ids, actor_user_id, now, request_id=None,
                 expected_revision=None, origin_territory_id=None):
        cycle, row, state, bindings = self._locked(db, cycle_id)
        self._actor(db, sender_clan_id, actor_user_id)
        ids = tuple(sorted(player_user_ids))
        for uid in ids:
            rules._positive(uid)
        if not ids or len(set(ids)) != len(ids) or any(uid not in bindings for uid in ids):
            raise ValueError('Unique frozen player IDs required')
        if set(ids) & CyclePlanService.scouting_user_ids(db, cycle_id):
            raise ValueError('A scout is unavailable until the end of this cycle')
        players = tuple(bindings[uid][1] for uid in ids)
        old = next((d for d in state.dispatches if d.id == dispatch_id), None)
        routes = CycleDispatchRouteService()
        if old is not None:
            routes.check_retry(db, cycle_id=cycle_id, dispatch_id=dispatch_id, origin_id=origin_territory_id)
        at = old.sent_at if old else self._command_time(db, cycle, now)
        if old is None:
            verified = self._identities(db, ids)
            if any(verified[uid] != bindings[uid][1] for uid in ids):
                raise ValueError('Verified identity no longer matches frozen player')
        eligible = frozenset() if old else self._eligible(db, ids, sender_clan_id, at, state.battle_at, bindings)
        updated = state.dispatch(dispatch_id, sender_clan_id, players, recipient_clan_id,
                                 territory_id, at, request_id=request_id, eligible_players=eligible)
        if updated is state:
            return row
        route = routes.prepare(db, clan_id=sender_clan_id, origin_id=origin_territory_id, target_id=territory_id)
        row = self._write(db, cycle, row, updated, expected_revision)
        routes.save(db, cycle_id=cycle_id, dispatch_id=dispatch_id, snapshot=route)
        if updated.dispatches[-1].ambush_clan_ids:
            self.cycles.register_dependency(db, cycle_id=cycle_id, key=f'interception:{dispatch_id}')
        return row

    def _resolve_interception(self, db, *, cycle_id, dispatch_id, help_score, ambush_scores,
                              now, expected_revision=None):
        """TRUSTED INTERNAL ONLY: scores must come from validated worker accounting.

        No actor flag or user-supplied authorization bypass is accepted. Do not
        wire this method to a route accepting public game points.
        """
        cycle, row, state, _ = self._locked(db, cycle_id)
        updated = state.resolve(dispatch_id, help_score, ambush_scores, now)
        if updated is state:
            return row
        if cycle.settled_at is not None:
            raise ValueError('Settled interception requires administrative review')
        key = f'interception:{dispatch_id}'
        if key not in cycle.dependencies:
            raise ValueError('Missing interception settlement dependency')
        row = self._write(db, cycle, row, updated, expected_revision)
        self.cycles.complete_dependency(db, cycle_id=cycle_id, key=key)
        return row

    def read(self, db, *, cycle_id, viewer_clan_id=None, actor_user_id=None):
        _, row, state, bindings = self._locked(db, cycle_id)
        if viewer_clan_id is not None:
            self._permission(db, viewer_clan_id, actor_user_id)
        return CycleDispatchRouteService.project(db, cycle_id=cycle_id,
            view=self._view(row, state, bindings, viewer_clan_id))

    @staticmethod
    def _view(row, state, bindings, viewer_clan_id):
        def player_ids(players):
            return [uid for uid, (_, p) in bindings.items() if p in players]
        return {
            'revision': row.revision,
            'reserves': [{'clan_id': r.clan_id, 'capacity': r.capacity, 'player_user_ids': player_ids(r.players)}
                         for r in state.reserves if r.clan_id == viewer_clan_id],
            'ambushes': [{'clan_id': a.clan_id, 'territory_id': a.territory_id,
                         'player_user_ids': player_ids(a.players), 'dispatch_id': a.dispatch_id}
                        for a in state.visible_ambushes(viewer_clan_id)],
            'dispatches': [{'id': d.id, 'sender_clan_id': d.sender_clan_id,
                           'recipient_clan_id': d.recipient_clan_id, 'territory_id': d.territory_id,
                           'player_user_ids': player_ids(d.players), 'sent_at': d.sent_at.isoformat(),
                           'arrives_at': d.arrives_at.isoformat(), 'outcome': d.outcome.value}
                          for d in state.dispatches],
            'requests': [{'id': q.id, 'recipient_clan_id': q.recipient_clan_id,
                          'territory_id': q.territory_id, 'dispatch_id': q.dispatch_id}
                         for q in state.requests if q.recipient_clan_id == viewer_clan_id
                         or state._allied(q.recipient_clan_id, viewer_clan_id)],
        }

    def context(self, db, *, cycle_id, viewer_clan_id, actor_user_id, now):
        clan, member = self._permission(db, viewer_clan_id, actor_user_id)
        cycle = db.get(CampaignCycleRecord, cycle_id)
        if cycle is None:
            raise ValueError('Unknown cycle')
        timeline = self.cycles.timeline(cycle)
        now = rules._time(now)
        row = db.query(CycleReinforcementState).filter_by(cycle_id=cycle_id).one_or_none()
        actor = db.get(User, actor_user_id)
        can_command = bool(row and actor and actor.onboarding_completed_at is not None
                           and (clan.leader_id == actor_user_id or member.is_warlord))
        if can_command:
            try:
                self._command_time(db, cycle, now)
            except ValueError:
                can_command = False
        result = dict(cycle_id=cycle_id, clan_id=viewer_clan_id, clan_name=clan.name,
                      phase=timeline.phase_at(now).value if now >= timeline.starts_at else 'scheduled',
                      server_time=now, command_deadline=timeline.battle_at + timedelta(hours=24),
                      ready=row is not None, can_command=can_command, state=None,
                      players=[], own_targets=[], help_targets=[], allied_targets=[],
                      clans=[], territories=[], names=[], origins=[], route_previews=[])
        if row is None:
            return result
        state, bindings = self._unpack(row, cycle)
        view = self._view(row, state, bindings, viewer_clan_id)
        CycleDispatchRouteService.project(db, cycle_id=cycle_id, view=view)
        # Only revealed routes contribute interception times to this projection.
        for dispatch, source in zip(view['dispatches'], state.dispatches):
            dispatch.update(interception_at=source.interception_at,
                            interception_ends_at=source.interception_ends_at)
        result['state'] = view
        reserve = next((r for r in state.reserves if r.clan_id == viewer_clan_id), None)
        reserve_ids = sorted(uid for uid, (owner, identity) in bindings.items()
                             if owner == viewer_clan_id and reserve and identity in reserve.players)
        eligible = self._eligible(db, reserve_ids, viewer_clan_id, now, state.battle_at, bindings)
        used = {p for d in state.dispatches for p in d.players}
        scouts = CyclePlanService.scouting_user_ids(db, cycle_id)
        for uid in reserve_ids:
            reason = None
            if uid in scouts:
                reason = 'scouting'
            elif bindings[uid][1] in used:
                reason = 'already_sent'
            elif bindings[uid][1] not in eligible:
                reason = 'ineligible'
            else:
                try:
                    if self._identities(db, [uid])[uid] != bindings[uid][1]:
                        reason = 'identity_changed'
                except ValueError:
                    reason = 'identity_changed'
            player = db.get(User, uid)
            result['players'].append(dict(user_id=uid, name=(player.display_name or player.username) if player else None,
                                          avatar_url=player.avatar_url if player else None,
                                          available=reason is None, unavailable_reason=reason))
        records = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).all()
        battle_ids = {b.territory_id: b.id for b in records}
        for battle in state.battles:
            if viewer_clan_id in battle.clan_ids:
                result['own_targets'].append(dict(territory_id=battle.territory_id, battle_id=battle_ids.get(battle.territory_id)))
                if not any(q.recipient_clan_id == viewer_clan_id and q.territory_id == battle.territory_id
                           and q.dispatch_id is None for q in state.requests):
                    result['help_targets'].append(battle.territory_id)
        for request in state.requests:
            if request.dispatch_id is not None or request.recipient_clan_id == viewer_clan_id:
                continue
            try:
                state._validate_route(viewer_clan_id, request.recipient_clan_id, request.territory_id, request.id)
            except ValueError:
                continue
            result['allied_targets'].append(dict(request_id=request.id, recipient_clan_id=request.recipient_clan_id,
                territory_id=request.territory_id, battle_id=battle_ids.get(request.territory_id)))
        territory_ids = {b.territory_id for b in state.battles}
        result.update(CycleDispatchRouteService().context(db, clan_id=viewer_clan_id,
            target_ids=[t['territory_id'] for t in result['own_targets'] + result['allied_targets']]))
        visible_clans = {viewer_clan_id}
        visible_users = set(reserve_ids)
        for collection in ('reserves', 'ambushes', 'dispatches', 'requests'):
            for item in view[collection]:
                visible_clans.update(item[key] for key in ('clan_id', 'sender_clan_id', 'recipient_clan_id') if key in item)
                visible_users.update(item.get('player_user_ids', []))
        result['clans'] = [dict(id=c.id, name=c.name if not c.is_deleted else None)
                           for c in db.query(Clan).filter(Clan.id.in_(visible_clans)).order_by(Clan.id)]
        result['territories'] = [dict(id=t.id, name=t.name) for t in db.query(Territory).filter(Territory.id.in_(territory_ids)).order_by(Territory.id)]
        result['names'] = [dict(user_id=u.id, name=u.display_name or u.username)
                           for u in db.query(User).filter(User.id.in_(visible_users)).order_by(User.id)]
        return result

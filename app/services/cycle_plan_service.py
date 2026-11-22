from dataclasses import asdict
from datetime import timedelta
from uuid import UUID

from app.core.time import as_utc
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord, CampaignCyclePlanRevision, CycleScoutRequest
from app.models.clan import Clan, ClanMember
from app.models.campaign import CampaignSeason
from app.models.user import User
from app.models.cycle_diplomacy import CycleDiplomacyPair
from app.models.external_identity import ExternalPlayerIdentity
from app.models.territory import Territory
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_defence_template import CycleDefenceTemplate
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.campaign_cycle_service import CyclePhase, _utc
from app.services.campaign_cycle_store import CampaignCycleStore, CycleConflict
from app.services.cycle_orders import Order, PlanningContext, TerritoryState, attack_limit, validate_plan, fill_defence_template


class CyclePlanService:
    def __init__(self):
        self.cycles = CampaignCycleStore()

    @staticmethod
    def _identity_key(source, value):
        try:
            value = str(UUID(value))
        except (ValueError, TypeError, AttributeError):
            pass
        return source, value

    @staticmethod
    def _identity_snapshot(db, user_ids):
        rows = db.query(ExternalPlayerIdentity).filter(
            ExternalPlayerIdentity.user_id.in_(user_ids),
            ExternalPlayerIdentity.source == 'bfmeladder',
            ExternalPlayerIdentity.verification_status == 'verified',
        ).all()
        return {str(row.user_id): {'source': row.source, 'uuid': row.external_uuid} for row in rows}

    @classmethod
    def scouting_user_ids(cls, db, cycle_id):
        requests = db.query(CycleScoutRequest).filter_by(cycle_id=cycle_id).all()
        ids = {r.scout_user_id for r in requests if r.scout_user_id is not None}
        keys = {cls._identity_key('bfmeladder', r.scout_uuid) for r in requests if r.scout_uuid}
        if keys:
            ids.update(i.user_id for i in db.query(ExternalPlayerIdentity).filter_by(source='bfmeladder')
                       if cls._identity_key(i.source, i.external_uuid) in keys)
        return ids

    @staticmethod
    def _permission(db, clan_id, user_id, *, edit=False):
        clan = db.get(Clan, clan_id)
        member = db.query(ClanMember).filter_by(clan_id=clan_id, user_id=user_id).first()
        if clan is None or clan.is_deleted or member is None:
            raise PermissionError('Current clan membership required')
        if edit and clan.leader_id != user_id and not member.is_warlord:
            raise PermissionError('Only the head or a voivode can edit orders')
        return clan

    def capture_preparation(self, db, *, cycle_id, now):
        cycle = self.cycles._locked(db, cycle_id)
        if cycle.planning_snapshot is not None:
            return cycle
        if self.cycles.timeline(cycle).phase_at(now) != CyclePhase.PREPARATION:
            raise ValueError('Preparation snapshot must be captured during preparation')
        territories = db.query(Territory).filter(Territory.is_playable.is_(True)).order_by(Territory.id).all()
        snapshot = [dict(id=t.id, owner_clan_id=t.owner_clan_id,
                         neighbours=list(t.adjacent_territory_ids or []),
                         coastal=bool(t.is_coastal), port=bool(t.has_port), fortress=t.is_great_stronghold)
                    for t in territories]
        self.cycles._bump(db, cycle)
        cycle.planning_snapshot = snapshot
        db.flush()
        return cycle

    def _template_window(self, db, cycle, now):
        season = db.get(CampaignSeason, cycle.season_id)
        timeline = self.cycles.timeline(cycle)
        phase = timeline.phase_at(now) if _utc(now) >= timeline.starts_at else None
        latest = not db.query(CampaignCycleRecord.id).filter(
            CampaignCycleRecord.season_id == cycle.season_id,
            CampaignCycleRecord.number > cycle.number).first()
        return bool(season and season.status == 'active'
                    and (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1'
                    and latest and (phase == CyclePhase.REST or (
                        phase == CyclePhase.PREPARATION and cycle.orders_frozen_at is None)))

    @staticmethod
    def _template_data(db, cycle, clan_id):
        row = db.query(CycleDefenceTemplate).filter_by(season_id=cycle.season_id, clan_id=clan_id).one_or_none()
        return dict(revision=row.revision if row else 0, assignments=list(row.assignments) if row else [])

    def read_defence_template(self, db, *, cycle_id, clan_id, actor_user_id, now):
        clan = self._permission(db, clan_id, actor_user_id)
        cycle = db.get(CampaignCycleRecord, cycle_id)
        if cycle is None:
            raise ValueError('Unknown cycle')
        window = self._template_window(db, cycle, now)
        frozen = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one_or_none()
        historical = cycle.orders_frozen_at is not None and not window
        if historical:
            data = (frozen.snapshot or {}).get('defence_template', {}) if frozen else {}
        else:
            data = self._template_data(db, cycle, clan_id)
        membership = db.query(ClanMember).filter_by(clan_id=clan_id, user_id=actor_user_id).one()
        actor = db.get(User, actor_user_id)
        current_ids = {r[0] for r in db.query(ClanMember.user_id).filter_by(clan_id=clan_id)}
        member_ids = sorted(int(key) for key in self._identity_snapshot(db, current_ids))
        targets = [dict(id=t.id, name=t.name) for t in db.query(Territory).filter_by(
            owner_clan_id=clan_id, is_playable=True).order_by(Territory.id)]
        fallback = []
        if not historical and cycle.orders_frozen_at is None and cycle.planning_snapshot is not None:
            context = self._context(db, cycle, clan)
            fallback, _ = self._template_fallback(db, context, data.get('assignments', []), frozen.orders if frozen else [])
        # Frozen fallback assignments are already present in plan.orders.
        timeline = self.cycles.timeline(cycle)
        editable_until = None
        if window:
            editable_until = (as_utc(cycle.settled_at) + timedelta(hours=12)
                              if cycle.orders_frozen_at is not None else timeline.battle_at)
        return dict(revision=data.get('revision', 0), assignments=data.get('assignments', []),
                    editable=bool(window and actor.onboarding_completed_at is not None
                                  and (clan.leader_id == actor_user_id or membership.is_warlord)),
                    editable_until=editable_until, member_ids=member_ids, targets=targets, fallback_orders=fallback)

    def save_defence_template(self, db, *, cycle_id, clan_id, actor_user_id, expected_revision, assignments, now):
        cycle = self.cycles._locked(db, cycle_id)
        self._permission(db, clan_id, actor_user_id, edit=True)
        actor = db.get(User, actor_user_id)
        if actor.onboarding_completed_at is None:
            raise PermissionError('Onboarding required')
        if not self._template_window(db, cycle, now):
            raise ValueError('Defence template can only be edited during current preparation or rest')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Nonnegative template revision required')
        row = db.query(CycleDefenceTemplate).filter_by(season_id=cycle.season_id, clan_id=clan_id).one_or_none()
        if expected_revision != (row.revision if row else 0):
            raise CycleConflict('Defence template changed; refresh before retry')
        members = {r[0] for r in db.query(ClanMember.user_id).filter_by(clan_id=clan_id)}
        eligible = {int(key) for key in self._identity_snapshot(db, members)}
        owned = {r[0] for r in db.query(Territory.id).filter_by(owner_clan_id=clan_id, is_playable=True)}
        if not isinstance(assignments, list) or len(assignments) > 500:
            raise ValueError('Defence template assignments required')
        seen, validated = set(), []
        for entry in assignments:
            if not isinstance(entry, dict) or set(entry) != {'user_id', 'territory_id'}:
                raise ValueError('Defence template only accepts player and owned territory')
            user_id, territory_id = entry['user_id'], entry['territory_id']
            if type(user_id) is not int or type(territory_id) is not int or user_id <= 0 or territory_id <= 0:
                raise ValueError('Positive player and territory identifiers required')
            if user_id in seen or user_id not in eligible or territory_id not in owned:
                raise ValueError('Template requires unique eligible players and owned land')
            seen.add(user_id)
            validated.append(dict(user_id=user_id, territory_id=territory_id))
        validated.sort(key=lambda entry: entry['user_id'])
        self.cycles._bump(db, cycle)
        values = dict(revision=expected_revision + 1, assignments=validated,
                      updated_at=_utc(now), updated_by_user_id=actor_user_id)
        if row is None:
            db.add(CycleDefenceTemplate(season_id=cycle.season_id, clan_id=clan_id, **values))
        else:
            changed = db.query(CycleDefenceTemplate).filter_by(id=row.id, revision=expected_revision).update(
                values, synchronize_session=False)
            if changed != 1:
                raise CycleConflict('Concurrent defence template update')
            db.refresh(row)
        db.flush()
        return self.read_defence_template(db, cycle_id=cycle_id, clan_id=clan_id, actor_user_id=actor_user_id, now=now)

    @staticmethod
    def _template_fallback(db, context, assignments, manual):
        assigned = {entry['user_id'] for entry in manual}
        current_owned = {r[0] for r in db.query(Territory.id).filter_by(owner_clan_id=context.clan_id, is_playable=True)}
        owned = current_owned & {t.id for t in context.territories if t.owner_clan_id == context.clan_id}
        eligible, warnings = {}, []
        for entry in assignments:
            user_id, territory_id = entry['user_id'], entry['territory_id']
            if user_id in assigned:
                continue
            reason = ('member_no_longer_eligible' if user_id not in context.member_ids else
                      'scouting' if user_id in context.scouting_ids else
                      'land_no_longer_owned' if territory_id not in owned else None)
            if reason:
                warnings.append(dict(user_id=user_id, territory_id=territory_id, source='defence_template', reason=reason))
            else:
                eligible[user_id] = territory_id
        return [asdict(o) for o in fill_defence_template([], eligible, context)], warnings

    def _context(self, db, cycle, clan):
        if cycle.planning_snapshot is None:
            raise ValueError('Preparation snapshot is missing')
        members = db.query(ClanMember.user_id).filter_by(clan_id=clan.id).all()
        member_ids = {row[0] for row in members}
        identities = db.query(ExternalPlayerIdentity).filter(
            ExternalPlayerIdentity.user_id.in_(member_ids),
            ExternalPlayerIdentity.source == 'bfmeladder',
            ExternalPlayerIdentity.verification_status == 'verified',
        ).all()
        verified = {i.user_id for i in identities}
        blocked = set()
        prior = db.query(CampaignCyclePlan).join(CampaignCycleRecord, CampaignCycleRecord.id == CampaignCyclePlan.cycle_id).filter(
            CampaignCycleRecord.season_id == cycle.season_id,
            CampaignCycleRecord.number >= cycle.number - 2,
            CampaignCycleRecord.number < cycle.number,
            CampaignCyclePlan.frozen_at.isnot(None),
        ).all()
        for plan in prior:
            blocked.update(o['user_id'] for o in plan.orders if o['kind'] == 'reserve')
            previous_identities = (plan.snapshot or {}).get('player_identities', {})
            used = {self._identity_key(identity['source'], identity['uuid']) for order in plan.orders
                    if order['kind'] == 'reserve'
                    for identity in [previous_identities.get(str(order['user_id']))] if identity}
            blocked.update(identity.user_id for identity in identities
                           if self._identity_key(identity.source, identity.external_uuid) in used)
        allies = set()
        for relation in db.query(CycleDiplomacyPair).filter(
            CycleDiplomacyPair.season_id == cycle.season_id,
            CycleDiplomacyPair.allied_at.isnot(None),
        ).all():
            if clan.id in (relation.clan_low_id, relation.clan_high_id):
                allies.add(relation.clan_high_id if relation.clan_low_id == clan.id else relation.clan_low_id)
        territories = tuple(TerritoryState(**{**t, 'neighbours': frozenset(t['neighbours'])}) for t in cycle.planning_snapshot)
        return PlanningContext(clan.id, clan.level, clan.territory_points or 0, frozenset(verified),
                               frozenset(blocked), territories, frozenset(allies),
                               frozenset(self.scouting_user_ids(db, cycle.id)))

    def save(self, db, *, cycle_id, clan_id, actor_user_id, expected_revision, orders, now):
        cycle = self.cycles._locked(db, cycle_id)
        clan = self._permission(db, clan_id, actor_user_id, edit=True)
        season = db.get(CampaignSeason, cycle.season_id)
        if season is None or season.status != 'active' or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
            raise ValueError('An active cycle season is required')
        if cycle.orders_frozen_at is not None or self.cycles.timeline(cycle).phase_at(now) != CyclePhase.PREPARATION:
            raise ValueError('Orders can only be edited during preparation')
        plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one_or_none()
        if expected_revision != (plan.revision if plan else 0):
            raise CycleConflict('Plan changed; refresh before retry')
        validated = validate_plan(orders, self._context(db, cycle, clan))
        # Serialize all changes for this cycle, including a first plan creation.
        self.cycles._bump(db, cycle)
        if plan is None:
            plan = CampaignCyclePlan(cycle_id=cycle_id, clan_id=clan_id, revision=1)
            db.add(plan)
        else:
            plan.revision += 1
        plan.orders = [asdict(order) for order in validated]
        plan.updated_by_user_id = actor_user_id
        db.flush()
        db.add(CampaignCyclePlanRevision(plan_id=plan.id, revision=plan.revision,
               saved_at=_utc(now), actor_user_id=actor_user_id, orders=[asdict(order) for order in validated]))
        db.flush()
        return plan

    def read(self, db, *, cycle_id, clan_id, actor_user_id):
        self._permission(db, clan_id, actor_user_id)
        plan = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one_or_none()
        return {'revision': plan.revision if plan else 0,
                'orders': list(plan.orders) if plan else [],
                'warnings': (plan.snapshot or {}).get('warnings', []) if plan else [],
                'frozen_at': plan.frozen_at if plan else None}

    def planning(self, db, *, cycle_id, clan_id, actor_user_id, now):
        clan = self._permission(db, clan_id, actor_user_id)
        cycle = db.get(CampaignCycleRecord, cycle_id)
        if cycle is None:
            raise ValueError('Unknown cycle')
        season = db.get(CampaignSeason, cycle.season_id)
        timeline = self.cycles.timeline(cycle)
        phase = timeline.phase_at(now).value if _utc(now) >= timeline.starts_at else 'scheduled'
        actor = db.get(User, actor_user_id)
        membership = db.query(ClanMember).filter_by(clan_id=clan_id, user_id=actor_user_id).one()
        ready = cycle.planning_snapshot is not None
        editable = bool(ready and phase == CyclePhase.PREPARATION.value and cycle.orders_frozen_at is None
                        and season and season.status == 'active'
                        and (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1'
                        and actor.onboarding_completed_at is not None
                        and (clan.leader_id == actor_user_id or membership.is_warlord))
        plan = self.read(db, cycle_id=cycle_id, clan_id=clan_id, actor_user_id=actor_user_id)
        reserve_capacity = clan.level
        if plan['frozen_at'] is not None:
            frozen = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id, clan_id=clan_id).one()
            reserve_capacity = (frozen.snapshot or {}).get('level', clan.level)
        context = self._context(db, cycle, clan) if ready else None
        current_ids = {row[0] for row in db.query(ClanMember.user_id).filter_by(clan_id=clan_id)}
        # Keep names for departed players in the saved plan without making them assignable.
        ids = current_ids | {order['user_id'] for order in plan['orders']}
        users = db.query(User).filter(User.id.in_(ids)).order_by(User.id).all()
        verified = context.member_ids if context else {int(key) for key in self._identity_snapshot(db, current_ids)}
        scouts = self.scouting_user_ids(db, cycle.id)
        members = [dict(user_id=u.id, name=u.display_name or u.username, avatar_url=u.avatar_url,
                        eligible=u.id in current_ids and u.id in verified and u.id not in scouts,
                        scouting=u.id in scouts,
                        reserve_blocked=bool(context and u.id in context.reserve_blocked_ids)) for u in users]
        routes = []
        own = [t for t in context.territories if t.owner_clan_id == clan_id] if context else []
        assignable = context.member_ids - context.scouting_ids if context else frozenset()
        if context and assignable:
            representative = min(assignable)
            for target in context.territories:
                candidates = [(None, 'land')] if not own else [
                    (source.id, route) for source in own for route in ('land', 'sea')
                    if (route == 'land' and target.id in source.neighbours)
                    or (route == 'sea' and source.port and target.coastal)]
                for source_id, route in candidates:
                    try:
                        validate_plan([Order(representative, 'attack', target.id, source_id, route)], context)
                    except ValueError:
                        continue
                    routes.append(dict(territory_id=target.id, source_id=source_id, route=route))
        territory_ids = {t.id for t in context.territories} if context else set()
        names = {t.id: t.name for t in db.query(Territory).filter(Territory.id.in_(territory_ids))}
        reachable = {r['territory_id'] for r in routes}
        unavailable = []
        if context:
            for target in context.territories:
                if target.id in reachable:
                    continue
                reason = ('owned' if target.owner_clan_id == clan_id else
                    'ally' if target.owner_clan_id in context.allied_clan_ids else
                    'no_eligible_players' if not assignable else
                    'fortress_requirements' if target.fortress and (not own or len(own) < 5 or context.influence < 350) else
                    'landless_port' if not own and target.port else 'no_adjacent_land_or_port')
                unavailable.append(dict(territory_id=target.id, reason=reason))
        return dict(cycle_id=cycle_id, clan_id=clan_id, clan_name=clan.name, phase=phase,
                    battle_at=timeline.battle_at, server_time=_utc(now), editable=editable,
                    snapshot_ready=ready, plan=plan, members=members,
                    defence_template=self.read_defence_template(db, cycle_id=cycle_id, clan_id=clan_id,
                                                               actor_user_id=actor_user_id, now=now),
                    limits=dict(attacks=attack_limit(len(own)), reserves=reserve_capacity, ambush_players=2),
                    territories=[dict(id=t.id, name=names.get(t.id), port=t.port, fortress=t.fortress)
                                 for t in context.territories] if context else [],
                    defence_targets=[t.id for t in own], attack_routes=routes, attack_unavailable=unavailable)

    def freeze(self, db, *, cycle_id, now):
        cycle = self.cycles._locked(db, cycle_id)
        if cycle.orders_frozen_at is not None:
            return cycle
        now = _utc(now)
        if now < self.cycles.timeline(cycle).battle_at or cycle.planning_snapshot is None:
            raise ValueError('Reveal requires preparation snapshot and battle start')
        economy = CycleEconomyStore()
        economy._season(db, cycle.season_id)
        states = db.query(CycleEconomyState).filter_by(season_id=cycle.season_id).order_by(CycleEconomyState.id).all()
        wallet_ids = {state.clan_id: state.id for state in states}
        planned = {row[0] for row in db.query(CampaignCyclePlan.clan_id).filter_by(cycle_id=cycle_id)}
        for clan in db.query(Clan).filter(Clan.is_deleted.is_(False)).order_by(Clan.id):
            if clan.id not in planned:
                db.add(CampaignCyclePlan(cycle_id=cycle_id, clan_id=clan.id, revision=1, orders=[]))
        db.flush()
        plans = db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id).order_by(CampaignCyclePlan.clan_id).all()
        prepared = []
        for plan in plans:
            clan = db.get(Clan, plan.clan_id)
            if clan is None or clan.is_deleted:
                prepared.append((plan, (), {'level': 0, 'member_ids': [], 'allied_clan_ids': []}))
                continue
            context = self._context(db, cycle, clan)
            warnings = []
            orders = []
            for data in plan.orders:
                order = Order(**data)
                if order.user_id not in context.member_ids:
                    warnings.append({'user_id': order.user_id, 'reason': 'member_no_longer_eligible'})
                elif order.user_id in context.scouting_ids:
                    warnings.append({'user_id': order.user_id, 'reason': 'scouting'})
                elif order.kind == 'ambush':
                    orders.append(order)
                else:
                    try:
                        validate_plan([order], context)
                        orders.append(order)
                    except ValueError as error:
                        warnings.append({'user_id': order.user_id, 'reason': str(error)})
            ordinary = {o.territory_id for o in orders if o.kind in {'attack', 'defend'}}
            orphaned = [o for o in orders if o.kind == 'ambush' and o.territory_id not in ordinary]
            for order in orphaned:
                warnings.append({'user_id': order.user_id, 'reason': 'ambush_has_no_ordinary_squad'})
            orders = [o for o in orders if o not in orphaned]
            if sum(o.kind == 'reserve' for o in orders) > context.level:
                # Do not choose a favored subset on the head's behalf.
                warnings.extend({'user_id': o.user_id, 'reason': 'draft_reserve_exceeds_reveal_capacity'}
                                for o in orders if o.kind == 'reserve')
                orders = [o for o in orders if o.kind != 'reserve']
            template = self._template_data(db, cycle, clan.id)
            fallback, skipped = self._template_fallback(db, context, template['assignments'], plan.orders)
            warnings.extend(skipped)
            orders.extend(Order(**data) for data in fallback)
            # Never invent replacement destinations for skipped orders.
            validated = validate_plan(orders, context)
            prepared.append((plan, validated, {'level': context.level,
                             'member_ids': sorted(context.member_ids),
                             'player_identities': self._identity_snapshot(db, context.member_ids),
                             'allied_clan_ids': sorted(context.allied_clan_ids),
                             'defence_template': {**template, 'fallback_orders': fallback},
                             'warnings': warnings}))
        self.cycles._bump(db, cycle)
        for plan, orders, snapshot in prepared:
            plan.orders = [asdict(o) for o in orders]
            plan.snapshot = {**snapshot, 'economy_state_id': wallet_ids.get(plan.clan_id)}
            plan.frozen_at = self.cycles.timeline(cycle).battle_at
        for state in states:
            economy.freeze_snapshot(db, state_id=state.id, cycle_id=cycle.id,
                                    now=now, expected_revision=state.revision)
        cycle.orders_frozen_at = self.cycles.timeline(cycle).battle_at
        db.flush()
        return cycle

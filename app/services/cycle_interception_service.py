"""Ведёт зачёт проверенных реплеев в отдельных боях перехвата.

Публичного API записи нет: данные и полноту проверки временного окна подтверждает
адаптер источника, а не флаг из браузера. Транзакцией управляет вызывающий код.
Очки перехвата не входят в счёт территории; передаётся только исход отправки помощи.
"""

from datetime import timedelta
from decimal import Decimal

from app.core.time import as_utc
from app.models.clan import Clan
from app.models.cycle_interception import (
    CycleInterception, CycleInterceptionContribution, CycleInterceptionAdjustment,
)
from app.models.territory import Territory
from app.models.user import User
from app.services import cycle_economy as economy
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import _stored_points
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_match_service import CycleMatchService
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from app.services.cycle_reinforcements import Outcome
from app.services.cycle_scoring import MatchPlayer, Contribution, calculate_contributions
from app.services.clan_membership_service import ClanMembershipService


PENDING = frozenset({'missing_historical_elo', 'missing_match_times', 'unknown_result'})


def effective_counted(row):
    return row.counted if row.review_counted is None else row.review_counted


def applied_result(dispatch):
    return dict(outcome=dispatch.outcome.value,
        help_score=format(dispatch.help_score.normalize(), 'f') if dispatch.help_score is not None else None,
        ambush_scores={str(clan): format(score.normalize(), 'f') for clan, score in dispatch.ambush_scores})


def history_scores(db, record, dispatch):
    scores = {clan: Decimal(0) for clan in (dispatch.sender_clan_id, *dispatch.ambush_clan_ids)}
    if record is not None:
        for row in db.query(CycleInterceptionContribution).filter_by(interception_id=record.id):
            if effective_counted(row):
                if row.side_clan_id not in scores:
                    raise ValueError('Вклад не принадлежит стороне перехвата')
                scores[row.side_clan_id] += row.points
        for row in db.query(CycleInterceptionAdjustment).filter_by(interception_id=record.id):
            if row.side_clan_id not in scores:
                raise ValueError('Поправка не принадлежит стороне перехвата')
            scores[row.side_clan_id] += row.points
    return scores


class CycleInterceptionService:
    @staticmethod
    def _pending_sources(cycle):
        return any(not done for key, done in cycle.dependencies.items() if key.startswith('source-replay:'))

    @staticmethod
    def _context(db, cycle_id, dispatch_id):
        cycle, _, state, bindings = CycleReinforcementStore()._locked(db, cycle_id)
        dispatch = next((d for d in state.dispatches if d.id == dispatch_id), None)
        if dispatch is None or not dispatch.ambush_clan_ids:
            raise ValueError('Unknown triggered interception')
        record = db.query(CycleInterception).filter_by(cycle_id=cycle_id,
            dispatch_id=dispatch_id).with_for_update().populate_existing().one_or_none()
        return cycle, state, bindings, dispatch, record

    @staticmethod
    def _record(db, cycle, dispatch, record):
        if record is None:
            if cycle.settled_at is not None or dispatch.outcome != Outcome.PENDING:
                raise ValueError('Late interception evidence requires administrative review')
            record = CycleInterception(cycle_id=cycle.id, dispatch_id=dispatch.id)
            db.add(record)
            CampaignCycleStore._bump(db, cycle)
            db.flush()
        return record

    @staticmethod
    def _fingerprint(replay, players, *, ratings=True):
        return CycleMatchService._fingerprint(replay, players, ratings=ratings)

    @staticmethod
    def _save(db, cycle, record, *, replay_id, uid, side, contribution, calculation):
        row = db.query(CycleInterceptionContribution).filter_by(interception_id=record.id,
            replay_id=replay_id, user_id=uid).one_or_none()
        if row is not None and row.review_counted is not None and row.reason not in PENDING:
            return row
        if row is not None and row.calculation == calculation and row.reason == contribution.reason:
            return row
        if record.completed_at is not None or cycle.settled_at is not None:
            raise ValueError('Late interception evidence requires administrative review')
        same_exclusion = bool(row is not None and not row.counted and contribution.reason == row.reason
            and contribution.points == row.points == 0
            and row.calculation.get('structure_fingerprint') == calculation['structure_fingerprint'])
        if row is not None and ((row.reason not in PENDING and not same_exclusion) or row.side_clan_id != side):
            raise ValueError('Conflicting replay evidence requires administrative review')
        if row is None:
            row = CycleInterceptionContribution(interception_id=record.id,
                replay_id=replay_id, user_id=uid, side_clan_id=side)
            db.add(row)
        row.points = _stored_points(contribution.points)
        row.reason, row.counted, row.calculation = contribution.reason, contribution.reason == 'counted', calculation
        record.revision += 1
        record.verified_at = record.verified_revision = record.source_cursor = None
        record.covered_start = record.covered_end = None
        CampaignCycleStore._bump(db, cycle)
        db.flush()
        return row

    def process(self, db, *, cycle_id, dispatch_id, replay):
        players = CycleMatchService._validate(replay)
        fingerprint = self._fingerprint(replay, players)
        structure = self._fingerprint(replay, players, ratings=False)
        with CycleEconomyStore._atomic(db):
            cycle, state, bindings, dispatch, record = self._context(db, cycle_id, dispatch_id)
            sides = {p: dispatch.sender_clan_id for p in dispatch.players}
            for ambush in state.ambushes:
                if ambush.dispatch_id == dispatch.id:
                    sides.update({p: ambush.clan_id for p in ambush.players})
            identities = {(p.source, str(p.uuid)): (uid, clan) for uid, (clan, p) in bindings.items()}
            assigned = {(p.source, str(p.uuid)): clan for p, clan in sides.items()}
            if not set(players) & set(assigned):
                return []
            record = self._record(db, cycle, dispatch, record)
            class Window:
                @staticmethod
                def accepts_match(start, finish):
                    return state.interception_match_allowed(dispatch.id, start, finish)
            gate = CycleMatchService._gate(Window(), replay)
            invalid_members = set()
            if replay.started_at is not None:
                invalid_members = {key for key in players if key in assigned
                    and not ClanMembershipService.dispatched_member_since(db, user_id=identities[key][0],
                        clan_id=assigned[key], since=as_utc(cycle.orders_frozen_at),
                        occurred_at=_utc(replay.started_at),
                        dispatch=dispatch if assigned[key] == dispatch.sender_clan_id else None)}
            snapshots = CycleMatchService._snapshots(db, cycle)
            scoring = []
            for key, player in players.items():
                clan = identities[key][1] if key in identities else None
                snapshot = snapshots.get(clan)
                effects = tuple(economy.RelicEffect(e['key'], e['level'], e['effect'], Decimal(e['percent']))
                    for e in snapshot.effects) if snapshot else ()
                scoring.append(MatchPlayer(identity=':'.join(key), team=player.team, clan_id=clan,
                    elo=player.elo if player.historical and player.rating_patch == replay.patch_family else None,
                    side_id=assigned.get(key) if key not in invalid_members else None,
                    victory_bonus_percent=economy.victory_bonus(effects, role='interception',
                        allied_help=assigned.get(key) == dispatch.sender_clan_id
                        and dispatch.sender_clan_id != dispatch.recipient_clan_id)))
            calculated = calculate_contributions(scoring, winning_team=replay.winning_team,
                draw=replay.draw, alliances=state.alliances)
            rows = []
            for key, player in players.items():
                if key not in assigned:
                    continue
                side = assigned[key]
                other_ambush = side in dispatch.ambush_clan_ids and any(
                    p.team != player.team and assigned.get(k) in dispatch.ambush_clan_ids
                    and assigned[k] != side for k, p in players.items())
                reason = gate or ('membership_changed' if key in invalid_members else
                    'ambush_opponent' if other_ambush else None)
                contribution = Contribution(Decimal(0), reason) if reason else calculated[':'.join(key)]
                calculation = dict(input_fingerprint=fingerprint, structure_fingerprint=structure, source=replay.source,
                    uuid=key[1], patch_family=replay.patch_family,
                    historical_elo=str(player.elo) if player.historical and player.rating_patch == replay.patch_family else None,
                    started_at=_utc(replay.started_at).isoformat() if replay.started_at else None,
                    finished_at=_utc(replay.finished_at).isoformat() if replay.finished_at else None,
                    base_points=str(contribution.base_points), victory_bonus_percent=str(contribution.victory_bonus_percent),
                    direct_multiplier=contribution.direct_multiplier,
                    exhaustion_multiplier=str(contribution.exhaustion_multiplier))
                rows.append(self._save(db, cycle, record, replay_id=f'{replay.source}:{replay.replay_id}',
                    uid=identities[key][0], side=side, contribution=contribution, calculation=calculation))
            return rows

    def _verify_window(self, db, *, cycle_id, dispatch_id, covered_start, covered_end, source_cursor, now):
        """Вызывается доверенным адаптером после полного обхода и сохранения данных источника."""
        now, start, end = _utc(now), _utc(covered_start), _utc(covered_end)
        if not isinstance(source_cursor, str) or not source_cursor.strip() or len(source_cursor) > 500:
            raise ValueError('Bounded verified source cursor required')
        with CycleEconomyStore._atomic(db):
            cycle, _, _, dispatch, record = self._context(db, cycle_id, dispatch_id)
            if (start > dispatch.interception_at or end < dispatch.interception_ends_at
                    or end > now or now < dispatch.interception_ends_at + timedelta(minutes=5)):
                raise ValueError('Complete interception window and replay grace required')
            record = self._record(db, cycle, dispatch, record)
            if record.completed_at is not None:
                return record
            if self._pending_sources(cycle):
                raise ValueError('Pending source replay identities must be resolved before interception verification')
            record.verified_at, record.verified_revision = now, record.revision
            record.covered_start, record.covered_end, record.source_cursor = start, end, source_cursor
            CampaignCycleStore._bump(db, cycle)
            db.flush()
            return record

    def finalize(self, db, *, cycle_id, dispatch_id, now):
        now = _utc(now)
        with CycleEconomyStore._atomic(db):
            cycle, _, _, dispatch, record = self._context(db, cycle_id, dispatch_id)
            if record is not None and record.completed_at is not None:
                return dispatch
            if self._pending_sources(cycle):
                raise ValueError('Pending source replay identities must be resolved before interception settlement')
            if record is None or record.verified_at is None or record.verified_revision != record.revision:
                raise ValueError('A verified whole-window import is required')
            if db.query(CycleInterceptionContribution.id).filter(
                    CycleInterceptionContribution.interception_id == record.id,
                    CycleInterceptionContribution.reason.in_(PENDING)).first():
                raise ValueError('Interception has pending replay evidence')
            # Авторасчёт использует только исходник; исправленная история применяется отдельно.
            scores = {clan: Decimal(0) for clan in (dispatch.sender_clan_id, *dispatch.ambush_clan_ids)}
            for row in db.query(CycleInterceptionContribution).filter_by(interception_id=record.id, counted=True):
                scores[row.side_clan_id] += row.points
            result = CycleReinforcementStore()._resolve_interception(db, cycle_id=cycle_id,
                dispatch_id=dispatch.id, help_score=scores[dispatch.sender_clan_id],
                ambush_scores={clan: scores[clan] for clan in dispatch.ambush_clan_ids}, now=now)
            record.completed_at = now
            resolved = next(d for d in CycleReinforcementStore()._unpack(result, cycle)[0].dispatches if d.id == dispatch.id)
            record.original_applied_result = applied_result(resolved)
            db.flush()
            return resolved

    def settle_ready(self, db, *, cycle_id, now):
        """Обработчик фоновой задачи: истечение времени само по себе не подтверждает проверку."""
        if self._pending_sources(CampaignCycleStore()._locked(db, cycle_id)):
            return []
        ready = db.query(CycleInterception).filter_by(cycle_id=cycle_id, completed_at=None).all()
        result = []
        for record in ready:
            if record.verified_at is None or record.verified_revision != record.revision:
                continue
            if db.query(CycleInterceptionContribution.id).filter(
                    CycleInterceptionContribution.interception_id == record.id,
                    CycleInterceptionContribution.reason.in_(PENDING)).first():
                continue
            result.append(self.finalize(db, cycle_id=cycle_id, dispatch_id=record.dispatch_id, now=now))
        return result

    def read(self, db, *, cycle_id, dispatch_id, now):
        """Открывает данные авторизованным пользователям только после начала сработавшего перехвата."""
        now = _utc(now)
        cycle, state, bindings, dispatch, record = self._context(db, cycle_id, dispatch_id)
        if now < dispatch.interception_at:
            raise ValueError('Interception has not started')
        rows = db.query(CycleInterceptionContribution).filter_by(interception_id=record.id).order_by(
            CycleInterceptionContribution.id).all() if record else []
        scores = history_scores(db, record, dispatch)
        personal = {}
        for row in rows:
            if effective_counted(row):
                summary = personal.setdefault(row.user_id, [Decimal(0), Decimal(0)])
                summary[0 if row.points >= 0 else 1] += row.points
        sides = []
        assigned = {dispatch.sender_clan_id: dispatch.players}
        assigned.update({a.clan_id: a.players for a in state.ambushes if a.dispatch_id == dispatch.id})
        users = {u.id: u for u in db.query(User).filter(User.id.in_(bindings)).all()}
        for clan_id, players in assigned.items():
            clan = db.get(Clan, clan_id)
            sides.append(dict(clan_id=clan_id, clan_name=clan.name if clan and not clan.is_deleted else None,
                role='help' if clan_id == dispatch.sender_clan_id else 'ambush', score=str(scores[clan_id]),
                members=[dict(user_id=uid, username=users[uid].username, display_name=users[uid].display_name,
                    positive_points=str(personal.get(uid, [Decimal(0), Decimal(0)])[0]),
                    negative_points=str(personal.get(uid, [Decimal(0), Decimal(0)])[1]),
                    total_points=str(sum(personal.get(uid, [Decimal(0), Decimal(0)])))) for uid, (_, identity) in bindings.items()
                         if identity in players and uid in users]))
        safe_fields = {'historical_elo', 'patch_family', 'started_at', 'finished_at', 'base_points',
                       'victory_bonus_percent', 'direct_multiplier', 'exhaustion_multiplier'}
        territory = db.get(Territory, dispatch.territory_id)
        return dict(cycle_id=cycle.id, dispatch_id=dispatch.id, territory_id=dispatch.territory_id,
            territory_name=territory.name if territory else None, sides=sides, outcome=dispatch.outcome.value,
            recipient_clan_id=dispatch.recipient_clan_id, starts_at=dispatch.interception_at,
            ends_at=dispatch.interception_ends_at, replay_deadline=dispatch.interception_ends_at + timedelta(minutes=5),
            arrives_at=dispatch.arrives_at, server_time=now,
            revision=record.revision if record else None,
            applied_result=applied_result(dispatch),
            original_applied_result=(record.original_applied_result or applied_result(dispatch))
                if record and dispatch.outcome in (Outcome.BLOCKED, Outcome.EXHAUSTED) else None,
            completed_at=record.completed_at if record else None,
            phase=('completed' if dispatch.outcome in (Outcome.BLOCKED, Outcome.EXHAUSTED) else
                   'battle' if now < dispatch.interception_ends_at else
                   'replay_loading' if now < dispatch.interception_ends_at + timedelta(minutes=5) else 'settlement'),
            contributions=[dict(replay_id=r.replay_id, user_id=r.user_id, clan_id=r.side_clan_id,
                points=str(r.points), counted=effective_counted(r), source_counted=r.counted,
                reviewed=r.review_counted is not None, reason=r.reason,
                calculation={key: value for key, value in r.calculation.items() if key in safe_fields}) for r in rows],
            adjustments=[dict(id=a.id, clan_id=a.side_clan_id, points=str(a.points), reason=a.reason,
                actor_user_id=a.actor_user_id, created_at=a.created_at)
                for a in db.query(CycleInterceptionAdjustment).filter_by(interception_id=record.id).order_by(
                    CycleInterceptionAdjustment.id)] if record else [])

"""Рассчитывает личные очки по UUID из проверенных данных реплея в одной транзакции.

Не предназначен для прямого приёма данных из HTTP-запроса. Дата Арены означает
начало игры, что подтверждено владельцем проекта. Рейтинг нужного патча на момент
игры должен подтверждаться источником, а не текущим Elo профиля. Отсутствующие
данные остаются явно отмеченными и не заменяются выдуманными значениями.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re
from uuid import UUID

from app.core.time import as_utc

from app.models.campaign_cycle import CampaignCyclePlan
from app.models.cycle_battle import CycleMatchContribution
from app.models.cycle_economy import CycleEconomyState, CycleEconomySnapshot
from app.services import cycle_economy as economy
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService, _stored_points
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reinforcements import Outcome
from app.services.cycle_scoring import Contribution, MatchPlayer, calculate_contributions, _decimal
from app.services.match_eligibility_service import parse_match_duration_seconds
from app.services.clan_membership_service import ClanMembershipService


@dataclass(frozen=True)
class ReplayPlayer:
    uuid: str
    team: int
    elo: int | Decimal | None
    historical: bool
    rating_patch: str | None


@dataclass(frozen=True)
class ReplayFacts:
    replay_id: str
    source: str
    patch_family: str
    ranked: bool
    started_at: datetime | None
    finished_at: datetime | None
    players: tuple[ReplayPlayer, ...]
    winning_team: int | None
    draw: bool = False

    @staticmethod
    def arena_start(date_ms):
        """Разбирает исходное начало игры без подстановки времени загрузки."""
        valid_date = type(date_ms) is int and date_ms >= 0 or (
            isinstance(date_ms, str) and re.fullmatch(r'[0-9]{1,20}', date_ms) is not None)
        if valid_date:
            try:
                return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(date_ms))
            except (OverflowError, ValueError):
                pass
        return None

    def with_arena_times(self, *, date_ms, duration):
        """Вычисляет время игры из начала в миллисекундах и длительности, не подтверждая Elo."""
        if self.source != 'bfmeladder':
            raise ValueError('BFME Arena time source required')
        start = finish = None
        valid_duration = isinstance(duration, str) and re.fullmatch(
            r'[0-9]{1,6}:(?:[0-5][0-9]:)?[0-5][0-9]', duration) is not None
        if valid_duration:
            try:
                start = self.arena_start(date_ms)
                if start is not None:
                    finish = start + timedelta(seconds=parse_match_duration_seconds(duration))
            except (OverflowError, ValueError):
                start = finish = None
        return replace(self, started_at=start, finished_at=finish)


_PENDING = {'missing_historical_elo', 'missing_match_times', 'unknown_result', 'interception_pending'}


class CycleMatchService:
    @staticmethod
    def _fingerprint(replay, players, *, ratings=True):
        payload = dict(source=replay.source, replay_id=replay.replay_id, patch=replay.patch_family,
            ranked=replay.ranked, draw=replay.draw, winner=replay.winning_team,
            start=_utc(replay.started_at).isoformat() if replay.started_at else None,
            finish=_utc(replay.finished_at).isoformat() if replay.finished_at else None,
            players=[(key, p.team, str(p.elo) if p.elo is not None else None,
                      p.historical, p.rating_patch) if ratings else (key, p.team)
                     for key, p in sorted(players.items())])
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _validate(replay):
        if not isinstance(replay, ReplayFacts) or replay.source != 'bfmeladder':
            raise ValueError('Trusted BFME Arena replay facts required')
        if not isinstance(replay.replay_id, str) or not replay.replay_id.strip() or len(replay.replay_id) > 100:
            raise ValueError('Bounded replay ID required')
        if type(replay.ranked) is not bool or type(replay.draw) is not bool:
            raise ValueError('Explicit ranked/result flags required')
        players = {}
        for player in replay.players:
            if not isinstance(player, ReplayPlayer) or type(player.team) is not int or type(player.historical) is not bool:
                raise ValueError('Complete typed replay players required')
            try:
                identity = (replay.source, str(UUID(player.uuid)))
            except (ValueError, TypeError, AttributeError) as error:
                raise ValueError('Permanent replay identity required') from error
            if identity in players:
                raise ValueError('Duplicate replay identity')
            if player.elo is not None and _decimal(player.elo) < 0:
                raise ValueError('Historical Elo cannot be negative')
            players[identity] = player
        teams = {p.team for p in players.values()}
        if len(teams) != 2 or (replay.winning_team is not None and replay.winning_team not in teams):
            raise ValueError('Two complete teams and a valid result required')
        if replay.draw and replay.winning_team is not None:
            raise ValueError('Draw cannot have a winner')
        return players

    @staticmethod
    def _gate(timeline, replay):
        if not replay.ranked:
            return 'not_ranked'
        if replay.patch_family != 'ennorath':
            return 'unsupported_patch'
        if replay.started_at is None or replay.finished_at is None:
            return 'missing_match_times'
        start, finish = _utc(replay.started_at), _utc(replay.finished_at)
        if finish <= start:
            return 'invalid_match_times'
        if finish - start < timedelta(minutes=1):
            return 'too_short'
        if not timeline.accepts_match(start, finish):
            return 'outside_battle_window'
        return None

    @staticmethod
    def _snapshots(db, cycle):
        result = {}
        states = {row.clan_id: row for row in db.query(CycleEconomyState).filter_by(season_id=cycle.season_id)}
        for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id):
            state = states.get(plan.clan_id)
            # Старые тестовые данные созданы до явного сохранения снимка раскрытия.
            expected = (plan.snapshot or {}).get('economy_state_id', state.id if state else None)
            if expected is None:
                continue
            if type(expected) is not int or state is None or state.id != expected:
                raise ValueError('Complete frozen economic snapshot manifest required')
            snapshot = db.query(CycleEconomySnapshot).filter_by(cycle_id=cycle.id, state_id=expected).one_or_none()
            if snapshot is None:
                raise ValueError('Complete frozen economic snapshots required')
            result[state.clan_id] = snapshot
        return result

    @staticmethod
    def _assignments(battle, state, bindings, orders, replay):
        assignments = {}
        for side in battle.sides:
            for uid in side['user_ids']:
                assignments[uid] = dict(side=side['clan_id'], actual_clan=bindings[uid][0],
                    order=orders[uid], pending=None, exhausted=False)
        for dispatch in state.dispatches:
            if dispatch.territory_id != battle.territory_id:
                continue
            for uid, (clan_id, identity) in bindings.items():
                if identity not in dispatch.players:
                    continue
                pending = None
                if replay.started_at is not None and _utc(replay.started_at) < dispatch.arrives_at:
                    pending = 'reinforcement_not_arrived'
                elif dispatch.outcome == Outcome.BLOCKED:
                    pending = 'reinforcement_blocked'
                elif dispatch.outcome == Outcome.PENDING:
                    pending = 'interception_pending'
                assignments[uid] = dict(side=dispatch.recipient_clan_id, actual_clan=clan_id,
                    order=None, pending=pending, exhausted=dispatch.outcome == Outcome.EXHAUSTED,
                    dispatch=dispatch)
        return assignments

    @staticmethod
    def _bonus(battle, cycle, assignment, snapshots, *, direct):
        clan_id = assignment['actual_clan']
        snapshot = snapshots.get(clan_id)
        effects = tuple(economy.RelicEffect(e['key'], e['level'], e['effect'], Decimal(e['percent']))
                        for e in snapshot.effects) if snapshot else ()
        defense = assignment['side'] == battle.owner_clan_id
        military = snapshots.get(assignment['side']) if defense else snapshot
        order = assignment['order']
        source = battle.territory_id if defense else order.get('source_id') if order else None
        levels = military.territory_upgrades.get(str(source), {}) if military and source is not None else {}
        land = next(t for t in cycle.planning_snapshot if t['id'] == battle.territory_id)
        return economy.victory_bonus(effects, role='defense' if defense else 'attack',
            allied_help=clan_id != assignment['side'], direct=direct,
            fortress=land.get('fortress', False), naval=bool(order and order.get('route') == 'sea'),
            fortification_level=levels.get('fortification', 0),
            offense_level=levels.get('offense', 0), naval_level=levels.get('naval', 0))

    @staticmethod
    def _save(db, cycle, battle, replay_id, uid, side, contribution, calculation):
        points = _stored_points(contribution.points)
        row = db.query(CycleMatchContribution).filter_by(battle_id=battle.id,
            replay_id=replay_id, user_id=uid).one_or_none()
        if row is not None and row.review_reason is not None:
            return row
        if (row is not None and row.clan_id == side and row.points == points
                and row.reason == contribution.reason and row.calculation == calculation):
            return row
        if battle.completed_at is not None:
            raise ValueError('Late replay evidence requires administrative review')
        same_exclusion = bool(row is not None and not row.counted and contribution.reason == row.reason
            and points == row.points == 0
            and (row.calculation or {}).get('structure_fingerprint') == calculation['structure_fingerprint'])
        if row is not None and ((row.reason not in _PENDING and not same_exclusion) or row.clan_id != side):
            raise ValueError('Conflicting replay evidence requires administrative review')
        CampaignCycleStore._bump(db, cycle)
        cycle.import_verified_at = None
        if row is None:
            row = CycleMatchContribution(battle_id=battle.id, replay_id=replay_id, user_id=uid, clan_id=side)
            db.add(row)
        row.points, row.reason = points, contribution.reason
        row.counted = contribution.reason == 'counted'
        row.calculation = calculation
        db.flush()
        return row

    def evaluate(self, db, *, cycle, battle, state, bindings, replay):
        """Предварительный расчёт без записи, общий для импорта и проверки поздних игр."""
        players = self._validate(replay)
        fingerprint = self._fingerprint(replay, players)
        structure = self._fingerprint(replay, players, ratings=False)
        if cycle.orders_frozen_at is None or not cycle.battles_registered:
            raise ValueError('Fully revealed battle required')
        keyed = {(identity.source, str(identity.uuid)): uid for uid, (_, identity) in bindings.items()}
        if len(keyed) != len(bindings):
            raise ValueError('Unique frozen identity bindings required')
        orders = {o['user_id']: o for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id)
                  for o in plan.orders}
        assignments = self._assignments(battle, state, bindings, orders, replay)
        for uid in CyclePlanService.scouting_user_ids(db, cycle.id):
            if uid in assignments:
                assignments[uid]['pending'] = 'scouting'
        if replay.started_at is not None:
            for uid in {keyed.get(identity) for identity in players}:
                assignment = assignments.get(uid)
                if assignment and not ClanMembershipService.dispatched_member_since(db, user_id=uid,
                        clan_id=assignment['actual_clan'], since=as_utc(cycle.orders_frozen_at),
                        occurred_at=_utc(replay.started_at), dispatch=assignment.get('dispatch')):
                    assignment['pending'] = 'membership_changed'
        gate = self._gate(CampaignCycleStore.timeline(cycle), replay)
        if gate is None and any(assignments.get(keyed.get(identity), {}).get('pending') == 'interception_pending'
                                for identity in players):
            # Исход перехвата может изменить и множитель прямого боя у соперника.
            gate = 'interception_pending'
        snapshots = self._snapshots(db, cycle)
        scoring = []
        eligible_sides = {}
        for identity, player in players.items():
            assigned = assignments.get(keyed.get(identity))
            eligible_sides[identity] = assigned['side'] if assigned and not assigned['pending'] else None
        for identity, player in players.items():
            uid = keyed.get(identity)
            assigned = assignments.get(uid)
            direct = assigned is not None and any(p.team != player.team and eligible_sides[key] is not None
                and eligible_sides[key] != assigned['side'] for key, p in players.items())
            scoring.append(MatchPlayer(identity=':'.join(identity), team=player.team,
                clan_id=bindings[uid][0] if uid is not None else None,
                elo=player.elo if player.historical and player.rating_patch == replay.patch_family else None,
                side_id=eligible_sides[identity],
                victory_bonus_percent=self._bonus(battle, cycle, assigned, snapshots, direct=direct) if assigned else 0,
                exhausted=bool(assigned and assigned['exhausted'])))
        calculated = calculate_contributions(scoring, winning_team=replay.winning_team,
            draw=replay.draw, alliances=state.alliances)
        result = []
        for identity, player in players.items():
            uid = keyed.get(identity)
            assignment = assignments.get(uid)
            if assignment is None:
                continue
            reason = gate or assignment['pending']
            contribution = Contribution(Decimal(0), reason) if reason else calculated[':'.join(identity)]
            calculation = dict(input_fingerprint=fingerprint, structure_fingerprint=structure,
                source=replay.source, uuid=identity[1],
                actual_clan_id=assignment['actual_clan'], patch_family=replay.patch_family,
                historical_elo=str(player.elo) if player.elo is not None and player.historical
                    and player.rating_patch == replay.patch_family else None,
                started_at=_utc(replay.started_at).isoformat() if replay.started_at else None,
                finished_at=_utc(replay.finished_at).isoformat() if replay.finished_at else None,
                base_points=str(contribution.base_points), victory_bonus_percent=str(contribution.victory_bonus_percent),
                direct_multiplier=contribution.direct_multiplier,
                exhaustion_multiplier=str(contribution.exhaustion_multiplier))
            result.append(dict(user_id=uid, clan_id=assignment['side'],
                               contribution=contribution, calculation=calculation))
        return result

    def process(self, db, *, battle_id, replay):
        with CycleEconomyStore._atomic(db):
            cycle, battle = CycleBattleService()._locked(db, battle_id)
            _, _, state, bindings = CycleReinforcementStore()._locked(db, cycle.id)
            return [self._save(db, cycle, battle, f'{replay.source}:{replay.replay_id}',
                        row['user_id'], row['clan_id'], row['contribution'], row['calculation'])
                    for row in self.evaluate(db, cycle=cycle, battle=battle,
                        state=state, bindings=bindings, replay=replay)]

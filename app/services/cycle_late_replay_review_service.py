"""Явное решение администратора по пропущенному реплею завершённой битвы."""

from hashlib import sha256
import json

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.cycle_battle import CycleMatchContribution, CycleLateReplayDecision
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.match import Match
from app.models.user import User
from app.services.campaign_cycle_service import _utc
from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.cycle_battle_service import CycleBattleService, _stored_points
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_match_service import CycleMatchService
from app.services.cycle_reinforcement_store import CycleReinforcementStore


SAFE_CALCULATION = frozenset({'historical_elo', 'patch_family', 'started_at', 'finished_at',
    'base_points', 'victory_bonus_percent', 'direct_multiplier', 'exhaustion_multiplier'})


class CycleLateReplayReviewService:
    def _proposal(self, db, *, cycle, battle, match_id):
        season = db.get(CampaignSeason, cycle.season_id)
        if (battle.completed_at is None or cycle.orders_frozen_at is None
                or (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'):
            raise ValueError('Нужна завершённая битва нового режима с сохранёнными приказами')
        match = db.get(Match, match_id)
        if match is None or match.game_name != 'RotWK' or match.is_live:
            raise ValueError('Сохранённый реплей не найден')
        replay = CycleArenaIngestionService.adapt(match)
        if CycleMatchService._gate(CycleBattleService().cycles.timeline(cycle), replay) is not None:
            raise ValueError('Реплей не подходит по патчу, времени или рейтинговому режиму')
        state_row = db.query(CycleReinforcementState).filter_by(cycle_id=cycle.id).one_or_none()
        if state_row is None:
            raise ValueError('Нет сохранённого состояния участников и подкреплений')
        state, bindings = CycleReinforcementStore._unpack(state_row, cycle)
        recorded = db.query(CycleMatchContribution).filter_by(battle_id=battle.id,
            replay_id=f'bfmeladder:{replay.replay_id}').order_by(CycleMatchContribution.user_id).all()
        known = {row.user_id for row in recorded}
        proposed = [row for row in CycleMatchService().evaluate(db, cycle=cycle, battle=battle,
            state=state, bindings=bindings, replay=replay) if row['user_id'] not in known]
        if not proposed:
            raise ValueError('Новых вкладов для этой битвы нет: матч уже проверен либо участники не назначены')
        token_input = dict(battle_id=battle.id, revision=cycle.revision, state_revision=state_row.revision,
            match_id=match.id, source=match.source_payload,
            rows=[dict(user_id=r['user_id'], clan_id=r['clan_id'],
                points=str(r['contribution'].points), reason=r['contribution'].reason,
                calculation=r['calculation']) for r in proposed],
            recorded=[(r.user_id, str(r.points), r.counted, r.reason, r.review_reason) for r in recorded])
        token = sha256(json.dumps(token_input, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return match, replay, proposed, token

    def preview(self, db, *, battle_id, match_id):
        from app.models.cycle_battle import CycleTerritoryBattle
        from app.models.campaign_cycle import CampaignCycleRecord
        battle = db.get(CycleTerritoryBattle, battle_id)
        if battle is None:
            raise ValueError('Битва не найдена')
        cycle = db.get(CampaignCycleRecord, battle.cycle_id)
        _, replay, proposed, token = self._proposal(db, cycle=cycle, battle=battle, match_id=match_id)
        users = {u.id: u for u in db.query(User).filter(User.id.in_([r['user_id'] for r in proposed]))}
        return dict(match_id=match_id, replay_id=f'bfmeladder:{replay.replay_id}', preview_token=token,
            can_accept=all(r['contribution'].reason == 'counted' for r in proposed),
            players=[dict(user_id=r['user_id'], clan_id=r['clan_id'],
                display_name=(users[r['user_id']].display_name or users[r['user_id']].username)
                    if r['user_id'] in users else None,
                points=str(r['contribution'].points), reason=r['contribution'].reason,
                calculation={k: v for k, v in r['calculation'].items() if k in SAFE_CALCULATION})
                for r in proposed])

    def decide(self, db, *, battle_id, match_id, preview_token, counted, command_id, actor_user_id, reason, now):
        reason = CycleBattleService._reason(reason)
        if (type(counted) is not bool or not isinstance(command_id, str)
                or not command_id.strip() or len(command_id) > 120):
            raise ValueError('Нужны явное решение и постоянный ключ команды')
        now = _utc(now)
        with CycleEconomyStore._atomic(db):
            accounting = CycleBattleService()
            cycle, battle = accounting._locked(db, battle_id)
            previous = db.query(CycleLateReplayDecision).filter_by(battle_id=battle.id,
                command_id=command_id).one_or_none()
            if previous:
                if (previous.match_id, previous.preview_token, previous.counted, previous.actor_user_id,
                        previous.reason) != (match_id, preview_token, counted, actor_user_id, reason):
                    raise ValueError('Этот ключ уже использован для другого решения')
                return previous
            match = db.query(Match).filter_by(id=match_id).with_for_update().populate_existing().one_or_none()
            if match is None:
                raise ValueError('Сохранённый реплей не найден')
            _, replay, proposed, token = self._proposal(db, cycle=cycle, battle=battle, match_id=match_id)
            if token != preview_token:
                raise ValueError('Данные изменились: обновите предварительный расчёт')
            if now < as_utc(battle.completed_at):
                raise ValueError('Время решения не может предшествовать завершению битвы')
            if counted and any(r['contribution'].reason != 'counted' for r in proposed):
                raise ValueError('Нет подтверждённых данных для начисления: используйте отдельную ручную поправку')
            for row in proposed:
                value = row['contribution']
                db.add(CycleMatchContribution(battle_id=battle.id, replay_id=f'bfmeladder:{replay.replay_id}',
                    user_id=row['user_id'], clan_id=row['clan_id'], points=_stored_points(value.points),
                    counted=counted, reason=value.reason, calculation=row['calculation'],
                    review_reason=reason, reviewed_by_user_id=actor_user_id))
            decision = CycleLateReplayDecision(battle_id=battle.id, match_id=match_id,
                command_id=command_id, preview_token=token, counted=counted, reason=reason,
                actor_user_id=actor_user_id, decided_at=now, user_ids=sorted(r['user_id'] for r in proposed))
            db.add(decision)
            accounting.cycles._bump(db, cycle)
            db.flush()
            battle.recalculated_winner_clan_id = accounting._project(db, battle)
            db.flush()
            return decision

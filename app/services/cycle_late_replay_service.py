"""Показывает пропущенные реплеи завершённой битвы, не пересчитывая её результат."""

from sqlalchemy import or_

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCyclePlan, CampaignCycleRecord
from app.models.cycle_battle import CycleMatchContribution, CycleTerritoryBattle
from app.models.cycle_reinforcement_state import CycleReinforcementState
from app.models.match import Match
from app.models.user import User
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.clan_membership_service import ClanMembershipService
from app.services.cycle_arena_ingestion_service import CycleArenaIngestionService
from app.services.cycle_match_service import CycleMatchService
from app.services.cycle_reinforcement_store import CycleReinforcementStore


class CycleLateReplayService:
    def read(self, db, *, battle_id, after_id=0, limit=200):
        if type(after_id) is not int or after_id < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('Нужны допустимые границы страницы реплеев')
        battle = db.get(CycleTerritoryBattle, battle_id)
        if battle is None or battle.completed_at is None:
            raise ValueError('Поиск пропущенных реплеев доступен только для завершённой битвы')
        cycle = db.get(CampaignCycleRecord, battle.cycle_id)
        season = db.get(CampaignSeason, cycle.season_id)
        row = db.query(CycleReinforcementState).filter_by(cycle_id=cycle.id).one_or_none()
        if ((season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1'
                or cycle.orders_frozen_at is None or row is None):
            raise ValueError('Нужны сохранённые правила и личности раскрытого цикла')
        state, bindings = CycleReinforcementStore._unpack(row, cycle)
        keyed = {str(identity.uuid): uid for uid, (_, identity) in bindings.items()}
        timeline = CampaignCycleStore.timeline(cycle)
        orders = {order['user_id']: order for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle.id)
            for order in plan.orders}
        # Проверяем и исходное окно, и поздние загрузки с ошибочной старой локальной датой.
        page = db.query(Match).filter(Match.id > after_id, Match.game_name == 'RotWK', Match.is_live.is_(False),
            or_(Match.match_date.between(timeline.battle_at, timeline.battle_ends_at),
                Match.created_at >= battle.completed_at)).order_by(Match.id).limit(limit + 1).all()
        matches = page[:limit]
        recorded = set(db.query(CycleMatchContribution.replay_id, CycleMatchContribution.user_id).filter(
            CycleMatchContribution.battle_id == battle.id,
            CycleMatchContribution.replay_id.in_([f'bfmeladder:{m.match_id}' for m in matches])).all())
        items = []
        for match in matches:
            try:
                replay = CycleArenaIngestionService.adapt(match)
            except ValueError:
                continue
            if CycleMatchService._gate(timeline, replay) is not None:
                continue
            assignments = CycleMatchService._assignments(battle, state, bindings, orders, replay)
            players = []
            for player in replay.players:
                uid = keyed.get(player.uuid)
                assigned = assignments.get(uid)
                if assigned is None or (f'bfmeladder:{replay.replay_id}', uid) in recorded:
                    continue
                reason = assigned['pending']
                if not ClanMembershipService.continuous_member_since(db, user_id=uid,
                        clan_id=assigned['actual_clan'], since=as_utc(cycle.orders_frozen_at),
                        occurred_at=replay.started_at):
                    reason = 'membership_changed'
                players.append(dict(user_id=uid, clan_id=assigned['side'], reason=reason))
            if players:
                items.append(dict(match_id=match.id, replay_id=f'bfmeladder:{replay.replay_id}',
                    source_replay_id=replay.replay_id, started_at=replay.started_at, finished_at=replay.finished_at,
                    imported_at=match.created_at, players=players,
                    historical_elo_available=all(p.elo is not None and p.historical
                        and p.rating_patch == replay.patch_family for p in replay.players)))
        users = {user.id: user for user in db.query(User).filter(
            User.id.in_({p['user_id'] for item in items for p in item['players']}))}
        for item in items:
            for player in item['players']:
                user = users.get(player['user_id'])
                player['display_name'] = (user.display_name or user.username) if user else None
        return dict(items=items, scanned=len(matches),
            next_after_id=matches[-1].id if len(page) > limit else None)

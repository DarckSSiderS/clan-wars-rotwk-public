from decimal import Decimal

from app.core.time import as_utc, utc_now
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_battle import CycleMatchContribution, CycleScoreAdjustment, CycleTerritoryBattle
from app.models.territory import Territory
from app.services.campaign_cycle_store import CampaignCycleStore


class CycleClanHistoryService:
    def read(self, db, *, clan_id, now=None):
        clan = db.get(Clan, clan_id)
        if clan is None or clan.is_deleted:
            raise LookupError('Clan not found')
        now = as_utc(now or utc_now())
        seasons = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).all()
        current = next((s for s in seasons if s.status == 'active'), seasons[0] if seasons else None)
        cycle_seasons = {s.id for s in seasons if (s.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1'}
        rows = db.query(CycleTerritoryBattle, CampaignCycleRecord, Territory).join(
            CampaignCycleRecord, CycleTerritoryBattle.cycle_id == CampaignCycleRecord.id).join(
            Territory, CycleTerritoryBattle.territory_id == Territory.id).filter(
            CampaignCycleRecord.season_id.in_(cycle_seasons),
            CampaignCycleRecord.orders_frozen_at.isnot(None),
            CampaignCycleRecord.battles_registered.is_(True)).order_by(
            CampaignCycleRecord.season_id.desc(), CampaignCycleRecord.number.desc(),
            CycleTerritoryBattle.territory_id).all()
        rows = [(battle, cycle, land) for battle, cycle, land in rows
                if any(side['clan_id'] == clan_id for side in battle.sides)
                and CampaignCycleStore.timeline(cycle).battle_at <= now]
        battle_ids = [battle.id for battle, _, _ in rows]
        scores = {(battle.id, side['clan_id']): Decimal(0)
                  for battle, _, _ in rows for side in battle.sides}
        # Sum the same counted contributions and adjustments as the battle view,
        # without fetching player identities or issuing a query per battle.
        for model in (CycleMatchContribution, CycleScoreAdjustment):
            query = db.query(model.battle_id, model.clan_id, model.points).filter(model.battle_id.in_(battle_ids))
            if model is CycleMatchContribution:
                query = query.filter(model.counted.is_(True))
            for battle_id, side_id, points in query:
                key = (battle_id, side_id)
                if key in scores:
                    scores[key] += points
        clan_ids = {side['clan_id'] for battle, _, _ in rows for side in battle.sides}
        clans = {c.id: c for c in db.query(Clan).filter(Clan.id.in_(clan_ids), Clan.is_deleted.is_(False))}
        return dict(season_id=current.id if current else None, battles=[dict(
            id=battle.id, season_id=cycle.season_id, cycle_id=cycle.id, cycle_number=cycle.number,
            territory_id=land.id, territory_name=land.name, started_at=CampaignCycleStore.timeline(cycle).battle_at,
            completed_at=battle.completed_at, winner_clan_id=battle.winner_clan_id,
            sides=[dict(clan_id=side['clan_id'], clan_name=clans[side['clan_id']].name if side['clan_id'] in clans else None,
                        score=str(scores[(battle.id, side['clan_id'])]),
                        role='defense' if side['clan_id'] == battle.owner_clan_id else 'attack') for side in battle.sides])
            for battle, cycle, land in rows])

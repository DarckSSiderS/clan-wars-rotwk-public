"""Opt-in periodic cycle transitions; caller owns commit and replay verification.

Never starts/reset seasons, infers a missed planning snapshot, or certifies an
Arena scan from a heartbeat. Closed-season accepted caravans keep arriving.
"""

from app.core.time import as_utc
from app.models.campaign import CampaignSeason
from app.models.campaign_cycle import CampaignCycleRecord
from app.models.clan import Clan
from app.models.cycle_economy import CycleEconomyState
from app.models.cycle_market import CycleMarketCaravan, CycleMarketOffer
from app.models.cycle_startup import CycleStartup
from app.services.campaign_cycle_service import CyclePhase, _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.campaign_rule_service import CampaignRuleService
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_income_service import CycleIncomeService
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reveal_service import CycleRevealService
from app.services.cycle_settlement_service import CycleSettlementService
from app.services.cycle_startup_service import CycleStartupService
from app.services.cycle_interception_service import CycleInterceptionService


class CycleRuntimeService:
    @staticmethod
    def owns_campaign(db):
        season = db.query(CampaignSeason).filter_by(status='active').first()
        if season is None:
            season = db.query(CampaignSeason).order_by(CampaignSeason.number.desc()).first()
        return bool(season and (season.rules_snapshot or {}).get('mechanics_version') == 'cycle_v1')

    @staticmethod
    def _latest(db, season_id):
        return db.query(CampaignCycleRecord).filter_by(season_id=season_id).order_by(
            CampaignCycleRecord.number.desc()).with_for_update().populate_existing().first()

    @staticmethod
    def _deliver(db, cycle, now):
        due = db.query(CycleMarketCaravan).join(CycleMarketOffer).filter(
            CycleMarketOffer.season_id == cycle.season_id,
            CycleMarketCaravan.delivered_at.is_(None),
            CycleMarketCaravan.arrives_at <= now).order_by(CycleMarketCaravan.id).all()
        for caravan in due:
            wallet = db.query(CycleEconomyState).filter_by(season_id=cycle.season_id,
                clan_id=caravan.recipient_clan_id).populate_existing().one()
            CycleMarketService().deliver(db, cycle_id=cycle.id, caravan_id=caravan.id,
                now=now, command_id=f'runtime:deliver:{caravan.id}',
                expected_revision=caravan.revision, expected_wallet_revision=wallet.revision)

    @staticmethod
    def _accrue(db, cycle, now):
        states = db.query(CycleEconomyState).join(Clan).filter(
            CycleEconomyState.season_id == cycle.season_id,
            Clan.is_deleted.is_(False)).order_by(CycleEconomyState.id).all()
        for state in states:
            CycleIncomeService().accrue(db, state_id=state.id, now=now)

    def tick(self, db, *, now, allow_settlement=True):
        """Keep cycle-mode ownership between seasons too; do not resume legacy pay."""
        now = _utc(now)
        with CycleEconomyStore._atomic(db):
            seasons = db.query(CampaignSeason).order_by(CampaignSeason.id).all()
            active = None
            for season in seasons:
                if (season.rules_snapshot or {}).get('mechanics_version') != 'cycle_v1':
                    continue
                cycle = self._latest(db, season.id)
                if season.status == 'active':
                    active = (season, cycle)
                elif cycle is not None:
                    self._deliver(db, cycle, now)
            if active is None:
                return self.owns_campaign(db)
            season, cycle = active
            if cycle is None:
                raise ValueError('An explicit cycle-season launch is required')
            if now < as_utc(cycle.starts_at):
                return True
            startup = db.get(CycleStartup, season.id, populate_existing=True)
            if startup is None:
                raise ValueError('An explicit startup snapshot is required')
            timeline = CampaignCycleStore.timeline(cycle)
            phase = timeline.phase_at(now)
            if phase == CyclePhase.REGISTRATION:
                CycleStartupService().qualify(db, cycle_id=cycle.id, now=now)
            else:
                if startup.expired_at is None:
                    CycleStartupService().expire(db, cycle_id=cycle.id, now=now)
                if phase == CyclePhase.PREPARATION:
                    CyclePlanService().capture_preparation(db, cycle_id=cycle.id, now=now)
                elif phase in (CyclePhase.BATTLE, CyclePhase.REPLAY_LOADING, CyclePhase.SETTLEMENT):
                    if cycle.planning_snapshot is None:
                        raise ValueError('Missed preparation requires explicit review, not a guessed snapshot')
                    CycleRevealService().reveal(db, cycle_id=cycle.id, now=now)
            self._accrue(db, cycle, now)
            self._deliver(db, cycle, now)
            if allow_settlement:
                CycleInterceptionService().settle_ready(db, cycle_id=cycle.id, now=now)
            if (allow_settlement and phase == CyclePhase.SETTLEMENT and cycle.import_verified_at is not None
                    and all(done for key, done in cycle.dependencies.items()
                            if key.startswith('interception:'))):
                CycleSettlementService().settle(db, cycle_id=cycle.id, now=now)
            phase = CampaignCycleStore.timeline(cycle).phase_at(now)
            CycleMarketService().expire(db, cycle_id=cycle.id, now=now,
                command_id=f'runtime:expire:{cycle.id}:{int(cycle.settled_at is not None)}')
            if phase == CyclePhase.COMPLETE:
                version = CampaignRuleService().get_active(db, create=False).version
                next_cycle = CampaignCycleStore().advance(db, cycle_id=cycle.id, now=now, rule_version=version)
                CyclePlanService().capture_preparation(db, cycle_id=next_cycle.id, now=now)
            return True

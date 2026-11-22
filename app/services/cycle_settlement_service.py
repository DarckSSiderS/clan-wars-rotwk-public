"""Trusted settlement composition; importer verification is a separate prerequisite.

No commit, HTTP entry point or implicit claim that Arena scanning succeeded.
The worker must resolve interceptions and verify full replay coverage first.
"""

from app.core.time import as_utc
from app.models.cycle_battle import CycleTerritoryBattle
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_ownership_service import CycleOwnershipService


class CycleSettlementService:
    def settle(self, db, *, cycle_id, now):
        now = _utc(now)
        cycles = CampaignCycleStore()
        with CycleEconomyStore._atomic(db):
            cycle = cycles._locked(db, cycle_id)
            if cycle.settled_at is not None:
                return cycle
            if cycle.import_verified_at is None or now < as_utc(cycle.import_verified_at):
                raise ValueError('Successful full import verification is required')
            if now < cycles.timeline(cycle).replay_deadline:
                raise ValueError('Replay grace has not ended')
            if cycle.orders_frozen_at is None or not cycle.battles_registered:
                raise ValueError('Frozen orders and complete battle creation are required')
            if any(not done for key, done in cycle.dependencies.items()
                   if key.startswith('interception:')):
                raise ValueError('Interception dependencies are not complete')
            battles = db.query(CycleTerritoryBattle).filter_by(cycle_id=cycle_id).order_by(
                CycleTerritoryBattle.territory_id).all()
            accounting, ownership = CycleBattleService(), CycleOwnershipService()
            for battle in battles:
                accounting.finalize(db, battle_id=battle.id, completed_at=now)
                ownership.apply_result(db, battle_id=battle.id, now=now)
            # Empty cycles also need their frozen-rate income credited before rest.
            CycleOwnershipService._accrue_before_change(db, cycle.season_id, now)
            return cycles.settle(db, cycle_id=cycle_id, completed_at=now)

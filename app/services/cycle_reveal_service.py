"""Atomic trusted reveal; never called while a plan is still hidden."""

from app.models.campaign_cycle import CampaignCyclePlan
from app.models.clan import Clan
from app.models.cycle_diplomacy import CycleDiplomacyEvent, CycleDiplomacyPair
from app.services.campaign_cycle_service import _utc
from app.services.campaign_cycle_store import CampaignCycleStore
from app.services.cycle_battle_service import CycleBattleService
from app.services.cycle_diplomacy_service import CycleDiplomacyService
from app.services.cycle_economy_store import CycleEconomyStore
from app.services.cycle_market_service import CycleMarketService
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reinforcement_store import CycleReinforcementStore


class CycleRevealService:
    def reveal(self, db, *, cycle_id, now):
        now = _utc(now)
        with CycleEconomyStore._atomic(db):
            cycles = CampaignCycleStore()
            cycle = cycles._locked(db, cycle_id)
            if cycle.settled_at is not None:
                raise ValueError('A settled cycle cannot be revealed')
            CyclePlanService().freeze(db, cycle_id=cycle_id, now=now)
            battles = CycleBattleService().create_from_orders(db, cycle_id=cycle_id)
            owners = {land['id']: land['owner_clan_id'] for land in cycle.planning_snapshot}
            attacks = set()
            for plan in db.query(CampaignCyclePlan).filter_by(cycle_id=cycle_id):
                for order in plan.orders:
                    if order['kind'] == 'attack':
                        defender = owners[order['territory_id']]
                        if defender is not None and defender != plan.clan_id:
                            attacks.add((plan.clan_id, defender))
            for attacker, defender in sorted(attacks):
                clans = db.query(Clan).filter(Clan.id.in_((attacker, defender))).all()
                if len(clans) != 2 or any(clan.is_deleted for clan in clans):
                    continue
                event = db.query(CycleDiplomacyEvent.id).join(CycleDiplomacyPair).filter(
                    CycleDiplomacyEvent.cycle_id == cycle_id,
                    CycleDiplomacyEvent.actor_clan_id == attacker,
                    CycleDiplomacyEvent.kind == 'attack_revealed',
                    CycleDiplomacyPair.clan_low_id == min(attacker, defender),
                    CycleDiplomacyPair.clan_high_id == max(attacker, defender)).first()
                if event is None:
                    CycleDiplomacyService().record_revealed_attack(db, cycle_id=cycle_id,
                        attacker_clan_id=attacker, defender_clan_id=defender,
                        now=cycles.timeline(cycle).battle_at)
                CycleMarketService().cancel_hostile_pair(db, cycle_id=cycle_id,
                    clan_id=attacker, other_clan_id=defender, now=now,
                    command_id=f'reveal:{cycle_id}:hostile:{attacker}:{defender}')
            CycleReinforcementStore().initialize(db, cycle_id=cycle_id)
            return battles

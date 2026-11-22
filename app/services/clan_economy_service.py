from collections.abc import Mapping
from datetime import datetime, timedelta
from math import ceil
from typing import Dict, List
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.campaign_mode import cycle_owns_campaign, is_interseason, require_legacy_economy
from app.core.exceptions import InsufficientPermissionsException
from app.core.permissions import ClanPermission, is_admin, require_clan_permission
from app.core.time import as_utc, utc_now
from app.core.economy_balance import is_admin_territory_name
from app.models.clan import Clan, ClanMember
from app.models.user import User
from app.services.clan_attack_service import get_clan_attack_status
from app.services.operation_service import ResourceLedgerService
from app.services.clan_influence_service import ClanInfluenceService
from app.services.territory_ownership_service import TerritoryOwnershipService
from app.core.territory_development import initial_military_level
from app.models.clan_asset import ClanAsset, ClanOwnedAsset
from app.models.territory import Territory, TerritoryAttackingClans, TerritoryDefendingClans
from app.models.war import ClanWar
from app.models.operation import ResourceLedgerEntry
from app.services.campaign_history_service import CampaignHistoryService
from app.services.campaign_rule_service import CampaignRuleService
from app.services.clan_attack_point_service import ClanAttackPointService
from app.services.operation_service import AdminAuditService
from app.services.war_deployment_service import WarDeploymentService
from app.services.notification_service import notification_service


RESOURCE_FIELDS = {"gold": "gold", "iron": "iron", "wood": "wood", "food": "food", "mithril": "mithril"}
REGION_RESOURCES = {
    "mordor": "food",
    "misty-mountains": "mithril",
    "rhovanion": "wood",
    "rohan": "wood",
    "eriador": "wood",
    "lindon": "wood",
    "gondor": "iron",
    "isen": "iron",
    "angmar": "iron",
    "harad": "food",
    "rhun": "iron",
}
RELIC_LOADOUT_SIZE = 4
RELIC_LOADOUT_COOLDOWN = timedelta(days=2)


class ClanEconomyService:
    def __init__(self):
        self.ledger = ResourceLedgerService()
        self.influence = ClanInfluenceService()
        self.ownership = TerritoryOwnershipService()
        self.rule_service = CampaignRuleService()

    def _rule_values(
        self,
        db: Session | None,
        rules: Mapping[str, int | float] | None,
    ) -> Mapping[str, int | float]:
        if rules is not None:
            return rules
        if db is None:
            raise ValueError("db or an explicit campaign rule snapshot is required")
        return self.rule_service.get_active(db).values

    def start_new_season(
        self,
        db: Session,
        starting_influence: int,
        reset_development: bool = True,
        *,
        actor_user_id: int | None = None,
        season_name: str | None = None,
    ) -> Dict:
        require_legacy_economy(db)
        if starting_influence < 0 or starting_influence > 100000:
            raise InsufficientPermissionsException("Стартовое влияние должно быть от 0 до 100000")
        # Market operations and a season reset must not cross transaction boundaries.
        from app.services.market_service import ClanMarketService
        market = ClanMarketService()
        market.cancel_for_season_reset(db)
        rules = self._rule_values(db, None)
        starting_resources = {
            resource: int(rules[f"CAMPAIGN_STARTING_{resource.upper()}"])
            for resource in ("gold", "iron", "wood", "food", "mithril")
        }
        now = utc_now()
        campaign_history = CampaignHistoryService()
        completed_season = campaign_history.complete_active_season(
            db,
            completed_at=now,
        )
        attack_points = ClanAttackPointService()
        deployments = WarDeploymentService()
        active_wars = (
            db.query(ClanWar)
            .filter(ClanWar.status == "active")
            .with_for_update()
            .all()
        )
        for war in active_wars:
            war.status = "canceled"
            war.ended_at = now
            for deployment in war.deployments:
                deployments.release_attack_lock(db, deployment, now=now)
            linked_spends = [
                spend
                for spend in war.attack_point_spends
                if spend.refunded_at is None and as_utc(spend.recover_at) > now
            ]
            for spend in linked_spends:
                attack_points.refund(
                    db,
                    spend,
                    actor_user_id=actor_user_id,
                    reason="season_reset",
                    now=now,
                )
            if not linked_spends:
                attack_points.refund_for_war(
                    db,
                    war,
                    actor_user_id=actor_user_id,
                    reason="season_reset",
                    now=now,
                )
            if actor_user_id is not None:
                AdminAuditService().record(
                    db,
                    actor_user_id=actor_user_id,
                    action="war_canceled_for_season_reset",
                    entity_type="clan_war",
                    entity_id=war.id,
                    before_data={"status": "active"},
                    after_data={"status": "canceled"},
                    reason="season_reset",
                )
        db.query(TerritoryAttackingClans).delete(synchronize_session=False)
        db.query(TerritoryDefendingClans).delete(synchronize_session=False)
        for territory in db.query(Territory).all():
            self.ownership.transfer(
                db,
                territory,
                None,
                changed_at=now,
                reason="season_reset",
            )
            territory.status = "neutral"
            if reset_development:
                military_level = initial_military_level(
                    territory.name,
                    is_playable=territory.is_playable,
                    stronghold_power=territory.stronghold_power or 0,
                )
                territory.development_level = 0
                territory.fortifications = military_level
                territory.offense_level = military_level
                territory.port_level = 0
                territory.fleet_level = 0
                territory.strategic_value = territory.calculate_strategic_value()
        clans = db.query(Clan).all()
        influence_before_reset = {
            clan.id: int(clan.territory_points or 0)
            for clan in clans
        }
        resources_before_reset = {
            clan.id: {
                resource: int(getattr(clan, resource) or 0)
                for resource in starting_resources
            }
            for clan in clans
        }
        for clan in clans:
            clan.base_influence = starting_influence
            clan.territory_points = starting_influence
            if not clan.is_admin_clan:
                for resource, amount in starting_resources.items():
                    setattr(clan, resource, amount)
                clan.resources = clan.gold
            clan.last_economy_tick = now
            clan.gold_income_remainder = 0.0
            clan.next_attack_at = None
        season = campaign_history.create_season(
            db,
            starting_influence=starting_influence,
            reset_development=reset_development,
            actor_user_id=actor_user_id,
            name=season_name,
            starts_at=utc_now(),
        )
        for clan in clans:
            before = influence_before_reset[clan.id]
            db.add(
                ResourceLedgerEntry(
                    operation_id=f"season-start:{season.id}:{clan.id}",
                    clan_id=clan.id,
                    resource="influence",
                    amount=starting_influence - before,
                    balance_before=before,
                    balance_after=starting_influence,
                    action="season_started",
                    source_type="campaign_season",
                    source_id=str(season.id),
                    actor_user_id=actor_user_id,
                    details={"season_name": season.name},
                )
            )
            if clan.is_admin_clan:
                continue
            for resource, balance_after in starting_resources.items():
                balance_before = resources_before_reset[clan.id][resource]
                db.add(
                    ResourceLedgerEntry(
                        operation_id=(
                            f"season-start:{season.id}:{clan.id}:{resource}"
                        ),
                        clan_id=clan.id,
                        resource=resource,
                        amount=balance_after - balance_before,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        action="season_started",
                        source_type="campaign_season",
                        source_id=str(season.id),
                        actor_user_id=actor_user_id,
                        details={"season_name": season.name},
                    )
                )
        db.commit()
        return {
            "message": "Новый сезон начат",
            "season_id": season.id,
            "season_name": season.name,
            "completed_season_id": completed_season.id if completed_season else None,
            "clans": len(clans),
            "territories": db.query(Territory).count(),
            "starting_influence": starting_influence,
        }

    def settle_clan(
        self,
        db: Session,
        clan: Clan,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> Clan:
        if cycle_owns_campaign(db) or is_interseason(db):
            return clan
        self.ledger.lock_clans(db, [clan.id])
        rules = self._rule_values(db, rules)
        now = utc_now()
        self._ensure_balances(clan)
        territories = [
            territory
            for territory in db.query(Territory)
            .filter(Territory.owner_clan_id == clan.id)
            .all()
            if not is_admin_territory_name(territory.name)
        ]
        clan_bonuses = self.get_clan_bonuses(db, clan.id)
        self.influence.recalculate(db, clan.id)
        for territory in territories:
            self.prepare_territory(db, territory, rules=rules)
            self._settle_daily_territory_resources(
                db,
                clan,
                territory,
                now,
                clan_bonuses,
                rules,
            )

        if not clan.last_economy_tick:
            clan.last_economy_tick = now
            return clan

        last_economy_tick = as_utc(clan.last_economy_tick)
        elapsed = now - last_economy_tick
        economy_tick = timedelta(hours=float(rules["ECONOMY_TICK_HOURS"]))
        if elapsed < economy_tick:
            return clan

        max_catchup_ticks = max(
            1,
            int(
                timedelta(
                    days=int(rules["ECONOMY_MAX_CATCHUP_DAYS"])
                ).total_seconds()
                // economy_tick.total_seconds()
            ),
        )
        tick_count = min(
            int(elapsed.total_seconds() // economy_tick.total_seconds()),
            max_catchup_ticks,
        )
        accrued_hours = tick_count * float(rules["ECONOMY_TICK_HOURS"])
        accrued_gold = float(clan.gold_income_remainder or 0)
        for territory in territories:
            accrued_gold += (
                self._daily_income(territory, rules)
                * accrued_hours
                / 24
                * (100 + clan_bonuses.get("gold_income_percent", 0))
                / 100
            )
        gold_income = int(accrued_gold + 1e-9)
        gold_income_remainder = max(
            0.0,
            round(accrued_gold - gold_income, 9),
        )
        clan.gold_income_remainder = (
            0.0 if gold_income_remainder < 1e-8 else gold_income_remainder
        )

        operation_id = (
            f"daily-gold:{clan.id}:{last_economy_tick.isoformat()}:"
            f"{tick_count}:{accrued_hours}"
        )
        if gold_income:
            self.ledger.apply_change(
                db,
                clan,
                resource="gold",
                amount=gold_income,
                operation_id=operation_id,
                action="territory_income",
                source_type="economy_tick",
                details={
                    "days": accrued_hours / 24,
                    "ticks": tick_count,
                    "tick_hours": float(rules["ECONOMY_TICK_HOURS"]),
                },
            )
        clan.resources = clan.gold
        clan.last_economy_tick = last_economy_tick + economy_tick * tick_count
        return clan

    def _settle_daily_territory_resources(
        self,
        db: Session,
        clan: Clan,
        territory: Territory,
        now: datetime,
        clan_bonuses: Dict[str, int],
        rules: Mapping[str, int | float],
    ) -> None:
        if territory.owner_clan_id != clan.id:
            return
        if territory.owned_since is None:
            self.ownership.transfer(
                db,
                territory,
                clan.id,
                changed_at=now,
                reason="economy_backfill",
            )

        ready_at = as_utc(territory.resource_income_ready_at)
        if ready_at is None:
            ready_at = as_utc(territory.owned_since) + timedelta(
                hours=float(rules["TERRITORY_RESOURCE_READY_HOURS"])
            )
            territory.resource_income_ready_at = ready_at

        payout_interval = timedelta(
            hours=float(rules["TERRITORY_RESOURCE_PAYOUT_HOURS"])
        )
        last_payout = as_utc(territory.last_resource_payout_at)
        if now < ready_at:
            return

        if last_payout is None:
            cycles = 1 + int(
                (now - ready_at).total_seconds() // payout_interval.total_seconds()
            )
            first_payout_at = ready_at
        else:
            cycles = int(
                (now - last_payout).total_seconds() // payout_interval.total_seconds()
            )
            first_payout_at = last_payout + payout_interval
        cycles = min(cycles, int(rules["TERRITORY_MAX_RESOURCE_CATCHUP_CYCLES"]))
        if cycles <= 0:
            return
        rewards = self._daily_resource_rewards(territory, clan_bonuses)

        for cycle in range(cycles):
            payout_at = first_payout_at + payout_interval * cycle
            operation_id = f"daily-territory:{territory.id}:{payout_at.isoformat()}"
            for resource, resource_amount in rewards:
                if (
                    resource not in RESOURCE_FIELDS
                    or resource == "gold"
                    or resource_amount <= 0
                ):
                    continue
                self.ledger.apply_change(
                    db,
                    clan,
                    resource=resource,
                    amount=resource_amount,
                    operation_id=operation_id,
                    action="territory_daily_resource",
                    source_type="territory",
                    source_id=territory.id,
                    details={
                        "territory_name": territory.name,
                        "payout_at": payout_at.isoformat(),
                        "great_stronghold": territory.is_great_stronghold,
                    },
                )

        territory.last_resource_payout_at = (
            first_payout_at + payout_interval * (cycles - 1)
        )
        territory.last_weekly_payout_at = territory.last_resource_payout_at

    @staticmethod
    def _population_income_bonuses(
        territory: Territory,
        rules: Mapping[str, int | float],
    ) -> tuple[float, int]:
        population = min(
            int(rules["POPULATION_INCOME_BONUS_CAP_PERCENT"])
            * int(rules["POPULATION_PER_INCOME_PERCENT"]),
            max(0, int(territory.population or 0)),
        )
        bonus_percent = population / int(rules["POPULATION_PER_INCOME_PERCENT"])
        level = max(0, int(territory.development_level or 0))
        break_level = int(rules["POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL"])
        development_bonus_percent = (
            min(level, break_level)
            * int(rules["POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT"])
            + max(0, level - break_level)
            * int(rules["POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT"])
        )
        return round(bonus_percent, 2), development_bonus_percent

    @classmethod
    def _daily_income(
        cls,
        territory: Territory,
        rules: Mapping[str, int | float],
    ) -> float:
        population_bonus, development_bonus = cls._population_income_bonuses(
            territory,
            rules,
        )
        return round(
            max(0, int(territory.resource_wealth or 0))
            * (1 + (population_bonus + development_bonus) / 100),
            2,
        )

    @staticmethod
    def _daily_resource_rewards(
        territory: Territory,
        clan_bonuses: Dict[str, int],
    ) -> List[tuple[str, int]]:
        bonus = clan_bonuses.get("resource_income_flat", 0)
        if territory.is_great_stronghold and territory.secondary_resource_type:
            return [
                (territory.resource_type, 1 + bonus),
                (territory.secondary_resource_type, 1 + bonus),
            ]
        return [
            (
                territory.resource_type,
                max(1, int(territory.resource_output or 1)) + bonus,
            )
        ]

    def settle_all(
        self,
        db: Session,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> None:
        if cycle_owns_campaign(db) or is_interseason(db):
            return
        rules = self._rule_values(db, rules)
        clans = db.query(Clan).order_by(Clan.id).all()
        self.ledger.lock_clans(db, [clan.id for clan in clans])
        for clan in clans:
            self.settle_clan(db, clan, rules=rules)
        db.commit()

    def prepare_territory(
        self,
        db: Session | None,
        territory: Territory,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> Territory:
        if db is not None and is_interseason(db):
            return territory
        rules = self._rule_values(db, rules)
        region = (territory.region or "").lower()
        if territory.adjacent_territory_ids is None:
            territory.adjacent_territory_ids = []
        territory.strategic_value = territory.calculate_strategic_value()
        resource_type = (territory.resource_type or "").strip().lower()
        if resource_type not in RESOURCE_FIELDS:
            resource_type = REGION_RESOURCES.get(region, "iron")
        territory.resource_type = resource_type
        if not territory.resource_output:
            territory.resource_output = max(
                int(rules["TERRITORY_MIN_RESOURCE_OUTPUT"]),
                (territory.resource_wealth or 0)
                // int(rules["TERRITORY_RESOURCE_WEALTH_DIVISOR"])
                + (territory.strategic_value or 1),
            )
        if (
            territory.is_great_stronghold
            and (
                not territory.secondary_resource_type
                or territory.secondary_resource_type == territory.resource_type
            )
        ):
            territory.secondary_resource_type = next(
                resource
                for resource in ("iron", "wood", "food", "mithril")
                if resource != territory.resource_type
            )
        return territory

    def get_territory_economy(
        self,
        territory: Territory,
        db: Session | None = None,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> Dict:
        rules = self._rule_values(db, rules)
        self.prepare_territory(db, territory, rules=rules)
        bonuses = (
            self.get_clan_bonuses(db, territory.owner_clan_id)
            if db is not None and territory.owner_clan_id else {}
        )
        ready_at = as_utc(territory.resource_income_ready_at)
        if ready_at is None and territory.owned_since is not None:
            ready_at = as_utc(territory.owned_since) + timedelta(
                hours=float(rules["TERRITORY_RESOURCE_READY_HOURS"])
            )
        last_payout = as_utc(territory.last_resource_payout_at)
        next_resource_payout_at = (
            last_payout + timedelta(hours=float(rules["TERRITORY_RESOURCE_PAYOUT_HOURS"]))
            if last_payout is not None
            else ready_at
        )
        daily_income = self._daily_income(territory, rules)
        population_bonus, population_development_bonus = (
            self._population_income_bonuses(territory, rules)
        )
        daily_income_with_clan_bonus = round(
            daily_income * (100 + bonuses.get("gold_income_percent", 0)) / 100,
            2,
        )
        daily_rewards = self._daily_resource_rewards(territory, bonuses)
        return {
            "prosperity_score": territory.prosperity_score,
            "base_daily_income": max(0, territory.resource_wealth or 0),
            "gold_income_period_hours": 24,
            "population_income_bonus_percent": population_bonus,
            "population_development_income_bonus_percent": population_development_bonus,
            "population_next_development_income_bonus_percent": (
                int(rules["POPULATION_DEVELOPMENT_BONUS_FIRST_LEVELS_PERCENT"])
                if int(territory.development_level or 0)
                < int(rules["POPULATION_DEVELOPMENT_BONUS_BREAK_LEVEL"])
                else int(rules["POPULATION_DEVELOPMENT_BONUS_LATER_LEVELS_PERCENT"])
            ),
            "daily_income": daily_income,
            "clan_gold_income_bonus_percent": bonuses.get("gold_income_percent", 0),
            "daily_income_with_clan_bonus": daily_income_with_clan_bonus,
            "base_weekly_income": max(0, territory.resource_wealth or 0) * 7,
            "weekly_income": round(daily_income * 7, 2),
            "weekly_income_with_clan_bonus": round(daily_income_with_clan_bonus * 7, 2),
            "resource_type": territory.resource_type,
            "resource_output": territory.resource_output,
            "secondary_resource_type": territory.secondary_resource_type,
            "daily_resource_rewards": [
                {"resource": resource, "amount": amount}
                for resource, amount in daily_rewards
            ],
            "weekly_resource_rewards": [
                {"resource": resource, "amount": amount * 7}
                for resource, amount in daily_rewards
            ],
            "development_level": territory.development_level or 0,
            "offense_level": territory.offense_level or 0,
            "port_level": territory.port_level or 0,
            "fleet_level": territory.fleet_level or 0,
            "naval_level": max(territory.port_level or 0, territory.fleet_level or 0),
            "defense_bonus_percent": (
                (territory.fortifications or 0)
                * int(rules["TERRITORY_LEVEL_BONUS_PERCENT"])
            ),
            "population_growth_percent_per_level": (
                float(rules["POPULATION_BASE_GROWTH_PERCENT"])
                + bonuses.get("population_growth_percent", 0)
                / float(rules["POPULATION_GROWTH_RELIC_DIVISOR"])
            ),
            "population_flat_growth_per_level": int(
                rules["POPULATION_FLAT_GROWTH_PER_LEVEL"]
            ),
            "territory_influence": self.influence.get_territory_influence(
                db,
                territory,
            ) if db is not None else int(territory.influence_value or 0),
            "base_territory_influence": int(territory.influence_value or 0),
            "daily_resource_output": sum(amount for _, amount in daily_rewards),
            "weekly_resource_output": sum(amount * 7 for _, amount in daily_rewards),
            "resource_ready_period_hours": int(rules["TERRITORY_RESOURCE_READY_HOURS"]),
            "resource_payout_period_hours": int(
                rules["TERRITORY_RESOURCE_PAYOUT_HOURS"]
            ),
            "owned_since": territory.owned_since,
            "resource_income_ready_at": ready_at,
            "last_resource_payout_at": last_payout,
            "next_resource_payout_at": next_resource_payout_at,
            "next_weekly_payout_at": next_resource_payout_at,
            "land_attack_bonus_percent": (
                (territory.offense_level or 0)
                * int(rules["TERRITORY_LEVEL_BONUS_PERCENT"])
            ),
            "sea_attack_bonus_percent": (
                (territory.port_level or 0)
                * int(rules["PORT_LEVEL_BONUS_PERCENT"])
                + (territory.fleet_level or 0)
                * int(rules["FLEET_LEVEL_BONUS_PERCENT"])
            ) if territory.has_port else 0,
        }

    def get_upgrade_costs(
        self,
        db: Session,
        territory: Territory,
        upgrade_type: str,
        levels: int = 1,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> Dict[str, int]:
        rules = self._rule_values(db, rules)
        current = {
            "population": territory.development_level or 0,
            "fortifications": territory.fortifications or 0,
            "offense": territory.offense_level or 0,
            "port": territory.port_level or 0,
            "fleet": territory.fleet_level or 0,
            "naval": max(territory.port_level or 0, territory.fleet_level or 0),
        }[upgrade_type]
        if current + levels > int(rules["TERRITORY_MAX_UPGRADE_LEVEL"]):
            return {}
        if upgrade_type in {"port", "fleet", "naval"} and not territory.has_port:
            return {}
        if upgrade_type == "fleet" and current + levels > (territory.port_level or 0):
            return {}

        costs = {"gold": 0, "iron": 0, "wood": 0, "food": 0, "mithril": 0}
        for level in range(current, current + levels):
            if upgrade_type == "population":
                wealth_cost = ceil(
                    max(0, int(territory.resource_wealth or 0))
                    * int(rules["POPULATION_GOLD_COST_WEALTH_PERCENT"])
                    / 100
                )
                costs["gold"] += (
                    int(rules["POPULATION_BASE_GOLD_COST"])
                    + wealth_cost
                    + level * int(rules["POPULATION_GOLD_COST_PER_LEVEL"])
                )
                costs["wood"] += int(rules["POPULATION_BASE_WOOD_COST"]) + (
                    level // int(rules["POPULATION_WOOD_LEVEL_DIVISOR"])
                ) * int(rules["POPULATION_WOOD_COST_PER_LEVEL"])
            elif upgrade_type == "fortifications":
                costs["gold"] += int(rules["FORTIFICATION_BASE_GOLD_COST"]) + level * int(
                    rules["FORTIFICATION_GOLD_COST_PER_LEVEL"]
                )
                costs["iron"] += int(rules["FORTIFICATION_BASE_IRON_COST"]) + level * int(
                    rules["FORTIFICATION_IRON_COST_PER_LEVEL"]
                )
                if level >= int(rules["FORTIFICATION_MITHRIL_START_LEVEL"]):
                    costs["mithril"] += int(
                        rules["FORTIFICATION_MITHRIL_COST_PER_LEVEL"]
                    )
            elif upgrade_type == "offense":
                costs["gold"] += int(rules["OFFENSE_BASE_GOLD_COST"]) + level * int(
                    rules["OFFENSE_GOLD_COST_PER_LEVEL"]
                )
                costs["iron"] += int(rules["OFFENSE_BASE_IRON_COST"]) + level * int(
                    rules["OFFENSE_IRON_COST_PER_LEVEL"]
                )
                costs["food"] += int(rules["OFFENSE_BASE_FOOD_COST"]) + (
                    level // int(rules["OFFENSE_FOOD_LEVEL_DIVISOR"])
                ) * int(rules["OFFENSE_FOOD_COST_PER_STEP"])
            elif upgrade_type == "port":
                costs["gold"] += int(rules["PORT_BASE_GOLD_COST"]) + level * int(
                    rules["PORT_GOLD_COST_PER_LEVEL"]
                )
                costs["wood"] += int(rules["PORT_BASE_WOOD_COST"]) + (
                    level // int(rules["PORT_WOOD_LEVEL_DIVISOR"])
                ) * int(rules["PORT_WOOD_COST_PER_LEVEL"])
                costs["iron"] += int(rules["PORT_BASE_IRON_COST"]) + (
                    level // int(rules["PORT_IRON_LEVEL_DIVISOR"])
                ) * int(rules["PORT_IRON_COST_PER_STEP"])
            elif upgrade_type == "fleet":
                costs["gold"] += int(rules["FLEET_BASE_GOLD_COST"]) + level * int(
                    rules["FLEET_GOLD_COST_PER_LEVEL"]
                )
                costs["wood"] += int(rules["FLEET_BASE_WOOD_COST"]) + (
                    level // int(rules["FLEET_WOOD_LEVEL_DIVISOR"])
                ) * int(rules["FLEET_WOOD_COST_PER_LEVEL"])
                costs["iron"] += int(rules["FLEET_BASE_IRON_COST"]) + (
                    level // int(rules["FLEET_IRON_LEVEL_DIVISOR"])
                ) * int(rules["FLEET_IRON_COST_PER_LEVEL"])
                costs["food"] += int(rules["FLEET_BASE_FOOD_COST"]) + (
                    level // int(rules["FLEET_FOOD_LEVEL_DIVISOR"])
                ) * int(rules["FLEET_FOOD_COST_PER_STEP"])
            elif upgrade_type == "naval":
                # Единая морская инфраструктура заменяет две последовательные
                # покупки, сохраняя суммарную цену и баланс ресурсов сезона.
                costs["gold"] += (
                    int(rules["PORT_BASE_GOLD_COST"])
                    + level * int(rules["PORT_GOLD_COST_PER_LEVEL"])
                    + int(rules["FLEET_BASE_GOLD_COST"])
                    + level * int(rules["FLEET_GOLD_COST_PER_LEVEL"])
                )
                costs["wood"] += (
                    int(rules["PORT_BASE_WOOD_COST"])
                    + (level // int(rules["PORT_WOOD_LEVEL_DIVISOR"]))
                    * int(rules["PORT_WOOD_COST_PER_LEVEL"])
                    + int(rules["FLEET_BASE_WOOD_COST"])
                    + (level // int(rules["FLEET_WOOD_LEVEL_DIVISOR"]))
                    * int(rules["FLEET_WOOD_COST_PER_LEVEL"])
                )
                costs["iron"] += (
                    int(rules["PORT_BASE_IRON_COST"])
                    + (level // int(rules["PORT_IRON_LEVEL_DIVISOR"]))
                    * int(rules["PORT_IRON_COST_PER_STEP"])
                    + int(rules["FLEET_BASE_IRON_COST"])
                    + (level // int(rules["FLEET_IRON_LEVEL_DIVISOR"]))
                    * int(rules["FLEET_IRON_COST_PER_LEVEL"])
                )
                costs["food"] += int(rules["FLEET_BASE_FOOD_COST"]) + (
                    level // int(rules["FLEET_FOOD_LEVEL_DIVISOR"])
                ) * int(rules["FLEET_FOOD_COST_PER_STEP"])

        bonuses = self.get_clan_bonuses(db, territory.owner_clan_id) if territory.owner_clan_id else {}
        if upgrade_type == "population":
            costs["gold"] = ceil(costs["gold"] * (100 - bonuses.get("population_cost_percent", 0)) / 100)
        if upgrade_type == "fortifications":
            costs["gold"] = ceil(costs["gold"] * (100 - bonuses.get("fortification_cost_percent", 0)) / 100)
        return {resource: amount for resource, amount in costs.items() if amount > 0}

    def get_upgrade_quotes(
        self,
        db: Session,
        territory: Territory,
        *,
        rules: Mapping[str, int | float] | None = None,
    ) -> Dict[str, Dict[str, int]]:
        rules = self._rule_values(db, rules)
        upgrade_types = ["population", "fortifications", "offense"]
        if territory.has_port:
            upgrade_types.append("naval")
        return {
            upgrade_type: self.get_upgrade_costs(
                db,
                territory,
                upgrade_type,
                rules=rules,
            )
            for upgrade_type in upgrade_types
        }

    def get_clan_economy(self, db: Session, clan_id: int) -> Dict:
        rules = self.rule_service.get_active(db).values
        clan = db.query(Clan).filter(Clan.id == clan_id).first()
        if not clan:
            raise InsufficientPermissionsException("Клан не найден")
        self.settle_clan(db, clan, rules=rules)
        territories = [
            territory
            for territory in db.query(Territory)
            .filter(Territory.owner_clan_id == clan_id)
            .all()
            if not is_admin_territory_name(territory.name)
        ]
        for territory in territories:
            self.prepare_territory(db, territory, rules=rules)
        db.commit()
        return {
            "clan_id": clan.id,
            "gold": clan.gold,
            "iron": clan.iron,
            "wood": clan.wood,
            "food": clan.food,
            "mithril": clan.mithril,
            "base_influence": clan.base_influence,
            "territory_points": clan.territory_points,
            "territory_influence": max(
                0,
                (clan.territory_points or 0) - (clan.base_influence or 0),
            ),
            **get_clan_attack_status(
                clan.next_attack_at,
                cooldown_hours=int(rules["CLAN_ATTACK_COOLDOWN_HOURS"]),
            ),
            "daily_income": sum(self._daily_income(territory, rules) for territory in territories),
            "weekly_income": sum(self._daily_income(territory, rules) * 7 for territory in territories),
            "bonuses": self.get_clan_bonuses(db, clan_id),
            "territories": [
                {
                    "id": territory.id,
                    "name": territory.name,
                    **self.get_territory_economy(
                        territory,
                        db,
                        rules=rules,
                    ),
                }
                for territory in territories
            ],
        }

    def set_trader(
        self,
        db: Session,
        clan_id: int,
        member_user_id: int,
        is_trader: bool,
        current_user: User,
    ) -> ClanMember:
        clan, _ = require_clan_permission(
            db,
            clan_id,
            current_user,
            ClanPermission.MANAGE_ROLES,
        )
        member = db.query(ClanMember).filter(ClanMember.clan_id == clan_id, ClanMember.user_id == member_user_id).first()
        if not member:
            raise InsufficientPermissionsException("Игрок не состоит в этом клане")
        if clan.leader_id == member_user_id:
            raise InsufficientPermissionsException(
                "изменить роль главы клана без передачи лидерства"
            )
        member.is_trader = is_trader
        member.rank = "Торговец" if is_trader else "Воин"
        notification_service.create(
            db,
            user_id=member_user_id,
            notification_type="clan_trader_changed",
            title="Торговая роль изменена",
            message=(
                f"В клане «{clan.name}» вы "
                f"{'назначены Торговцем' if is_trader else 'больше не являетесь Торговцем'}."
            ),
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            commit=False,
        )
        db.commit()
        db.refresh(member)
        return member

    def _ensure_balances(self, clan: Clan) -> None:
        for resource in RESOURCE_FIELDS:
            if getattr(clan, resource, None) is None:
                setattr(clan, resource, 0)
        if clan.gold_income_remainder is None:
            clan.gold_income_remainder = 0.0
        if clan.gold == 0 and clan.resources:
            clan.gold = clan.resources
        clan.resources = clan.gold

    def _authorized_operator(
        self,
        db: Session,
        clan_id: int,
        current_user: User,
        permission: ClanPermission,
    ) -> Clan:
        self.ledger.lock_clans(db, [clan_id])
        clan, _ = require_clan_permission(db, clan_id, current_user, permission)
        return clan

    def upgrade_territory(
        self,
        db: Session,
        territory_id: int,
        upgrade_type: str,
        levels: int,
        current_user: User,
    ) -> Dict:
        require_legacy_economy(db)
        rules = self.rule_service.get_active(db).values
        max_levels_per_purchase = int(
            rules["TERRITORY_MAX_UPGRADE_LEVELS_PER_PURCHASE"]
        )
        if levels < 1 or levels > max_levels_per_purchase:
            raise InsufficientPermissionsException(
                f"За один раз можно купить от 1 до {max_levels_per_purchase} уровней"
            )
        territory = db.query(Territory).filter(Territory.id == territory_id).first()
        if not territory or not territory.owner_clan_id:
            raise InsufficientPermissionsException("Развивать можно только территорию своего клана")
        clan = self._authorized_operator(
            db,
            territory.owner_clan_id,
            current_user,
            ClanPermission.MANAGE_TERRITORY,
        )
        self.ledger.lock_clans(db, [clan.id])
        # Reload the level and owner after waiting for another purchase/capture.
        db.refresh(territory, with_for_update=True)
        if territory.owner_clan_id != clan.id:
            raise InsufficientPermissionsException("Владелец территории изменился")
        self.settle_clan(db, clan, rules=rules)
        self.prepare_territory(db, territory, rules=rules)
        if upgrade_type not in {"population", "fortifications", "offense", "port", "fleet", "naval"}:
            raise InsufficientPermissionsException("Неизвестный тип развития")
        if upgrade_type in {"port", "fleet", "naval"} and not territory.has_port:
            raise InsufficientPermissionsException(
                "Морские улучшения доступны только на территории с портом"
            )

        current = {
            "population": territory.development_level or 0,
            "fortifications": territory.fortifications or 0,
            "offense": territory.offense_level or 0,
            "port": territory.port_level or 0,
            "fleet": territory.fleet_level or 0,
            "naval": max(territory.port_level or 0, territory.fleet_level or 0),
        }[upgrade_type]
        if current + levels > int(rules["TERRITORY_MAX_UPGRADE_LEVEL"]):
            raise InsufficientPermissionsException("Достигнут максимальный уровень развития")
        if upgrade_type == "fleet" and current + levels > (territory.port_level or 0):
            raise InsufficientPermissionsException(
                "Сначала улучшите порт: уровень флота не может быть выше уровня порта"
            )
        costs = self.get_upgrade_costs(
            db,
            territory,
            upgrade_type,
            levels,
            rules=rules,
        )
        bonuses = self.get_clan_bonuses(db, clan.id)
        for resource, cost in costs.items():
            if getattr(clan, resource) < cost:
                raise InsufficientPermissionsException(f"Недостаточно ресурса: {resource}")
        operation_id = f"territory-upgrade:{territory.id}:{uuid4()}"
        for resource, cost in costs.items():
            self.ledger.apply_change(
                db,
                clan,
                resource=resource,
                amount=-cost,
                operation_id=operation_id,
                action="territory_upgrade",
                source_type="territory",
                source_id=territory.id,
                actor_user_id=current_user.id,
                details={"upgrade_type": upgrade_type, "levels": levels},
            )

        if upgrade_type == "population":
            territory.development_level = current + levels
            growth = (
                float(rules["POPULATION_BASE_GROWTH_PERCENT"])
                + bonuses.get("population_growth_percent", 0)
                / float(rules["POPULATION_GROWTH_RELIC_DIVISOR"])
            ) / 100
            territory.population = min(
                int(rules["POPULATION_MAXIMUM"]),
                int((territory.population or 0) * (1 + growth * levels))
                + int(rules["POPULATION_FLAT_GROWTH_PER_LEVEL"]) * levels,
            )
        elif upgrade_type == "fortifications":
            territory.fortifications = current + levels
        elif upgrade_type == "offense":
            territory.offense_level = current + levels
        elif upgrade_type == "port":
            territory.port_level = current + levels
        elif upgrade_type == "fleet":
            territory.fleet_level = current + levels
        else:
            territory.port_level = current + levels
            territory.fleet_level = current + levels
        territory.strategic_value = territory.calculate_strategic_value()
        clan.resources = clan.gold
        db.commit()
        db.refresh(territory)
        return {
            "territory": territory,
            "clan": clan,
            "cost": costs,
            "economy": self.get_territory_economy(
                territory,
                db,
                rules=rules,
            ),
        }

    def get_relic_bonuses(self, db: Session, clan_id: int) -> Dict[str, int]:
        bonuses: Dict[str, int] = {}
        owned = (
            db.query(ClanOwnedAsset)
            .filter(
                ClanOwnedAsset.clan_id == clan_id,
                ClanOwnedAsset.is_active.is_(True),
            )
            .all()
        )
        for item in owned:
            bonuses[item.asset.bonus_type] = bonuses.get(item.asset.bonus_type, 0) + (item.asset.bonus_value or 0) * (item.level or 1)
        return bonuses

    def get_clan_bonuses(self, db: Session, clan_id: int) -> Dict[str, int]:
        bonuses = self.get_relic_bonuses(db, clan_id)
        stronghold_power = sum(
            territory.stronghold_power or 0
            for territory in db.query(Territory).filter(Territory.owner_clan_id == clan_id).all()
        )
        if stronghold_power:
            bonuses["attack_power"] = bonuses.get("attack_power", 0) + stronghold_power
            bonuses["defense_power"] = bonuses.get("defense_power", 0) + stronghold_power
        return bonuses

    def list_assets(self, db: Session, clan_id: int) -> List[Dict]:
        rules = self.rule_service.get_active(db).values
        owned = {row.asset_id: row for row in db.query(ClanOwnedAsset).filter(ClanOwnedAsset.clan_id == clan_id).all()}
        clan = db.query(Clan).filter(Clan.id == clan_id).first()
        clan_influence = int(clan.territory_points or 0) if clan else 0
        result = []
        for asset in db.query(ClanAsset).filter(ClanAsset.is_available == True).all():
            level = owned[asset.id].level if asset.id in owned else 0
            next_level_available = level < (asset.max_level or 3)
            next_cost_multiplier = (
                self._asset_cost_multiplier(rules, level)
                if next_level_available
                else None
            )
            required_influence = self._required_asset_influence(asset, level + 1)
            result.append(
                {
                    "asset": asset,
                    "owned": asset.id in owned,
                    "level": level,
                    "active": bool(owned[asset.id].is_active) if asset.id in owned else False,
                    "loadout_locked_until": clan.relic_loadout_locked_until if clan else None,
                    "loadout_slots": RELIC_LOADOUT_SIZE,
                    "clan_influence": clan_influence,
                    "next_required_influence": required_influence,
                    "influence_unlocked": clan_influence >= required_influence,
                    "next_cost_multiplier": next_cost_multiplier,
                    "next_costs": (
                        self._asset_costs(asset, next_cost_multiplier)
                        if next_cost_multiplier is not None
                        else {}
                    ),
                }
            )
        return result

    def update_relic_loadout(
        self,
        db: Session,
        clan_id: int,
        asset_ids: List[int],
        current_user: User,
    ) -> Dict:
        require_legacy_economy(db)
        if len(asset_ids) > RELIC_LOADOUT_SIZE or len(asset_ids) != len(set(asset_ids)):
            raise InsufficientPermissionsException(
                f"Можно выбрать не более {RELIC_LOADOUT_SIZE} разных реликвий"
            )

        clan = self._authorized_operator(
            db,
            clan_id,
            current_user,
            ClanPermission.MANAGE_RELICS,
        )
        if not is_admin(current_user) and clan.leader_id != current_user.id:
            raise InsufficientPermissionsException(
                "Активный комплект реликвий может менять только глава клана"
            )

        clan = (
            db.query(Clan)
            .filter(Clan.id == clan_id)
            .with_for_update()
            .one()
        )
        owned_items = (
            db.query(ClanOwnedAsset)
            .filter(ClanOwnedAsset.clan_id == clan_id)
            .with_for_update()
            .all()
        )
        owned_by_asset_id = {item.asset_id: item for item in owned_items}
        missing_ids = sorted(set(asset_ids) - set(owned_by_asset_id))
        if missing_ids:
            raise InsufficientPermissionsException(
                "В комплект можно добавить только приобретённые кланом реликвии"
            )

        current_ids = {
            item.asset_id for item in owned_items if bool(item.is_active)
        }
        requested_ids = set(asset_ids)
        if current_ids == requested_ids:
            return {
                "asset_ids": sorted(current_ids),
                "locked_until": clan.relic_loadout_locked_until,
                "slots": RELIC_LOADOUT_SIZE,
            }

        now = utc_now()
        locked_until = as_utc(clan.relic_loadout_locked_until)
        if locked_until and locked_until > now:
            raise InsufficientPermissionsException(
                f"Комплект реликвий заблокирован до {locked_until.isoformat()}"
            )

        for item in owned_items:
            item.is_active = item.asset_id in requested_ids
        clan.relic_loadout_locked_until = now + RELIC_LOADOUT_COOLDOWN
        notification_service.create_for_clan(
            db,
            clan_id=clan_id,
            notification_type="clan_relic_loadout_changed",
            title="Комплект реликвий обновлён",
            message=(
                f"{current_user.username} изменил активный комплект: "
                f"{len(requested_ids)} из {RELIC_LOADOUT_SIZE} слотов."
            ),
            link_url=f"/clans/{clan_id}",
            entity_type="clan",
            entity_id=clan_id,
            excluded_user_id=current_user.id,
            commit=False,
        )
        db.commit()
        return {
            "asset_ids": sorted(requested_ids),
            "locked_until": clan.relic_loadout_locked_until,
            "slots": RELIC_LOADOUT_SIZE,
        }

    @staticmethod
    def _required_asset_influence(asset: ClanAsset, level: int) -> int:
        return int(
            {
                1: asset.required_influence_level_1,
                2: asset.required_influence_level_2,
                3: asset.required_influence_level_3,
            }.get(level, asset.required_influence_level_3)
            or 0
        )

    @staticmethod
    def _asset_cost_multiplier(rules, current_level: int) -> int:
        return (
            int(rules["RELIC_LEVEL_1_COST_MULTIPLIER"]),
            int(rules["RELIC_LEVEL_2_COST_MULTIPLIER"]),
            int(rules["RELIC_LEVEL_3_COST_MULTIPLIER"]),
        )[min(current_level, 2)]

    @staticmethod
    def _asset_costs(asset: ClanAsset, multiplier: int) -> Dict[str, int]:
        return {
            resource: int(getattr(asset, f"{resource}_cost") or 0) * multiplier
            for resource in ("gold", "iron", "wood", "food", "mithril")
        }

    def purchase_asset(
        self,
        db: Session,
        clan_id: int,
        asset_id: int,
        current_user: User,
    ) -> ClanOwnedAsset:
        require_legacy_economy(db)
        rules = self.rule_service.get_active(db).values
        clan = self._authorized_operator(db, clan_id, current_user, ClanPermission.MANAGE_RELICS)
        self.settle_clan(db, clan, rules=rules)
        asset = db.query(ClanAsset).filter(ClanAsset.id == asset_id, ClanAsset.is_available == True).first()
        if not asset:
            raise InsufficientPermissionsException("Предмет клана не найден")
        owned = db.query(ClanOwnedAsset).filter(ClanOwnedAsset.clan_id == clan_id, ClanOwnedAsset.asset_id == asset_id).populate_existing().first()
        current_level = owned.level if owned else 0
        if current_level >= (asset.max_level or 3):
            raise InsufficientPermissionsException("Уникальный предмет уже улучшен до максимального уровня")
        required_influence = self._required_asset_influence(
            asset,
            current_level + 1,
        )
        if int(clan.territory_points or 0) < required_influence:
            raise InsufficientPermissionsException(
                f"Для уровня {current_level + 1} нужно {required_influence} влияния; "
                f"у клана сейчас {int(clan.territory_points or 0)}"
            )
        multiplier = self._asset_cost_multiplier(rules, current_level)
        costs = self._asset_costs(asset, multiplier)
        for resource, cost in costs.items():
            if getattr(clan, resource) < cost:
                raise InsufficientPermissionsException(f"Недостаточно ресурса: {resource}")
        operation_id = f"relic-purchase:{clan_id}:{asset_id}:{current_level + 1}:{uuid4()}"
        for resource, cost in costs.items():
            if cost:
                self.ledger.apply_change(
                    db,
                    clan,
                    resource=resource,
                    amount=-cost,
                    operation_id=operation_id,
                    action="relic_purchase",
                    source_type="clan_asset",
                    source_id=asset_id,
                    actor_user_id=current_user.id,
                    details={"level": current_level + 1},
                )
        clan.resources = clan.gold
        if owned:
            owned.level = current_level + 1
            owned.purchased_by = current_user.id
        else:
            owned = ClanOwnedAsset(clan_id=clan_id, asset_id=asset_id, purchased_by=current_user.id, level=1)
            db.add(owned)
        db.flush()
        notification_service.create_for_clan(
            db,
            clan_id=clan.id,
            notification_type="clan_relic_purchased",
            title="Реликвия приобретена",
            message=(
                f"{current_user.username} приобрёл «{asset.name}» "
                f"уровня {current_level + 1}."
            ),
            link_url=f"/clans/{clan.id}",
            entity_type="clan_asset",
            entity_id=asset.id,
            excluded_user_id=current_user.id,
            commit=False,
        )
        self.influence.recalculate(
            db,
            clan.id,
            operation_id=f"relic-influence:{clan.id}:{asset.id}:{current_level + 1}",
            action="relic_influence_recalculated",
            source_type="clan_asset",
            source_id=asset.id,
            actor_user_id=current_user.id,
            details={"level": current_level + 1},
        )
        db.commit()
        db.refresh(owned)
        return owned

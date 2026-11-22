from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
from collections.abc import Mapping
from typing import Any

from app.services.balance_simulation_catalog import (
    BalanceSimulationCatalog,
    RelicSimulationInput,
    TerritorySimulationInput,
)
from app.services.clan_economy_service import ClanEconomyService
from app.services.clan_level_service import ClanLevelService
from app.services.market_service import ClanMarketService


RESOURCE_NAMES = ("gold", "iron", "wood", "food", "mithril")
PACE_DAYS = {"slow": 12, "normal": 8, "aggressive": 4}
STRATEGIES = ("economic", "military", "balanced")
PROFILE_CONFIG = {
    "new": {"territories": 1, "level": 1, "needs_port": False, "needs_stronghold": False},
    "growing": {"territories": 3, "level": 2, "needs_port": False, "needs_stronghold": False},
    "developed": {"territories": 5, "level": 3, "needs_port": True, "needs_stronghold": False},
    "large": {"territories": 8, "level": 4, "needs_port": True, "needs_stronghold": True},
}
REPORT_FORMAT_VERSION = 1


@dataclass
class SimulatedTerritory:
    source: TerritorySimulationInput
    captured_hour: int
    development_level: int = 0
    fortifications: int = 0
    offense_level: int = 0
    port_level: int = 0
    fleet_level: int = 0
    population: int = 0

    def __post_init__(self) -> None:
        self.population = int(self.source.population)

    @property
    def id(self) -> int:
        return self.source.id

    @property
    def resource_wealth(self) -> int:
        return self.source.resource_wealth

    @property
    def resource_type(self) -> str:
        return self.source.resource_type

    @property
    def resource_output(self) -> int:
        return self.source.resource_output

    @property
    def secondary_resource_type(self) -> str | None:
        return self.source.secondary_resource_type

    @property
    def is_great_stronghold(self) -> bool:
        return self.source.is_great_stronghold

    @property
    def has_port(self) -> bool:
        return self.source.has_port

    @property
    def prosperity_score(self) -> int:
        return self.source.prosperity_score

    def total_levels(self) -> int:
        levels = self.development_level + self.fortifications + self.offense_level
        if self.has_port:
            levels += max(self.port_level, self.fleet_level)
        return levels


@dataclass
class SimulationState:
    resources: dict[str, float]
    base_influence: int
    active_members: int
    territories: list[SimulatedTerritory]
    capture_queue: list[TerritorySimulationInput]
    relic_levels: dict[int, int] = field(default_factory=dict)
    accumulated: dict[str, float] = field(
        default_factory=lambda: {resource: 0.0 for resource in RESOURCE_NAMES}
    )
    spent: dict[str, float] = field(
        default_factory=lambda: {resource: 0.0 for resource in RESOURCE_NAMES}
    )
    gold_remainder: float = 0.0
    purchases: list[dict[str, Any]] = field(default_factory=list)
    capture_events: list[dict[str, Any]] = field(default_factory=list)
    capture_delays: list[dict[str, Any]] = field(default_factory=list)
    blocked_hours: dict[str, int] = field(default_factory=dict)
    current_goal: dict[str, Any] | None = None
    goal_started_hour: int = 0
    balanced_cycle: int = 0
    next_capture_hour: int = 0
    next_attack_hour: int = 0
    stronghold_access: dict[int, dict[str, float | int | str | None]] = field(default_factory=dict)


def _spread(items: list[TerritorySimulationInput], count: int) -> list[TerritorySimulationInput]:
    if count <= 0:
        return []
    if len(items) < count:
        return []
    if count == 1:
        return [items[len(items) // 2]]
    indexes = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    selected: list[TerritorySimulationInput] = []
    for index in indexes:
        candidate = items[index]
        if candidate not in selected:
            selected.append(candidate)
    if len(selected) < count:
        selected.extend(item for item in items if item not in selected)
    return selected[:count]


def _median(items: list[TerritorySimulationInput]) -> TerritorySimulationInput | None:
    if not items:
        return None
    ordered = sorted(items, key=lambda item: (item.resource_wealth, item.id))
    return ordered[len(ordered) // 2]


def _profile_members(rules: Mapping[str, int | float], level: int) -> int:
    if level <= 1:
        return max(1, int(rules["CLAN_ATTACK_SQUAD_MIN_MEMBERS"]))
    return int(rules[f"CLAN_LEVEL_{level}_ACTIVE_MEMBERS"])


def build_profile_portfolios(
    catalog: BalanceSimulationCatalog,
) -> tuple[dict[str, tuple[TerritorySimulationInput, ...]], list[dict[str, str]]]:
    ordinary = sorted(
        (territory for territory in catalog.territories if not territory.is_great_stronghold),
        key=lambda item: (item.resource_wealth, item.id),
    )
    ports = [territory for territory in ordinary if territory.has_port]
    strongholds = sorted(
        (territory for territory in catalog.territories if territory.is_great_stronghold),
        key=lambda item: (item.resource_wealth, item.id),
    )
    portfolios: dict[str, tuple[TerritorySimulationInput, ...]] = {}
    unavailable: list[dict[str, str]] = []

    for name, config in PROFILE_CONFIG.items():
        required_count = int(config["territories"])
        selected: list[TerritorySimulationInput] = []
        if config["needs_port"]:
            port = _median(ports)
            if port is None:
                unavailable.append({"profile": name, "reason": "no_playable_port"})
                continue
            selected.append(port)
        if config["needs_stronghold"]:
            stronghold = _median(strongholds)
            if stronghold is None:
                unavailable.append({"profile": name, "reason": "no_playable_great_stronghold"})
                continue
            selected.append(stronghold)

        remaining = [territory for territory in ordinary if territory not in selected]
        selected.extend(_spread(remaining, required_count - len(selected)))
        if len(selected) != required_count:
            unavailable.append({"profile": name, "reason": "not_enough_playable_territories"})
            continue
        portfolios[name] = tuple(sorted(selected, key=lambda item: item.id))

    return portfolios, unavailable


def calculate_upgrade_cost(
    territory: SimulatedTerritory,
    upgrade_type: str,
    rules: Mapping[str, int | float],
    bonuses: Mapping[str, int],
) -> dict[str, int]:
    current = {
        "population": territory.development_level,
        "fortifications": territory.fortifications,
        "offense": territory.offense_level,
        "port": territory.port_level,
        "fleet": territory.fleet_level,
        "naval": max(territory.port_level, territory.fleet_level),
    }[upgrade_type]
    if current + 1 > int(rules["TERRITORY_MAX_UPGRADE_LEVEL"]):
        return {}
    if upgrade_type in {"port", "fleet", "naval"} and not territory.has_port:
        return {}
    if upgrade_type == "fleet" and current + 1 > territory.port_level:
        return {}

    level = current
    costs = {resource: 0 for resource in RESOURCE_NAMES}
    if upgrade_type == "population":
        wealth_cost = ceil(
            max(0, territory.resource_wealth)
            * int(rules["POPULATION_GOLD_COST_WEALTH_PERCENT"])
            / 100
        )
        costs["gold"] = (
            int(rules["POPULATION_BASE_GOLD_COST"])
            + wealth_cost
            + level * int(rules["POPULATION_GOLD_COST_PER_LEVEL"])
        )
        costs["wood"] = int(rules["POPULATION_BASE_WOOD_COST"]) + (
            level // int(rules["POPULATION_WOOD_LEVEL_DIVISOR"])
        ) * int(rules["POPULATION_WOOD_COST_PER_LEVEL"])
        costs["gold"] = ceil(
            costs["gold"]
            * (100 - int(bonuses.get("population_cost_percent", 0)))
            / 100
        )
    elif upgrade_type == "fortifications":
        costs["gold"] = int(rules["FORTIFICATION_BASE_GOLD_COST"]) + level * int(
            rules["FORTIFICATION_GOLD_COST_PER_LEVEL"]
        )
        costs["iron"] = int(rules["FORTIFICATION_BASE_IRON_COST"]) + level * int(
            rules["FORTIFICATION_IRON_COST_PER_LEVEL"]
        )
        if level >= int(rules["FORTIFICATION_MITHRIL_START_LEVEL"]):
            costs["mithril"] = int(rules["FORTIFICATION_MITHRIL_COST_PER_LEVEL"])
        costs["gold"] = ceil(
            costs["gold"]
            * (100 - int(bonuses.get("fortification_cost_percent", 0)))
            / 100
        )
    elif upgrade_type == "offense":
        costs["gold"] = int(rules["OFFENSE_BASE_GOLD_COST"]) + level * int(
            rules["OFFENSE_GOLD_COST_PER_LEVEL"]
        )
        costs["iron"] = int(rules["OFFENSE_BASE_IRON_COST"]) + level * int(
            rules["OFFENSE_IRON_COST_PER_LEVEL"]
        )
        costs["food"] = int(rules["OFFENSE_BASE_FOOD_COST"]) + (
            level // int(rules["OFFENSE_FOOD_LEVEL_DIVISOR"])
        ) * int(rules["OFFENSE_FOOD_COST_PER_STEP"])
    elif upgrade_type == "port":
        costs["gold"] = int(rules["PORT_BASE_GOLD_COST"]) + level * int(
            rules["PORT_GOLD_COST_PER_LEVEL"]
        )
        costs["wood"] = int(rules["PORT_BASE_WOOD_COST"]) + (
            level // int(rules["PORT_WOOD_LEVEL_DIVISOR"])
        ) * int(rules["PORT_WOOD_COST_PER_LEVEL"])
        costs["iron"] = int(rules["PORT_BASE_IRON_COST"]) + (
            level // int(rules["PORT_IRON_LEVEL_DIVISOR"])
        ) * int(rules["PORT_IRON_COST_PER_STEP"])
    elif upgrade_type == "fleet":
        costs["gold"] = int(rules["FLEET_BASE_GOLD_COST"]) + level * int(
            rules["FLEET_GOLD_COST_PER_LEVEL"]
        )
        costs["wood"] = int(rules["FLEET_BASE_WOOD_COST"]) + (
            level // int(rules["FLEET_WOOD_LEVEL_DIVISOR"])
        ) * int(rules["FLEET_WOOD_COST_PER_LEVEL"])
        costs["iron"] = int(rules["FLEET_BASE_IRON_COST"]) + (
            level // int(rules["FLEET_IRON_LEVEL_DIVISOR"])
        ) * int(rules["FLEET_IRON_COST_PER_LEVEL"])
        costs["food"] = int(rules["FLEET_BASE_FOOD_COST"]) + (
            level // int(rules["FLEET_FOOD_LEVEL_DIVISOR"])
        ) * int(rules["FLEET_FOOD_COST_PER_STEP"])
    elif upgrade_type == "naval":
        port_cost = calculate_upgrade_cost(territory, "port", rules, bonuses)
        fleet_level = territory.fleet_level
        port_level = territory.port_level
        territory.port_level = max(port_level, fleet_level, level + 1)
        territory.fleet_level = level
        try:
            fleet_cost = calculate_upgrade_cost(territory, "fleet", rules, bonuses)
        finally:
            territory.port_level = port_level
            territory.fleet_level = fleet_level
        for resource in RESOURCE_NAMES:
            costs[resource] = port_cost.get(resource, 0) + fleet_cost.get(resource, 0)
    else:
        raise ValueError(f"Unknown upgrade type: {upgrade_type}")
    return {resource: value for resource, value in costs.items() if value > 0}


def calculate_relic_cost(
    relic: RelicSimulationInput,
    next_level: int,
    rules: Mapping[str, int | float],
) -> dict[str, int]:
    multiplier = int(rules[f"RELIC_LEVEL_{next_level}_COST_MULTIPLIER"])
    return {
        resource: int(relic.costs[resource]) * multiplier
        for resource in RESOURCE_NAMES
        if int(relic.costs[resource]) > 0
    }


class BalanceSimulationService:
    def run(self, catalog: BalanceSimulationCatalog, *, days: int = 30) -> dict[str, Any]:
        if days not in {7, 14, 30}:
            raise ValueError("Simulation horizon must be one of 7, 14 or 30 days.")
        portfolios, unavailable_profiles = build_profile_portfolios(catalog)
        checkpoints = [value for value in (7, 14, 30) if value <= days]
        scenarios: list[dict[str, Any]] = []
        for profile_name in PROFILE_CONFIG:
            if profile_name not in portfolios:
                continue
            for pace_name in PACE_DAYS:
                for strategy_name in STRATEGIES:
                    scenarios.append(
                        self._run_scenario(
                            catalog,
                            profile_name=profile_name,
                            initial_territories=portfolios[profile_name],
                            pace_name=pace_name,
                            strategy_name=strategy_name,
                            days=days,
                            checkpoints=checkpoints,
                        )
                    )

        signals = self._signals(catalog, scenarios, days)
        return {
            "report_format_version": REPORT_FORMAT_VERSION,
            "rule_set": {
                "id": catalog.rule_set_id,
                "version": catalog.rule_version,
            },
            "horizon_days": days,
            "checkpoints": checkpoints,
            "inputs": self._serialize_inputs(catalog, portfolios),
            "unavailable_profiles": unavailable_profiles,
            "scenarios": scenarios,
            "signals": signals,
            "recommendations": self._recommendations(signals),
            "limitations": [
                "War winners, match activity and Elo are not predicted.",
                "Great-stronghold geography is not simulated.",
                "Market exchanges are diagnostic and do not change balances.",
                "Results validate current rules and do not replace a closed beta season.",
            ],
        }

    @staticmethod
    def _serialize_inputs(
        catalog: BalanceSimulationCatalog,
        portfolios: Mapping[str, tuple[TerritorySimulationInput, ...]],
    ) -> dict[str, Any]:
        return {
            "starting_resources": dict(catalog.starting_resources),
            "rules": dict(catalog.rules),
            "territories": [asdict(territory) for territory in catalog.territories],
            "relics": [
                {
                    "id": relic.id,
                    "key": relic.key,
                    "name": relic.name,
                    "bonus_type": relic.bonus_type,
                    "bonus_value": relic.bonus_value,
                    "costs": dict(relic.costs),
                    "required_influence": list(relic.required_influence),
                    "max_level": relic.max_level,
                }
                for relic in catalog.relics
            ],
            "profiles": {
                name: {
                    "territory_ids": [territory.id for territory in territory_rows],
                    "active_members": _profile_members(
                        catalog.rules,
                        int(PROFILE_CONFIG[name]["level"]),
                    ),
                }
                for name, territory_rows in portfolios.items()
            },
            "paces_days_per_capture": dict(PACE_DAYS),
            "strategies": list(STRATEGIES),
        }

    def _run_scenario(
        self,
        catalog: BalanceSimulationCatalog,
        *,
        profile_name: str,
        initial_territories: tuple[TerritorySimulationInput, ...],
        pace_name: str,
        strategy_name: str,
        days: int,
        checkpoints: list[int],
    ) -> dict[str, Any]:
        owned_ids = {territory.id for territory in initial_territories}
        capture_interval_hours = self._capture_interval_hours(
            catalog.rules,
            PACE_DAYS[pace_name],
        )
        state = SimulationState(
            resources={
                resource: float(catalog.starting_resources[resource])
                for resource in RESOURCE_NAMES
            },
            base_influence=int(catalog.starting_resources["influence"]),
            active_members=_profile_members(
                catalog.rules,
                int(PROFILE_CONFIG[profile_name]["level"]),
            ),
            territories=[
                SimulatedTerritory(territory, captured_hour=0)
                for territory in initial_territories
            ],
            capture_queue=sorted(
                (territory for territory in catalog.territories if territory.id not in owned_ids),
                key=lambda item: (
                    item.is_great_stronghold,
                    item.required_territories,
                    item.required_influence,
                    item.resource_wealth,
                    item.id,
                ),
            ),
            next_capture_hour=capture_interval_hours,
        )
        state.stronghold_access = {
            territory.id: {
                "territory_id": territory.id,
                "territory_name": territory.name,
                "required_territories": territory.required_territories,
                "required_influence": territory.required_influence,
                "territory_day": None,
                "influence_day": None,
                "both_day": None,
                "obstacle": None,
                "daily_resources_after_capture": [
                    territory.resource_type,
                    territory.secondary_resource_type,
                ],
            }
            for territory in catalog.territories
            if territory.is_great_stronghold
        }
        snapshots: dict[str, dict[str, Any]] = {}
        total_hours = days * 24

        for hour in range(total_hours + 1):
            if hour and hour % int(catalog.rules["ECONOMY_TICK_HOURS"]) == 0:
                self._accrue_gold(state, catalog.rules)
            self._accrue_rare_resources(state, catalog.rules, hour)
            self._attempt_capture(state, catalog.rules, hour, capture_interval_hours)
            self._update_stronghold_access(state, hour)
            self._attempt_purchase(state, catalog, strategy_name, hour)
            if hour and hour % 24 == 0 and hour // 24 in checkpoints:
                snapshots[str(hour // 24)] = self._snapshot(state, catalog.rules)

        for access in state.stronghold_access.values():
            if access["both_day"] is None:
                missing = []
                if access["territory_day"] is None:
                    missing.append("territories")
                if access["influence_day"] is None:
                    missing.append("influence")
                access["obstacle"] = ",".join(missing) or "geography_not_simulated"

        final_snapshot = self._snapshot(state, catalog.rules)
        return {
            "id": f"{profile_name}:{pace_name}:{strategy_name}",
            "profile": profile_name,
            "pace": pace_name,
            "strategy": strategy_name,
            "parameters": {
                "capture_interval_days": PACE_DAYS[pace_name],
                "war_duration_hours": int(catalog.rules["WAR_DURATION_HOURS"]),
                "attack_cooldown_hours": int(catalog.rules["CLAN_ATTACK_COOLDOWN_HOURS"]),
                "active_members": state.active_members,
            },
            "checkpoints": snapshots,
            "purchases": state.purchases,
            "captures": state.capture_events,
            "capture_delays": state.capture_delays,
            "great_strongholds": list(state.stronghold_access.values()),
            "market_diagnostic": self._market_diagnostic(state, catalog.rules),
            "final": final_snapshot,
        }

    def run_custom(
        self,
        catalog: BalanceSimulationCatalog,
        *,
        days: int,
        starting_territory_ids: list[int],
        active_members: int,
        capture_interval_days: int,
        strategy_name: str,
        automatic_captures: bool = True,
    ) -> dict[str, Any]:
        """Run one editable, geography-aware scenario without changing live data."""
        territory_by_id = {territory.id: territory for territory in catalog.territories}
        initial_territories = tuple(
            territory_by_id[territory_id]
            for territory_id in dict.fromkeys(starting_territory_ids)
            if territory_id in territory_by_id
        )
        if not initial_territories:
            raise LookupError("Select at least one playable starting territory.")

        owned_ids = {territory.id for territory in initial_territories}
        capture_interval_hours = self._capture_interval_hours(
            catalog.rules,
            capture_interval_days,
        )
        state = SimulationState(
            resources={
                resource: float(catalog.starting_resources[resource])
                for resource in RESOURCE_NAMES
            },
            base_influence=int(catalog.starting_resources["influence"]),
            active_members=active_members,
            territories=[
                SimulatedTerritory(territory, captured_hour=0)
                for territory in initial_territories
            ],
            capture_queue=sorted(
                (territory for territory in catalog.territories if territory.id not in owned_ids),
                key=lambda item: (
                    item.is_great_stronghold,
                    item.required_territories,
                    item.required_influence,
                    -item.prosperity_score,
                    item.id,
                ),
            ) if automatic_captures else [],
            next_capture_hour=capture_interval_hours,
        )
        state.stronghold_access = {
            territory.id: {
                "territory_id": territory.id,
                "territory_name": territory.name,
                "required_territories": territory.required_territories,
                "required_influence": territory.required_influence,
                "territory_day": None,
                "influence_day": None,
                "both_day": None,
                "obstacle": None,
                "daily_resources_after_capture": [
                    territory.resource_type,
                    territory.secondary_resource_type,
                ],
            }
            for territory in catalog.territories
            if territory.is_great_stronghold
        }

        timeline: list[dict[str, Any]] = [
            {"day": 0, **self._snapshot(state, catalog.rules)}
        ]
        total_hours = days * 24
        for hour in range(1, total_hours + 1):
            if hour % int(catalog.rules["ECONOMY_TICK_HOURS"]) == 0:
                self._accrue_gold(state, catalog.rules)
            self._accrue_rare_resources(state, catalog.rules, hour)
            self._attempt_capture(
                state,
                catalog.rules,
                hour,
                capture_interval_hours,
                require_adjacent=True,
            )
            self._update_stronghold_access(state, hour)
            self._attempt_purchase(state, catalog, strategy_name, hour)
            if hour % 24 == 0:
                timeline.append({
                    "day": hour // 24,
                    **self._snapshot(state, catalog.rules),
                })

        final_snapshot = self._snapshot(state, catalog.rules)
        return {
            "parameters": {
                "days": days,
                "active_members": active_members,
                "capture_interval_days": capture_interval_days,
                "strategy": strategy_name,
                "automatic_captures": automatic_captures,
            },
            "initial_territory_ids": sorted(owned_ids),
            "final_territory_ids": sorted(territory.id for territory in state.territories),
            "captured_territory_ids": [event["territory_id"] for event in state.capture_events],
            "timeline": timeline,
            "purchases": state.purchases,
            "captures": state.capture_events,
            "capture_delays": state.capture_delays,
            "market_diagnostic": self._market_diagnostic(state, catalog.rules),
            "final": final_snapshot,
        }

    @staticmethod
    def _capture_interval_hours(
        rules: Mapping[str, int | float],
        pace_days: int,
    ) -> int:
        return max(
            pace_days * 24,
            int(rules["WAR_DURATION_HOURS"]),
        )

    @staticmethod
    def _bonuses(state: SimulationState, catalog: BalanceSimulationCatalog) -> dict[str, int]:
        relic_by_id = {relic.id: relic for relic in catalog.relics}
        bonuses: dict[str, int] = {}
        for relic_id, level in state.relic_levels.items():
            relic = relic_by_id[relic_id]
            bonuses[relic.bonus_type] = (
                bonuses.get(relic.bonus_type, 0) + relic.bonus_value * level
            )
        return bonuses

    @staticmethod
    def _influence(state: SimulationState, bonuses: Mapping[str, int]) -> int:
        territory_influence = sum(
            territory.source.influence_value for territory in state.territories
        )
        territory_bonus = int(
            territory_influence
            * (100 + int(bonuses.get("territory_points_percent", 0)))
            / 100
        )
        return max(0, state.base_influence + territory_bonus)

    @staticmethod
    def _level_status(
        state: SimulationState,
        rules: Mapping[str, int | float],
        influence: int,
    ) -> tuple[int, int]:
        selected = ClanLevelService.thresholds(rules)[0]
        for threshold in reversed(ClanLevelService.thresholds(rules)):
            if (
                state.active_members >= threshold.active_members
                and len(state.territories) >= threshold.territories
                and influence >= threshold.influence
            ):
                selected = threshold
                break
        return selected.level, selected.attack_capacity

    @staticmethod
    def _accrue_gold(
        state: SimulationState,
        rules: Mapping[str, int | float],
    ) -> None:
        bonuses = BalanceSimulationService._state_bonuses_without_catalog(state)
        accrued = state.gold_remainder
        for territory in state.territories:
            accrued += (
                ClanEconomyService._daily_income(territory, rules)
                * (100 + bonuses.get("gold_income_percent", 0))
                / 100
            )
        payout = int(accrued + 1e-9)
        state.gold_remainder = max(0.0, round(accrued - payout, 9))
        state.resources["gold"] += payout
        state.accumulated["gold"] += payout

    @staticmethod
    def _state_bonuses_without_catalog(state: SimulationState) -> dict[str, int]:
        # The populated cache is attached by _attempt_purchase/_snapshot before
        # income is evaluated. Keeping it on the state avoids database access.
        return getattr(state, "_bonuses_cache", {})

    @staticmethod
    def _accrue_rare_resources(
        state: SimulationState,
        rules: Mapping[str, int | float],
        hour: int,
    ) -> None:
        ready_hours = int(rules["TERRITORY_RESOURCE_READY_HOURS"])
        payout_hours = int(rules["TERRITORY_RESOURCE_PAYOUT_HOURS"])
        bonuses = BalanceSimulationService._state_bonuses_without_catalog(state)
        for territory in state.territories:
            first_payout = territory.captured_hour + ready_hours
            if hour < first_payout or (hour - first_payout) % payout_hours:
                continue
            for resource, amount in ClanEconomyService._daily_resource_rewards(
                territory,
                bonuses,
            ):
                if resource not in state.resources:
                    continue
                state.resources[resource] += amount
                state.accumulated[resource] += amount

    def _attempt_capture(
        self,
        state: SimulationState,
        rules: Mapping[str, int | float],
        hour: int,
        capture_interval_hours: int,
        require_adjacent: bool = False,
    ) -> None:
        if hour < state.next_capture_hour or not state.capture_queue:
            return
        bonuses = self._state_bonuses_without_catalog(state)
        influence = self._influence(state, bonuses)
        _, attack_capacity = self._level_status(state, rules, influence)
        if hour < state.next_attack_hour:
            self._record_capture_delay(state, hour, "attack_cooldown")
            return
        if attack_capacity < 1:
            self._record_capture_delay(state, hour, "attack_capacity")
            return

        owned_ids = {territory.id for territory in state.territories}
        candidate = next(
            (
                territory
                for territory in state.capture_queue
                if influence >= territory.required_influence
                and len(state.territories) >= territory.required_territories
                and (
                    not require_adjacent
                    or bool(owned_ids.intersection(territory.adjacent_territory_ids))
                )
            ),
            None,
        )
        if candidate is None:
            first = state.capture_queue[0]
            if require_adjacent and not any(
                owned_ids.intersection(territory.adjacent_territory_ids)
                for territory in state.capture_queue
            ):
                reason = "geography_blocked"
            elif len(state.territories) < first.required_territories:
                reason = "territory_requirement"
            else:
                reason = "influence_requirement"
            self._record_capture_delay(state, hour, reason, first.id)
            return

        state.capture_queue.remove(candidate)
        state.territories.append(SimulatedTerritory(candidate, captured_hour=hour))
        state.capture_events.append({
            "hour": hour,
            "day": round(hour / 24, 2),
            "territory_id": candidate.id,
            "territory_name": candidate.name,
        })
        state.next_capture_hour = hour + capture_interval_hours
        state.next_attack_hour = hour + int(rules["CLAN_ATTACK_COOLDOWN_HOURS"])

    @staticmethod
    def _record_capture_delay(
        state: SimulationState,
        hour: int,
        reason: str,
        territory_id: int | None = None,
    ) -> None:
        last = state.capture_delays[-1] if state.capture_delays else None
        if last and last["reason"] == reason and hour - int(last["hour"]) < 24:
            return
        state.capture_delays.append({
            "hour": hour,
            "day": round(hour / 24, 2),
            "reason": reason,
            "territory_id": territory_id,
        })

    def _update_stronghold_access(self, state: SimulationState, hour: int) -> None:
        bonuses = self._state_bonuses_without_catalog(state)
        influence = self._influence(state, bonuses)
        for access in state.stronghold_access.values():
            if (
                access["territory_day"] is None
                and len(state.territories) >= int(access["required_territories"])
            ):
                access["territory_day"] = round(hour / 24, 2)
            if (
                access["influence_day"] is None
                and influence >= int(access["required_influence"])
            ):
                access["influence_day"] = round(hour / 24, 2)
            if (
                access["both_day"] is None
                and access["territory_day"] is not None
                and access["influence_day"] is not None
            ):
                access["both_day"] = max(
                    float(access["territory_day"]),
                    float(access["influence_day"]),
                )

    def _attempt_purchase(
        self,
        state: SimulationState,
        catalog: BalanceSimulationCatalog,
        strategy_name: str,
        hour: int,
    ) -> None:
        bonuses = self._bonuses(state, catalog)
        setattr(state, "_bonuses_cache", bonuses)
        if state.current_goal is None:
            state.current_goal = self._next_goal(state, catalog, strategy_name)
            state.goal_started_hour = hour
        goal = state.current_goal
        if goal is None:
            return

        influence = self._influence(state, bonuses)
        if goal["kind"] == "upgrade":
            territory = next(
                item for item in state.territories if item.id == goal["territory_id"]
            )
            costs = calculate_upgrade_cost(
                territory,
                goal["upgrade_type"],
                catalog.rules,
                bonuses,
            )
            required_influence = 0
        else:
            relic = next(item for item in catalog.relics if item.id == goal["relic_id"])
            next_level = state.relic_levels.get(relic.id, 0) + 1
            costs = calculate_relic_cost(relic, next_level, catalog.rules)
            required_influence = relic.required_influence[next_level - 1]

        blocker = self._blocking_resource(state, costs, influence, required_influence)
        if blocker is not None:
            state.blocked_hours[blocker] = state.blocked_hours.get(blocker, 0) + 1
            return

        for resource, cost in costs.items():
            state.resources[resource] -= cost
            state.spent[resource] += cost
        if goal["kind"] == "upgrade":
            self._apply_upgrade(territory, goal["upgrade_type"], catalog.rules, bonuses)
            purchased_level = {
                "population": territory.development_level,
                "fortifications": territory.fortifications,
                "offense": territory.offense_level,
                "port": territory.port_level,
                "fleet": territory.fleet_level,
                "naval": max(territory.port_level, territory.fleet_level),
            }[goal["upgrade_type"]]
            label = f"{goal['upgrade_type']}:{territory.source.name}"
        else:
            next_level = state.relic_levels.get(relic.id, 0) + 1
            state.relic_levels[relic.id] = next_level
            purchased_level = next_level
            label = f"relic:{relic.key}"

        state.purchases.append({
            "hour": hour,
            "day": round(hour / 24, 2),
            "goal": label,
            "level": purchased_level,
            "cost": costs,
            "wait_hours": hour - state.goal_started_hour,
        })
        if strategy_name == "balanced":
            state.balanced_cycle = (state.balanced_cycle + 1) % 5
        state.current_goal = None
        setattr(state, "_bonuses_cache", self._bonuses(state, catalog))

    @staticmethod
    def _blocking_resource(
        state: SimulationState,
        costs: Mapping[str, int],
        influence: int,
        required_influence: int,
    ) -> str | None:
        shortages = [
            (float(cost) - state.resources[resource], resource)
            for resource, cost in costs.items()
            if state.resources[resource] + 1e-9 < float(cost)
        ]
        if shortages:
            return max(shortages, key=lambda item: (item[0], -RESOURCE_NAMES.index(item[1])))[1]
        if influence < required_influence:
            return "influence"
        return None

    @staticmethod
    def _apply_upgrade(
        territory: SimulatedTerritory,
        upgrade_type: str,
        rules: Mapping[str, int | float],
        bonuses: Mapping[str, int],
    ) -> None:
        if upgrade_type == "population":
            territory.development_level += 1
            growth = (
                float(rules["POPULATION_BASE_GROWTH_PERCENT"])
                + bonuses.get("population_growth_percent", 0)
                / float(rules["POPULATION_GROWTH_RELIC_DIVISOR"])
            ) / 100
            territory.population = min(
                int(rules["POPULATION_MAXIMUM"]),
                int(territory.population * (1 + growth))
                + int(rules["POPULATION_FLAT_GROWTH_PER_LEVEL"]),
            )
        elif upgrade_type == "fortifications":
            territory.fortifications += 1
        elif upgrade_type == "offense":
            territory.offense_level += 1
        elif upgrade_type == "port":
            territory.port_level += 1
        elif upgrade_type == "fleet":
            territory.fleet_level += 1
        elif upgrade_type == "naval":
            next_level = max(territory.port_level, territory.fleet_level) + 1
            territory.port_level = next_level
            territory.fleet_level = next_level

    def _next_goal(
        self,
        state: SimulationState,
        catalog: BalanceSimulationCatalog,
        strategy_name: str,
    ) -> dict[str, Any] | None:
        max_level = int(catalog.rules["TERRITORY_MAX_UPGRADE_LEVEL"])

        def upgrade_goal(upgrade_type: str, candidates: list[SimulatedTerritory]):
            field_name = {
                "population": "development_level",
                "fortifications": "fortifications",
                "offense": "offense_level",
                "port": "port_level",
                "fleet": "fleet_level",
                "naval": "port_level",
            }[upgrade_type]
            for territory in candidates:
                if int(getattr(territory, field_name)) >= max_level:
                    continue
                if upgrade_type == "fleet" and territory.fleet_level >= territory.port_level:
                    continue
                return {
                    "kind": "upgrade",
                    "territory_id": territory.id,
                    "upgrade_type": upgrade_type,
                }
            return None

        richest = sorted(
            state.territories,
            key=lambda item: (-item.resource_wealth, item.development_level, item.id),
        )
        most_valuable_border = sorted(
            state.territories,
            key=lambda item: (
                -len(item.source.adjacent_territory_ids),
                -item.prosperity_score,
                item.fortifications,
                item.id,
            ),
        )
        strongest_attack = sorted(
            state.territories,
            key=lambda item: (-item.offense_level, -len(item.source.adjacent_territory_ids), item.id),
        )
        least_developed = sorted(
            state.territories,
            key=lambda item: (item.total_levels(), item.id),
        )
        ports = [territory for territory in least_developed if territory.has_port]

        if strategy_name == "economic":
            return (
                upgrade_goal("population", richest)
                or self._relic_goal(state, catalog, {"gold_income_percent", "resource_income_flat", "population_cost_percent"})
                or upgrade_goal("naval", ports)
                or upgrade_goal("fortifications", least_developed)
                or upgrade_goal("offense", least_developed)
            )
        if strategy_name == "military":
            return (
                upgrade_goal("fortifications", most_valuable_border)
                or upgrade_goal("offense", strongest_attack)
                or upgrade_goal("naval", ports)
                or self._relic_goal(state, catalog, {"attack_power", "defense_power", "fortification_cost_percent"})
                or upgrade_goal("population", least_developed)
            )

        cycle = ("population", "fortifications", "offense", "relic", "naval")
        for _ in cycle:
            cycle_type = cycle[state.balanced_cycle]
            if cycle_type == "relic":
                goal = self._relic_goal(state, catalog, None)
            elif cycle_type == "naval":
                goal = upgrade_goal("naval", ports)
            else:
                goal = upgrade_goal(cycle_type, least_developed)
            if goal is not None:
                return goal
            state.balanced_cycle = (state.balanced_cycle + 1) % len(cycle)
        return None

    @staticmethod
    def _relic_goal(
        state: SimulationState,
        catalog: BalanceSimulationCatalog,
        bonus_types: set[str] | None,
    ) -> dict[str, Any] | None:
        candidates = [
            relic
            for relic in catalog.relics
            if (bonus_types is None or relic.bonus_type in bonus_types)
            and state.relic_levels.get(relic.id, 0) < relic.max_level
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda relic: (
                sum(
                    calculate_relic_cost(
                        relic,
                        state.relic_levels.get(relic.id, 0) + 1,
                        catalog.rules,
                    ).values()
                ),
                relic.key,
            )
        )
        return {"kind": "relic", "relic_id": candidates[0].id}

    def _snapshot(
        self,
        state: SimulationState,
        rules: Mapping[str, int | float],
    ) -> dict[str, Any]:
        bonuses = self._state_bonuses_without_catalog(state)
        influence = self._influence(state, bonuses)
        clan_level, attack_capacity = self._level_status(state, rules, influence)
        daily_gold = round(
            sum(ClanEconomyService._daily_income(territory, rules) for territory in state.territories)
            * (100 + bonuses.get("gold_income_percent", 0))
            / 100,
            2,
        )
        daily_resources = {resource: 0 for resource in RESOURCE_NAMES[1:]}
        for territory in state.territories:
            for resource, amount in ClanEconomyService._daily_resource_rewards(territory, bonuses):
                if resource in daily_resources:
                    daily_resources[resource] += amount
        total_blocked = sum(state.blocked_hours.values())
        blocked_share = {
            resource: round(hours / total_blocked, 4)
            for resource, hours in sorted(state.blocked_hours.items())
        } if total_blocked else {}
        return {
            "resources": {
                resource: round(state.resources[resource], 2)
                for resource in RESOURCE_NAMES
            },
            "accumulated": {
                resource: round(state.accumulated[resource], 2)
                for resource in RESOURCE_NAMES
            },
            "spent": {
                resource: round(state.spent[resource], 2)
                for resource in RESOURCE_NAMES
            },
            "daily_income": {"gold": daily_gold, **daily_resources},
            "territory_count": len(state.territories),
            "influence": influence,
            "clan_level": clan_level,
            "attack_capacity": attack_capacity,
            "upgrade_levels": {
                upgrade_type: sum(
                    getattr(territory, field_name) for territory in state.territories
                )
                for upgrade_type, field_name in {
                    "population": "development_level",
                    "fortifications": "fortifications",
                    "offense": "offense_level",
                    "naval": "port_level",
                }.items()
            },
            "total_development_levels": sum(
                territory.total_levels() for territory in state.territories
            ),
            "relic_levels": sum(state.relic_levels.values()),
            "relics": [
                {"id": relic_id, "level": level}
                for relic_id, level in sorted(state.relic_levels.items())
            ],
            "blocked_hours": dict(sorted(state.blocked_hours.items())),
            "blocked_share": blocked_share,
            "average_purchase_wait_hours": round(
                sum(item["wait_hours"] for item in state.purchases) / len(state.purchases),
                2,
            ) if state.purchases else None,
            "unused_production_ratio": {
                resource: round(
                    max(0.0, state.accumulated[resource] - state.spent[resource])
                    / state.accumulated[resource],
                    4,
                ) if state.accumulated[resource] else 0.0
                for resource in RESOURCE_NAMES
            },
        }

    @staticmethod
    def _market_diagnostic(
        state: SimulationState,
        rules: Mapping[str, int | float],
    ) -> dict[str, Any] | None:
        if state.current_goal is None:
            return None
        bonuses = BalanceSimulationService._state_bonuses_without_catalog(state)
        if state.current_goal["kind"] == "upgrade":
            territory = next(
                item for item in state.territories if item.id == state.current_goal["territory_id"]
            )
            costs = calculate_upgrade_cost(
                territory,
                state.current_goal["upgrade_type"],
                rules,
                bonuses,
            )
        else:
            return None
        missing = [
            (resource, int(ceil(cost - state.resources[resource])))
            for resource, cost in costs.items()
            if state.resources[resource] < cost and resource != "gold"
        ]
        if not missing:
            return None
        missing_resource, amount = max(missing, key=lambda item: (item[1], item[0]))
        surplus_resource = max(
            (resource for resource in RESOURCE_NAMES[1:] if resource != missing_resource),
            key=lambda resource: (state.resources[resource], resource),
        )
        routes = []
        for steps in (1, 4, 8):
            routes.append({
                "mode": "land",
                "steps": steps,
                "gold_cost": ClanMarketService.shipping_cost(steps, amount, rules),
                "eta_hours": steps * int(rules["CARAVAN_HOURS_PER_STEP"]),
            })
        routes.append({
            "mode": "sea",
            "steps": 4,
            "gold_cost": ClanMarketService.shipping_cost(4, amount, rules),
            "eta_hours": 4 * int(rules["CARAVAN_SEA_HOURS_PER_STEP"]),
        })
        return {
            "missing_resource": missing_resource,
            "amount": amount,
            "offered_surplus_resource": surplus_resource,
            "routes": routes,
        }

    def _signals(
        self,
        catalog: BalanceSimulationCatalog,
        scenarios: list[dict[str, Any]],
        days: int,
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for scenario in scenarios:
            scenario_id = scenario["id"]
            purchases = scenario["purchases"]
            first_upgrade = next(
                (purchase for purchase in purchases if not purchase["goal"].startswith("relic:")),
                None,
            )
            if scenario["profile"] == "new" and (
                first_upgrade is None or float(first_upgrade["day"]) > 7
            ):
                signals.append(self._signal(
                    "first_upgrade_slow",
                    scenario_id,
                    "A new clan cannot buy its first upgrade within 7 days.",
                    "POPULATION_BASE_GOLD_COST",
                    catalog.rules["POPULATION_BASE_GOLD_COST"],
                    max(1, round(float(catalog.rules["POPULATION_BASE_GOLD_COST"]) * 0.9)),
                ))
            first_relic = next(
                (purchase for purchase in purchases if purchase["goal"].startswith("relic:")),
                None,
            )
            if scenario["profile"] == "growing" and days >= 14 and (
                first_relic is None or float(first_relic["day"]) > 14
            ):
                signals.append(self._signal(
                    "first_relic_slow",
                    scenario_id,
                    "A growing clan cannot buy a level-one relic within 14 days.",
                    "relic_catalog_costs",
                    None,
                    None,
                ))
            if scenario["pace"] == "normal" and days >= 30:
                if not any(item["both_day"] is not None and float(item["both_day"]) <= 30 for item in scenario["great_strongholds"]):
                    signals.append(self._signal(
                        "normal_stronghold_unreachable",
                        scenario_id,
                        "No great stronghold meets both numeric gates within 30 days.",
                        "great_stronghold_requirements",
                        None,
                        None,
                    ))
            if scenario["pace"] == "aggressive":
                upper_stronghold = max(
                    scenario["great_strongholds"],
                    key=lambda item: (
                        int(item["required_territories"]),
                        int(item["required_influence"]),
                        int(item["territory_id"]),
                    ),
                    default=None,
                )
                if (
                    upper_stronghold
                    and upper_stronghold["both_day"] is not None
                    and float(upper_stronghold["both_day"]) < 14
                ):
                    signals.append(self._signal(
                        "upper_stronghold_too_early",
                        scenario_id,
                        "The highest great-stronghold gate is met before day 14.",
                        "great_stronghold_requirements",
                        upper_stronghold["both_day"],
                        14,
                    ))
            blocked_share = scenario["final"]["blocked_share"]
            if blocked_share:
                resource, share = max(blocked_share.items(), key=lambda item: (item[1], item[0]))
                if float(share) > 0.6:
                    signals.append(self._signal(
                        "resource_bottleneck",
                        scenario_id,
                        f"{resource} blocks {float(share):.0%} of purchase waiting time.",
                        resource,
                        float(share),
                        0.6,
                    ))
            for resource, ratio in scenario["final"]["unused_production_ratio"].items():
                if float(ratio) > 0.5 and scenario["final"]["accumulated"][resource] > 0:
                    signals.append(self._signal(
                        "unused_resource_surplus",
                        scenario_id,
                        f"More than half of produced {resource} remains unused.",
                        resource,
                        float(ratio),
                        0.5,
                    ))
            market = scenario["market_diagnostic"]
            weekly_gold = float(scenario["final"]["daily_income"]["gold"]) * 7
            if market and weekly_gold > 0 and any(
                float(route["gold_cost"]) > weekly_gold for route in market["routes"]
            ):
                signals.append(self._signal(
                    "market_shipping_expensive",
                    scenario_id,
                    "At least one diagnostic exchange costs more than weekly gold income.",
                    "CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT",
                    catalog.rules["CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT"],
                    max(100, int(catalog.rules["CARAVAN_GOLD_FEE_MULTIPLIER_PERCENT"]) - 10),
                ))
            relic_by_key = {relic.key: relic for relic in catalog.relics}
            for purchase in purchases:
                if not purchase["goal"].startswith("relic:"):
                    continue
                relic = relic_by_key.get(purchase["goal"].split(":", 1)[1])
                if relic is None or relic.bonus_type != "gold_income_percent":
                    continue
                total_gold_bonus = sum(
                    relic_by_key[item["goal"].split(":", 1)[1]].bonus_value
                    for item in purchases
                    if item["goal"].startswith("relic:")
                    and item["goal"].split(":", 1)[1] in relic_by_key
                    and relic_by_key[item["goal"].split(":", 1)[1]].bonus_type == "gold_income_percent"
                )
                final_daily_gold = float(scenario["final"]["daily_income"]["gold"])
                base_daily_gold = (
                    final_daily_gold / (1 + total_gold_bonus / 100)
                    if total_gold_bonus else final_daily_gold
                )
                incremental_gold = base_daily_gold * relic.bonus_value / 100
                if incremental_gold <= 0:
                    continue
                payback_days = float(purchase["cost"].get("gold", 0)) / incremental_gold
                if payback_days < 7 or payback_days > 30:
                    signals.append(self._signal(
                        "income_relic_payback_outside_window",
                        scenario_id,
                        f"{relic.key} has an estimated gold payback of {payback_days:.1f} days.",
                        f"relic:{relic.key}:gold_cost",
                        round(payback_days, 2),
                        "7..30",
                    ))
                break

        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for scenario in scenarios:
            grouped.setdefault((scenario["profile"], scenario["pace"]), []).append(scenario)
        for (profile, pace), rows in grouped.items():
            if len(rows) != len(STRATEGIES):
                continue
            totals = sorted(
                (
                    int(row["final"]["total_development_levels"]),
                    row["strategy"],
                    row["id"],
                )
                for row in rows
            )
            if totals[0][0] > 0 and totals[-1][0] > totals[-2][0] * 2:
                signals.append(self._signal(
                    "strategy_runaway",
                    totals[-1][2],
                    f"{totals[-1][1]} development exceeds both alternatives by more than 2x for {profile}/{pace}.",
                    "strategy_priorities",
                    totals[-1][0],
                    totals[-2][0] * 2,
                ))

        return sorted(signals, key=lambda item: (item["code"], item["scenario_id"], item["parameter"]))

    @staticmethod
    def _signal(
        code: str,
        scenario_id: str,
        detail: str,
        parameter: str,
        current_value: Any,
        proposed_value: Any,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "severity": "warning",
            "scenario_id": scenario_id,
            "detail": detail,
            "parameter": parameter,
            "current_value": current_value,
            "proposed_value": proposed_value,
        }

    @staticmethod
    def _recommendations(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for signal in signals:
            key = (signal["code"], signal["parameter"])
            if key in seen:
                continue
            seen.add(key)
            recommendations.append({
                "signal": signal["code"],
                "parameter": signal["parameter"],
                "current_value": signal["current_value"],
                "proposed_value": signal["proposed_value"],
                "recommendation": (
                    "Validate this change in a new campaign-rule version during closed beta; "
                    "do not modify the active version automatically."
                ),
            })
        return recommendations

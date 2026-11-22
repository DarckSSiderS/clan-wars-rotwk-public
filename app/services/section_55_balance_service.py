from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from app.core.campaign_rules import default_campaign_rule_values
from app.core.section_55_balance import (
    ACTIVE_CLAN_STARTING_GOLD,
    ACTIVE_CLAN_STARTING_INFLUENCE,
    ACTIVE_CLAN_TERRITORIES,
    ORDINARY_GOLD_CENTER,
    ORDINARY_GOLD_TOLERANCE,
    ORDINARY_INFLUENCE,
    SECTION_55_BALANCE_VERSION,
    SECTION_55_RELIC_COSTS,
    STRONGHOLD_GOLD_CENTER,
    STRONGHOLD_GOLD_TOLERANCE,
    STRONGHOLD_MAX_GOLD_RATIO,
    STRONGHOLD_MIN_GOLD_RATIO,
    STRONGHOLD_REQUIRED_INFLUENCE,
    STRONGHOLD_REQUIRED_TERRITORIES,
    TARGET_MAX_DAYS,
    TARGET_MIN_DAYS,
)
from app.core.territory_resource_balance import TERRITORY_BALANCE
from app.services.balance_simulation_catalog import TerritorySimulationInput
from app.services.balance_simulation_service import (
    SimulatedTerritory,
    calculate_upgrade_cost,
)
from app.services.market_service import ClanMarketService


UPGRADE_TYPES = ("population", "fortifications", "offense", "naval")
MAX_ACTIVE_CLAN_TRADE_FEE_SHARE = 0.20
MIN_ACTIVE_CLAN_TRADE_FEE_SHARE = 0.05


def _check(
    code: str,
    passed: bool,
    *,
    actual: Any,
    expected: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "passed": bool(passed),
        "actual": actual,
        "expected": expected,
    }


def _reference_territory(wealth: int) -> SimulatedTerritory:
    source = TerritorySimulationInput(
        id=1,
        name="Section 55 reference land",
        region="reference",
        resource_wealth=wealth,
        influence_value=ORDINARY_INFLUENCE,
        population=0,
        resource_type="iron",
        resource_output=1,
        secondary_resource_type=None,
        is_coastal=True,
        has_port=True,
        required_influence=30,
        required_territories=0,
        stronghold_power=0,
        adjacent_territory_ids=(),
    )
    return SimulatedTerritory(source, captured_hour=0)


def _apply_upgrade_level(territory: SimulatedTerritory, upgrade_type: str) -> None:
    if upgrade_type == "population":
        territory.development_level += 1
    elif upgrade_type == "fortifications":
        territory.fortifications += 1
    elif upgrade_type == "offense":
        territory.offense_level += 1
    elif upgrade_type == "naval":
        territory.port_level += 1
        territory.fleet_level += 1
    else:  # pragma: no cover - guarded by the module-level tuple
        raise ValueError(f"Unsupported Section 55 upgrade type: {upgrade_type}")


def _max_upgrade_cost(wealth: int, upgrade_type: str) -> dict[str, int]:
    rules = default_campaign_rule_values()
    territory = _reference_territory(wealth)
    total: defaultdict[str, int] = defaultdict(int)
    for _ in range(int(rules["TERRITORY_MAX_UPGRADE_LEVEL"])):
        for resource, amount in calculate_upgrade_cost(
            territory,
            upgrade_type,
            rules,
            {},
        ).items():
            total[resource] += amount
        _apply_upgrade_level(territory, upgrade_type)
    return dict(sorted(total.items()))


def _saving_days(gold_cost: float, daily_gold: float) -> float:
    return max(0.0, (gold_cost - ACTIVE_CLAN_STARTING_GOLD) / daily_gold)


def build_section_55_balance_report() -> dict[str, Any]:
    ordinary = [
        balance
        for balance in TERRITORY_BALANCE.values()
        if balance.stronghold_power == 0
    ]
    strongholds = [
        balance
        for balance in TERRITORY_BALANCE.values()
        if balance.stronghold_power > 0
    ]
    ordinary_gold = [balance.resource_wealth for balance in ordinary]
    stronghold_gold = [balance.resource_wealth for balance in strongholds]
    average_ordinary_gold = mean(ordinary_gold)
    average_stronghold_gold = mean(stronghold_gold)
    stronghold_ratio = average_stronghold_gold / average_ordinary_gold
    active_daily_gold = average_ordinary_gold * ACTIVE_CLAN_TERRITORIES

    checks = [
        _check(
            "ordinary_gold_range",
            min(ordinary_gold) >= ORDINARY_GOLD_CENTER - ORDINARY_GOLD_TOLERANCE
            and max(ordinary_gold) <= ORDINARY_GOLD_CENTER + ORDINARY_GOLD_TOLERANCE,
            actual={"min": min(ordinary_gold), "max": max(ordinary_gold)},
            expected="40..60 gold/day",
        ),
        _check(
            "stronghold_gold_range",
            min(stronghold_gold)
            >= STRONGHOLD_GOLD_CENTER - STRONGHOLD_GOLD_TOLERANCE
            and max(stronghold_gold)
            <= STRONGHOLD_GOLD_CENTER + STRONGHOLD_GOLD_TOLERANCE,
            actual={"min": min(stronghold_gold), "max": max(stronghold_gold)},
            expected="140..160 gold/day",
        ),
        _check(
            "stronghold_gold_ratio",
            STRONGHOLD_MIN_GOLD_RATIO
            <= stronghold_ratio
            <= STRONGHOLD_MAX_GOLD_RATIO,
            actual=round(stronghold_ratio, 3),
            expected="2.8x..3.2x ordinary average",
        ),
        _check(
            "ordinary_single_resource_type",
            all(balance.secondary_resource_type is None for balance in ordinary),
            actual=sum(
                balance.secondary_resource_type is not None for balance in ordinary
            ),
            expected="0 ordinary lands with a secondary resource",
        ),
        _check(
            "stronghold_two_distinct_resource_types",
            all(
                balance.secondary_resource_type is not None
                and balance.secondary_resource_type != balance.resource_type
                for balance in strongholds
            ),
            actual=sum(
                balance.secondary_resource_type is not None
                and balance.secondary_resource_type != balance.resource_type
                for balance in strongholds
            ),
            expected=f"{len(strongholds)} strongholds",
        ),
        _check(
            "five_lands_unlock_stronghold",
            all(balance.influence_value == ORDINARY_INFLUENCE for balance in ordinary)
            and all(
                balance.required_territories == STRONGHOLD_REQUIRED_TERRITORIES
                and balance.required_influence == STRONGHOLD_REQUIRED_INFLUENCE
                for balance in strongholds
            )
            and (
                ACTIVE_CLAN_STARTING_INFLUENCE
                + ACTIVE_CLAN_TERRITORIES * ORDINARY_INFLUENCE
                == STRONGHOLD_REQUIRED_INFLUENCE
            ),
            actual={
                "starting_influence": ACTIVE_CLAN_STARTING_INFLUENCE,
                "land_influence": ORDINARY_INFLUENCE,
                "lands": ACTIVE_CLAN_TERRITORIES,
                "result": ACTIVE_CLAN_STARTING_INFLUENCE
                + ACTIVE_CLAN_TERRITORIES * ORDINARY_INFLUENCE,
            },
            expected="100 + 5 * 50 = 350 influence and 5 lands",
        ),
    ]

    upgrade_rows = []
    for upgrade_type in UPGRADE_TYPES:
        costs = [_max_upgrade_cost(wealth, upgrade_type) for wealth in ordinary_gold]
        gold_costs = [cost["gold"] for cost in costs]
        average_days = _saving_days(mean(gold_costs), active_daily_gold)
        worst_days = _saving_days(max(gold_costs), active_daily_gold)
        rare_max = {
            resource: max(cost.get(resource, 0) for cost in costs)
            for resource in ("iron", "wood", "food", "mithril")
        }
        upgrade_rows.append(
            {
                "type": upgrade_type,
                "average_gold_cost": round(mean(gold_costs), 2),
                "maximum_gold_cost": max(gold_costs),
                "average_saving_days": round(average_days, 2),
                "worst_saving_days": round(worst_days, 2),
                "maximum_rare_costs": rare_max,
            }
        )
        checks.append(
            _check(
                f"{upgrade_type}_max_level_timing",
                TARGET_MIN_DAYS <= average_days <= TARGET_MAX_DAYS
                and worst_days <= TARGET_MAX_DAYS,
                actual={
                    "average_days": round(average_days, 2),
                    "worst_days": round(worst_days, 2),
                },
                expected=f"{TARGET_MIN_DAYS:g}..{TARGET_MAX_DAYS:g} days",
            )
        )
        checks.append(
            _check(
                f"{upgrade_type}_rare_resource_budget",
                rare_max["mithril"] == 0
                and max(rare_max[resource] for resource in ("iron", "wood", "food"))
                <= 10,
                actual=rare_max,
                expected="no mithril and at most 10 of each common resource",
            )
        )

    relic_gold_costs = [costs[0] for costs in SECTION_55_RELIC_COSTS.values()]
    average_relic_gold = mean(relic_gold_costs)
    average_relic_days = _saving_days(average_relic_gold, active_daily_gold)
    checks.append(
        _check(
            "average_level_one_relic_timing",
            TARGET_MIN_DAYS <= average_relic_days <= TARGET_MAX_DAYS,
            actual={
                "average_gold_cost": round(average_relic_gold, 2),
                "saving_days": round(average_relic_days, 2),
            },
            expected=f"{TARGET_MIN_DAYS:g}..{TARGET_MAX_DAYS:g} days",
        )
    )

    rules = default_campaign_rule_values()
    resource_indexes = {"iron": 1, "wood": 2, "food": 3, "mithril": 4}
    resource_ready_days = float(rules["TERRITORY_RESOURCE_READY_HOURS"]) / 24
    production_days = max(0.0, average_relic_days - resource_ready_days)
    relic_resource_budget = {}
    for resource, index in resource_indexes.items():
        average_cost = mean(costs[index] for costs in SECTION_55_RELIC_COSTS.values())
        average_daily_output = (
            sum(
                balance.resource_output
                for balance in ordinary
                if balance.resource_type == resource
            )
            / len(ordinary)
            * ACTIVE_CLAN_TERRITORIES
        )
        available = (
            float(rules[f"CAMPAIGN_STARTING_{resource.upper()}"])
            + average_daily_output * production_days
        )
        relic_resource_budget[resource] = {
            "average_cost": round(average_cost, 2),
            "available_by_target_day": round(available, 2),
            "market_deficit": round(max(0.0, average_cost - available), 2),
        }
    checks.append(
        _check(
            "average_relic_resource_budget",
            all(
                row["market_deficit"] <= 1
                for row in relic_resource_budget.values()
            ),
            actual=relic_resource_budget,
            expected="own average production plus at most 1 traded unit per resource",
        )
    )

    trade_cases = {
        "near_10_units": ClanMarketService.shipping_cost(1, 10, rules),
        "far_50_units": ClanMarketService.shipping_cost(8, 50, rules),
    }
    trade_shares = {
        name: fee / active_daily_gold for name, fee in trade_cases.items()
    }
    checks.append(
        _check(
            "trade_fee_corridor",
            trade_shares["near_10_units"] >= MIN_ACTIVE_CLAN_TRADE_FEE_SHARE
            and trade_shares["far_50_units"] <= MAX_ACTIVE_CLAN_TRADE_FEE_SHARE,
            actual={
                name: {
                    "gold": trade_cases[name],
                    "daily_income_share_percent": round(share * 100, 2),
                }
                for name, share in trade_shares.items()
            },
            expected="near cargo >=5% and far cargo <=20% of active daily gold",
        )
    )

    return {
        "balance_version": SECTION_55_BALANCE_VERSION,
        "passed": all(check["passed"] for check in checks),
        "reference_active_clan": {
            "territories": ACTIVE_CLAN_TERRITORIES,
            "starting_gold": ACTIVE_CLAN_STARTING_GOLD,
            "average_ordinary_gold": round(average_ordinary_gold, 3),
            "daily_gold": round(active_daily_gold, 3),
            "target_days": [TARGET_MIN_DAYS, TARGET_MAX_DAYS],
        },
        "map": {
            "ordinary_count": len(ordinary),
            "stronghold_count": len(strongholds),
            "ordinary_gold": {
                "min": min(ordinary_gold),
                "max": max(ordinary_gold),
                "average": round(average_ordinary_gold, 3),
            },
            "stronghold_gold": {
                "min": min(stronghold_gold),
                "max": max(stronghold_gold),
                "average": round(average_stronghold_gold, 3),
                "ratio": round(stronghold_ratio, 3),
            },
        },
        "upgrades": upgrade_rows,
        "relics": {
            "count": len(relic_gold_costs),
            "minimum_gold_cost": min(relic_gold_costs),
            "maximum_gold_cost": max(relic_gold_costs),
            "average_gold_cost": round(average_relic_gold, 2),
            "average_saving_days": round(average_relic_days, 2),
            "resource_budget": relic_resource_budget,
        },
        "trade": {
            "fees": trade_cases,
            "daily_income_share_percent": {
                name: round(share * 100, 2) for name, share in trade_shares.items()
            },
        },
        "checks": checks,
    }

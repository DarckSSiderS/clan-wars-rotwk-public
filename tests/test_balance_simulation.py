from __future__ import annotations

from datetime import date
from types import MappingProxyType

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.clan_asset import ClanAsset
from app.models.territory import Territory
from app.schemas.balance_simulation import StrategicSandboxRequest
from app.services.balance_simulation_catalog import (
    BalanceSimulationCatalog,
    BalanceSimulationCatalogLoader,
    RelicSimulationInput,
    TerritorySimulationInput,
)
from app.services.balance_simulation_report import serialize_simulation_json
from app.services.balance_simulation_service import (
    BalanceSimulationService,
    SimulatedTerritory,
    SimulationState,
    calculate_relic_cost,
    calculate_upgrade_cost,
)
from app.services.clan_economy_service import ClanEconomyService
from app.services.strategic_simulation_service import StrategicSimulationService


def territory_input(
    territory_id: int,
    *,
    wealth: int = 100,
    influence: int = 25,
    has_port: bool = False,
    stronghold: bool = False,
) -> TerritorySimulationInput:
    return TerritorySimulationInput(
        id=territory_id,
        name=f"Territory {territory_id}",
        region="gondor",
        resource_wealth=wealth,
        influence_value=influence,
        population=100,
        resource_type="iron",
        resource_output=1,
        secondary_resource_type="wood" if stronghold else None,
        is_coastal=has_port,
        has_port=has_port,
        required_influence=300 if stronghold else 0,
        required_territories=5 if stronghold else 0,
        stronghold_power=3 if stronghold else 0,
        adjacent_territory_ids=tuple(range(1, min(territory_id, 5))),
    )


def relic_input(
    relic_id: int = 1,
    *,
    key: str = "white_tree",
    bonus_type: str = "gold_income_percent",
) -> RelicSimulationInput:
    return RelicSimulationInput(
        id=relic_id,
        key=key,
        name=key.replace("_", " ").title(),
        bonus_type=bonus_type,
        bonus_value=8,
        costs=MappingProxyType({
            "gold": 100,
            "iron": 2,
            "wood": 2,
            "food": 0,
            "mithril": 0,
        }),
        required_influence=(100, 200, 300),
        max_level=3,
    )


def simulation_catalog() -> BalanceSimulationCatalog:
    rules = default_campaign_rule_values()
    territories = [
        territory_input(index, wealth=30 + index * 9, has_port=index in {4, 8})
        for index in range(1, 13)
    ]
    territories.append(territory_input(20, wealth=180, has_port=True, stronghold=True))
    return BalanceSimulationCatalog(
        rule_set_id=7,
        rule_version=4,
        rules=MappingProxyType(rules),
        territories=tuple(territories),
        relics=(
            relic_input(),
            relic_input(2, key="granite_bastion", bonus_type="defense_power"),
        ),
        starting_resources=MappingProxyType({
            "gold": 500,
            "iron": 10,
            "wood": 10,
            "food": 5,
            "mithril": 2,
            "influence": 100,
        }),
    )


def test_simulation_json_is_byte_deterministic_for_identical_inputs():
    catalog = simulation_catalog()
    service = BalanceSimulationService()

    first = service.run(catalog, days=7)
    second = service.run(catalog, days=7)

    assert serialize_simulation_json(
        first,
        calculation_date=date(2026, 8, 25),
    ) == serialize_simulation_json(
        second,
        calculation_date=date(2026, 8, 25),
    )
    assert len(first["scenarios"]) == 36


def test_daily_gold_formula_matches_clan_economy_service():
    rules = default_campaign_rule_values()
    source = territory_input(1, wealth=137)
    simulated = SimulatedTerritory(source, captured_hour=0)
    simulated.development_level = 4
    simulated.population = 720
    server_territory = Territory(
        resource_wealth=137,
        development_level=4,
        population=720,
    )

    assert ClanEconomyService._daily_income(simulated, rules) == (
        ClanEconomyService._daily_income(server_territory, rules)
    )


def test_rare_resources_start_after_48_hours_and_stronghold_yields_two_types():
    rules = default_campaign_rule_values()
    stronghold = SimulatedTerritory(
        territory_input(20, stronghold=True),
        captured_hour=0,
    )
    state = SimulationState(
        resources={resource: 0.0 for resource in ("gold", "iron", "wood", "food", "mithril")},
        base_influence=100,
        active_members=5,
        territories=[stronghold],
        capture_queue=[],
    )
    setattr(state, "_bonuses_cache", {})

    BalanceSimulationService._accrue_rare_resources(state, rules, 47)
    assert state.resources["iron"] == 0
    assert state.resources["wood"] == 0

    BalanceSimulationService._accrue_rare_resources(state, rules, 48)
    assert state.resources["iron"] == 1
    assert state.resources["wood"] == 1

    BalanceSimulationService._accrue_rare_resources(state, rules, 72)
    assert state.resources["iron"] == 2
    assert state.resources["wood"] == 2


def test_capture_interval_respects_campaign_pace_and_war_duration():
    rules = default_campaign_rule_values()
    rules["WAR_DURATION_HOURS"] = 120

    assert BalanceSimulationService._capture_interval_hours(rules, 4) == 120
    assert BalanceSimulationService._capture_interval_hours(rules, 8) == 192


def test_upgrade_costs_match_server_and_fleet_cannot_exceed_port(db):
    rules = default_campaign_rule_values()
    source = territory_input(4, wealth=115, has_port=True)
    simulated = SimulatedTerritory(source, captured_hour=0)
    simulated.development_level = 2
    simulated.fortifications = 2
    simulated.offense_level = 2
    simulated.port_level = 2
    simulated.fleet_level = 1
    server = Territory(
        name="Contract land",
        region="gondor",
        svg_path_data="M0 0",
        resource_wealth=115,
        development_level=2,
        fortifications=2,
        offense_level=2,
        has_port=True,
        port_level=2,
        fleet_level=1,
    )
    economy = ClanEconomyService()

    for upgrade_type in ("population", "fortifications", "offense", "port", "fleet"):
        assert calculate_upgrade_cost(simulated, upgrade_type, rules, {}) == (
            economy.get_upgrade_costs(
                db,
                server,
                upgrade_type,
                rules=rules,
            )
        )

    simulated.port_level = 0
    simulated.fleet_level = 0
    assert calculate_upgrade_cost(simulated, "fleet", rules, {}) == {}


def test_relic_costs_use_1_5_15_and_purchase_does_not_spend_influence():
    catalog = simulation_catalog()
    relic = catalog.relics[0]
    assert calculate_relic_cost(relic, 1, catalog.rules)["gold"] == 100
    assert calculate_relic_cost(relic, 2, catalog.rules)["gold"] == 500
    assert calculate_relic_cost(relic, 3, catalog.rules)["gold"] == 1500

    territory = SimulatedTerritory(catalog.territories[0], captured_hour=0)
    state = SimulationState(
        resources={
            "gold": 10_000.0,
            "iron": 1_000.0,
            "wood": 1_000.0,
            "food": 1_000.0,
            "mithril": 1_000.0,
        },
        base_influence=1_000,
        active_members=30,
        territories=[territory],
        capture_queue=[],
        current_goal={"kind": "relic", "relic_id": relic.id},
    )
    service = BalanceSimulationService()
    before = service._influence(state, {})
    service._attempt_purchase(state, catalog, "balanced", 0)
    after = service._influence(state, service._bonuses(state, catalog))

    assert state.relic_levels[relic.id] == 1
    assert before == after


def test_catalog_excludes_admin_land_and_does_not_mutate_entities(db):
    rules = default_campaign_rule_values()
    db.add(CampaignRuleSet(version=1, values=rules, is_active=True, reason="test"))
    normal = Territory(
        name="Playable land",
        region="rohan",
        svg_path_data="M0 0",
        resource_wealth=50,
        resource_type="iron",
        resource_output=0,
        is_playable=True,
    )
    admin = Territory(
        name="Тол-Фалас",
        region="gondor",
        svg_path_data="M1 1",
        resource_wealth=999,
        is_playable=True,
    )
    db.add_all([normal, admin, ClanAsset(
        key="test_relic",
        name="Test relic",
        bonus_type="gold_income_percent",
        bonus_value=5,
        gold_cost=100,
        is_available=True,
    )])
    db.flush()

    catalog = BalanceSimulationCatalogLoader().load(db)

    assert [territory.name for territory in catalog.territories] == ["Playable land"]
    assert catalog.territories[0].resource_type == "iron"
    assert normal.resource_type == "iron"
    assert normal.resource_output == 0
    assert not db.dirty


def test_impossible_purchase_records_the_actual_blocking_resource():
    state = SimulationState(
        resources={
            "gold": 500.0,
            "iron": 0.0,
            "wood": 10.0,
            "food": 5.0,
            "mithril": 2.0,
        },
        base_influence=100,
        active_members=5,
        territories=[],
        capture_queue=[],
    )

    blocker = BalanceSimulationService._blocking_resource(
        state,
        {"gold": 350, "iron": 3},
        influence=100,
        required_influence=0,
    )

    assert blocker == "iron"


def test_level_and_stronghold_gates_use_the_supplied_rule_and_catalog_snapshot():
    rules = default_campaign_rule_values()
    rules.update({
        "CLAN_LEVEL_2_ACTIVE_MEMBERS": 6,
        "CLAN_LEVEL_2_TERRITORIES": 2,
        "CLAN_LEVEL_2_INFLUENCE": 100,
        "CLAN_LEVEL_2_ATTACK_CAPACITY": 2,
    })
    territories = [
        SimulatedTerritory(territory_input(1), captured_hour=0),
        SimulatedTerritory(territory_input(2), captured_hour=0),
    ]
    state = SimulationState(
        resources={resource: 0.0 for resource in ("gold", "iron", "wood", "food", "mithril")},
        base_influence=50,
        active_members=6,
        territories=territories,
        capture_queue=[],
        stronghold_access={
            20: {
                "territory_id": 20,
                "territory_name": "Stronghold",
                "required_territories": 3,
                "required_influence": 100,
                "territory_day": None,
                "influence_day": None,
                "both_day": None,
                "obstacle": None,
                "daily_resources_after_capture": ["iron", "wood"],
            },
        },
    )
    service = BalanceSimulationService()
    influence = service._influence(state, {})

    assert service._level_status(state, rules, influence) == (2, 2)
    service._update_stronghold_access(state, 0)
    assert state.stronghold_access[20]["influence_day"] == 0
    assert state.stronghold_access[20]["territory_day"] is None

    state.territories.append(SimulatedTerritory(territory_input(3), captured_hour=24))
    service._update_stronghold_access(state, 24)
    assert state.stronghold_access[20]["territory_day"] == 1
    assert state.stronghold_access[20]["both_day"] == 1


def test_result_contains_no_user_or_clan_personal_fields():
    result = BalanceSimulationService().run(simulation_catalog(), days=7)
    serialized = serialize_simulation_json(
        result,
        calculation_date=date(2026, 8, 25),
    ).casefold()

    assert '"email"' not in serialized
    assert '"token"' not in serialized
    assert '"password"' not in serialized
    assert '"username"' not in serialized
    assert '"clan_name"' not in serialized


def test_custom_simulation_uses_editable_parameters_and_map_adjacency():
    catalog = simulation_catalog()
    result = BalanceSimulationService().run_custom(
        catalog,
        days=14,
        starting_territory_ids=[1],
        active_members=17,
        capture_interval_days=4,
        strategy_name="economic",
    )

    assert result["parameters"]["active_members"] == 17
    assert result["parameters"]["strategy"] == "economic"
    assert result["timeline"][0]["day"] == 0
    assert result["timeline"][-1]["day"] == 14
    assert set(result["captured_territory_ids"]).isdisjoint({20})
    assert all(
        territory_id in {territory.id for territory in catalog.territories}
        for territory_id in result["final_territory_ids"]
    )


def test_strategic_sandbox_models_economy_war_trade_and_map_routes():
    catalog = simulation_catalog()
    payload = StrategicSandboxRequest.model_validate({
        "economy": {
            "days": 7,
            "active_members": 12,
            "starting_territory_ids": [1, 2],
            "starting_resources": dict(catalog.starting_resources),
            "capture_interval_days": 4,
            "strategy": "balanced",
            "production_multiplier_percent": 120,
            "cost_multiplier_percent": 90,
        },
        "war": {
            "source_territory_id": 4,
            "target_territory_id": 8,
            "route_mode": "sea",
            "attacker_rating": 1150,
            "defender_rating": 1000,
            "match_count": 12,
            "team_size": 2,
            "attacker_naval_level": 3,
            "defender_fortification_level": 2,
        },
        "trade": {
            "source_territory_id": 4,
            "target_territory_id": 8,
            "route_mode": "sea",
            "give_resource": "wood",
            "give_amount": 30,
            "receive_resource": "iron",
            "receive_amount": 18,
            "disruption_risk_percent": 10,
        },
    })

    result = StrategicSimulationService().run(catalog, payload)

    assert result["rule_set"] == {"id": 7, "version": 4}
    assert result["economy"]["scenario"]["parameters"]["days"] == 7
    assert result["economy"]["delta_from_current_rules"]["resources"]
    assert result["war"]["possible"] is True
    assert result["war"]["route"]["mode"] == "sea"
    assert round(sum(result["war"]["war_outcome_probability"].values()), 3) == 1
    assert result["trade"]["possible"] is True
    assert result["trade"]["shipping_gold"]["total"] > 0
    assert result["trade"]["risk_model"]["expected_receive_delivered"] == 16.2
    assert result["trade"]["map"]["route_ids"] == [4, 8]

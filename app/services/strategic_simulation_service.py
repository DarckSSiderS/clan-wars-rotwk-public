from __future__ import annotations

from collections import deque
from dataclasses import replace
from math import comb
from types import MappingProxyType
from typing import Any

from app.schemas.balance_simulation import (
    EconomyScenarioInput,
    StrategicSandboxRequest,
    TradeScenarioInput,
    WarScenarioInput,
)
from app.services.balance_simulation_catalog import BalanceSimulationCatalog
from app.services.balance_simulation_service import BalanceSimulationService
from app.services.elo_service import expected_score, winner_territory_points
from app.services.market_service import ClanMarketService
from app.services.war_service import apply_war_power_modifier


RESOURCE_NAMES = ("gold", "iron", "wood", "food", "mithril")


class StrategicSimulationService:
    """Read-only sandbox that uses the current campaign rule snapshot."""

    def run(
        self,
        catalog: BalanceSimulationCatalog,
        request: StrategicSandboxRequest,
    ) -> dict[str, Any]:
        return {
            "rule_set": {
                "id": catalog.rule_set_id,
                "version": catalog.rule_version,
            },
            "catalog": self._catalog_payload(catalog),
            "economy": self._simulate_economy(catalog, request.economy),
            "war": self._simulate_war(catalog, request.war),
            "trade": self._simulate_trade(catalog, request.trade),
            "disclaimer": (
                "The sandbox never writes to the campaign. Results are projections "
                "from the selected parameters and the referenced rule version."
            ),
        }

    @staticmethod
    def _catalog_payload(catalog: BalanceSimulationCatalog) -> dict[str, Any]:
        return {
            "territories": [
                {
                    "id": territory.id,
                    "name": territory.name,
                    "region": territory.region,
                    "resource_type": territory.resource_type,
                    "resource_output": territory.resource_output,
                    "resource_wealth": territory.resource_wealth,
                    "influence_value": territory.influence_value,
                    "required_influence": territory.required_influence,
                    "stronghold_power": territory.stronghold_power,
                    "has_port": territory.has_port,
                    "is_coastal": territory.is_coastal,
                    "adjacent_territory_ids": list(territory.adjacent_territory_ids),
                    "svg_path_data": territory.svg_path_data,
                }
                for territory in catalog.territories
            ],
            "starting_resources": dict(catalog.starting_resources),
            "rules": {
                key: catalog.rules[key]
                for key in (
                    "TERRITORY_LEVEL_BONUS_PERCENT",
                    "PORT_LEVEL_BONUS_PERCENT",
                    "FLEET_LEVEL_BONUS_PERCENT",
                    "WAR_MODIFIER_CAP_PERCENT",
                    "WAR_TEAM_SIZE_BONUS_STEP_PERCENT",
                    "WAR_FULL_CLAN_TEAM_BONUS_PERCENT",
                    "CARAVAN_HOURS_PER_STEP",
                    "CARAVAN_SEA_HOURS_PER_STEP",
                )
            },
        }

    def _simulate_economy(
        self,
        catalog: BalanceSimulationCatalog,
        params: EconomyScenarioInput,
    ) -> dict[str, Any]:
        baseline_catalog = self._adjusted_catalog(
            catalog,
            params,
            production_percent=100,
            cost_percent=100,
        )
        custom_catalog = self._adjusted_catalog(
            catalog,
            params,
            production_percent=params.production_multiplier_percent,
            cost_percent=params.cost_multiplier_percent,
        )
        service = BalanceSimulationService()
        common = {
            "days": params.days,
            "starting_territory_ids": params.starting_territory_ids,
            "active_members": params.active_members,
            "capture_interval_days": params.capture_interval_days,
            "strategy_name": params.strategy,
            "automatic_captures": params.automatic_captures,
        }
        baseline = service.run_custom(baseline_catalog, **common)
        scenario = service.run_custom(custom_catalog, **common)
        deltas = {
            resource: round(
                float(scenario["final"]["resources"][resource])
                - float(baseline["final"]["resources"][resource]),
                2,
            )
            for resource in RESOURCE_NAMES
        }
        return {
            "scenario": scenario,
            "baseline": {
                "final": baseline["final"],
                "timeline": baseline["timeline"],
            },
            "delta_from_current_rules": {
                "resources": deltas,
                "territories": (
                    scenario["final"]["territory_count"]
                    - baseline["final"]["territory_count"]
                ),
                "development_levels": (
                    scenario["final"]["total_development_levels"]
                    - baseline["final"]["total_development_levels"]
                ),
            },
        }

    @staticmethod
    def _adjusted_catalog(
        catalog: BalanceSimulationCatalog,
        params: EconomyScenarioInput,
        *,
        production_percent: int,
        cost_percent: int,
    ) -> BalanceSimulationCatalog:
        production_factor = production_percent / 100
        cost_factor = cost_percent / 100
        rules = dict(catalog.rules)
        for key, value in tuple(rules.items()):
            if "_COST" not in key or key.startswith("RELIC_"):
                continue
            rules[key] = max(0, round(float(value) * cost_factor))

        territories = tuple(
            replace(
                territory,
                resource_wealth=max(0, round(territory.resource_wealth * production_factor)),
                resource_output=max(1, round(territory.resource_output * production_factor)),
            )
            for territory in catalog.territories
        )
        relics = tuple(
            replace(
                relic,
                costs=MappingProxyType({
                    resource: max(0, round(float(amount) * cost_factor))
                    for resource, amount in relic.costs.items()
                }),
            )
            for relic in catalog.relics
        )
        starting_resources = MappingProxyType(
            params.starting_resources.model_dump()
        )
        return replace(
            catalog,
            rules=MappingProxyType(rules),
            territories=territories,
            relics=relics,
            starting_resources=starting_resources,
        )

    def _simulate_war(
        self,
        catalog: BalanceSimulationCatalog,
        params: WarScenarioInput,
    ) -> dict[str, Any]:
        source = self._territory(catalog, params.source_territory_id)
        target = self._territory(catalog, params.target_territory_id)
        route = self._select_route(catalog, source.id, target.id, params.route_mode)
        if route is None:
            return {
                "possible": False,
                "reason": "No valid route exists for the selected mode.",
                "map": {"source_id": source.id, "target_id": target.id, "route_ids": []},
            }

        rules = catalog.rules
        if route["mode"] == "sea":
            route_power = params.attacker_naval_level * (
                int(rules["PORT_LEVEL_BONUS_PERCENT"])
                + int(rules["FLEET_LEVEL_BONUS_PERCENT"])
            )
        else:
            route_power = (
                params.attacker_offense_level
                * int(rules["TERRITORY_LEVEL_BONUS_PERCENT"])
            )
        attacker_power = route_power + params.attacker_relic_power
        defender_power = (
            params.defender_fortification_level
            * int(rules["TERRITORY_LEVEL_BONUS_PERCENT"])
            + params.defender_development_level
            + params.defender_relic_power
        )
        attacker_probability = expected_score(
            params.attacker_rating,
            params.defender_rating,
            rules,
        )
        attacker_points = self._points_per_win(
            attacker_probability,
            attacker_power,
            params.team_size,
            params.clan_team,
            rules,
        )
        defender_points = self._points_per_win(
            1 - attacker_probability,
            defender_power,
            params.team_size,
            params.clan_team,
            rules,
        )
        outcome = self._war_outcome_distribution(
            params.match_count,
            attacker_probability,
            attacker_points,
            defender_points,
        )
        expected_attacker_score = round(
            params.match_count * attacker_probability * attacker_points,
            2,
        )
        expected_defender_score = round(
            params.match_count * (1 - attacker_probability) * defender_points,
            2,
        )
        return {
            "possible": True,
            "route": route,
            "influence_cost": target.required_influence,
            "match_win_probability": {
                "attacker": round(attacker_probability, 4),
                "defender": round(1 - attacker_probability, 4),
            },
            "power": {
                "attacker": attacker_power,
                "defender": defender_power,
                "cap": int(rules["WAR_MODIFIER_CAP_PERCENT"]),
            },
            "points_per_win": {
                "attacker": attacker_points,
                "defender": defender_points,
            },
            "expected_score": {
                "attacker": expected_attacker_score,
                "defender": expected_defender_score,
            },
            "war_outcome_probability": outcome,
            "verdict": self._war_verdict(outcome["attacker"]),
            "map": {
                "source_id": source.id,
                "target_id": target.id,
                "route_ids": route["territory_ids"],
            },
        }

    @staticmethod
    def _points_per_win(probability, power, team_size, clan_team, rules) -> float:
        mode_multiplier = 1 + (
            max(0, team_size - 1)
            * float(rules["WAR_TEAM_SIZE_BONUS_STEP_PERCENT"])
            / 100
        )
        base = round(winner_territory_points(probability, rules) * mode_multiplier, 2)
        adjusted = apply_war_power_modifier(base, power, rules)
        if clan_team and team_size > 1:
            adjusted += round(
                adjusted * float(rules["WAR_FULL_CLAN_TEAM_BONUS_PERCENT"]) / 100,
                2,
            )
        return round(adjusted, 2)

    @staticmethod
    def _war_outcome_distribution(
        match_count: int,
        attacker_probability: float,
        attacker_points: float,
        defender_points: float,
    ) -> dict[str, float]:
        attacker = defender = draw = 0.0
        for attacker_wins in range(match_count + 1):
            probability = (
                comb(match_count, attacker_wins)
                * attacker_probability ** attacker_wins
                * (1 - attacker_probability) ** (match_count - attacker_wins)
            )
            attacker_score = attacker_wins * attacker_points
            defender_score = (match_count - attacker_wins) * defender_points
            if abs(attacker_score - defender_score) < 1e-9:
                draw += probability
            elif attacker_score > defender_score:
                attacker += probability
            else:
                defender += probability
        return {
            "attacker": round(attacker, 4),
            "defender": round(defender, 4),
            "draw": round(draw, 4),
        }

    @staticmethod
    def _war_verdict(attacker_probability: float) -> str:
        if attacker_probability >= 0.7:
            return "attacker_advantage"
        if attacker_probability <= 0.3:
            return "defender_advantage"
        return "uncertain"

    def _simulate_trade(
        self,
        catalog: BalanceSimulationCatalog,
        params: TradeScenarioInput,
    ) -> dict[str, Any]:
        source = self._territory(catalog, params.source_territory_id)
        target = self._territory(catalog, params.target_territory_id)
        selected = self._select_route(catalog, source.id, target.id, params.route_mode)
        alternatives = [
            route
            for route in (
                self._select_route(catalog, source.id, target.id, "land"),
                self._select_route(catalog, source.id, target.id, "sea"),
            )
            if route is not None
        ]
        if selected is None:
            return {
                "possible": False,
                "reason": "No delivery route exists for the selected mode.",
                "alternatives": alternatives,
                "map": {"source_id": source.id, "target_id": target.id, "route_ids": []},
            }

        creator_shipping = ClanMarketService.shipping_cost(
            selected["steps"],
            params.give_amount,
            catalog.rules,
        )
        accepter_shipping = ClanMarketService.shipping_cost(
            selected["steps"],
            params.receive_amount,
            catalog.rules,
        )
        hours_per_step = int(
            catalog.rules[
                "CARAVAN_SEA_HOURS_PER_STEP"
                if selected["mode"] == "sea"
                else "CARAVAN_HOURS_PER_STEP"
            ]
        )
        delivery_factor = (100 - params.disruption_risk_percent) / 100
        expected_give = round(params.give_amount * delivery_factor, 2)
        expected_receive = round(params.receive_amount * delivery_factor, 2)
        return {
            "possible": True,
            "route": selected,
            "alternatives": alternatives,
            "eta_hours": selected["steps"] * hours_per_step,
            "shipping_gold": {
                "creator": creator_shipping,
                "accepter": accepter_shipping,
                "total": creator_shipping + accepter_shipping,
            },
            "cargo": {
                "give_resource": params.give_resource,
                "give_amount": params.give_amount,
                "receive_resource": params.receive_resource,
                "receive_amount": params.receive_amount,
                "nominal_rate": round(params.receive_amount / params.give_amount, 4),
            },
            "risk_model": {
                "disruption_risk_percent": params.disruption_risk_percent,
                "expected_give_delivered": expected_give,
                "expected_receive_delivered": expected_receive,
                "note": "Risk is a what-if parameter; live caravans currently deliver all reserved cargo.",
            },
            "map": {
                "source_id": source.id,
                "target_id": target.id,
                "route_ids": selected["territory_ids"],
            },
        }

    @staticmethod
    def _territory(catalog: BalanceSimulationCatalog, territory_id: int):
        territory = next(
            (item for item in catalog.territories if item.id == territory_id),
            None,
        )
        if territory is None:
            raise LookupError(f"Playable territory {territory_id} does not exist.")
        return territory

    def _select_route(
        self,
        catalog: BalanceSimulationCatalog,
        source_id: int,
        target_id: int,
        requested_mode: str,
    ) -> dict[str, Any] | None:
        options = []
        if requested_mode in {"auto", "land"}:
            land_ids = self._land_route(catalog, source_id, target_id)
            if land_ids:
                options.append({
                    "mode": "land",
                    "steps": max(1, len(land_ids) - 1),
                    "territory_ids": land_ids,
                })
        if requested_mode in {"auto", "sea"}:
            source = self._territory(catalog, source_id)
            target = self._territory(catalog, target_id)
            if source.has_port and target.has_port:
                options.append({
                    "mode": "sea",
                    "steps": 2,
                    "territory_ids": [source_id, target_id],
                })
        if not options:
            return None
        return min(
            options,
            key=lambda route: (route["steps"], 0 if route["mode"] == "land" else 1),
        )

    @staticmethod
    def _land_route(
        catalog: BalanceSimulationCatalog,
        source_id: int,
        target_id: int,
    ) -> list[int] | None:
        territory_ids = {territory.id for territory in catalog.territories}
        graph = {territory_id: set() for territory_id in territory_ids}
        for territory in catalog.territories:
            for neighbor_id in territory.adjacent_territory_ids:
                if neighbor_id not in territory_ids:
                    continue
                graph[territory.id].add(neighbor_id)
                graph[neighbor_id].add(territory.id)
        queue = deque([source_id])
        previous: dict[int, int | None] = {source_id: None}
        while queue:
            current = queue.popleft()
            if current == target_id:
                break
            for neighbor_id in sorted(graph[current]):
                if neighbor_id in previous:
                    continue
                previous[neighbor_id] = current
                queue.append(neighbor_id)
        if target_id not in previous:
            return None
        route = []
        cursor: int | None = target_id
        while cursor is not None:
            route.append(cursor)
            cursor = previous[cursor]
        route.reverse()
        return route

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from collections.abc import Mapping

from sqlalchemy.orm import Session, joinedload

from app.core.campaign_rules import default_campaign_rule_values
from app.core.economy_balance import is_admin_territory_name
from app.models.campaign import CampaignRuleSet
from app.models.clan_asset import ClanAsset
from app.models.territory import Territory
from app.services.clan_economy_service import REGION_RESOURCES


ResourceValues = Mapping[str, int | float]


@dataclass(frozen=True)
class TerritorySimulationInput:
    id: int
    name: str
    region: str
    resource_wealth: int
    influence_value: int
    population: int
    resource_type: str
    resource_output: int
    secondary_resource_type: str | None
    is_coastal: bool
    has_port: bool
    required_influence: int
    required_territories: int
    stronghold_power: int
    adjacent_territory_ids: tuple[int, ...]
    svg_path_data: str | None = None

    @property
    def is_great_stronghold(self) -> bool:
        return self.stronghold_power > 0

    @property
    def prosperity_score(self) -> int:
        return max(
            1,
            int(
                self.resource_wealth
                + self.population / 1000
                + self.stronghold_power * 40
            ),
        )


@dataclass(frozen=True)
class RelicSimulationInput:
    id: int
    key: str
    name: str
    bonus_type: str
    bonus_value: int
    costs: ResourceValues
    required_influence: tuple[int, int, int]
    max_level: int


@dataclass(frozen=True)
class BalanceSimulationCatalog:
    rule_set_id: int
    rule_version: int
    rules: ResourceValues
    territories: tuple[TerritorySimulationInput, ...]
    relics: tuple[RelicSimulationInput, ...]
    starting_resources: ResourceValues


def _normalized_resource_type(territory: Territory) -> str:
    resource_type = (territory.resource_type or "").strip().lower()
    if resource_type not in {"iron", "wood", "food", "mithril"}:
        return REGION_RESOURCES.get((territory.region or "").strip().lower(), "iron")
    return resource_type


def _normalized_resource_output(territory: Territory, rules: ResourceValues) -> int:
    if territory.resource_output:
        return max(1, int(territory.resource_output))
    strategic_value = float(territory.strategic_value or 1)
    return max(
        int(rules["TERRITORY_MIN_RESOURCE_OUTPUT"]),
        int(territory.resource_wealth or 0)
        // int(rules["TERRITORY_RESOURCE_WEALTH_DIVISOR"])
        + int(strategic_value),
    )


def _secondary_resource(territory: Territory, primary: str) -> str | None:
    if not territory.is_great_stronghold:
        return None
    secondary = (territory.secondary_resource_type or "").strip().lower()
    if secondary and secondary != primary:
        return secondary
    return next(
        resource
        for resource in ("iron", "wood", "food", "mithril")
        if resource != primary
    )


class BalanceSimulationCatalogLoader:
    """Load immutable simulation inputs without mutating SQLAlchemy entities."""

    @staticmethod
    def _rule_row(db: Session, rule_version: int | None) -> CampaignRuleSet:
        query = db.query(CampaignRuleSet)
        if rule_version is None:
            row = query.filter(CampaignRuleSet.is_active.is_(True)).one_or_none()
            if row is None:
                raise LookupError("No active campaign rule set exists.")
            return row
        row = query.filter(CampaignRuleSet.version == rule_version).one_or_none()
        if row is None:
            raise LookupError(f"Campaign rule version {rule_version} does not exist.")
        return row

    def load(
        self,
        db: Session,
        *,
        rule_version: int | None = None,
    ) -> BalanceSimulationCatalog:
        rule_row = self._rule_row(db, rule_version)
        normalized_rules = default_campaign_rule_values()
        normalized_rules.update(dict(rule_row.values))
        rules = MappingProxyType(normalized_rules)

        territory_rows = (
            db.query(Territory)
            .options(joinedload(Territory.owner_clan))
            .order_by(Territory.id.asc())
            .all()
        )
        territories: list[TerritorySimulationInput] = []
        for row in territory_rows:
            if not row.is_playable or is_admin_territory_name(row.name):
                continue
            if row.owner_clan is not None and row.owner_clan.is_admin_clan:
                continue
            primary_resource = _normalized_resource_type(row)
            territories.append(
                TerritorySimulationInput(
                    id=int(row.id),
                    name=str(row.name),
                    region=str(row.region or ""),
                    resource_wealth=max(0, int(row.resource_wealth or 0)),
                    influence_value=max(0, int(row.influence_value or 0)),
                    population=max(0, int(row.population or 0)),
                    resource_type=primary_resource,
                    resource_output=_normalized_resource_output(row, rules),
                    secondary_resource_type=_secondary_resource(row, primary_resource),
                    is_coastal=bool(row.is_coastal),
                    has_port=bool(row.has_port),
                    required_influence=max(0, int(row.required_influence or 0)),
                    required_territories=max(0, int(row.required_territories or 0)),
                    stronghold_power=max(0, int(row.stronghold_power or 0)),
                    adjacent_territory_ids=tuple(
                        sorted(int(value) for value in (row.adjacent_territory_ids or []))
                    ),
                    svg_path_data=str(row.svg_path_data or "") or None,
                )
            )

        relic_rows = (
            db.query(ClanAsset)
            .filter(ClanAsset.is_available.is_(True))
            .order_by(ClanAsset.key.asc(), ClanAsset.id.asc())
            .all()
        )
        relics = tuple(
            RelicSimulationInput(
                id=int(row.id),
                key=str(row.key),
                name=str(row.name),
                bonus_type=str(row.bonus_type),
                bonus_value=int(row.bonus_value or 0),
                costs=MappingProxyType({
                    resource: max(0, int(getattr(row, f"{resource}_cost") or 0))
                    for resource in ("gold", "iron", "wood", "food", "mithril")
                }),
                required_influence=(
                    max(0, int(row.required_influence_level_1 or 0)),
                    max(0, int(row.required_influence_level_2 or 0)),
                    max(0, int(row.required_influence_level_3 or 0)),
                ),
                max_level=max(1, min(3, int(row.max_level or 3))),
            )
            for row in relic_rows
        )

        if not territories:
            raise LookupError("No playable territories exist for balance simulation.")
        if not relics:
            raise LookupError("No available relic catalog exists for balance simulation.")

        starting_resources = MappingProxyType({
            resource: int(rules[f"CAMPAIGN_STARTING_{resource.upper()}"])
            for resource in ("gold", "iron", "wood", "food", "mithril")
        } | {
            "influence": int(rules["CAMPAIGN_STARTING_INFLUENCE"]),
        })
        return BalanceSimulationCatalog(
            rule_set_id=int(rule_row.id),
            rule_version=int(rule_row.version),
            rules=rules,
            territories=tuple(territories),
            relics=relics,
            starting_resources=starting_resources,
        )

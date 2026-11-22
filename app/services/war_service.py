from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from dataclasses import dataclass
from typing import List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.models.clan import Clan, ClanMember
from app.models.diplomacy import ClanDiplomaticRelation
from app.models.external_identity import ExternalPlayerAlias, ExternalPlayerIdentity
from app.models.match import Match
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanTimeout, ClanWar, ClanWarMatchResult, ClanWarParticipant
from app.models.worker import WorkerHeartbeat
from app.config import settings
from app.core.permissions import ClanPermission, require_clan_permission
from app.core.time import as_utc, utc_now
from app.core.campaign_mode import INTERSEASON_MESSAGE, is_interseason
from app.repositories.war_repository import (
    WarTerritoryRepository,
    ClanWarRepository,
    ClanWarParticipantRepository,
    ClanTimeoutRepository,
)
from app.repositories.clan_repository import ClanRepository
from app.repositories.user_repository import UserRepository
from app.core.exceptions import (
    TerritoryNotFoundException,
    ClanWarNotFoundException,
    ClanNotFoundException,
    UserNotFoundException,
    InsufficientPermissionsException,
    WarCreationException,
)
from app.schemas.war import TerritoryCreate, TerritoryUpdate, ClanWarCreate, ClanWarParticipantCreate
from app.services.clan_economy_service import ClanEconomyService
from app.services.clan_attack_point_service import (
    AttackPointsExhausted,
    ClanAttackPointService,
)
from app.services.clan_level_service import ClanLevelService
from app.services.clan_membership_service import ClanMembershipService
from app.services.match_eligibility_service import ranked_1v1_rejection_reason
from app.services.territory_ownership_service import TerritoryOwnershipService
from app.services.elo_service import (
    PATCH_ALL,
    expected_score,
    get_patch_family,
    is_unverified_rating,
    winner_territory_points,
)
from app.services.campaign_rule_service import CampaignRuleService
from app.services.operation_service import AdminAuditService
from app.services.war_deployment_service import (
    DeploymentConflict,
    SquadValidationError,
    WarDeploymentService,
)
from app.services.notification_service import notification_service


LEGACY_WAR_WIN_POINTS = 3
LEGACY_WAR_LOSS_POINTS = 1
PROTECTED_TERRITORY_NAMES = frozenset({"Тол-Фалас"})


@dataclass(frozen=True)
class WarMatchSideContext:
    clan_id: int | None
    deployment_id: int | None
    team_size: int
    eligible_users: tuple[User, ...]
    participation_share: float
    full_clan_bonus_eligible: bool
    eligibility_code: str


def get_attack_influence_cost(territory: Territory) -> int:
    return max(0, int(territory.required_influence or 0))


def clans_are_allied(db: Session, first_clan_id: int, second_clan_id: int) -> bool:
    low_id, high_id = sorted((int(first_clan_id), int(second_clan_id)))
    return db.query(ClanDiplomaticRelation.id).filter(
        ClanDiplomaticRelation.clan_low_id == low_id,
        ClanDiplomaticRelation.clan_high_id == high_id,
        ClanDiplomaticRelation.status == "allied",
    ).first() is not None


class TerritoryService:
    """Сервис для работы с территориями"""

    def __init__(self):
        self.territory_repo = WarTerritoryRepository()

    def get_territory(self, db: Session, territory_id: int):
        territory = self.territory_repo.get(db, territory_id)
        if not territory:
            raise TerritoryNotFoundException(territory_id)
        return territory

    def get_territories(self, db: Session, skip: int = 0, limit: int = 100) -> List:
        return self.territory_repo.get_multi(db, skip=skip, limit=limit)

    def get_available_territories(self, db: Session) -> List:
        return self.territory_repo.get_available_territories(db)

    def create_territory(self, db: Session, territory_data: TerritoryCreate):
        return self.territory_repo.create(db, obj_in=territory_data)

    def update_territory(self, db: Session, territory_id: int, territory_data: TerritoryUpdate):
        territory = self.get_territory(db, territory_id)
        return self.territory_repo.update(db, db_obj=territory, obj_in=territory_data)

    def delete_territory(self, db: Session, territory_id: int):
        self.get_territory(db, territory_id)
        return self.territory_repo.remove(db, id=territory_id)


def apply_war_power_modifier(
    base_points: float,
    power_percent: int,
    rules: Mapping[str, int | float],
) -> float:
    capped_power = min(
        int(rules["WAR_MODIFIER_CAP_PERCENT"]),
        max(0, power_percent or 0),
    )
    return round(base_points * (1 + capped_power / 100), 2)


class ClanWarService:
    """Сервис клановых войн и учета матчей в прогресс территорий."""

    def __init__(self):
        self.war_repo = ClanWarRepository()
        self.territory_repo = WarTerritoryRepository()
        self.clan_repo = ClanRepository()
        self.participant_repo = ClanWarParticipantRepository()
        self.timeout_repo = ClanTimeoutRepository()
        self.economy = ClanEconomyService()
        self.membership_history = ClanMembershipService()
        self.ownership = TerritoryOwnershipService()
        self.rule_service = CampaignRuleService()
        self.level_service = ClanLevelService()
        self.attack_points = ClanAttackPointService()
        self.deployments = WarDeploymentService()
        self.audit = AdminAuditService()

    def get_war(self, db: Session, war_id: int):
        war = self.war_repo.get(db, war_id)
        if not war:
            raise ClanWarNotFoundException(war_id)
        return war

    def get_active_wars(self, db: Session) -> List:
        self.complete_expired_wars(db)
        return self.war_repo.get_active_wars(db)

    def get_wars(self, db: Session, *, skip: int = 0, limit: int = 100) -> List:
        self.complete_expired_wars(db)
        return self.war_repo.get_wars(db, skip=skip, limit=limit)

    def get_wars_by_territory(self, db: Session, territory_id: int) -> List:
        self.complete_expired_wars(db)
        return self.war_repo.get_wars_by_territory(db, territory_id)

    def get_wars_by_clan(self, db: Session, clan_id: int) -> List:
        self.complete_expired_wars(db)
        return self.war_repo.get_wars_by_clan(db, clan_id)

    def serialize_war(self, db: Session, war: ClanWar) -> dict:
        from app.models.war_adjustment import WarScoreAdjustment
        adjustments = db.query(WarScoreAdjustment).filter_by(war_id=war.id).order_by(WarScoreAdjustment.id.desc()).all()
        rules = war.rules_snapshot or self.rule_service.get_active(db).values
        scores = self._get_clan_scores(db, war)
        match_breakdown = self._serialize_match_results(db, war)
        deployment_tracking = war.scoring_version == "elo_team_v3_squads"
        side_groups = self.deployments.public_side_groups(db, war)
        winner = war.winner_clan or (self.clan_repo.get(db, war.winner_clan_id) if war.winner_clan_id else None)
        best_attacker_score = next(
            (score["wins"] for score in scores if score["clan_id"] == war.attacking_clan_id),
            0,
        )
        progress_percent = 0
        if war.war_type == "neutral_capture" and war.required_wins:
            progress_percent = min(100, round(best_attacker_score / war.required_wins * 100))

        days_remaining = None
        if war.ends_at and war.status == "active":
            days_remaining = max(
                0,
                int((as_utc(war.ends_at) - utc_now()).total_seconds() // 86400) + 1,
            )

        return {
            "id": war.id,
            "territory_id": war.territory_id,
            "source_territory_id": war.source_territory_id,
            "territory_name": war.territory.name if war.territory else f"Территория #{war.territory_id}",
            "attacking_clan_id": war.attacking_clan_id,
            "attacking_clan_name": war.attacking_clan.name if war.attacking_clan else "Удалённый клан",
            "attacking_clan_avatar_url": (
                war.attacking_clan.avatar_url if war.attacking_clan else None
            ),
            "attacking_clan_map_emblem_url": (
                war.attacking_clan.map_emblem_url if war.attacking_clan else None
            ),
            "attacking_clan_map_color": (
                war.attacking_clan.map_color if war.attacking_clan else None
            ),
            "defending_clan_id": war.defending_clan_id,
            "defending_clan_name": war.defending_clan.name if war.defending_clan else ("Удалённый клан" if war.war_type == "territory_attack" else None),
            "defending_clan_avatar_url": (
                war.defending_clan.avatar_url if war.defending_clan else None
            ),
            "defending_clan_map_emblem_url": (
                war.defending_clan.map_emblem_url if war.defending_clan else None
            ),
            "defending_clan_map_color": (
                war.defending_clan.map_color if war.defending_clan else None
            ),
            "winner_clan_id": war.winner_clan_id,
            "winner_clan_name": winner.name if winner else None,
            "war_type": war.war_type,
            "status": war.status,
            "required_wins": war.required_wins,
            "started_at": war.started_at,
            "ends_at": war.ends_at,
            "ended_at": war.ended_at,
            "clan_scores": scores,
            "score_adjustments": [{"id": row.id, "clan_id": row.clan_id, "points": row.points, "reason": row.reason, "created_at": row.created_at} for row in adjustments],
            "match_breakdown": match_breakdown,
            "tracked_matches": sum(
                1 for result in match_breakdown if result["is_counted"]
            ),
            "rejected_matches": sum(
                1 for result in match_breakdown if not result["is_counted"]
            ),
            "progress_percent": progress_percent,
            "attacker_power": war.attacker_power or 0,
            "defender_power": war.defender_power or 0,
            "influence_cost": war.influence_cost or 0,
            "attack_route": war.attack_route or "land",
            "attacker_patch": war.attacker_patch or PATCH_ALL,
            "defender_patch": (
                war.defender_patch or PATCH_ALL
                if war.defending_clan_id else None
            ),
            "scoring_version": war.scoring_version or "legacy",
            "deployment_tracking": deployment_tracking,
            "side_groups": side_groups,
            "days_remaining": days_remaining,
            "scoring_rules": {
                "base_points": int(rules["WAR_ELO_BASE_POINTS"]),
                "minimum_win_points": int(rules["WAR_ELO_MIN_POINTS"]),
                "maximum_win_points": int(rules["WAR_ELO_MAX_POINTS"]),
                "loss_points": 0,
                "duration_hours": int(rules["WAR_DURATION_HOURS"]),
                "minimum_match_minutes": int(rules["WAR_MIN_MATCH_DURATION_SECONDS"]) // 60,
                "ranked_only": True,
                "clanmate_matches": "excluded",
                "opponent_clan_required": False,
                "tie_breaker": "defender_on_equal_points",
            },
        }

    def get_war_readiness(
        self,
        db: Session,
        clan_id: int,
        current_user: User,
    ) -> dict:
        clan, _ = require_clan_permission(
            db,
            clan_id,
            current_user,
            ClanPermission.DECLARE_WAR,
        )
        rule_set = self.rule_service.get_active(db)
        now = utc_now()
        level = self.level_service.evaluate(
            db,
            clan,
            rule_set=rule_set,
            now=now,
            record=False,
        )
        points = self.attack_points.status(
            db,
            clan,
            capacity=level.attack_capacity,
            now=now,
        )
        candidates = self.deployments.candidates(
            db,
            clan.id,
            activity={},
        )
        warlord_count = sum(1 for candidate in candidates if candidate.is_warlord)
        return {
            "clan_id": clan.id,
            "level": asdict(level),
            "attack_points": asdict(points),
            "candidates": [asdict(candidate) for candidate in candidates],
            "minimum_squad_size": (
                1
                if level.level == 1
                else int(rule_set.values["CLAN_ATTACK_SQUAD_MIN_MEMBERS"])
            ),
            "warlord_limit": level.level,
            "warlord_count": warlord_count,
            "rule_version": rule_set.version,
        }

    def create_war(self, db: Session, war_data: ClanWarCreate, current_user: User):
        if is_interseason(db):
            raise InsufficientPermissionsException(INTERSEASON_MESSAGE)
        try:
            from app.services.cycle_runtime_service import CycleRuntimeService
            if CycleRuntimeService.owns_campaign(db):
                raise WarCreationException('cycle_orders_required',
                    'Атаки назначаются в плане отрядов текущего цикла.')
            membership = (
                db.query(ClanMember)
                .filter(ClanMember.user_id == current_user.id)
                .first()
            )
            if not membership:
                raise InsufficientPermissionsException(
                    "начать войну: пользователь не состоит в клане"
                )
            require_clan_permission(
                db,
                membership.clan_id,
                current_user,
                ClanPermission.DECLARE_WAR,
            )
            attacking_clan = (
                db.query(Clan)
                .filter(Clan.id == membership.clan_id)
                .with_for_update()
                .one()
            )
            rule_set = self.rule_service.get_active(db)
            if war_data.expected_rule_version != rule_set.version:
                raise WarCreationException(
                    "campaign_rules_changed",
                    "Правила кампании изменились. Обновите данные похода.",
                )
            now = utc_now()
            level = self.level_service.evaluate(
                db,
                attacking_clan,
                rule_set=rule_set,
                now=now,
                record=True,
            )
            point_status = self.attack_points.status(
                db,
                attacking_clan,
                capacity=level.attack_capacity,
                now=now,
            )
            if point_status.available <= 0:
                raise WarCreationException(
                    "attack_points_exhausted",
                    "У клана нет доступных очков атаки.",
                )
            warlord_count = (
                db.query(ClanMember)
                .filter(
                    ClanMember.clan_id == attacking_clan.id,
                    ClanMember.is_warlord.is_(True),
                )
                .count()
            )
            if warlord_count > level.level:
                raise WarCreationException(
                    "warlord_limit_exceeded",
                    "Сначала сократите число Воевод до лимита текущего уровня клана.",
                )

            territory = (
                db.query(Territory)
                .filter(Territory.id == war_data.territory_id)
                .with_for_update()
                .one_or_none()
            )
            if territory is None:
                raise TerritoryNotFoundException(war_data.territory_id)
            if not territory.is_playable:
                raise InsufficientPermissionsException(
                    "атаковать недоступную территорию кампании"
                )
            if territory.name in PROTECTED_TERRITORY_NAMES:
                raise InsufficientPermissionsException(
                    "атаковать защищенную административную территорию"
                )
            if territory.owner_clan_id == attacking_clan.id:
                raise InsufficientPermissionsException("атаковать собственную территорию")

            if territory.owner_clan_id:
                owner = (
                    db.query(Clan)
                    .filter(Clan.id == territory.owner_clan_id)
                    .with_for_update()
                    .one_or_none()
                )
                if owner is not None and owner.is_deleted:
                    # Archived ownership must not create a war that cleanup cancels.
                    territory.owner_clan_id = None
                    territory.owner_clan = None
                    territory.defending_clans = []
                    territory.status = "neutral"

            active_territory_wars = (
                db.query(ClanWar)
                .filter(
                    ClanWar.territory_id == territory.id,
                    ClanWar.status == "active",
                )
                .with_for_update()
                .all()
            )
            neutral_claim = (
                active_territory_wars[0]
                if len(active_territory_wars) == 1
                and active_territory_wars[0].war_type == "neutral_capture"
                and active_territory_wars[0].defending_clan_id is None
                and active_territory_wars[0].attacking_clan_id != attacking_clan.id
                else None
            )
            if active_territory_wars and neutral_claim is None:
                raise WarCreationException(
                    "war_state_changed",
                    "На территории уже сформирован конфликт из двух сторон.",
                )

            original_deployment = None
            if neutral_claim is not None:
                original_deployment = next(
                    (
                        deployment
                        for deployment in neutral_claim.deployments
                        if deployment.clan_id == neutral_claim.attacking_clan_id
                    ),
                    None,
                )
                if (
                    neutral_claim.scoring_version != "elo_team_v3_squads"
                    or original_deployment is None
                    or not neutral_claim.rules_snapshot
                ):
                    raise WarCreationException(
                        "legacy_war_not_challengeable",
                        "Старая заявка завершится по прежним правилам и не может быть оспорена.",
                    )

            self.economy.settle_clan(
                db,
                attacking_clan,
                rules=rule_set.values,
            )
            owned_territories = (
                db.query(Territory)
                .filter(Territory.owner_clan_id == attacking_clan.id)
                .all()
            )
            if (territory.required_territories or 0) > len(owned_territories):
                raise InsufficientPermissionsException(
                    f"похода на {territory.name}: требуется минимум "
                    f"{territory.required_territories} территорий"
                )

            def get_attack_route(source: Territory) -> Optional[str]:
                target_adjacent_ids = territory.adjacent_territory_ids or []
                source_adjacent_ids = source.adjacent_territory_ids or []
                if source.id in target_adjacent_ids or territory.id in source_adjacent_ids:
                    return "land"
                if source.has_port and territory.is_coastal:
                    return "sea"
                return None

            explicit_source = None
            if war_data.source_territory_id:
                explicit_source = next(
                    (
                        item
                        for item in owned_territories
                        if item.id == war_data.source_territory_id
                    ),
                    None,
                )
                if explicit_source is None:
                    raise InsufficientPermissionsException(
                        "использовать источник атаки, который не принадлежит клану"
                    )
                if get_attack_route(explicit_source) is None:
                    raise InsufficientPermissionsException(
                        "похода: до этой территории нет сухопутного или морского пути"
                    )
            source_territory = explicit_source or next(
                (
                    item
                    for item in owned_territories
                    if get_attack_route(item) is not None
                ),
                None,
            )
            if owned_territories and source_territory is None:
                raise InsufficientPermissionsException(
                    "похода: у клана нет подходящей исходной территории"
                )
            attack_route = (
                get_attack_route(source_territory) if source_territory else "land"
            )

            try:
                squad = self.deployments.validate_squad(
                    db,
                    attacking_clan.id,
                    war_data.squad_member_ids,
                    minimum_size=(
                        1
                        if level.level == 1
                        else int(rule_set.values["CLAN_ATTACK_SQUAD_MIN_MEMBERS"])
                    ),
                    warlord_user_id=war_data.warlord_user_id,
                )
            except SquadValidationError as exc:
                raise WarCreationException(
                    exc.code,
                    "Состав похода не прошёл проверку.",
                    status_code=409 if isinstance(exc, DeploymentConflict) else 422,
                    user_ids=list(exc.user_ids),
                ) from exc

            if neutral_claim is not None:
                war = neutral_claim
                defending_clan = (
                    db.query(Clan)
                    .filter(Clan.id == neutral_claim.attacking_clan_id)
                    .with_for_update()
                    .one()
                )
                defending_clan_id = defending_clan.id
                war_rules = dict(war.rules_snapshot)
                war_type = "territory_attack"
                required_wins = 0
            elif territory.owner_clan_id:
                defending_clan = (
                    db.query(Clan)
                    .filter(Clan.id == territory.owner_clan_id)
                    .with_for_update()
                    .one_or_none()
                )
                if defending_clan is None:
                    raise ClanNotFoundException(territory.owner_clan_id)
                defending_clan_id = defending_clan.id
                war_rules = dict(rule_set.values)
                war_type = "territory_attack"
                required_wins = 0
            else:
                defending_clan = None
                defending_clan_id = None
                war_rules = dict(rule_set.values)
                war_type = "neutral_capture"
                required_wins = war_data.required_wins or int(
                    war_rules["NEUTRAL_CAPTURE_REQUIRED_WINS"]
                )

            if defending_clan_id and clans_are_allied(
                db,
                attacking_clan.id,
                defending_clan_id,
            ):
                raise WarCreationException(
                    "allied_clans_cannot_fight",
                    "Нельзя объявить войну союзному клану. Сначала измените дипломатический статус.",
                )
            ends_at = now + timedelta(hours=int(war_rules["WAR_DURATION_HOURS"]))

            self.economy.prepare_territory(db, territory, rules=war_rules)
            if source_territory:
                self.economy.prepare_territory(db, source_territory, rules=war_rules)
            influence_cost = get_attack_influence_cost(territory)
            if (attacking_clan.territory_points or 0) < influence_cost:
                raise InsufficientPermissionsException(
                    f"объявления войны: нужно {influence_cost} влияния, "
                    f"доступно {attacking_clan.territory_points or 0}"
                )
            clan_bonuses = self.economy.get_clan_bonuses(db, attacking_clan.id)
            if attack_route == "sea":
                route_power = (
                    (source_territory.port_level or 0)
                    * int(war_rules["PORT_LEVEL_BONUS_PERCENT"])
                    + (source_territory.fleet_level or 0)
                    * int(war_rules["FLEET_LEVEL_BONUS_PERCENT"])
                )
            else:
                route_power = (
                    (source_territory.offense_level or 0)
                    * int(war_rules["TERRITORY_LEVEL_BONUS_PERCENT"])
                    if source_territory
                    else 0
                )
            attacker_power = route_power + clan_bonuses.get("attack_power", 0)
            defender_bonuses = (
                self.economy.get_clan_bonuses(db, defending_clan_id)
                if defending_clan_id
                else {}
            )
            if neutral_claim is None or "RELIC_BONUSES_BY_CLAN" not in war_rules:
                relic_bonuses_by_clan = {
                    str(attacking_clan.id): self.economy.get_relic_bonuses(
                        db, attacking_clan.id
                    )
                }
                if defending_clan_id:
                    relic_bonuses_by_clan[str(defending_clan_id)] = (
                        self.economy.get_relic_bonuses(db, defending_clan_id)
                    )
                war_rules["RELIC_BONUSES_BY_CLAN"] = relic_bonuses_by_clan
            defender_power = (
                (territory.fortifications or 0)
                * int(war_rules["TERRITORY_LEVEL_BONUS_PERCENT"])
                + (territory.development_level or 0)
                + defender_bonuses.get("defense_power", 0)
            )

            if neutral_claim is not None:
                self.deployments.transition_neutral_claim_to_defense(
                    db,
                    original_deployment,
                    now=now,
                )
                war.attacking_clan_id = attacking_clan.id
                war.defending_clan_id = defending_clan_id
                war.war_type = war_type
                war.required_wins = required_wins
                war.ends_at = ends_at
                war.source_territory_id = (
                    source_territory.id if source_territory else None
                )
                war.attacker_power = attacker_power
                war.defender_power = defender_power
                war.influence_cost = influence_cost
                war.attack_route = attack_route
                war.attacker_patch = attacking_clan.preferred_patch or PATCH_ALL
                war.defender_patch = defending_clan.preferred_patch or PATCH_ALL
                war.rules_snapshot = dict(war_rules)
                territory.attacking_clans.clear()
                territory.defending_clans.clear()
                self.deployments.create_attack(
                    db,
                    war,
                    attacking_clan,
                    squad,
                    source_territory_id=(
                        source_territory.id if source_territory else None
                    ),
                    territory_count=len(owned_territories),
                    actor_user_id=current_user.id,
                    rule_set=rule_set,
                    claim_sequence=2,
                    warlord_user_id=war_data.warlord_user_id,
                )
            else:
                war = ClanWar(
                    territory_id=territory.id,
                    attacking_clan_id=attacking_clan.id,
                    defending_clan_id=defending_clan_id,
                    war_type=war_type,
                    status="active",
                    required_wins=required_wins,
                    started_at=now,
                    ends_at=ends_at,
                    source_territory_id=(
                        source_territory.id if source_territory else None
                    ),
                    attacker_power=attacker_power,
                    defender_power=defender_power,
                    influence_cost=influence_cost,
                    attack_route=attack_route,
                    attacker_patch=attacking_clan.preferred_patch or PATCH_ALL,
                    defender_patch=(
                        defending_clan.preferred_patch or PATCH_ALL
                        if defending_clan
                        else None
                    ),
                    scoring_version="elo_team_v3_squads",
                    campaign_rule_set_id=rule_set.id,
                    rules_snapshot=dict(war_rules),
                )
                db.add(war)
                db.flush()
                self.deployments.create_attack(
                    db,
                    war,
                    attacking_clan,
                    squad,
                    source_territory_id=(
                        source_territory.id if source_territory else None
                    ),
                    territory_count=len(owned_territories),
                    actor_user_id=current_user.id,
                    rule_set=rule_set,
                    claim_sequence=1,
                    warlord_user_id=war_data.warlord_user_id,
                )
                if defending_clan_id:
                    self.deployments.create_whole_clan_defense(
                        db,
                        war,
                        defending_clan_id,
                        defense_rule="occupied_territory_owner",
                        rule_set=rule_set,
                        now=now,
                    )

            try:
                self.attack_points.spend(
                    db,
                    attacking_clan,
                    war=war,
                    actor_user_id=current_user.id,
                    level=level.level,
                    capacity=level.attack_capacity,
                    rule_set=rule_set,
                    now=now,
                )
            except AttackPointsExhausted as exc:
                raise WarCreationException(
                    "attack_points_exhausted",
                    "Очко атаки уже занято другой операцией.",
                ) from exc

            territory.status = "contested"
            if attacking_clan not in territory.attacking_clans:
                territory.attacking_clans.append(attacking_clan)
            if defending_clan and defending_clan not in territory.defending_clans:
                territory.defending_clans.append(defending_clan)
            self._ensure_war_participants(db, war)
            war_link = f"/battles/{war.id}"
            defending_name = defending_clan.name if defending_clan else "свободные земли"
            notification_service.create_for_clan(
                db,
                clan_id=attacking_clan.id,
                notification_type="war_started",
                title=f"Поход на «{territory.name}» начался",
                message=f"{attacking_clan.name} выступает против {defending_name}.",
                link_url=war_link,
                entity_type="clan_war",
                entity_id=war.id,
            )
            notification_service.create_for_clan(
                db,
                clan_id=defending_clan_id,
                notification_type="war_started",
                title=f"«{territory.name}» атакована",
                message=f"Клан {attacking_clan.name} начал поход на владения {defending_name}.",
                link_url=war_link,
                entity_type="clan_war",
                entity_id=war.id,
            )
            self.audit.record(
                db,
                actor_user_id=current_user.id,
                action="war_deployment_created",
                entity_type="clan_war",
                entity_id=war.id,
                after_data={
                    "clan_id": attacking_clan.id,
                    "squad_member_ids": list(war_data.squad_member_ids),
                    "warlord_user_id": war_data.warlord_user_id,
                    "rule_version": rule_set.version,
                    "level": level.level,
                    "attack_capacity": level.attack_capacity,
                },
                reason="clan_declared_war",
            )
            db.commit()
            db.refresh(war)
            return war
        except Exception:
            db.rollback()
            raise

    def update_war_status(self, db: Session, war_id: int, status: str):
        war = self.get_war(db, war_id)
        if status not in {"active", "completed", "canceled"}:
            raise InsufficientPermissionsException("установить неизвестный статус войны")
        war.status = status
        if status in {"completed", "canceled"} and not war.ended_at:
            war.ended_at = utc_now()
        db.commit()
        db.refresh(war)
        return war

    def end_war(self, db: Session, war_id: int, winner_clan_id: int):
        war = self.get_war(db, war_id)
        self.economy.ledger.lock_clans(db, [war.attacking_clan_id, war.defending_clan_id])
        db.refresh(war, with_for_update=True)
        winner = self.clan_repo.get(db, winner_clan_id)
        if not winner:
            raise ClanNotFoundException(winner_clan_id)
        return self._complete_war(db, war, winner_clan_id)

    def extend_war(
        self,
        db: Session,
        war_id: int,
        hours: int,
        *,
        commit: bool = True,
    ) -> ClanWar:
        war = self.get_war(db, war_id)
        if war.status != "active":
            raise InsufficientPermissionsException("продлить завершенную войну")
        base_time = max(
            as_utc(war.ends_at) if war.ends_at else utc_now(),
            utc_now(),
        )
        war.ends_at = base_time + timedelta(hours=hours)
        if commit:
            db.commit()
            db.refresh(war)
        else:
            db.flush()
        return war

    def cancel_war(
        self,
        db: Session,
        war_id: int,
        *,
        refund_attack: bool = True,
        commit: bool = True,
    ) -> ClanWar:
        war = self.get_war(db, war_id)
        if war.status != "active":
            raise InsufficientPermissionsException("отменить завершенную войну")

        ended_at = utc_now()
        war.status = "canceled"
        war.winner_clan_id = None
        war.ended_at = ended_at
        for participant in war.participants:
            participant.is_active = False
        territory = war.territory
        if territory:
            if war.attacking_clan in territory.attacking_clans:
                territory.attacking_clans.remove(war.attacking_clan)
            if war.defending_clan and war.defending_clan in territory.defending_clans:
                territory.defending_clans.remove(war.defending_clan)
            remaining_active = db.query(ClanWar).filter(
                ClanWar.territory_id == territory.id,
                ClanWar.status == "active",
                ClanWar.id != war.id,
            ).count()
            territory.status = (
                "contested" if remaining_active
                else "active" if territory.owner_clan_id
                else "neutral"
            )

        for deployment in war.deployments:
            self.deployments.release_attack_lock(
                db,
                deployment,
                now=ended_at,
            )

        if refund_attack:
            linked_spends = [
                spend
                for spend in war.attack_point_spends
                if spend.refunded_at is None and as_utc(spend.recover_at) > ended_at
            ]
            if linked_spends:
                for spend in linked_spends:
                    self.attack_points.refund(
                        db,
                        spend,
                        actor_user_id=None,
                        reason="war_canceled",
                        now=ended_at,
                    )
            else:
                legacy_refund = self.attack_points.refund_for_war(
                    db,
                    war,
                    actor_user_id=None,
                    reason="war_canceled",
                    now=ended_at,
                )
                if (
                    legacy_refund is None
                    and war.scoring_version == "elo_team_v2"
                    and war.attacking_clan
                ):
                    # Directly-created legacy rows in tests and very old data may
                    # predate the migration backfill.
                    war.attacking_clan.next_attack_at = None

        if commit:
            db.commit()
            db.refresh(war)
        else:
            db.flush()
        return war

    def cancel_active_wars_with_deleted_clans(
        self,
        db: Session,
        *,
        commit: bool = True,
    ) -> int:
        """Cancel stale active wars whose attacker or defender was archived."""
        orphaned_wars = (
            db.query(ClanWar)
            .filter(
                ClanWar.status == "active",
                or_(
                    ClanWar.attacking_clan.has(Clan.is_deleted.is_(True)),
                    ClanWar.defending_clan.has(Clan.is_deleted.is_(True)),
                ),
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        for war in orphaned_wars:
            self.cancel_war(db, war.id, refund_attack=True, commit=False)
        if orphaned_wars and commit:
            db.commit()
        return len(orphaned_wars)

    def reconcile_territory_war_sides(
        self,
        db: Session,
        *,
        commit: bool = True,
    ) -> int:
        """Keep map-side projections aligned with canonical active wars."""
        territories = db.query(Territory).with_for_update().all()
        active_wars = (
            db.query(ClanWar)
            .filter(ClanWar.status == "active")
            .all()
        )
        wars_by_territory: dict[int, list[ClanWar]] = {}
        for war in active_wars:
            wars_by_territory.setdefault(war.territory_id, []).append(war)

        repaired = 0
        for territory in territories:
            territory_wars = wars_by_territory.get(territory.id, [])
            expected_attackers = {
                war.attacking_clan.id: war.attacking_clan
                for war in territory_wars
                if war.attacking_clan and not war.attacking_clan.is_deleted
            }
            expected_defenders = {
                war.defending_clan.id: war.defending_clan
                for war in territory_wars
                if war.defending_clan and not war.defending_clan.is_deleted
            }
            current_attacker_ids = {clan.id for clan in territory.attacking_clans}
            current_defender_ids = {clan.id for clan in territory.defending_clans}
            projection_changed = (
                current_attacker_ids != set(expected_attackers)
                or current_defender_ids != set(expected_defenders)
            )
            if not projection_changed:
                continue

            territory.attacking_clans = list(expected_attackers.values())
            territory.defending_clans = list(expected_defenders.values())
            territory.status = (
                "contested"
                if territory_wars
                else "active"
                if territory.owner_clan_id
                else "neutral"
            )
            repaired += 1

        if repaired:
            if commit:
                db.commit()
            else:
                db.flush()
        return repaired

    def _match_team_contexts(
        self,
        db: Session,
        match: Match,
        played_at: datetime,
        rules: Mapping[str, int | float],
    ) -> dict:
        participants = [
            participant
            for participant in (match.participants or [])
            if not participant.is_observer
        ]
        if not participants:
            participants = [
                type("LegacyParticipant", (), {
                    "nickname": match.winner_player,
                    "is_winner": True,
                    "elo": match.winner_elo,
                })(),
                type("LegacyParticipant", (), {
                    "nickname": match.loser_player,
                    "is_winner": False,
                    "elo": match.loser_elo,
                })(),
            ]

        usernames = [participant.nickname for participant in participants]
        participant_uuids = [
            participant.player_uuid
            for participant in participants
            if getattr(participant, "player_uuid", None)
        ]
        identity_filters = []
        if participant_uuids:
            identity_filters.append(
                ExternalPlayerIdentity.external_uuid.in_(tuple(participant_uuids))
            )
        if usernames:
            identity_filters.append(
                ExternalPlayerIdentity.current_nickname.in_(tuple(usernames))
            )
        identities = (
            db.query(ExternalPlayerIdentity)
            .filter(or_(*identity_filters))
            .all()
            if identity_filters else []
        )
        aliases = (
            db.query(ExternalPlayerAlias)
            .filter(ExternalPlayerAlias.nickname.in_(tuple(usernames)))
            .all()
            if usernames else []
        )
        known_identity_ids = {identity.id for identity in identities}
        missing_identity_ids = {
            alias.identity_id for alias in aliases
        } - known_identity_ids
        if missing_identity_ids:
            identities.extend(
                db.query(ExternalPlayerIdentity)
                .filter(ExternalPlayerIdentity.id.in_(tuple(missing_identity_ids)))
                .all()
            )
        identity_by_id = {identity.id: identity for identity in identities}
        identity_user_ids = {
            identity.user_id for identity in identities
        } | {
            identity_by_id[alias.identity_id].user_id
            for alias in aliases
            if alias.identity_id in identity_by_id
        }
        users = (
            db.query(User)
            .filter(
                or_(
                    User.username.in_(tuple(usernames)),
                    User.id.in_(tuple(identity_user_ids)),
                )
            )
            .all()
            if usernames or identity_user_ids else []
        )
        users_by_name = {user.username.casefold(): user for user in users}
        users_by_id = {user.id: user for user in users}
        users_by_uuid = {
            identity.external_uuid: users_by_id[identity.user_id]
            for identity in identities
            if identity.user_id in users_by_id
        }
        for identity in identities:
            if identity.user_id in users_by_id:
                users_by_name[identity.current_nickname.casefold()] = users_by_id[
                    identity.user_id
                ]
        for alias in aliases:
            identity = identity_by_id.get(alias.identity_id)
            if identity and identity.user_id in users_by_id:
                users_by_name[alias.nickname.casefold()] = users_by_id[
                    identity.user_id
                ]
        contexts = {
            True: {
                "entries": [],
                "users": [],
                "clan_users": defaultdict(list),
                "verified_clan_users": defaultdict(list),
            },
            False: {
                "entries": [],
                "users": [],
                "clan_users": defaultdict(list),
                "verified_clan_users": defaultdict(list),
            },
        }

        for participant in participants:
            context = contexts[bool(participant.is_winner)]
            context["entries"].append(participant)
            user = users_by_uuid.get(
                getattr(participant, "player_uuid", None)
            ) or users_by_name.get(str(participant.nickname).casefold())
            if not user:
                continue
            context["users"].append(user)
            for clan_id in self.membership_history.clan_ids_at(db, user.id, played_at):
                context["clan_users"][clan_id].append(user)
                if user.external_identity_status == "verified":
                    context["verified_clan_users"][clan_id].append(user)

        for is_winner, context in contexts.items():
            ratings = [
                float(entry.elo)
                for entry in context["entries"]
                if entry.elo is not None
            ]
            fallback_rating = match.winner_elo if is_winner else match.loser_elo
            context["rating"] = (
                sum(ratings) / len(ratings)
                if ratings
                else float(
                    fallback_rating
                    if fallback_rating is not None
                    else rules["ELO_START_RATING"]
                )
            )
            context["team_size"] = max(1, len(context["entries"]))
            context["representative"] = context["users"][0] if context["users"] else None
            context["clan_ids"] = set(context["clan_users"])
        return contexts

    def _v3_side_context(
        self,
        db: Session,
        war: ClanWar,
        clan_id: int | None,
        played_at: datetime,
        team: dict,
    ) -> WarMatchSideContext:
        team_size = int(team["team_size"])
        if clan_id is None:
            return WarMatchSideContext(
                clan_id=None,
                deployment_id=None,
                team_size=team_size,
                eligible_users=(),
                participation_share=0.0,
                full_clan_bonus_eligible=False,
                eligibility_code="not_a_war_side",
            )
        allowed = self.deployments.eligible_side(db, war, clan_id, played_at)
        allowed_ids = {user.id for user in allowed.users}
        actual_users = team["verified_clan_users"].get(clan_id, [])
        eligible_users = tuple(
            user for user in actual_users if user.id in allowed_ids
        )
        participation_share = round(
            len(eligible_users) / max(1, team_size),
            6,
        )
        if eligible_users:
            eligibility_code = allowed.eligibility_code
        elif allowed.scope == "squad":
            eligibility_code = "not_assigned_to_attack_squad"
        else:
            eligibility_code = "not_eligible_for_whole_clan_defense"
        return WarMatchSideContext(
            clan_id=clan_id,
            deployment_id=allowed.deployment_id,
            team_size=team_size,
            eligible_users=eligible_users,
            participation_share=participation_share,
            full_clan_bonus_eligible=(
                bool(eligible_users) and len(eligible_users) == team_size
            ),
            eligibility_code=eligibility_code,
        )

    def record_match_result(
        self,
        db: Session,
        winner_player: str,
        loser_player: str,
        match_date: Optional[datetime] = None,
        match: Optional[Match] = None,
    ):
        """Учитывает завершенный матч во всех активных войнах участвующих кланов."""
        if not match:
            return
        active_rules = self.rule_service.get_active(db).values
        played_at = as_utc(match_date) or utc_now()
        teams = self._match_team_contexts(db, match, played_at, active_rules)
        winner_team = teams[True]
        loser_team = teams[False]
        winner = winner_team["representative"]
        loser = loser_team["representative"]
        if not winner or not loser:
            return
        winner_clan_ids = winner_team["clan_ids"]
        loser_clan_ids = loser_team["clan_ids"]
        if not winner_clan_ids or not loser_clan_ids:
            if not winner_clan_ids and not loser_clan_ids:
                return

        touched_wars = set()
        active_wars = self.war_repo.get_active_wars(db)
        # Purchases lock clans before territories. Finalization must use the same
        # order before taking a war lock and potentially transferring ownership.
        for war in active_wars:
            self.economy.ledger.lock_clans(db, [
                clan_id for active in active_wars
                for clan_id in (active.attacking_clan_id, active.defending_clan_id)
            ])
            # A deadline timer may have read this war concurrently with ingestion.
            db.refresh(war, with_for_update=True)
            if war.status != "active":
                continue
            rules = war.rules_snapshot or active_rules
            war_teams = self._match_team_contexts(db, match, played_at, rules)
            winner_team = war_teams[True]
            loser_team = war_teams[False]
            winner_clan_ids = winner_team["clan_ids"]
            loser_clan_ids = loser_team["clan_ids"]
            if war.started_at and played_at < as_utc(war.started_at):
                continue
            if war.ends_at and played_at > as_utc(war.ends_at):
                continue
            sides = {
                clan_id
                for clan_id in (war.attacking_clan_id, war.defending_clan_id)
                if clan_id is not None
            }
            winner_side_ids = sorted(winner_clan_ids & sides)
            loser_side_ids = sorted(loser_clan_ids & sides)
            if not winner_side_ids and not loser_side_ids:
                continue
            if match and db.query(ClanWarMatchResult).filter(
                ClanWarMatchResult.war_id == war.id,
                ClanWarMatchResult.match_id == match.id,
            ).first():
                continue

            winner_clan_id = winner_side_ids[0] if winner_side_ids else None
            loser_clan_id = loser_side_ids[0] if loser_side_ids else None
            rejection_reason = None
            if len(winner_side_ids) > 1 or len(loser_side_ids) > 1:
                rejection_reason = "Кланы этой войны играли в одной команде"
            if not rejection_reason:
                rejection_reason = self._match_rejection_reason(
                    war,
                    match,
                    winner_clan_ids,
                    loser_clan_ids,
                    rules=rules,
                )
            is_v3 = war.scoring_version == "elo_team_v3_squads"
            winner_side_context = (
                self._v3_side_context(
                    db,
                    war,
                    winner_clan_id,
                    played_at,
                    winner_team,
                )
                if is_v3 else None
            )
            loser_side_context = (
                self._v3_side_context(
                    db,
                    war,
                    loser_clan_id,
                    played_at,
                    loser_team,
                )
                if is_v3 else None
            )
            winner_users = (
                list(winner_side_context.eligible_users)
                if winner_side_context
                else winner_team["verified_clan_users"].get(winner_clan_id, [])
            )
            loser_users = (
                list(loser_side_context.eligible_users)
                if loser_side_context
                else loser_team["verified_clan_users"].get(loser_clan_id, [])
            )
            winner_is_eligible = bool(
                winner_clan_id
                and winner_users
            )
            loser_is_eligible = bool(
                loser_clan_id
                and loser_users
            )
            if not rejection_reason and not (winner_is_eligible or loser_is_eligible):
                rejection_reason = (
                    "Ни одна сторона матча не входит в разрешенную боевую группу"
                    if is_v3
                    else "Игровой аккаунт участника клана не подтвержден"
                )

            if rejection_reason:
                if match:
                    db.add(
                        self._build_match_result(
                            war=war,
                            match=match,
                            played_at=played_at,
                            winner=winner,
                            loser=loser,
                            winner_clan_id=winner_clan_id,
                            loser_clan_id=loser_clan_id,
                            is_counted=False,
                            rejection_reason=rejection_reason,
                            rules=rules,
                            winner_side_context=winner_side_context,
                            loser_side_context=loser_side_context,
                        )
                    )
                continue

            winner_points = self._score_war_side(
                db,
                war,
                winner_clan_id,
                winner_users[0],
                is_winner=True,
                match=match,
                users=winner_users,
                team_rating=winner_team["rating"],
                opponent_rating=loser_team["rating"],
                team_size=winner_team["team_size"],
                team_is_clan_only=(
                    winner_side_context.full_clan_bonus_eligible
                    if winner_side_context
                    else len(winner_users) == winner_team["team_size"]
                ),
                relic_participation_share=(
                    winner_side_context.participation_share
                    if winner_side_context else 1.0
                ),
                exact_distribution=is_v3,
                rules=rules,
            ) if winner_is_eligible else self._empty_match_points()
            loser_points = self._score_war_side(
                db,
                war,
                loser_clan_id,
                loser_users[0],
                is_winner=False,
                match=match,
                users=loser_users,
                team_rating=loser_team["rating"],
                opponent_rating=winner_team["rating"],
                team_size=loser_team["team_size"],
                team_is_clan_only=False,
                relic_participation_share=(
                    loser_side_context.participation_share
                    if loser_side_context else 1.0
                ),
                exact_distribution=is_v3,
                rules=rules,
            ) if loser_is_eligible else self._empty_match_points()
            if match:
                db.add(
                    self._build_match_result(
                        war=war,
                        match=match,
                        played_at=played_at,
                        winner=winner,
                        loser=loser,
                        winner_clan_id=winner_clan_id,
                        loser_clan_id=loser_clan_id,
                        winner_points=winner_points,
                        loser_points=loser_points,
                        rules=rules,
                        winner_side_context=winner_side_context,
                        loser_side_context=loser_side_context,
                    )
                )
            touched_wars.add(war.id)

        db.flush()
        for war_id in touched_wars:
            war = self.war_repo.get(db, war_id)
            if war and war.status == "active":
                self._maybe_complete_war(db, war)
        db.commit()

    def recalculate_active_war(
        self,
        db: Session,
        war_id: int,
        *,
        commit: bool = True,
        allow_finished: bool = False,
    ) -> dict:
        """Rebuilds one active territory war from its stored replay ledger."""
        war = self.get_war(db, war_id)
        rules = war.rules_snapshot or self.rule_service.get_active(db).values
        if war.status != "active" and not allow_finished:
            raise InsufficientPermissionsException(
                "пересчитать завершенную войну"
            )

        participants = db.query(ClanWarParticipant).filter(
            ClanWarParticipant.war_id == war.id,
        ).all()
        for participant in participants:
            participant.wins = 0
            participant.losses = 0
            participant.war_points = 0

        results = (
            db.query(ClanWarMatchResult)
            .filter(ClanWarMatchResult.war_id == war.id)
            .order_by(ClanWarMatchResult.played_at, ClanWarMatchResult.id)
            .all()
        )
        counted = 0
        rejected = 0
        is_v3 = war.scoring_version == "elo_team_v3_squads"

        for result in results:
            match = result.match
            winner = result.winner_user
            loser = result.loser_user
            teams = self._match_team_contexts(
                db,
                match,
                as_utc(result.played_at),
                rules,
            )
            winner_team = teams[True]
            loser_team = teams[False]
            winner_clan_ids = (
                {result.winner_clan_id}
                if result.winner_clan_id is not None else set()
            )
            loser_clan_ids = (
                {result.loser_clan_id}
                if result.loser_clan_id is not None else set()
            )
            rejection_reason = self._match_rejection_reason(
                war,
                match,
                winner_clan_ids,
                loser_clan_ids,
                rules=rules,
            )
            winner_side_context = (
                self._v3_side_context(
                    db,
                    war,
                    result.winner_clan_id,
                    as_utc(result.played_at),
                    winner_team,
                )
                if is_v3 else None
            )
            loser_side_context = (
                self._v3_side_context(
                    db,
                    war,
                    result.loser_clan_id,
                    as_utc(result.played_at),
                    loser_team,
                )
                if is_v3 else None
            )
            winner_users = (
                list(winner_side_context.eligible_users)
                if winner_side_context
                else winner_team["verified_clan_users"].get(
                    result.winner_clan_id, []
                )
            )
            loser_users = (
                list(loser_side_context.eligible_users)
                if loser_side_context
                else loser_team["verified_clan_users"].get(
                    result.loser_clan_id, []
                )
            )
            winner_is_eligible = bool(
                result.winner_clan_id
                and winner_users
            )
            loser_is_eligible = bool(
                result.loser_clan_id
                and loser_users
            )
            if not rejection_reason and not (winner_is_eligible or loser_is_eligible):
                rejection_reason = (
                    "Ни одна сторона матча не входит в разрешенную боевую группу"
                    if is_v3
                    else "Игровой аккаунт участника клана не подтвержден"
                )

            if result.admin_override is False:
                rejection_reason = (
                    "Исключено администратором: "
                    f"{result.admin_override_reason or 'причина указана в журнале аудита'}"
                )[:120]
            elif result.admin_override is True:
                rejection_reason = None
                # An explicit review can override automatic roster eligibility,
                # but only for the recorded player on an actual side of this war.
                sides = {war.attacking_clan_id, war.defending_clan_id} - {None}
                if not winner_users and winner and result.winner_clan_id in sides:
                    winner_users = [winner]
                    winner_is_eligible = True
                if not loser_users and loser and result.loser_clan_id in sides:
                    loser_users = [loser]
                    loser_is_eligible = True

            winner_points = self._empty_match_points()
            loser_points = self._empty_match_points()
            if not rejection_reason:
                if winner_is_eligible:
                    winner_points = self._score_war_side(
                        db,
                        war,
                        result.winner_clan_id,
                        winner_users[0],
                        is_winner=True,
                        match=match,
                        users=winner_users,
                        team_rating=winner_team["rating"],
                        opponent_rating=loser_team["rating"],
                        team_size=winner_team["team_size"],
                        team_is_clan_only=(
                            winner_side_context.full_clan_bonus_eligible
                            if winner_side_context
                            else len(winner_users) == winner_team["team_size"]
                        ),
                        relic_participation_share=(
                            winner_side_context.participation_share
                            if winner_side_context else 1.0
                        ),
                        exact_distribution=is_v3,
                        rules=rules,
                    )
                if loser_is_eligible:
                    loser_points = self._score_war_side(
                        db,
                        war,
                        result.loser_clan_id,
                        loser_users[0],
                        is_winner=False,
                        match=match,
                        users=loser_users,
                        team_rating=loser_team["rating"],
                        opponent_rating=winner_team["rating"],
                        team_size=loser_team["team_size"],
                        team_is_clan_only=False,
                        relic_participation_share=(
                            loser_side_context.participation_share
                            if loser_side_context else 1.0
                        ),
                        exact_distribution=is_v3,
                        rules=rules,
                    )
                counted += 1
            else:
                rejected += 1

            result.winner_base_points = winner_points["base_points"]
            result.winner_power_percent = winner_points["power_percent"]
            result.winner_power_bonus_points = winner_points["power_bonus_points"]
            result.winner_relic_bonus_points = winner_points["relic_bonus_points"]
            result.winner_total_points = winner_points["total_points"]
            result.loser_base_points = loser_points["base_points"]
            result.loser_power_percent = loser_points["power_percent"]
            result.loser_power_bonus_points = loser_points["power_bonus_points"]
            result.loser_relic_bonus_points = loser_points["relic_bonus_points"]
            result.loser_total_points = loser_points["total_points"]
            result.game_mode = match.gamemode_name or match.game_mode
            result.winner_team_size = winner_points["team_size"]
            result.loser_team_size = loser_points["team_size"]
            result.winner_clan_members = winner_points["clan_members"]
            result.loser_clan_members = loser_points["clan_members"]
            result.winner_team_bonus_percent = winner_points["team_bonus_percent"]
            result.winner_team_bonus_points = winner_points["team_bonus_points"]
            result.loser_team_bonus_percent = loser_points["team_bonus_percent"]
            result.loser_team_bonus_points = loser_points["team_bonus_points"]
            result.patch_family = (
                match.rating_patch_family
                or get_patch_family(
                    match.patch_name or match.patch_version,
                    match.patch_id,
                )
            )
            winner_rating = float(winner_team["rating"])
            loser_rating = float(loser_team["rating"])
            winner_probability = (
                round(expected_score(winner_rating, loser_rating, rules), 6)
                if rejection_reason is None else None
            )
            result.winner_rating = winner_rating
            result.loser_rating = loser_rating
            result.winner_expected_probability = winner_probability
            result.loser_expected_probability = (
                round(1 - winner_probability, 6)
                if winner_probability is not None else None
            )
            result.is_counted = rejection_reason is None
            result.rejection_reason = rejection_reason
            result.scoring_version = war.scoring_version or "elo_team_v2"
            result.winner_deployment_id = (
                winner_side_context.deployment_id if winner_side_context else None
            )
            result.loser_deployment_id = (
                loser_side_context.deployment_id if loser_side_context else None
            )
            result.winner_participation_share = (
                winner_side_context.participation_share
                if winner_side_context else None
            )
            result.loser_participation_share = (
                loser_side_context.participation_share
                if loser_side_context else None
            )
            result.winner_eligibility_code = (
                winner_side_context.eligibility_code
                if winner_side_context else None
            )
            result.loser_eligibility_code = (
                loser_side_context.eligibility_code
                if loser_side_context else None
            )

        if commit:
            db.commit()
        else:
            db.flush()
        return {
            "war_id": war.id,
            "counted": counted,
            "rejected": rejected,
            "scores": self._get_clan_scores(db, war),
        }

    def _match_rejection_reason(
        self,
        war: ClanWar,
        match: Optional[Match],
        winner_clan_ids: set,
        loser_clan_ids: set,
        *,
        rules: Mapping[str, int | float],
    ) -> Optional[str]:
        if winner_clan_ids & loser_clan_ids:
            return "Матч сыгран между соклановцами"
        rejection_reason = ranked_1v1_rejection_reason(match, rules=rules)
        if rejection_reason:
            return rejection_reason
        patch_family = (
            match.rating_patch_family
            or get_patch_family(
                match.patch_name or match.patch_version,
                match.patch_id,
            )
        )
        if not patch_family:
            return "Патч матча не поддерживается в клановых войнах"
        return None

    @staticmethod
    def _empty_match_points() -> dict:
        return {
            "base_points": 0,
            "power_percent": 0,
            "power_bonus_points": 0,
            "relic_bonus_points": 0,
            "team_bonus_percent": 0,
            "team_bonus_points": 0,
            "total_points": 0,
            "rating": None,
            "expected_probability": None,
            "team_size": 1,
            "clan_members": 0,
        }

    def _score_war_side(
        self,
        db: Session,
        war: ClanWar,
        clan_id: int,
        user: User,
        *,
        is_winner: bool,
        match: Optional[Match],
        users: Optional[List[User]] = None,
        team_rating: Optional[float] = None,
        opponent_rating: Optional[float] = None,
        team_size: int = 1,
        team_is_clan_only: bool = False,
        relic_participation_share: float = 1.0,
        exact_distribution: bool = False,
        rules: Mapping[str, int | float],
    ) -> dict:
        users = users or [user]
        fallback_rating = float(rules["ELO_START_RATING"])
        match_player_rating = (
            match.winner_elo if is_winner else match.loser_elo
        ) if match else None
        match_opponent_rating = (
            match.loser_elo if is_winner else match.winner_elo
        ) if match else None
        player_rating = float(team_rating if team_rating is not None else (
            match_player_rating
            if match_player_rating is not None
            else fallback_rating
        ))
        opponent_rating = float(opponent_rating if opponent_rating is not None else (
            match_opponent_rating
            if match_opponent_rating is not None
            else fallback_rating
        ))
        win_probability = expected_score(player_rating, opponent_rating, rules)
        base_points = 0.0
        if is_winner:
            participation_share = min(1.0, len(users) / max(1, team_size))
            mode_multiplier = 1 + (
                max(0, team_size - 1)
                * float(rules["WAR_TEAM_SIZE_BONUS_STEP_PERCENT"])
                / 100
            )
            base_points = round(
                winner_territory_points(win_probability, rules)
                * participation_share
                * mode_multiplier,
                2,
            )
        power = (
            war.attacker_power
            if clan_id == war.attacking_clan_id
            else war.defender_power
        )
        power_percent = min(
            int(rules["WAR_MODIFIER_CAP_PERCENT"]),
            max(0, power or 0),
        )
        adjusted_points = apply_war_power_modifier(base_points, power_percent, rules)
        team_bonus_percent = (
            float(rules["WAR_FULL_CLAN_TEAM_BONUS_PERCENT"])
            if is_winner and team_is_clan_only and team_size > 1
            else 0
        )
        team_bonus_points = round(
            adjusted_points * team_bonus_percent / 100,
            2,
        )
        relic_points = 0.0
        if is_winner:
            snapshot = (war.rules_snapshot or {}).get("RELIC_BONUSES_BY_CLAN")
            if snapshot is None:
                bonuses = self.economy.get_relic_bonuses(db, clan_id)
            else:
                bonuses = snapshot.get(str(clan_id), {})
            relic_points = round(
                float(bonuses.get("war_win_points", 0))
                * max(0.0, min(1.0, relic_participation_share)),
                2,
            )
        total_points = round(adjusted_points + team_bonus_points + relic_points, 2)
        points_per_member = total_points / max(1, len(users))
        distributed_points = [
            round(points_per_member, 2) for _ in users
        ]
        if exact_distribution and distributed_points:
            distributed_points[-1] = round(
                total_points - sum(distributed_points[:-1]),
                2,
            )
        for member, member_points in zip(users, distributed_points):
            participant = self._ensure_participant(db, war, clan_id, member.id)
            if is_winner:
                participant.wins += 1
            else:
                participant.losses += 1
            participant.war_points = round(
                (participant.war_points or 0) + member_points,
                2,
            )
        return {
            "base_points": base_points,
            "power_percent": power_percent,
            "power_bonus_points": round(adjusted_points - base_points, 2),
            "relic_bonus_points": relic_points,
            "team_bonus_percent": team_bonus_percent,
            "team_bonus_points": team_bonus_points,
            "total_points": total_points,
            "rating": player_rating,
            "expected_probability": round(win_probability, 6),
            "team_size": max(1, team_size),
            "clan_members": len(users),
        }

    def _build_match_result(
        self,
        *,
        war: ClanWar,
        match: Match,
        played_at: datetime,
        winner: User,
        loser: User,
        winner_clan_id: Optional[int],
        loser_clan_id: Optional[int],
        winner_points: Optional[dict] = None,
        loser_points: Optional[dict] = None,
        is_counted: bool = True,
        rejection_reason: Optional[str] = None,
        rules: Mapping[str, int | float],
        winner_side_context: WarMatchSideContext | None = None,
        loser_side_context: WarMatchSideContext | None = None,
    ) -> ClanWarMatchResult:
        winner_points = winner_points or self._empty_match_points()
        loser_points = loser_points or self._empty_match_points()
        winner_entries = [item for item in (match.participants or []) if item.is_winner and not item.is_observer]
        loser_entries = [item for item in (match.participants or []) if not item.is_winner and not item.is_observer]
        fallback_rating = float(rules["ELO_START_RATING"])
        winner_rating = float(
            winner_points["rating"]
            if winner_points["rating"] is not None
            else match.winner_elo
            if match.winner_elo is not None
            else fallback_rating
        )
        loser_rating = float(
            loser_points["rating"]
            if loser_points["rating"] is not None
            else match.loser_elo
            if match.loser_elo is not None
            else fallback_rating
        )
        winner_probability = (
            round(expected_score(winner_rating, loser_rating, rules), 6)
            if is_counted else None
        )
        return ClanWarMatchResult(
            war_id=war.id,
            match_id=match.id,
            played_at=played_at,
            winner_user_id=winner.id,
            loser_user_id=loser.id,
            winner_clan_id=winner_clan_id,
            loser_clan_id=loser_clan_id,
            winner_base_points=winner_points["base_points"],
            winner_power_percent=winner_points["power_percent"],
            winner_power_bonus_points=winner_points["power_bonus_points"],
            winner_relic_bonus_points=winner_points["relic_bonus_points"],
            winner_total_points=winner_points["total_points"],
            loser_base_points=loser_points["base_points"],
            loser_power_percent=loser_points["power_percent"],
            loser_power_bonus_points=loser_points["power_bonus_points"],
            loser_relic_bonus_points=loser_points["relic_bonus_points"],
            loser_total_points=loser_points["total_points"],
            game_mode=match.gamemode_name or match.game_mode,
            winner_team_size=max(winner_points["team_size"], len(winner_entries) or 1),
            loser_team_size=max(loser_points["team_size"], len(loser_entries) or 1),
            winner_clan_members=winner_points["clan_members"],
            loser_clan_members=loser_points["clan_members"],
            winner_team_bonus_percent=winner_points["team_bonus_percent"],
            winner_team_bonus_points=winner_points["team_bonus_points"],
            loser_team_bonus_percent=loser_points["team_bonus_percent"],
            loser_team_bonus_points=loser_points["team_bonus_points"],
            is_counted=is_counted,
            rejection_reason=rejection_reason,
            patch_family=match.rating_patch_family,
            winner_rating=winner_rating,
            loser_rating=loser_rating,
            winner_expected_probability=winner_probability,
            loser_expected_probability=(
                round(1 - winner_probability, 6)
                if winner_probability is not None else None
            ),
            scoring_version=war.scoring_version or "elo_team_v2",
            winner_deployment_id=(
                winner_side_context.deployment_id if winner_side_context else None
            ),
            loser_deployment_id=(
                loser_side_context.deployment_id if loser_side_context else None
            ),
            winner_participation_share=(
                winner_side_context.participation_share
                if winner_side_context else None
            ),
            loser_participation_share=(
                loser_side_context.participation_share
                if loser_side_context else None
            ),
            winner_eligibility_code=(
                winner_side_context.eligibility_code
                if winner_side_context else None
            ),
            loser_eligibility_code=(
                loser_side_context.eligibility_code
                if loser_side_context else None
            ),
        )

    def _replays_ready_for_finalization(self, db: Session, war: ClanWar) -> bool:
        if not war.ends_at:
            return False
        ready_at = as_utc(war.ends_at) + timedelta(minutes=settings.WAR_REPLAY_GRACE_MINUTES)
        heartbeat = db.get(WorkerHeartbeat, "campaign")
        return bool(
            utc_now() >= ready_at
            and heartbeat and heartbeat.replay_synced_through_at
            and as_utc(heartbeat.replay_synced_through_at) >= ready_at
        )

    def complete_expired_wars(self, db: Session):
        candidates = db.query(ClanWar.attacking_clan_id, ClanWar.defending_clan_id).filter(
            ClanWar.status == "active",
        ).all()
        self.economy.ledger.lock_clans(db, [clan_id for row in candidates for clan_id in row])
        canceled_orphaned = self.cancel_active_wars_with_deleted_clans(
            db,
            commit=False,
        )
        expired = (
            db.query(ClanWar)
            .filter(
                ClanWar.status == "active",
                ClanWar.ends_at.isnot(None),
                ClanWar.ends_at <= utc_now(),
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        handled_territories = set()
        completed = 0
        for war in expired:
            if not self._replays_ready_for_finalization(db, war):
                continue
            if war.war_type == "territory_attack":
                if war.territory_id in handled_territories:
                    continue
                self._complete_territory_attack_group(db, war.territory_id)
                handled_territories.add(war.territory_id)
            else:
                self._complete_war(db, war, war.attacking_clan_id, commit=False)
            completed += 1
        if canceled_orphaned or expired:
            db.commit()
        return completed

    def deactivate_user_for_clan_departure(self, db: Session, user_id: int, clan_id: int):
        """Фиксирует выход игрока из клана: старый прогресс остается, будущий не считается."""
        rules = self.rule_service.get_active(db).values
        active_rows = self.participant_repo.get_user_active_participations(db, user_id, clan_id)
        had_battles = any((row.wins or 0) + (row.losses or 0) > 0 for row in active_rows)
        for row in active_rows:
            row.is_active = False

        if had_battles and not self.timeout_repo.get_timeout_by_user(db, user_id):
            db.add(
                ClanTimeout(
                    user_id=user_id,
                    clan_id=clan_id,
                    timeout_until=utc_now() + timedelta(
                        hours=float(rules["CLAN_JOIN_TIMEOUT_HOURS"])
                    ),
                    reason="Выход из клана во время активной войны",
                )
            )
        db.flush()
        return had_battles

    def get_user_join_timeout(self, db: Session, user_id: int) -> Optional[ClanTimeout]:
        return self.timeout_repo.get_timeout_by_user(db, user_id)

    def _ensure_war_participants(self, db: Session, war: ClanWar):
        clan_ids = [war.attacking_clan_id]
        if war.defending_clan_id:
            clan_ids.append(war.defending_clan_id)
        for clan_id in clan_ids:
            members = db.query(ClanMember).filter(ClanMember.clan_id == clan_id).all()
            for member in members:
                self._ensure_participant(db, war, clan_id, member.user_id)

    def _ensure_participant(self, db: Session, war: ClanWar, clan_id: int, user_id: int) -> Optional[ClanWarParticipant]:
        if clan_id not in {war.attacking_clan_id, war.defending_clan_id}:
            return None
        participant = self.participant_repo.get_participant_by_user_and_war(db, user_id, war.id)
        if participant:
            return participant
        participant = ClanWarParticipant(
            war_id=war.id,
            clan_id=clan_id,
            user_id=user_id,
            wins=0,
            losses=0,
            is_active=war.status == "active",
        )
        db.add(participant)
        db.flush()
        return participant

    def _get_clan_scores(self, db: Session, war: ClanWar) -> List[dict]:
        from app.models.war_adjustment import WarScoreAdjustment
        adjustments = db.query(WarScoreAdjustment).filter_by(war_id=war.id).all()
        clan_ids = [war.attacking_clan_id] if war.attacking_clan_id else []
        if war.defending_clan_id:
            clan_ids.append(war.defending_clan_id)
        scores = []
        match_results = db.query(ClanWarMatchResult).filter(
            ClanWarMatchResult.war_id == war.id,
            ClanWarMatchResult.is_counted.is_(True),
        ).all()
        for clan_id in clan_ids:
            clan = self.clan_repo.get(db, clan_id)
            participants = db.query(ClanWarParticipant).filter(
                ClanWarParticipant.war_id == war.id,
                ClanWarParticipant.clan_id == clan_id,
            ).all()
            wins = sum(1 for result in match_results if result.winner_clan_id == clan_id)
            losses = sum(1 for result in match_results if result.loser_clan_id == clan_id)
            matches = wins + losses
            stored_points = sum(row.war_points or 0 for row in participants)
            manual_points = sum(row.points for row in adjustments if row.clan_id == clan_id)
            base_points = round(sum(
                result.winner_base_points
                if result.winner_clan_id == clan_id
                else result.loser_base_points
                for result in match_results
                if clan_id in {result.winner_clan_id, result.loser_clan_id}
            ), 2)
            power_bonus_points = round(sum(
                result.winner_power_bonus_points
                if result.winner_clan_id == clan_id
                else result.loser_power_bonus_points
                for result in match_results
                if clan_id in {result.winner_clan_id, result.loser_clan_id}
            ), 2)
            relic_bonus_points = round(sum(
                result.winner_relic_bonus_points
                if result.winner_clan_id == clan_id
                else result.loser_relic_bonus_points
                for result in match_results
                if clan_id in {result.winner_clan_id, result.loser_clan_id}
            ), 2)
            team_bonus_points = round(sum(
                result.winner_team_bonus_points
                if result.winner_clan_id == clan_id
                else result.loser_team_bonus_points
                for result in match_results
                if clan_id in {result.winner_clan_id, result.loser_clan_id}
            ), 2)
            tracked_points = round(
                base_points + power_bonus_points + relic_bonus_points + team_bonus_points,
                2,
            )
            scores.append(
                {
                    "clan_id": clan_id,
                    "clan_name": clan.name if clan else f"Клан #{clan_id}",
                    "wins": wins,
                    "losses": losses,
                    "matches": matches,
                    "points": round((stored_points or wins * LEGACY_WAR_WIN_POINTS + losses * LEGACY_WAR_LOSS_POINTS) + manual_points, 2),
                    "manual_points": round(manual_points, 2),
                    "base_points": base_points,
                    "power_bonus_points": power_bonus_points,
                    "relic_bonus_points": relic_bonus_points,
                    "team_bonus_points": team_bonus_points,
                    "legacy_points": round(max(0, stored_points - tracked_points), 2),
                    "win_rate": round(wins / matches * 100, 1) if matches else 0,
                    "active_participants": sum(1 for row in participants if row.is_active),
                }
            )
        return scores

    def _serialize_match_results(
        self,
        db: Session,
        war: ClanWar,
    ) -> List[dict]:
        results = (
            db.query(ClanWarMatchResult)
            .filter(ClanWarMatchResult.war_id == war.id)
            .order_by(ClanWarMatchResult.played_at.desc())
            .all()
        )
        participant_names = {
            participant.nickname
            for result in results
            for participant in (result.match.participants or [])
        }
        users_by_name = {
            user.username.casefold(): user
            for user in (
                db.query(User).filter(User.username.in_(participant_names)).all()
                if participant_names else []
            )
        }
        serialized = []
        for result in results:
            match_participants = []
            for participant in result.match.participants or []:
                user = users_by_name.get(participant.nickname.casefold())
                side_clan_id = result.winner_clan_id if participant.is_winner else result.loser_clan_id
                participant_clan_id = None
                if user and side_clan_id in self.membership_history.clan_ids_at(
                    db,
                    user.id,
                    as_utc(result.played_at),
                ):
                    participant_clan_id = side_clan_id
                match_participants.append({
                    "user_id": user.id if user else None,
                    "username": participant.nickname,
                    "player_uuid": participant.player_uuid,
                    "faction": participant.faction,
                    "team": participant.team,
                    "is_winner": participant.is_winner,
                    "elo": participant.elo,
                    "elo_is_verified": participant.elo is not None and not is_unverified_rating(result.match, participant.player_uuid, participant.nickname),
                    "clan_id": participant_clan_id,
                })
            serialized.append({
                "id": result.id,
                "match_id": result.match.match_id,
                "played_at": result.played_at,
                "map_name": result.match.map_name,
                "game_mode": result.game_mode or result.match.gamemode_name or result.match.game_mode,
                "patch_version": result.match.patch_version,
                "patch_family": result.patch_family,
                "duration": result.match.duration,
                "rating_warning": bool((result.match.source_payload or {}).get('rating_unverified_players')) or result.match.rating_source == 'bfmeladder_rating_incomplete',
                "is_counted": result.is_counted,
                "rejection_reason": result.rejection_reason,
                "admin_override": result.admin_override,
                "admin_override_reason": result.admin_override_reason,
                "admin_override_by": (
                    result.admin_override_by.username
                    if result.admin_override_by else None
                ),
                "admin_override_at": result.admin_override_at,
                "winner": {
                    "user_id": result.winner_user_id,
                    "username": result.winner_user.username,
                    "clan_id": result.winner_clan_id,
                    "clan_name": result.winner_clan.name if result.winner_clan else None,
                    "base_points": result.winner_base_points,
                    "power_percent": result.winner_power_percent,
                    "power_bonus_points": result.winner_power_bonus_points,
                    "relic_bonus_points": result.winner_relic_bonus_points,
                    "team_bonus_percent": result.winner_team_bonus_percent,
                    "team_bonus_points": result.winner_team_bonus_points,
                    "total_points": result.winner_total_points,
                    "rating": result.winner_rating,
                    "expected_probability": result.winner_expected_probability,
                    "team_size": result.winner_team_size,
                    "clan_members": result.winner_clan_members,
                    "deployment_id": result.winner_deployment_id,
                    "participation_share": result.winner_participation_share,
                    "eligibility_code": result.winner_eligibility_code,
                },
                "loser": {
                    "user_id": result.loser_user_id,
                    "username": result.loser_user.username,
                    "clan_id": result.loser_clan_id,
                    "clan_name": result.loser_clan.name if result.loser_clan else None,
                    "base_points": result.loser_base_points,
                    "power_percent": result.loser_power_percent,
                    "power_bonus_points": result.loser_power_bonus_points,
                    "relic_bonus_points": result.loser_relic_bonus_points,
                    "team_bonus_percent": result.loser_team_bonus_percent,
                    "team_bonus_points": result.loser_team_bonus_points,
                    "total_points": result.loser_total_points,
                    "rating": result.loser_rating,
                    "expected_probability": result.loser_expected_probability,
                    "team_size": result.loser_team_size,
                    "clan_members": result.loser_clan_members,
                    "deployment_id": result.loser_deployment_id,
                    "participation_share": result.loser_participation_share,
                    "eligibility_code": result.loser_eligibility_code,
                },
                "participants": match_participants,
                "scoring_version": result.scoring_version,
            })
        return serialized

    def _select_winner(self, scores: List[dict], defending_clan_id: Optional[int] = None) -> Optional[int]:
        if not scores:
            return None
        highest_points = max(round(score["points"], 2) for score in scores)
        tied_on_points = [
            score
            for score in scores
            if round(score["points"], 2) == highest_points
        ]
        if (
            defending_clan_id
            and len(tied_on_points) > 1
            and any(score["clan_id"] == defending_clan_id for score in tied_on_points)
        ):
            return defending_clan_id

        def ranking(score):
            return (
                score["points"],
                score["wins"],
                score["win_rate"],
                score["active_participants"],
                score["matches"],
            )

        ranked = sorted(scores, key=ranking, reverse=True)
        return ranked[0]["clan_id"]

    def _maybe_complete_war(self, db: Session, war: ClanWar):
        if war.war_type == "neutral_capture":
            attacker_wins = next(
                score["wins"]
                for score in self._get_clan_scores(db, war)
                if score["clan_id"] == war.attacking_clan_id
            )
            if attacker_wins >= war.required_wins:
                self._complete_war(db, war, war.attacking_clan_id)
        # Timed wars are finalized only after a complete successful replay scan,
        # never while individual matches from that scan are still being ingested.

    def _complete_territory_attack_group(self, db: Session, territory_id: int):
        wars = db.query(ClanWar).filter(
            ClanWar.territory_id == territory_id,
            ClanWar.status == "active",
            ClanWar.war_type == "territory_attack",
        ).all()
        if not wars:
            return
        if not all(self._replays_ready_for_finalization(db, war) for war in wars):
            return

        scores_by_clan = {}
        defending_clan_id = wars[0].defending_clan_id
        for war in wars:
            for score in self._get_clan_scores(db, war):
                current = scores_by_clan.setdefault(
                    score["clan_id"],
                    {
                        "clan_id": score["clan_id"],
                        "points": 0,
                        "wins": 0,
                        "losses": 0,
                        "matches": 0,
                        "win_rate": 0,
                        "active_participants": 0,
                    },
                )
                for key in ("points", "wins", "losses", "matches", "active_participants"):
                    current[key] += score[key]
                current["win_rate"] = round(current["wins"] / current["matches"] * 100, 1) if current["matches"] else 0

        winner_clan_id = self._select_winner(list(scores_by_clan.values()), defending_clan_id)
        for war in wars:
            self._complete_war(db, war, winner_clan_id, commit=False)

    def _complete_war(self, db: Session, war: ClanWar, winner_clan_id: int, commit: bool = True):
        if winner_clan_id not in {war.attacking_clan_id, war.defending_clan_id}:
            raise InsufficientPermissionsException("Победителем войны может быть только один из двух кланов конфликта")
        war.status = "completed"
        war.winner_clan_id = winner_clan_id
        war.ended_at = utc_now()

        for deployment in war.deployments:
            self.deployments.release_attack_lock(
                db,
                deployment,
                now=war.ended_at,
            )

        territory = war.territory
        if territory:
            self.ownership.transfer(
                db,
                territory,
                winner_clan_id,
                changed_at=war.ended_at,
                reason="war_victory",
                war_id=war.id,
            )
            remaining_active = db.query(ClanWar).filter(
                ClanWar.territory_id == territory.id,
                ClanWar.status == "active",
                ClanWar.id != war.id,
            ).count()
            territory.status = "contested" if remaining_active else "active"

            if war.attacking_clan in territory.attacking_clans:
                territory.attacking_clans.remove(war.attacking_clan)
            if war.defending_clan and war.defending_clan in territory.defending_clans:
                territory.defending_clans.remove(war.defending_clan)

        territory_name = territory.name if territory else "неизвестная территория"
        war_link = f"/battles/{war.id}"
        for clan_id in {war.attacking_clan_id, war.defending_clan_id}:
            if clan_id is None:
                continue
            won = clan_id == winner_clan_id
            notification_service.create_for_clan(
                db,
                clan_id=clan_id,
                notification_type="war_completed",
                title="Территория завоёвана" if won else "Битва завершена",
                message=(
                    f"Ваш клан победил в битве за «{territory_name}»."
                    if won
                    else f"Ваш клан уступил в битве за «{territory_name}»."
                ),
                link_url=war_link,
                entity_type="clan_war",
                entity_id=war.id,
            )

        if commit:
            db.commit()
            db.refresh(war)
        return war


class ClanWarParticipantService:
    """Сервис для работы с участниками войн"""

    def __init__(self):
        self.participant_repo = ClanWarParticipantRepository()
        self.war_repo = ClanWarRepository()
        self.user_repo = UserRepository()
        self.clan_repo = ClanRepository()

    def get_participants_by_war(self, db: Session, war_id: int) -> List:
        return self.participant_repo.get_participants_by_war(db, war_id)

    def get_participants_by_clan(self, db: Session, clan_id: int) -> List:
        return self.participant_repo.get_participants_by_clan(db, clan_id)

    def add_participant(self, db: Session, participant_data: ClanWarParticipantCreate):
        war = self.war_repo.get(db, participant_data.war_id)
        if not war:
            raise ClanWarNotFoundException(participant_data.war_id)

        user = self.user_repo.get(db, participant_data.user_id)
        if not user:
            raise UserNotFoundException(user_id=participant_data.user_id)

        clan = self.clan_repo.get(db, participant_data.clan_id)
        if not clan:
            raise ClanNotFoundException(participant_data.clan_id)

        existing = self.participant_repo.get_participant_by_user_and_war(
            db, participant_data.user_id, participant_data.war_id
        )
        if existing:
            raise InsufficientPermissionsException("добавить пользователя, который уже участвует в этой войне")

        return self.participant_repo.create(db, obj_in=participant_data)

    def remove_participant(self, db: Session, war_id: int, user_id: int):
        participant = self.participant_repo.get_participant_by_user_and_war(db, user_id, war_id)
        if not participant:
            raise UserNotFoundException(user_id=user_id)
        return self.participant_repo.remove(db, id=participant.id)

    def update_participant_stats(
        self,
        db: Session,
        war_id: int,
        user_id: int,
        battles_won: int = None,
        battles_lost: int = None,
    ):
        participant = self.participant_repo.get_participant_by_user_and_war(db, user_id, war_id)
        if not participant:
            raise UserNotFoundException(user_id=user_id)

        if battles_won is not None:
            participant.wins = battles_won
        if battles_lost is not None:
            participant.losses = battles_lost

        db.commit()
        db.refresh(participant)
        return participant

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.territory import Territory, TerritoryOwnershipHistory
from app.services.clan_influence_service import ClanInfluenceService
from app.services.campaign_rule_service import CampaignRuleService


class TerritoryOwnershipService:
    def __init__(self):
        self.influence = ClanInfluenceService()
        self.rules = CampaignRuleService()

    def transfer(
        self,
        db: Session,
        territory: Territory,
        new_owner_clan_id: int | None,
        *,
        changed_at: datetime | None = None,
        reason: str = "capture",
        war_id: int | None = None,
        actor_user_id: int | None = None,
        details: dict | None = None,
    ) -> bool:
        changed_at = changed_at or utc_now()
        ready_delay = timedelta(
            hours=float(
                self.rules.get_active(db).values["TERRITORY_RESOURCE_READY_HOURS"]
            )
        )
        old_owner_clan_id = territory.owner_clan_id

        if old_owner_clan_id == new_owner_clan_id:
            if new_owner_clan_id:
                if territory.owned_since is None:
                    territory.owned_since = changed_at
                if territory.last_weekly_payout_at is None:
                    territory.last_weekly_payout_at = territory.owned_since
                if territory.resource_income_ready_at is None:
                    territory.resource_income_ready_at = territory.owned_since + ready_delay
                self._ensure_open_history(
                    db,
                    territory,
                    new_owner_clan_id,
                    territory.owned_since,
                    reason,
                    war_id,
                )
                self.influence.recalculate(db, new_owner_clan_id)
            return False

        open_history = (
            db.query(TerritoryOwnershipHistory)
            .filter(
                TerritoryOwnershipHistory.territory_id == territory.id,
                TerritoryOwnershipHistory.ended_at.is_(None),
            )
            .first()
        )
        if open_history:
            open_history.ended_at = changed_at

        if (
            old_owner_clan_id is not None
            and new_owner_clan_id is not None
            and reason == "war_victory"
        ):
            # Only conquest of another clan's land destroys development.
            # Neutral claims, successful defenses and administrative transfers
            # retain their levels. Integer division rounds odd levels down.
            fields = (
                "offense_level", "fortifications", "development_level",
                "port_level", "fleet_level",
            )
            before = {field: max(0, int(getattr(territory, field) or 0)) for field in fields}
            for field, level in before.items():
                setattr(territory, field, level // 2)
            territory.strategic_value = territory.calculate_strategic_value()
            details = {
                **(details or {}),
                "development_before": before,
                "development_after": {field: getattr(territory, field) for field in fields},
            }

        territory.owner_clan_id = new_owner_clan_id
        territory.owned_since = changed_at if new_owner_clan_id else None
        territory.last_weekly_payout_at = changed_at if new_owner_clan_id else None
        territory.resource_income_ready_at = (
            changed_at + ready_delay if new_owner_clan_id else None
        )
        territory.last_resource_payout_at = None

        if new_owner_clan_id:
            db.add(
                TerritoryOwnershipHistory(
                    territory_id=territory.id,
                    clan_id=new_owner_clan_id,
                    started_at=changed_at,
                    war_id=war_id,
                    reason=reason,
                )
            )
        db.flush()
        operation_id = (
            f"territory-owner:{territory.id}:{changed_at.isoformat()}:"
            f"{old_owner_clan_id or 0}:{new_owner_clan_id or 0}"
        )
        self.influence.recalculate(
            db,
            old_owner_clan_id,
            operation_id=operation_id,
            action="territory_influence_lost",
            source_type="territory",
            source_id=territory.id,
            actor_user_id=actor_user_id,
            details={"territory_name": territory.name, "reason": reason, **(details or {})},
        )
        self.influence.recalculate(
            db,
            new_owner_clan_id,
            operation_id=operation_id,
            action="territory_influence_gained",
            source_type="territory",
            source_id=territory.id,
            actor_user_id=actor_user_id,
            details={"territory_name": territory.name, "reason": reason, **(details or {})},
        )
        return True

    def _ensure_open_history(
        self,
        db: Session,
        territory: Territory,
        clan_id: int,
        started_at: datetime,
        reason: str,
        war_id: int | None,
    ) -> None:
        exists = (
            db.query(TerritoryOwnershipHistory)
            .filter(
                TerritoryOwnershipHistory.territory_id == territory.id,
                TerritoryOwnershipHistory.clan_id == clan_id,
                TerritoryOwnershipHistory.ended_at.is_(None),
            )
            .first()
        )
        if not exists:
            db.add(
                TerritoryOwnershipHistory(
                    territory_id=territory.id,
                    clan_id=clan_id,
                    started_at=started_at,
                    war_id=war_id,
                    reason=reason,
                )
            )

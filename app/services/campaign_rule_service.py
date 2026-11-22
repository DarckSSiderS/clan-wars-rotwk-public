from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType
from collections.abc import Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.campaign_rules import (
    RULE_DEFINITIONS,
    CampaignRuleValidationError,
    default_campaign_rule_values,
    validate_campaign_rule_values,
)
from app.models.campaign import CampaignRuleSet
from app.services.operation_service import AdminAuditService


RuleValue = int | float


@dataclass(frozen=True)
class CampaignRuleSnapshot:
    id: int
    version: int
    values: Mapping[str, RuleValue]

    def value(self, key: str) -> RuleValue:
        return self.values[key]

    def subset(self, *keys: str) -> dict[str, RuleValue]:
        return {key: self.values[key] for key in keys}


class CampaignRuleVersionConflict(ValueError):
    def __init__(self, expected_version: int, active_version: int):
        self.expected_version = expected_version
        self.active_version = active_version
        super().__init__(
            f"Expected campaign rule version {expected_version}, "
            f"but active version is {active_version}."
        )


class CampaignRuleInputError(ValueError):
    def __init__(self, errors: list[CampaignRuleValidationError]):
        self.errors = errors
        super().__init__("Campaign rule values failed validation.")


class CampaignRuleService:
    @staticmethod
    def _snapshot(row: CampaignRuleSet) -> CampaignRuleSnapshot:
        return CampaignRuleSnapshot(
            id=row.id,
            version=row.version,
            values=MappingProxyType(dict(row.values)),
        )

    @staticmethod
    def _active_query(db: Session):
        return db.query(CampaignRuleSet).filter(CampaignRuleSet.is_active.is_(True))

    def get_active(
        self,
        db: Session,
        *,
        create: bool = True,
    ) -> CampaignRuleSnapshot:
        row = self._active_query(db).one_or_none()
        if row is None and create:
            latest_version = db.query(func.max(CampaignRuleSet.version)).scalar() or 0
            row = CampaignRuleSet(
                version=latest_version + 1,
                values=default_campaign_rule_values(),
                is_active=True,
                reason="initial_effective_defaults",
            )
            db.add(row)
            db.flush()
        if row is None:
            raise LookupError("No active campaign rule set exists.")
        return self._snapshot(row)

    def _locked_active(self, db: Session) -> CampaignRuleSet:
        row = self._active_query(db).with_for_update().one_or_none()
        if row is None:
            self.get_active(db)
            row = self._active_query(db).with_for_update().one()
        return row

    @staticmethod
    def _validate(values: Mapping[str, object]) -> None:
        errors = validate_campaign_rule_values(values)
        if errors:
            raise CampaignRuleInputError(errors)

    def _create_row(
        self,
        db: Session,
        *,
        active: CampaignRuleSet,
        values: Mapping[str, object],
        actor_user_id: int,
        reason: str,
        action: str,
        restored_from_version: int | None = None,
        commit: bool,
    ) -> CampaignRuleSet:
        self._validate(values)
        copied_values = dict(values)
        before_data = {
            "version": active.version,
            "values": dict(active.values),
        }

        active.is_active = False
        db.flush()

        row = CampaignRuleSet(
            version=active.version + 1,
            values=copied_values,
            is_active=True,
            created_by_user_id=actor_user_id,
            reason=reason,
        )
        db.add(row)
        db.flush()

        after_data = {
            "version": row.version,
            "values": dict(copied_values),
        }
        if restored_from_version is not None:
            after_data["restored_from_version"] = restored_from_version
        AdminAuditService().record(
            db,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="campaign_rule_set",
            entity_id=row.id,
            before_data=before_data,
            after_data=after_data,
            reason=reason,
        )

        if commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        return row

    def create_version(
        self,
        db: Session,
        *,
        expected_version: int,
        changes: Mapping[str, object],
        actor_user_id: int,
        reason: str,
        commit: bool = False,
    ) -> CampaignRuleSet:
        active = self._locked_active(db)
        if active.version != expected_version:
            raise CampaignRuleVersionConflict(expected_version, active.version)
        values = dict(active.values)
        values.update(changes)
        return self._create_row(
            db,
            active=active,
            values=values,
            actor_user_id=actor_user_id,
            reason=reason,
            action="campaign_rules_updated",
            commit=commit,
        )

    def restore_version(
        self,
        db: Session,
        *,
        source_version: int,
        expected_version: int,
        actor_user_id: int,
        reason: str,
        commit: bool = False,
    ) -> CampaignRuleSet:
        active = self._locked_active(db)
        if active.version != expected_version:
            raise CampaignRuleVersionConflict(expected_version, active.version)
        source = (
            db.query(CampaignRuleSet)
            .filter(CampaignRuleSet.version == source_version)
            .one_or_none()
        )
        if source is None:
            raise ValueError(f"Campaign rule version {source_version} does not exist.")
        return self._create_row(
            db,
            active=active,
            values=dict(source.values),
            actor_user_id=actor_user_id,
            reason=reason,
            action="campaign_rules_restored",
            restored_from_version=source_version,
            commit=commit,
        )

    @staticmethod
    def history(db: Session, *, limit: int = 100) -> list[CampaignRuleSet]:
        return (
            db.query(CampaignRuleSet)
            .order_by(CampaignRuleSet.version.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )

    @staticmethod
    def schema() -> list[dict[str, object]]:
        return [
            asdict(definition)
            for definition in sorted(
                RULE_DEFINITIONS.values(),
                key=lambda item: (item.category, item.key),
            )
        ]

import pytest

from app.core.campaign_rules import default_campaign_rule_values
from app.models.campaign import CampaignRuleSet
from app.models.operation import AdminAuditLog
from app.models.role import Role
from app.models.user import User
from app.services.campaign_rule_service import (
    CampaignRuleInputError,
    CampaignRuleService,
    CampaignRuleVersionConflict,
)


def _admin(db):
    role = Role(name="campaign-rule-admin", description="Administrator")
    user = User(
        username="campaign-rule-admin",
        email="campaign-rule-admin@example.com",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([role, user])
    db.flush()
    return user


def test_get_active_bootstraps_an_empty_database_with_an_immutable_snapshot(db):
    snapshot = CampaignRuleService().get_active(db)

    assert snapshot.id > 0
    assert snapshot.version == 1
    assert snapshot.values == default_campaign_rule_values()
    with pytest.raises(TypeError):
        snapshot.values["WAR_DURATION_HOURS"] = 72

    stored = db.query(CampaignRuleSet).one()
    assert stored.is_active is True
    assert stored.reason == "initial_effective_defaults"


def test_create_version_merges_changes_and_deactivates_previous(db):
    admin = _admin(db)
    service = CampaignRuleService()
    first = service.get_active(db)

    second = service.create_version(
        db,
        expected_version=first.version,
        changes={"WAR_DURATION_HOURS": 72},
        actor_user_id=admin.id,
        reason="Тест новой длительности",
        commit=True,
    )

    assert second.version == first.version + 1
    assert second.values["WAR_DURATION_HOURS"] == 72
    assert first.values["WAR_DURATION_HOURS"] == 60
    assert db.query(CampaignRuleSet).filter_by(is_active=True).one().id == second.id
    assert db.query(CampaignRuleSet).filter_by(version=1).one().values[
        "WAR_DURATION_HOURS"
    ] == 60


def test_create_version_rejects_stale_expected_version_after_active_lookup(db):
    admin = _admin(db)
    service = CampaignRuleService()
    first = service.get_active(db)
    service.create_version(
        db,
        expected_version=first.version,
        changes={"WAR_DURATION_HOURS": 72},
        actor_user_id=admin.id,
        reason="First update",
        commit=True,
    )

    with pytest.raises(CampaignRuleVersionConflict) as error:
        service.create_version(
            db,
            expected_version=first.version,
            changes={"WAR_DURATION_HOURS": 48},
            actor_user_id=admin.id,
            reason="Stale update",
        )

    assert error.value.expected_version == 1
    assert error.value.active_version == 2


@pytest.mark.parametrize(
    ("changes", "error_code", "field"),
    [
        ({"UNKNOWN_RULE": 1}, "unknown", "UNKNOWN_RULE"),
        ({"WAR_DURATION_HOURS": "long"}, "type", "WAR_DURATION_HOURS"),
        ({"WAR_ELO_MIN_POINTS": 100}, "range_order", "WAR_ELO_MIN_POINTS"),
    ],
)
def test_create_version_returns_structured_validation_errors(
    db,
    changes,
    error_code,
    field,
):
    admin = _admin(db)
    service = CampaignRuleService()
    active = service.get_active(db)

    with pytest.raises(CampaignRuleInputError) as error:
        service.create_version(
            db,
            expected_version=active.version,
            changes=changes,
            actor_user_id=admin.id,
            reason="Invalid update",
        )

    assert any(
        item.code == error_code and item.field == field
        for item in error.value.errors
    )
    assert db.query(CampaignRuleSet).filter_by(is_active=True).one().version == 1


def test_restore_creates_a_new_version_and_records_both_audit_actions(db):
    admin = _admin(db)
    service = CampaignRuleService()
    first = service.get_active(db)
    second = service.create_version(
        db,
        expected_version=first.version,
        changes={"WAR_DURATION_HOURS": 72},
        actor_user_id=admin.id,
        reason="Shorter wars",
        commit=True,
    )

    restored = service.restore_version(
        db,
        source_version=1,
        expected_version=second.version,
        actor_user_id=admin.id,
        reason="Restore initial duration",
        commit=True,
    )

    assert restored.version == 3
    assert restored.values["WAR_DURATION_HOURS"] == 60
    assert [row.version for row in service.history(db)] == [3, 2, 1]
    audits = db.query(AdminAuditLog).order_by(AdminAuditLog.id).all()
    assert [row.action for row in audits] == [
        "campaign_rules_updated",
        "campaign_rules_restored",
    ]
    assert audits[-1].before_data["version"] == 2
    assert audits[-1].after_data["version"] == 3
    assert audits[-1].after_data["restored_from_version"] == 1


def test_schema_exposes_typed_metadata_for_every_rule():
    schema = CampaignRuleService().schema()

    assert len(schema) == len(default_campaign_rule_values())
    duration = next(item for item in schema if item["key"] == "WAR_DURATION_HOURS")
    assert duration["value_type"] == "int"
    assert duration["unit"] == "hours"
    assert duration["minimum"] == 1

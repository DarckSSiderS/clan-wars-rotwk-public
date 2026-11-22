import pytest

from app.models.campaign import ReplaySyncState
from app.services.campaign_settings_service import (
    CampaignSettingsService,
    ReplaySyncStateService,
)
from app.services.elo_service import PATCH_202, PATCH_ENNORATH


def test_campaign_active_patches_are_configurable(db):
    service = CampaignSettingsService()

    assert service.active_patch_families(db) == {PATCH_202, PATCH_ENNORATH}

    updated = service.update(
        db,
        patch_202_enabled=False,
        ennorath_enabled=True,
        updated_by="darcks",
    )

    assert updated.updated_by == "clanwar"
    assert service.active_patch_families(db) == {PATCH_ENNORATH}


def test_campaign_rejects_disabling_every_patch(db):
    with pytest.raises(ValueError, match="хотя бы один патч"):
        CampaignSettingsService().update(
            db,
            patch_202_enabled=False,
            ennorath_enabled=False,
            updated_by="darcks",
        )


def test_replay_sync_state_is_updated_without_duplicates(db):
    service = ReplaySyncStateService()

    first = service.record(
        db,
        "replay-1",
        "error",
        patch_family=PATCH_202,
        patch_name="Patch 2.02",
        reason="Не удалось определить реальные ники игроков",
    )
    second = service.record(
        db,
        "replay-1",
        "imported",
        patch_family=PATCH_202,
        patch_name="Patch 2.02",
    )
    db.commit()

    assert first.replay_id == second.replay_id
    assert db.query(ReplaySyncState).count() == 1
    assert second.status == "imported"
    assert second.reason is None
    assert second.attempts == 2
    assert second.imported_at is not None
    assert service.summary(db)["imported"] == 1


def test_replay_sync_list_can_filter_errors(db):
    service = ReplaySyncStateService()
    service.record(db, "ok", "imported", patch_family=PATCH_ENNORATH)
    service.record(
        db,
        "bad",
        "error",
        patch_family=PATCH_ENNORATH,
        reason="Ошибка replay",
    )
    db.commit()

    errors = service.list_states(db, status="error")

    assert [state.replay_id for state in errors] == ["bad"]


def test_known_recheck_keeps_original_imported_status(db):
    service = ReplaySyncStateService()
    service.record(db, "replay-2", "imported", patch_family=PATCH_202)
    state = service.record(db, "replay-2", "known", patch_family=PATCH_202)
    db.commit()

    assert state.status == "imported"
    assert state.attempts == 2

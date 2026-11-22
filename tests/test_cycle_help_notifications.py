"""Просьба помощи доставляется союзникам один раз вместе с сохранением приказа."""

import pytest

from app.models.notification import UserNotification
from app.services.campaign_cycle_store import CycleConflict
from tests.test_cycle_reinforcement_store import world, initialize, request


def test_help_notifies_only_frozen_allies_once(db, world):
    users, clans, land, cycle = world
    initialize(db, world)
    request(db, world)
    notifications = db.query(UserNotification).all()
    assert {row.user_id for row in notifications} == {users[i].id for i in (0, 1, 2)}
    assert all(row.notification_type == 'cycle_help_requested' for row in notifications)
    assert all(row.link_url == f'/campaign/cycles/{cycle.id}?territory={land.id}' for row in notifications)
    assert all(clans[1].name in row.message and land.name in row.message for row in notifications)
    request(db, world)
    assert db.query(UserNotification).count() == 3


def test_failed_help_request_cannot_notify_allies(db, world):
    row = initialize(db, world)
    with pytest.raises(CycleConflict):
        request(db, world, revision=row.revision + 1)
    assert db.query(UserNotification).count() == 0


def test_help_notification_is_rolled_back_with_request(db, world):
    initialize(db, world)
    db.commit()
    request(db, world)
    assert db.query(UserNotification).count() == 3
    db.rollback()
    assert db.query(UserNotification).count() == 0

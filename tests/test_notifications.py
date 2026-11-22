import pytest
from fastapi import HTTPException

from app.api.v1.notifications import (
    get_notifications,
    get_unread_notification_count,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.models.notification import UserNotification
from app.models.clan import Clan, ClanMember
from app.models.role import Role
from app.models.shop import ShopItem
from app.models.user import User
from app.schemas.shop import PurchaseRequest
from app.services.notification_service import notification_service
from app.services.shop_service import UserItemService


def _users(db):
    role = Role(name="user", description="Игрок")
    first = User(
        username="notification-owner",
        email="notification-owner@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
        balance=100,
    )
    second = User(
        username="notification-other",
        email="notification-other@example.test",
        hashed_password="unused",
        role=role,
        is_active=True,
        is_claimed=True,
    )
    db.add_all([role, first, second])
    db.commit()
    return first, second


def test_notification_feed_is_private_and_supports_read_states(db):
    owner, other = _users(db)
    first = notification_service.create(
        db,
        user_id=owner.id,
        notification_type="clan_invite",
        title="Приглашение",
        message="Клан ждёт ответа.",
        link_url="/profile",
    )
    notification_service.create(
        db,
        user_id=owner.id,
        notification_type="achievement_completed",
        title="Награда",
        message="Получено достижение.",
        link_url="/achievements",
    )
    notification_service.create(
        db,
        user_id=other.id,
        notification_type="shop_purchase",
        title="Покупка",
        message="Чужое событие.",
    )

    feed = get_notifications(0, 30, False, owner, db)

    assert feed["total"] == 2
    assert feed["unread_count"] == 2
    assert {item.user_id for item in db.query(UserNotification).all()} == {owner.id, other.id}
    assert all(item.user_id == owner.id for item in feed["items"])

    marked = mark_notification_read(first.id, owner, db)
    assert marked.read_at is not None
    assert get_unread_notification_count(owner, db) == {"unread_count": 1}

    with pytest.raises(HTTPException) as exc_info:
        mark_notification_read(first.id, other, db)
    assert exc_info.value.status_code == 404

    assert mark_all_notifications_read(owner, db) == {"updated": 1}
    assert get_unread_notification_count(owner, db) == {"unread_count": 0}


def test_shop_purchase_creates_notification_in_same_user_feed(db):
    owner, _ = _users(db)
    item = ShopItem(
        name="Кольцо дозорного",
        description="Тестовая реликвия",
        price=40,
        item_type="relic",
        rarity="rare",
        is_available=True,
    )
    db.add(item)
    db.commit()

    result = UserItemService().purchase_item(
        db,
        owner.id,
        PurchaseRequest(item_id=item.id),
    )

    event = db.query(UserNotification).filter_by(user_id=owner.id).one()
    assert result["new_balance"] == 60
    assert event.notification_type == "shop_purchase"
    assert event.entity_type == "shop_item"
    assert event.entity_id == item.id
    assert event.link_url == "/shop"


def test_clan_notification_fans_out_to_current_members(db):
    leader, member = _users(db)
    clan = Clan(name="Хранители уведомлений", leader_id=leader.id)
    db.add(clan)
    db.flush()
    db.add_all([
        ClanMember(clan_id=clan.id, user_id=leader.id),
        ClanMember(clan_id=clan.id, user_id=member.id),
    ])
    db.commit()

    created = notification_service.create_for_clan(
        db,
        clan_id=clan.id,
        notification_type="war_started",
        title="Началась битва",
        message="Клан выступил в поход.",
        link_url="/battles/17",
        entity_type="clan_war",
        entity_id=17,
        commit=True,
    )

    assert created == 2
    assert {
        notification.user_id
        for notification in db.query(UserNotification).filter_by(entity_id=17).all()
    } == {leader.id, member.id}

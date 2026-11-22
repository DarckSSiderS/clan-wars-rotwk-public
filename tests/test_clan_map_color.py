import pytest
from pydantic import ValidationError

from app.core.exceptions import InsufficientPermissionsException
from app.core.clan_colors import (
    CLAN_MAP_COLOR_GROUPS,
    CLAN_MAP_COLORS,
)
from app.models.clan import Clan
from app.models.campaign import CampaignSeason
from app.models.role import Role
from app.models.user import User
from app.core.time import utc_now
from app.schemas.clan import ClanUpdate
from app.schemas.clan import Clan as ClanSchema, ClanCreate
from app.services.clan_service import ClanService


def test_clan_map_palette_contains_clear_color_families():
    grouped_colors = [
        color
        for group in CLAN_MAP_COLOR_GROUPS
        for color in group["colors"]
    ]

    assert len(grouped_colors) == 24
    assert len(set(grouped_colors)) == 24
    assert set(grouped_colors) == CLAN_MAP_COLORS
    assert {"#D32F2F", "#FBC02D", "#00897B", "#3949AB", "#AD1457"}.issubset(
        CLAN_MAP_COLORS
    )


def test_saved_legacy_color_is_readable_but_cannot_be_selected_again():
    stored_clan = ClanSchema(
        id=1,
        name="Старый цвет",
        leader_id=1,
        map_color="#C97518",
        level=1,
        experience=0,
        max_members=50,
        created_at=utc_now(),
    )

    assert stored_clan.map_color == "#C97518"
    with pytest.raises(ValidationError):
        ClanCreate(name="Новый клан", map_color="#C97518")


def test_clan_map_color_can_be_selected_then_changed_once_before_first_season(db):
    leader = User(username="color_leader", email="color@test", hashed_password="x")
    db.add(leader)
    db.flush()
    clan = Clan(
        name="Цветной клан",
        leader_id=leader.id,
        base_influence=100,
        territory_points=100,
    )
    db.add(clan)
    db.commit()
    service = ClanService()

    updated = service.update_clan(
        db,
        clan.id,
        ClanUpdate(map_color="#43A047"),
    )
    assert updated.map_color == "#43A047"
    assert updated.map_color_change_used is False

    updated = service.update_clan(
        db,
        clan.id,
        ClanUpdate(map_color="#D32F2F"),
    )
    assert updated.map_color == "#D32F2F"
    assert updated.map_color_change_used is True

    with pytest.raises(InsufficientPermissionsException):
        service.update_clan(
            db,
            clan.id,
            ClanUpdate(map_color="#F57C00"),
        )


def test_clan_map_color_change_is_locked_after_first_season(db):
    clan = Clan(name="Сезонный цвет", leader_id=1, map_color="#39D353")
    db.add_all([
        clan,
        CampaignSeason(
            number=1,
            name="Первый сезон",
            status="completed",
            starts_at=utc_now(),
        ),
    ])
    db.commit()

    with pytest.raises(InsufficientPermissionsException):
        ClanService().update_clan(
            db,
            clan.id,
            ClanUpdate(map_color="#D32F2F"),
        )


def test_admin_can_change_clan_map_color_after_season(db):
    admin_role = Role(name="admin", description="Администратор")
    admin = User(
        username="color_admin",
        email="color-admin@test",
        hashed_password="x",
        role=admin_role,
    )
    clan = Clan(name="Административный цвет", leader_id=1, map_color="#39D353")
    db.add_all([
        admin_role,
        admin,
        clan,
        CampaignSeason(
            number=1,
            name="Первый сезон",
            status="active",
            starts_at=utc_now(),
        ),
    ])
    db.commit()

    updated = ClanService().update_clan(
        db,
        clan.id,
        ClanUpdate(map_color="#D32F2F"),
        actor=admin,
    )

    assert updated.map_color == "#D32F2F"


def test_clan_map_color_must_be_unique(db):
    first = Clan(name="Первый цвет", leader_id=1, map_color="#43A047")
    second = Clan(name="Второй цвет", leader_id=2)
    db.add_all([first, second])
    db.commit()

    with pytest.raises(InsufficientPermissionsException):
        ClanService().update_clan(
            db,
            second.id,
            ClanUpdate(map_color="#43A047"),
        )


def test_clan_map_color_state_reports_groups_and_blocked_reasons(db):
    first = Clan(name="Занятый цвет", leader_id=1, map_color="#00897B")
    second = Clan(name="Выбирающий цвет", leader_id=2)
    db.add_all([first, second])
    db.commit()

    state = ClanService().get_map_color_state(db, clan_id=second.id)
    blocked = {item["color"]: item["reason"] for item in state["blocked_colors"]}

    assert sum(len(group["colors"]) for group in state["groups"]) == 24
    assert blocked["#00897B"] == "occupied"
    assert "#2EAD4B" not in blocked
    assert state["season_started"] is False
    assert state["can_change_existing"] is True

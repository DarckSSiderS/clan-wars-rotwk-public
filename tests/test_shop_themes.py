from app.models.shop import ShopItem
from app.schemas.shop import EquipRequest, PurchaseRequest
from app.services.bootstrap_service import ensure_default_admin, ensure_shop_content
from app.services.shop_service import UserItemService


def test_shop_theme_seed_is_idempotent(db):
    ensure_shop_content(db)
    ensure_shop_content(db)

    themes = db.query(ShopItem).filter(ShopItem.item_type == "site_theme").all()

    assert len(themes) == 3
    assert {theme.css_class for theme in themes} == {
        "theme-mordor",
        "theme-gondor",
        "theme-rivendell",
    }
    assert {theme.slot for theme in themes} == {"site_theme"}


def test_shop_seed_includes_independent_profile_layers(db):
    ensure_shop_content(db)

    cosmetics = (
        db.query(ShopItem)
        .filter(ShopItem.item_type.in_(["avatar_frame", "profile_background"]))
        .all()
    )

    assert {(item.item_type, item.slot, item.css_class) for item in cosmetics} == {
        ("avatar_frame", "avatar_frame", "avatar-frame-palantir"),
        (
            "profile_background",
            "profile_background",
            "profile-background-starlight",
        ),
    }


def test_equipping_a_theme_replaces_the_active_theme(db):
    user = ensure_default_admin(db)
    ensure_shop_content(db)
    service = UserItemService()
    themes = (
        db.query(ShopItem)
        .filter(ShopItem.item_type == "site_theme")
        .order_by(ShopItem.id)
        .limit(2)
        .all()
    )

    owned = [
        service.purchase_item(db, user.id, PurchaseRequest(item_id=theme.id))["user_item"]
        for theme in themes
    ]
    service.equip_item(db, user.id, EquipRequest(user_item_id=owned[0].id))
    service.equip_item(db, user.id, EquipRequest(user_item_id=owned[1].id))

    equipped = service.get_equipped_items(db, user.id)
    assert [item.id for item in equipped] == [owned[1].id]

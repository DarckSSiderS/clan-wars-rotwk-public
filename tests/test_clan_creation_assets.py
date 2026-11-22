from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette.datastructures import Headers

from app.api.v1.clans import create_clan_with_assets
from app.config import settings
from app.models.clan import Clan as ClanModel
from app.models.territory import Territory
from app.models.user import User
from app.schemas.clan import Clan as ClanSchema


def test_clan_schema_exposes_separate_map_emblem_url():
    clan = ClanModel(
        id=41,
        name="Хранители эмблемы",
        leader_id=7,
        avatar_url="/images/clans/avatar.gif",
        map_emblem_url="/images/clans/map-emblems/emblem.webp",
        map_color_change_used=False,
        level=1,
        experience=0,
        max_members=20,
        resources=0,
        base_influence=100,
        territory_points=0,
        gold_income_remainder=0,
        gold=0,
        iron=0,
        wood=0,
        food=0,
        mithril=0,
        is_admin_clan=False,
        preferred_patch="all",
        created_at=datetime.now(timezone.utc),
    )

    result = ClanSchema.model_validate(clan)

    assert result.map_emblem_url == "/images/clans/map-emblems/emblem.webp"


def make_image_bytes(image_format="PNG", color=(180, 45, 45)):
    output = BytesIO()
    Image.new("RGB", (48, 32), color).save(output, format=image_format)
    return output.getvalue()


def make_upload(filename, content, content_type):
    return UploadFile(
        file=BytesIO(content),
        filename=filename,
        size=len(content),
        headers=Headers({"content-type": content_type}),
    )


def create_user(db, username):
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_clan_with_assets_stores_avatar_and_static_map_emblem(
    db,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    user = create_user(db, "asset_leader")

    created = create_clan_with_assets(
        name="Красные врата",
        motto="Стоим до конца",
        description="Клан для проверки оформления.",
        preferred_patch="all",
        map_color="#D32F2F",
        avatar=make_upload("avatar.png", make_image_bytes(), "image/png"),
        map_emblem=make_upload(
            "emblem.png",
            make_image_bytes(color=(35, 80, 145)),
            "image/png",
        ),
        current_user=user,
        db=db,
    )

    assert created.avatar_url.startswith("/images/clans/")
    assert created.map_emblem_url.startswith("/images/clans/map-emblems/")
    avatar_path = tmp_path / created.avatar_url.removeprefix("/images/")
    emblem_path = tmp_path / created.map_emblem_url.removeprefix("/images/")
    assert avatar_path.is_file()
    assert emblem_path.is_file()
    with Image.open(emblem_path) as emblem:
        assert emblem.format == "WEBP"
        assert emblem.size == (150, 150)


def test_create_clan_with_broken_emblem_leaves_no_clan_or_files(
    db,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    user = create_user(db, "broken_asset_leader")

    with pytest.raises(HTTPException) as error:
        create_clan_with_assets(
            name="Несозданный клан",
            motto="",
            description="",
            preferred_patch="ennorath",
            map_color="#D32F2F",
            avatar=make_upload("avatar.png", make_image_bytes(), "image/png"),
            map_emblem=make_upload("broken.png", b"not an image", "image/png"),
            current_user=user,
            db=db,
        )

    assert error.value.status_code == 400
    assert db.query(ClanModel).filter(ClanModel.name == "Несозданный клан").first() is None
    assert not list(tmp_path.rglob("*.*"))


def test_territory_exposes_owner_map_emblem():
    clan = ClanModel(map_emblem_url="/images/clans/map-emblems/owner.webp")
    territory = Territory(owner_clan=clan)

    assert territory.owner_clan_map_emblem_url == "/images/clans/map-emblems/owner.webp"

import copy
import hashlib
import json
from datetime import timedelta
from xml.etree import ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.time import utc_now
from app.database import get_db
from app.models.achievement import Achievement, UserAchievement
from app.models.campaign import CampaignSeason, CampaignSeasonClanResult
from app.models.clan import Clan
from app.models.territory import Territory
from app.models.user import User
from app.models.war import ClanWar
from app.services.campaign_history_service import CampaignHistoryService


@pytest.fixture
def campaign(db):
    first = Clan(name="Frozen clan", map_color="#123456", territory_points=500, gold=700)
    second = Clan(name="Other clan", map_color="#654321", territory_points=300)
    db.add_all([first, second])
    db.flush()
    lands = [
        Territory(name="Arnor", region="arnor", svg_path_data="M 0 0 L 10 0 Z",
                  owner_clan_id=first.id, influence_value=50, development_level=4,
                  fortifications=3, offense_level=2, port_level=2, fleet_level=1,
                  has_port=True, stronghold_power=3, population=1200),
        Territory(name="Eriador", region="eriador", svg_path_data="M 10 0 L 20 0 Z",
                  owner_clan_id=first.id, influence_value=30),
        Territory(name="Mordor", region="mordor", svg_path_data="M 20 0 L 30 0 Z",
                  owner_clan_id=first.id, influence_value=80),
    ]
    db.add_all(lands)
    season = CampaignSeason(number=1, name="Frozen season", starts_at=utc_now() - timedelta(days=30),
                            status="active", rules_snapshot={"secret": "private-rule-value"})
    db.add(season)
    db.commit()
    return season, first, second, lands


@pytest.fixture
def client(db):
    from app.api.v1.campaign import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as result:
        yield result


def archive_model():
    from app.models.season_archive import CampaignSeasonArchive
    return CampaignSeasonArchive


def finish(db):
    return CampaignHistoryService().complete_active_season(db)


def test_completion_freezes_geometry_owners_development_results_and_awards(db, campaign):
    season, first, second, lands = campaign
    original_gold = first.gold
    finish(db)
    archive = db.get(archive_model(), season.id)
    payload = archive.payload
    assert payload["season"]["name"] == "Frozen season"
    assert payload["season"]["ends_at"]
    assert payload["schema_version"] == archive.schema_version == 1
    assert payload["captured_at"]
    assert payload["view_box"] == "0 0 3570.6 2339.7"
    land = payload["territories"][0]
    assert {key: land[key] for key in ("id", "name", "owner_clan_id", "owner_clan_name", "owner_clan_map_color")} == {
        "id": lands[0].id, "name": "Arnor", "owner_clan_id": first.id,
        "owner_clan_name": "Frozen clan", "owner_clan_map_color": "#123456",
    }
    assert land["svg_path_data"] == "M 0 0 L 10 0 Z"
    assert [land[key] for key in ("development_level", "fortifications", "offense_level", "port_level", "fleet_level", "stronghold_power", "influence_value")] == [4, 3, 2, 2, 1, 3, 50]
    assert land["is_playable"] is True and land["has_port"] is True
    result = payload["clans"][0]
    assert (result["clan_id"], result["rank"], result["influence"], result["gold"]) == (first.id, 1, 500, 700)
    assert result["clan_name"] == "Frozen clan" and result["clan_map_color"] == "#123456"
    assert [a["image"] for a in result["awards"]] == [
        "/assets/awards/clan/season-champion.png", "/assets/awards/clan/region-arnor.png",
        "/assets/awards/clan/region-mordor.png",
    ]
    assert result["awards"][1] == {
        "key": "region-arnor", "image": "/assets/awards/clan/region-arnor.png",
        "label_key": "clan_award_eriador", "description_key": "clan_award_regional_description",
    }
    assert first.gold == original_gold
    assert db.query(CampaignSeasonClanResult).count() == 2


def test_public_archive_is_immutable_after_live_changes_and_repeated_capture(db, campaign, client, monkeypatch):
    from app.services.season_archive_service import SeasonArchiveService

    season, first, second, lands = campaign
    finish(db)
    db.commit()
    archive = db.get(archive_model(), season.id)
    original = copy.deepcopy(archive.payload), archive.map_svg, archive.checksum, archive.captured_at
    detail_before = client.get(f"/api/v1/campaign/archives/{season.id}").json()
    list_before = client.get("/api/v1/campaign/archives").json()
    first.name, first.map_color, first.territory_points = "Renamed", "#ffffff", 1
    season.name = "Renamed season"
    lands[0].owner_clan_id, lands[0].name, lands[0].svg_path_data = second.id, "Changed", "M 999 999"
    lands[0].development_level = 0
    db.commit()
    monkeypatch.setattr(SeasonArchiveService, "_freeze_map", lambda self: pytest.fail("must not reread assets"))
    assert finish(db) is None
    assert SeasonArchiveService().capture(db, season) is archive
    db.commit()
    assert db.query(archive_model()).count() == 1
    assert db.query(CampaignSeasonClanResult).count() == 2
    assert (archive.payload, archive.map_svg, archive.checksum, archive.captured_at) == original
    assert client.get(f"/api/v1/campaign/archives/{season.id}").json() == detail_before
    assert client.get("/api/v1/campaign/archives").json() == list_before


def test_completion_has_no_implicit_commit_and_rolls_back_archive_and_results(db, campaign, monkeypatch):
    season, *_ = campaign
    season_id = season.id
    monkeypatch.setattr(db, "commit", lambda: pytest.fail("implicit commit"))
    finish(db)
    assert db.get(archive_model(), season_id) is not None
    db.rollback()
    assert db.get(CampaignSeason, season_id).status == "active"
    assert db.query(archive_model()).count() == db.query(CampaignSeasonClanResult).count() == 0


def test_capture_failure_rolls_back_entire_completion(db, campaign, monkeypatch):
    from app.services.season_archive_service import SeasonArchiveService

    season, *_ = campaign
    season_id = season.id
    def fail(self):
        raise ValueError("missing backdrop")
    monkeypatch.setattr(SeasonArchiveService, "_freeze_map", fail)
    with pytest.raises(ValueError, match="missing backdrop"):
        finish(db)
    db.rollback()
    assert db.get(CampaignSeason, season_id).status == "active"
    assert db.query(archive_model()).count() == db.query(CampaignSeasonClanResult).count() == 0


def test_active_legacy_war_blocks_completion_before_any_results(db, campaign):
    season, first, second, lands = campaign
    db.add(ClanWar(territory_id=lands[0].id, attacking_clan_id=first.id,
                   defending_clan_id=second.id, war_type="territory_attack", status="active"))
    db.flush()
    with pytest.raises(ValueError, match="[Aa]ctive.*war"):
        finish(db)
    assert season.status == "active" and season.ends_at is None
    assert db.query(CampaignSeasonClanResult).count() == 0
    assert db.query(archive_model()).count() == 0


def test_public_endpoints_need_no_auth_and_never_backfill(db, campaign, client):
    season, *_ = campaign
    assert client.get("/api/v1/campaign/archives").json() == {"seasons": []}
    for tail in (str(season.id), f"{season.id}/map.svg", "9999"):
        assert client.get(f"/api/v1/campaign/archives/{tail}").status_code == 404
    season.status, season.ends_at = "completed", utc_now()
    db.commit()
    assert client.get("/api/v1/campaign/archives").json() == {"seasons": []}
    assert client.get(f"/api/v1/campaign/archives/{season.id}").status_code == 404
    assert client.get(f"/api/v1/campaign/archives/{season.id}/map.svg").status_code == 404
    assert db.query(archive_model()).count() == 0


def test_public_payload_excludes_personal_secrets_and_changes_no_player_awards(db, campaign, client):
    season, first, *_ = campaign
    user = User(username="private-name", email="private@example.invalid", hashed_password="password-secret", balance=321)
    achievement = Achievement(name="personal", description="private-achievement", icon="star", category="combat",
                              requirement_type="wins", requirement_value=1, reward_amount=900)
    db.add_all([user, achievement])
    db.flush()
    player_award = UserAchievement(user_id=user.id, achievement_id=achievement.id, progress=7, is_completed=True)
    db.add(player_award)
    db.commit()
    before = (user.balance, player_award.progress, player_award.completed_at, first.gold)
    finish(db)
    db.commit()
    detail = client.get(f"/api/v1/campaign/archives/{season.id}")
    listing = client.get("/api/v1/campaign/archives")
    assert detail.status_code == listing.status_code == 200
    assert detail.json()["map_image_url"] == f"/api/v1/campaign/archives/{season.id}/map.svg"
    assert listing.json()["seasons"][0]["id"] == season.id
    assert listing.json()["seasons"][0]["winner"]["clan_name"] == "Frozen clan"
    for secret in ("private-name", "private@example.invalid", "password-secret", "private-achievement", "private-rule-value", "hashed_password", "created_by_user_id"):
        assert secret not in detail.text + listing.text
    db.refresh(user)
    db.refresh(player_award)
    assert (user.balance, player_award.progress, player_award.completed_at, first.gold) == before
    assert db.query(UserAchievement).count() == 1


def test_frozen_map_and_checksum_survive_asset_changes(db, campaign, client, monkeypatch, tmp_path):
    import app.services.season_archive_service as module

    season, *_ = campaign
    finish(db)
    db.commit()
    archive = db.get(archive_model(), season.id)
    body = json.dumps({"payload": archive.payload, "map_svg": archive.map_svg}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert archive.checksum == hashlib.sha256(body).hexdigest()
    monkeypatch.setattr(module, "MAP_ASSET_DIR", tmp_path)
    response = client.get(f"/api/v1/campaign/archives/{season.id}/map.svg")
    assert response.status_code == 200
    assert response.text == archive.map_svg
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["x-content-type-options"] == "nosniff"
    policy = response.headers["content-security-policy"]
    assert "sandbox" in policy and "default-src 'none'" in policy and "img-src data:" in policy
    root = ET.fromstring(response.text)
    assert root.attrib["viewBox"] == archive.payload["view_box"]
    images = [node for node in root.iter() if node.tag.endswith("}image")]
    assert images and len(response.content) > 1_000_000
    assert images[0].attrib["href"].startswith("data:image/jpeg;base64,")
    assert not any(node.tag.rsplit("}", 1)[-1] in ("script", "foreignObject") for node in root.iter())


def test_legacy_ranking_formula_is_preserved(db, campaign):
    season, first, second, _ = campaign
    second.territory_points = first.territory_points
    expected = CampaignHistoryService()._build_rankings(db, season.starts_at, utc_now())
    finish(db)
    rows = db.query(CampaignSeasonClanResult).order_by(CampaignSeasonClanResult.rank).all()
    assert [(r.clan_id, r.rank, r.influence) for r in rows] == [(r["clan_id"], r["rank"], r["influence"]) for r in expected]
    assert [(r["clan_id"], r["rank"], r["influence"]) for r in db.get(archive_model(), season.id).payload["clans"]] == [(r.clan_id, r.rank, r.influence) for r in rows]


def test_backdrop_keeps_only_embedded_raster_and_numeric_geometry(db, campaign, tmp_path, monkeypatch):
    import app.services.season_archive_service as module

    # A raster-only SVG is safe both as an <image> source and when opened directly.
    source = ET.parse(module.MAP_ASSET_DIR / "map.svg").getroot()
    image = next(node for node in source.iter() if node.tag.endswith("}image"))
    image.attrib["onload"] = "alert('private-script')"
    source.append(ET.fromstring('<script xmlns="http://www.w3.org/2000/svg">alert(1)</script>'))
    source.append(ET.fromstring('<foreignObject xmlns="http://www.w3.org/2000/svg"><div>unsafe</div></foreignObject>'))
    source.append(ET.fromstring('<image xmlns="http://www.w3.org/2000/svg" href="https://evil.invalid/map.png"/>'))
    source.append(ET.fromstring('<image xmlns="http://www.w3.org/2000/svg" href="data:image/svg+xml;base64,PHN2Zy8+"/>'))
    (tmp_path / "map.svg").write_bytes(ET.tostring(source))
    (tmp_path / "map-interactive.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600"/>', encoding="utf-8")
    monkeypatch.setattr(module, "MAP_ASSET_DIR", tmp_path)
    season, *_ = campaign
    finish(db)
    archive = db.get(archive_model(), season.id)
    assert archive.payload["view_box"] == "0 0 800 600"
    root = ET.fromstring(archive.map_svg)
    assert root.attrib["viewBox"] == "0 0 800 600"
    assert len(list(root)) == 1
    assert not any(key.lower().startswith("on") for node in root.iter() for key in node.attrib)
    for text in ("private-script", "script", "foreignObject", "evil.invalid", "svg+xml", "url("):
        assert text not in archive.map_svg


@pytest.mark.parametrize("svg", [
    '<!DOCTYPE svg [<!ENTITY secret "unsafe">]><svg>&secret;</svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil.invalid/map.png"/></svg>',
])
def test_unsafe_or_missing_raster_prevents_completion(db, campaign, tmp_path, monkeypatch, svg):
    import app.services.season_archive_service as module

    (tmp_path / "map.svg").write_text(svg, encoding="utf-8")
    (tmp_path / "map-interactive.svg").write_text('<svg viewBox="0 0 800 600"/>', encoding="utf-8")
    monkeypatch.setattr(module, "MAP_ASSET_DIR", tmp_path)
    with pytest.raises(ValueError):
        finish(db)
    db.rollback()
    assert db.query(CampaignSeason).one().status == "active"
    assert db.query(archive_model()).count() == db.query(CampaignSeasonClanResult).count() == 0


def test_public_json_reads_only_archive_metadata_without_writes_or_svg(db, campaign, client):
    season, *_ = campaign
    season_id = season.id
    finish(db)
    db.commit()
    db.expunge_all()
    statements = []
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client.get("/api/v1/campaign/archives").status_code == 200
        assert client.get(f"/api/v1/campaign/archives/{season_id}").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 2
    assert all(statement.lstrip().startswith("select") for statement in statements)
    assert all("map_svg" not in statement for statement in statements)
    assert all("territories" not in statement and "join clans" not in statement for statement in statements)


def test_completion_api_is_admin_only_and_active_war_conflict_is_atomic(db, campaign, client):
    from app.core.auth import get_current_admin_user

    season, first, second, lands = campaign
    url = "/api/v1/campaign/seasons/current/complete"
    assert client.post(url).status_code in (401, 403)
    client.app.dependency_overrides[get_current_admin_user] = lambda: object()
    db.add(ClanWar(territory_id=lands[0].id, attacking_clan_id=first.id,
                   defending_clan_id=second.id, war_type="territory_attack", status="active"))
    db.commit()
    response = client.post(url)
    assert response.status_code == 409
    db.refresh(season)
    assert season.status == "active"
    assert db.query(archive_model()).count() == db.query(CampaignSeasonClanResult).count() == 0


def test_completion_api_captures_once_and_preserves_archive_on_retry(db, campaign, client):
    from app.core.auth import get_current_admin_user

    season, *_ = campaign
    client.app.dependency_overrides[get_current_admin_user] = lambda: object()
    url = "/api/v1/campaign/seasons/current/complete"
    assert client.post(url).status_code == 200
    original = client.get(f"/api/v1/campaign/archives/{season.id}").json()
    assert client.post(url).status_code == 409
    assert client.get(f"/api/v1/campaign/archives/{season.id}").json() == original
    assert db.query(archive_model()).count() == 1
    assert db.query(CampaignSeason).count() == 1


def test_completion_excludes_deleted_clans_and_freezes_their_lands_as_neutral(db, campaign, client):
    season, first, second, _ = campaign
    history = CampaignHistoryService()
    expected = history._build_rankings(db, season.starts_at, utc_now())
    deleted = Clan(id=17, name="LastUnion17-deleted", map_color="#abcdef", is_deleted=True,
                   territory_points=350, gold=1234)
    other_deleted = [Clan(name=f"Deleted clan {index}", is_deleted=True, territory_points=9000)
                     for index in range(7)]
    db.add_all([deleted, *other_deleted])
    db.flush()
    orphaned_lands = [Territory(name=f"Historical land {index}", region="gondor", svg_path_data="M 0 0 Z",
                               owner_clan_id=deleted.id, influence_value=70, development_level=3)
                      for index in range(5)]
    db.add_all(orphaned_lands)
    db.commit()
    finish(db)
    db.commit()
    results = db.query(CampaignSeasonClanResult).order_by(CampaignSeasonClanResult.rank).all()
    assert [history._serialize_result(row) | {"captured_at": None} for row in results] == [
        row | {"captured_at": None} for row in expected
    ]
    payload = client.get(f"/api/v1/campaign/archives/{season.id}").json()
    listing = client.get("/api/v1/campaign/archives").json()
    assert {row["clan_id"] for row in payload["clans"]} == {first.id, second.id}
    assert listing["seasons"][0]["clan_count"] == 2
    assert listing["seasons"][0]["winner"]["clan_id"] == first.id
    assert [row["awards"][0]["key"] for row in payload["clans"]] == ["season-champion", "season-runner-up"]
    for land in orphaned_lands:
        frozen = next(row for row in payload["territories"] if row["id"] == land.id)
        assert frozen["owner_clan_id"] is None
        assert frozen["owner_clan_name"] is None
        assert frozen["owner_clan_map_color"] is None
        assert frozen["development_level"] == 3 and frozen["influence_value"] == 70
        db.refresh(land)
        assert land.owner_clan_id == deleted.id
    public_text = json.dumps([payload, listing])
    assert "LastUnion17-deleted" not in public_text and "Deleted clan" not in public_text
    db.refresh(deleted)
    assert deleted.is_deleted and deleted.territory_points == 350 and deleted.gold == 1234

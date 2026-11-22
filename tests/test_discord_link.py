from datetime import datetime, timedelta, timezone

import pytest

from app.models.user import User
from app.services.discord_link_service import (
    LinkError,
    consume_link_code,
    issue_link_code,
    unlink,
)
from app.models.discord import DiscordLink, DiscordLinkCode

NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
DID = "1551937393144238201"


def user(db, name="frodo", **kwargs):
    record = User(username=name, is_active=True, is_claimed=True, **kwargs)
    db.add(record)
    db.commit()
    return record


def test_one_time_code_stores_only_hash_and_links_correct_account(db):
    account = user(db)
    code = issue_link_code(db, DID, now=NOW)
    assert db.query(DiscordLinkCode).one().code_hash != code
    link = consume_link_code(db, account, code, now=NOW)
    assert link.discord_user_id == DID
    assert link.user_id == account.id
    with pytest.raises(LinkError):
        consume_link_code(db, account, code, now=NOW)


def test_new_code_invalidates_previous_code(db):
    account = user(db)
    old = issue_link_code(db, DID, now=NOW)
    new = issue_link_code(db, DID, now=NOW)
    with pytest.raises(LinkError):
        consume_link_code(db, account, old, now=NOW)
    assert consume_link_code(db, account, new, now=NOW).discord_user_id == DID


def test_expiry_is_enforced_at_exact_deadline(db):
    account = user(db)
    code = issue_link_code(db, DID, now=NOW)
    with pytest.raises(LinkError):
        consume_link_code(db, account, code, now=NOW + timedelta(minutes=10))
    assert db.query(DiscordLink).count() == 0


def test_identity_cannot_be_taken_by_second_account(db):
    first = user(db)
    second = user(db, "sam")
    consume_link_code(db, first, issue_link_code(db, DID, now=NOW), now=NOW)
    code = issue_link_code(db, DID, now=NOW)
    with pytest.raises(LinkError):
        consume_link_code(db, second, code, now=NOW)
    assert db.query(DiscordLink).one().user_id == first.id


def test_account_cannot_be_silently_rebound(db):
    account = user(db)
    consume_link_code(db, account, issue_link_code(db, DID, now=NOW), now=NOW)
    other = issue_link_code(db, "1551937393144238202", now=NOW)
    with pytest.raises(LinkError):
        consume_link_code(db, account, other, now=NOW)
    unlink(db, account.id)
    assert consume_link_code(db, account, other, now=NOW).discord_user_id.endswith(
        "202"
    )


@pytest.mark.parametrize("attribute", ["is_active", "is_claimed"])
def test_ineligible_account_cannot_link(db, attribute):
    account = user(db)
    setattr(account, attribute, False)
    db.commit()
    with pytest.raises(LinkError):
        consume_link_code(db, account, issue_link_code(db, DID, now=NOW), now=NOW)


@pytest.mark.parametrize("bad_id", ["x", "0", "-1", "1" * 30])
def test_invalid_discord_id_is_rejected(db, bad_id):
    with pytest.raises(LinkError):
        issue_link_code(db, bad_id, now=NOW)


def test_api_requires_session_rejects_impersonation_and_cross_site(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.v1.discord import router
    from app.core.auth import get_current_active_user
    from app.config import settings
    from app.database import get_db

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    account = user(db)
    monkeypatch.setattr(settings, "DISCORD_ENABLED", True)
    with TestClient(app) as client:
        assert client.get("/discord/link").status_code == 401
        app.dependency_overrides[get_current_active_user] = lambda: account
        code = issue_link_code(db, DID)
        account._is_admin_impersonation = True
        assert client.post("/discord/link", json={"code": code}).status_code == 403
        account._is_admin_impersonation = False
        assert (
            client.post(
                "/discord/link",
                json={"code": code},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        response = client.post("/discord/link", json={"code": code})
        assert response.status_code == 200
        assert response.json()["discord_user_id"] == DID
        assert response.headers["cache-control"] == "no-store"
        assert client.delete("/discord/link").status_code == 204
        assert client.get("/discord/link").json()["discord_user_id"] is None
        monkeypatch.setattr(settings, "DISCORD_ENABLED", False)
        assert client.get("/discord/link").json()["enabled"] is False
        assert client.post("/discord/link", json={"code": code}).status_code == 503


def test_discord_migration_round_trip_on_disposable_database():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    path = (
        Path(__file__).parents[1]
        / "alembic/versions/d6s7t8u9v0w1_add_discord_integration.py"
    )
    spec = importlib.util.spec_from_file_location("discord_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            assert {
                "discord_links",
                "discord_link_codes",
                "discord_resources",
                "discord_deliveries",
            } <= set(inspect(connection).get_table_names())
            module.downgrade()
            assert inspect(connection).get_table_names() == ["users"]


def test_simultaneous_claims_have_exactly_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'discord-race.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        first, second = user(db, "frodo"), user(db, "sam")
        ids = [first.id, second.id]
        code = issue_link_code(db, DID)
    barrier = Barrier(2)

    def claim(uid):
        with sessions() as db:
            account = db.get(User, uid)
            barrier.wait(timeout=5)
            try:
                consume_link_code(db, account, code)
                return True
            except LinkError:
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ids))
    assert sorted(results) == [False, True]
    with sessions() as db:
        assert db.query(DiscordLink).count() == 1
        assert db.query(DiscordLinkCode).count() == 0
    engine.dispose()

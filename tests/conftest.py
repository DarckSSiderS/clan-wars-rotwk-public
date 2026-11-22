import pytest
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401


@pytest.fixture(autouse=True)
def no_live_arena_ratings(monkeypatch):
    from app.services.arena_current_rating_service import arena_current_ratings

    async def empty_patch(patch):
        return []

    monkeypatch.setattr(arena_current_ratings, 'fetch_patch', empty_patch)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def postgres_db():
    """Disposable PostgreSQL only: exercise real transactions and foreign keys."""
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL concurrency checks")
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert parsed.database == "clanwar_test"
    # Старые поля DateTime без зоны также проверяем в UTC независимо от настроек хоста.
    engine = create_engine(url, connect_args={"options": "-c lock_timeout=10000 -c statement_timeout=20000 -c timezone=UTC"})
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        tables = ", ".join('"' + name + '"' for name in Base.metadata.tables)
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = sessionmaker(bind=engine, autoflush=False)()
    from app.models.role import Role
    session.add_all([Role(id=1, name="admin"), Role(id=2, name="user")])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

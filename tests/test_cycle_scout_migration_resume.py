"""Доработка уже подготовленной тестовой схемы не дублирует столбцы разведчика."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.database import Base


def test_scout_upgrade_accepts_existing_valid_columns_without_losing_assignment():
    path = Path(__file__).parents[1] / 'alembic/versions/q9f0g1h2i3j4_add_cycle_scout_player.py'
    spec = importlib.util.spec_from_file_location('scout_resume_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO cycle_scout_requests (id, cycle_id, clan_id, territory_id, requested_at, scout_user_id, scout_uuid) VALUES (1, 1, 1, 1, '2026-10-31', 7, '00000000-0000-0000-0000-000000000007')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert connection.execute(text('SELECT scout_user_id, scout_uuid FROM cycle_scout_requests')).one() == (
                7, '00000000-0000-0000-0000-000000000007')
            assert {'scout_user_id', 'scout_uuid'} <= {c['name'] for c in inspect(connection).get_columns('cycle_scout_requests')}
    finally:
        engine.dispose()

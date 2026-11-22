"""Миграция журнала решений не изменяет матчи и территориальные бои."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models.cycle_battle import CycleLateReplayDecision


def test_late_review_migration_adds_only_its_journal_and_downgrades():
    path = Path(__file__).parents[1] / 'alembic/versions/p8e9f0g1h2i3_add_late_replay_decisions.py'
    spec = importlib.util.spec_from_file_location('late_review_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with create_engine('sqlite://').begin() as connection:
        table = CycleLateReplayDecision.__table__
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
        before = connection.execute(text('SELECT count(*) FROM matches')).scalar_one()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)
        assert set(table.columns.keys()) == {c['name'] for c in inspector.get_columns(table.name)}
        assert inspector.get_foreign_keys(table.name)
        assert inspector.get_unique_constraints(table.name)
        assert connection.execute(text('SELECT count(*) FROM matches')).scalar_one() == before
        migration.downgrade()
        assert table.name not in inspect(connection).get_table_names()
        assert 'cycle_territory_battles' in inspect(connection).get_table_names()

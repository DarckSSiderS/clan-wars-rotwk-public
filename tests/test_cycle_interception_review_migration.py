import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.database import Base


def migration(prefix):
    path = next((Path(__file__).parents[1] / 'alembic/versions').glob(prefix + '*.py'), None)
    assert path is not None, 'Нет additive-миграции пересмотра перехватов'
    spec = importlib.util.spec_from_file_location(prefix, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_review_migration_is_nullable_additive_and_preserves_existing_rows():
    old = migration('m5b6c7d8e9f0')
    new = migration('n6c7d8e9f0g1')
    assert new.down_revision == old.revision
    with create_engine('sqlite://').begin() as connection:
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables
            if not t.name.startswith('cycle_interception')])
        operations = Operations(MigrationContext.configure(connection))
        old.op = new.op = operations
        old.upgrade()
        connection.execute(text("INSERT INTO cycle_interceptions (id, cycle_id, dispatch_id, revision) VALUES (1, 1, 'd', 4)"))
        connection.execute(text("INSERT INTO cycle_interception_contributions (id, interception_id, replay_id, user_id, side_clan_id, points, counted, reason, calculation) VALUES (1, 1, 'r', 2, 3, 100, 1, 'counted', '{}')"))
        new.upgrade()
        assert connection.execute(text('SELECT revision, original_applied_result FROM cycle_interceptions')).one() == (4, None)
        assert connection.execute(text('SELECT points, counted, review_counted FROM cycle_interception_contributions')).one() == (100, 1, None)
        assert {'cycle_interception_review_commands', 'cycle_interception_adjustments'} <= set(inspect(connection).get_table_names())
        new.downgrade()
        assert connection.execute(text('SELECT revision FROM cycle_interceptions')).scalar_one() == 4

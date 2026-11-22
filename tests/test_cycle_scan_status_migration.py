import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models.cycle_arena_scan import CycleArenaScanState


def test_scan_migration_is_additive_and_has_one_chain():
    root = Path(__file__).parents[1]
    path = root / 'alembic/versions/s1g2h3i4j5k6_add_complete_arena_scan_state.py'
    spec = importlib.util.spec_from_file_location('scan_state_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    config = Config()
    config.set_main_option('script_location', str(root / 'alembic'))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ['u3i4j5k6l7m8']
    assert scripts.get_revision('t2h3i4j5k6l7').down_revision == 's1g2h3i4j5k6'
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            table = CycleArenaScanState.__table__
            Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
            connection.execute(text("INSERT INTO worker_heartbeats (worker_name, consecutive_failures) VALUES ('campaign', 3)"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert {c['name'] for c in inspect(connection).get_columns(table.name)} == set(table.columns.keys())
            assert connection.execute(text('SELECT consecutive_failures FROM worker_heartbeats')).scalar_one() == 3
            migration.downgrade()
            assert table.name not in inspect(connection).get_table_names()
            assert connection.execute(text('SELECT consecutive_failures FROM worker_heartbeats')).scalar_one() == 3
    finally:
        engine.dispose()

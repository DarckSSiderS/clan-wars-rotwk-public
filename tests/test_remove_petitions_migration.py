import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def load_migration(filename, operations):
    path = Path(__file__).parents[1] / 'alembic' / 'versions' / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = operations
    return module


def test_petition_cleanup_keeps_war_adjustments_and_can_restore_empty_schema():
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            old = load_migration('c5r6s7t8u9v0_petitions_and_war_adjustments.py', operations)
            old.upgrade()
            tables = {'petitions', 'petition_votes', 'petition_comments', 'petition_reactions'}
            original = {table: {c['name'] for c in inspect(connection).get_columns(table)} for table in tables}
            cleanup = load_migration('k3z4a5b6c7d8_remove_petitions.py', operations)
            cleanup.upgrade()
            assert not tables & set(inspect(connection).get_table_names())
            assert 'war_score_adjustments' in inspect(connection).get_table_names()
            cleanup.downgrade()
            assert original == {table: {c['name'] for c in inspect(connection).get_columns(table)} for table in tables}
    finally:
        engine.dispose()

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models.cycle_interception import CycleInterception, CycleInterceptionContribution


def test_interception_migration_matches_models_and_preserves_territory_battles():
    path = Path(__file__).parents[1] / 'alembic/versions/m5b6c7d8e9f0_add_cycle_interception_accounting.py'
    assert path.is_file(), 'Interception accounting migration missing'
    spec = importlib.util.spec_from_file_location('interception_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    review_path = next(path.parent.glob('n6c7d8e9f0g1*.py'))
    review_spec = importlib.util.spec_from_file_location('interception_review_migration', review_path)
    review = importlib.util.module_from_spec(review_spec)
    review_spec.loader.exec_module(review)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            tables = [CycleInterception.__table__, CycleInterceptionContribution.__table__]
            Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables
                if not t.name.startswith('cycle_interception')])
            migration.op = Operations(MigrationContext.configure(connection))
            review.op = migration.op
            migration.upgrade()
            review.upgrade()
            inspector = inspect(connection)
            for table in tables:
                assert {c['name'] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
                assert inspector.get_unique_constraints(table.name)
                assert inspector.get_foreign_keys(table.name)
            review.downgrade()
            migration.downgrade()
            assert all(t.name not in inspect(connection).get_table_names() for t in tables)
            assert 'cycle_territory_battles' in inspect(connection).get_table_names()
    finally:
        engine.dispose()

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models.cycle_battle import CycleOwnershipCorrection


def test_ownership_correction_migration_matches_model_and_preserves_battles():
    path = Path(__file__).parents[1] / 'alembic/versions/l4a5b6c7d8e9_add_cycle_ownership_corrections.py'
    assert path.is_file(), 'Ownership correction journal migration is missing'
    spec = importlib.util.spec_from_file_location('ownership_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            table = CycleOwnershipCorrection.__table__
            Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            inspector = inspect(connection)
            assert {c['name'] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
            unique = inspector.get_unique_constraints(table.name)
            assert any(set(c['column_names']) == {'season_id', 'command_id'} for c in unique)
            assert {tuple(f['constrained_columns']) for f in inspector.get_foreign_keys(table.name)} == {
                ('season_id',), ('battle_id',), ('current_cycle_id',), ('territory_id',),
                ('previous_owner_clan_id',), ('new_owner_clan_id',), ('actor_user_id',),
            }
            migration.downgrade()
            assert table.name not in inspect(connection).get_table_names()
            assert 'cycle_territory_battles' in inspect(connection).get_table_names()
    finally:
        engine.dispose()

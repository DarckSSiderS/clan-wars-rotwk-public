import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models.cycle_dispatch_route import CycleDispatchRoute


def test_route_migration_preserves_aggregate_and_matches_model():
    path = Path(__file__).parents[1] / 'alembic/versions/o7d8e9f0g1h2_add_cycle_dispatch_routes.py'
    spec = importlib.util.spec_from_file_location('dispatch_route_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == 'o7d8e9f0g1h2'
    assert migration.down_revision == 'n6c7d8e9f0g1'
    engine = create_engine('sqlite://')
    try:
        with engine.begin() as connection:
            table = CycleDispatchRoute.__table__
            Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
            connection.execute(text('INSERT INTO cycle_reinforcement_states (id, cycle_id, revision, payload) VALUES (1, 1, 7, :payload)'), {'payload': '{"legacy":true}'})
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            inspector = inspect(connection)
            assert {c['name'] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
            assert inspector.get_unique_constraints(table.name)
            assert inspector.get_foreign_keys(table.name)
            assert {i['name'] for i in inspector.get_indexes(table.name)} == {'ix_cycle_dispatch_routes_cycle_id'}
            assert connection.execute(text('SELECT revision, payload FROM cycle_reinforcement_states')).one() == (7, '{"legacy":true}')
            migration.downgrade()
            assert table.name not in inspect(connection).get_table_names()
            assert connection.execute(text('SELECT revision FROM cycle_reinforcement_states')).scalar_one() == 7
    finally:
        engine.dispose()

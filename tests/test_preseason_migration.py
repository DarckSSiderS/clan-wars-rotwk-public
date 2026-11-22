import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from app.database import Base
from app.models.preseason import CampaignPreseason, CampaignPreseasonChoice, CampaignPreseasonCandidate


def test_additive_preseason_migration_matches_models_without_opening_or_changing_map():
    path = Path(__file__).parents[1] / 'alembic/versions/u3i4j5k6l7m8_add_untimed_preseason.py'
    spec = importlib.util.spec_from_file_location('preseason_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == 't2h3i4j5k6l7'
    tables = [CampaignPreseason.__table__, CampaignPreseasonChoice.__table__, CampaignPreseasonCandidate.__table__]
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t not in tables])
        connection.execute(text("INSERT INTO worker_heartbeats (worker_name, consecutive_failures) VALUES ('preseason-test', 9)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        for table in tables:
            assert {c['name'] for c in inspect(connection).get_columns(table.name)} == set(table.columns.keys())
            assert connection.execute(text(f'SELECT count(*) FROM {table.name}')).scalar_one() == 0
        assert connection.execute(text('SELECT count(*) FROM campaign_seasons')).scalar_one() == 0
        migration.downgrade()
        assert not {t.name for t in tables} & set(inspect(connection).get_table_names())
        assert connection.execute(text('SELECT consecutive_failures FROM worker_heartbeats')).scalar_one() == 9
    engine.dispose()

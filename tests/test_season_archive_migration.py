import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.database import Base


def test_archive_migration_is_additive_matches_model_and_preserves_existing_data():
    from app.models.season_archive import CampaignSeasonArchive

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("archive_migration", root / "alembic/versions/t2h3i4j5k6l7_add_season_archives.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "s1g2h3i4j5k6"
    config = Config()
    config.set_main_option("script_location", str(root / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["u3i4j5k6l7m8"]
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        table = CampaignSeasonArchive.__table__
        Base.metadata.create_all(connection, tables=[t for t in Base.metadata.sorted_tables if t is not table])
        connection.execute(text("INSERT INTO worker_heartbeats (worker_name, consecutive_failures) VALUES ('archive-test', 7)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = inspect(connection)
        assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
        assert inspector.get_pk_constraint(table.name)["constrained_columns"] == ["season_id"]
        assert inspector.get_foreign_keys(table.name)[0]["referred_table"] == "campaign_seasons"
        migration.downgrade()
        assert table.name not in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT consecutive_failures FROM worker_heartbeats")).scalar_one() == 7
    engine.dispose()

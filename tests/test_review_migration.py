from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_review_migration_preserves_escrow_and_attaches_only_live_offers():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/z2o3p4q5r6s7_review_consistency.py"
    spec = spec_from_file_location("review_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE campaign_seasons (id INTEGER PRIMARY KEY, status VARCHAR(20))"))
        connection.execute(sa.text("CREATE TABLE market_offers (id INTEGER PRIMARY KEY, status VARCHAR(20), give_amount INTEGER, receive_amount INTEGER)"))
        connection.execute(sa.text("CREATE TABLE worker_heartbeats (worker_name VARCHAR(80) PRIMARY KEY)"))
        connection.execute(sa.text("INSERT INTO campaign_seasons VALUES (1, 'completed'), (2, 'active')"))
        connection.execute(sa.text("INSERT INTO market_offers VALUES (1, 'open', 5, 4), (2, 'in_transit', 9, 8), (3, 'completed', 7, 6)"))
        connection.execute(sa.text("INSERT INTO worker_heartbeats VALUES ('campaign')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(sa.text("SELECT id, give_amount, receive_amount, season_id FROM market_offers ORDER BY id")).all() == [(1, 5, 4, 2), (2, 9, 8, 2), (3, 7, 6, None)]
        assert connection.execute(sa.text("SELECT replay_synced_through_at FROM worker_heartbeats")).scalar() is None
        migration.downgrade()
        assert connection.execute(sa.text("SELECT id, give_amount, receive_amount FROM market_offers ORDER BY id")).all() == [(1, 5, 4), (2, 9, 8), (3, 7, 6)]
    engine.dispose()

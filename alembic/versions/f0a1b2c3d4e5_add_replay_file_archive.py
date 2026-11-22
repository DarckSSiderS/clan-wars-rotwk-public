"""Add replay file archive metadata and source payload.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
"""

from alembic import op
import sqlalchemy as sa


revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("matches", sa.Column("replay_local_path", sa.String(length=500), nullable=True))
    op.add_column("matches", sa.Column("replay_file_size", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("replay_sha256", sa.String(length=64), nullable=True))
    op.add_column("matches", sa.Column("replay_download_status", sa.String(length=24), nullable=True))
    op.add_column("matches", sa.Column("replay_download_error", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("replay_downloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("matches", sa.Column("source_payload", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("matches", "source_payload")
    op.drop_column("matches", "replay_downloaded_at")
    op.drop_column("matches", "replay_download_error")
    op.drop_column("matches", "replay_download_status")
    op.drop_column("matches", "replay_sha256")
    op.drop_column("matches", "replay_file_size")
    op.drop_column("matches", "replay_local_path")

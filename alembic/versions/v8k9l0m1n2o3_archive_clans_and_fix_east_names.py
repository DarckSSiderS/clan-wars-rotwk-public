"""Archive deleted clans and reconcile eastern territory names.

Revision ID: v8k9l0m1n2o3
Revises: u7j8k9l0m1n2
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa


revision = "v8k9l0m1n2o3"
down_revision = "u7j8k9l0m1n2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clans",
        sa.Column("is_recruiting", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "clans",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "clans",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_clans_is_deleted", "clans", ["is_deleted"], unique=False)

    # The SVG contains three separate eastern lands that previously shared or
    # swapped labels. Rename in collision-safe order.
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Северный Рун',
            description = 'Северный Рун — восточные земли за Эсгаротом и Эребором.'
        WHERE name = 'Рун'
    """))
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Рун',
            region = 'rhun',
            description = 'Рун — восточные земли и побережья Моря Рун.'
        WHERE name IN ('Келдуин', 'Кельдуин')
    """))
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Келдуин',
            description = 'Келдуин — Бегущая река от Эребора к Морю Рун.'
        WHERE name IN ('Бегущая река (Келдуїн)', 'Бегущая река (Келдуин)')
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Бегущая река (Келдуїн)'
        WHERE name = 'Келдуин'
    """))
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Келдуин', region = 'eriador'
        WHERE name = 'Рун'
    """))
    op.execute(sa.text("""
        UPDATE territories
        SET name = 'Рун'
        WHERE name = 'Северный Рун'
    """))

    op.drop_index("ix_clans_is_deleted", table_name="clans")
    op.drop_column("clans", "deleted_at")
    op.drop_column("clans", "is_deleted")
    op.drop_column("clans", "is_recruiting")

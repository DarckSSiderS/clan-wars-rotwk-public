"""Add clan motto and normalize clan member roles.

Revision ID: d8e9f0a1b2c3
Revises: c6d7e8f9a0b1
"""

from alembic import op
import sqlalchemy as sa


revision = "d8e9f0a1b2c3"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("clans", sa.Column("motto", sa.String(length=160), nullable=True))
    op.execute(
        """
        UPDATE localizations
        SET ru = 'ROTWK ClanWars', eng = 'ROTWK ClanWars'
        WHERE identifier = 'homepage_welcome_title'
        """
    )
    op.execute(
        """
        UPDATE clan_members
        SET rank = CASE
            WHEN is_trader THEN 'Торговец'
            WHEN rank IN ('Лидер', 'Глава клана') THEN 'Глава клана'
            WHEN rank = 'Воин' THEN 'Воин'
            ELSE 'Салага'
        END
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE localizations
        SET ru = 'Добро пожаловать на Ennorath.TV',
            eng = 'Welcome to Ennorath.TV'
        WHERE identifier = 'homepage_welcome_title'
        """
    )
    op.execute(
        """
        UPDATE clan_members
        SET rank = CASE
            WHEN rank = 'Глава клана' THEN 'Лидер'
            WHEN rank = 'Торговец' THEN 'Участник'
            WHEN rank = 'Салага' THEN 'Участник'
            ELSE rank
        END
        """
    )
    op.drop_column("clans", "motto")

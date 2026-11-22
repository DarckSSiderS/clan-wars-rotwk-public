"""add_allow_clan_invites_to_user

Revision ID: 390dcbcb0840
Revises: add_language_to_user
Create Date: 2025-08-28 17:13:02.070689

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '390dcbcb0840'
down_revision: Union[str, None] = 'add_language_to_user'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем поле allow_clan_invites в таблицу users
    op.add_column('users', sa.Column('allow_clan_invites', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Удаляем поле allow_clan_invites из таблицы users
    op.drop_column('users', 'allow_clan_invites')

"""add language to user

Revision ID: add_language_to_user
Revises: fe0ff9acbbde
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_language_to_user'
down_revision = '3f9020cd9eb6'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле language в таблицу users
    op.add_column('users', sa.Column('language', sa.String(), nullable=False, server_default='ru'))


def downgrade():
    # Удаляем поле language из таблицы users
    op.drop_column('users', 'language') 
"""Remove petitions. Upgrade deletes petition data; downgrade restores schema only.

Back up an existing database before applying. War score adjustments are retained.
"""

from alembic import op
import sqlalchemy as sa


revision = 'k3z4a5b6c7d8'
down_revision = 'j2y3z4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('petition_reactions', 'petition_comments', 'petition_votes', 'petitions'):
        op.drop_table(table)


def _ref(name, target, nullable=False, ondelete='CASCADE'):
    return sa.Column(name, sa.Integer(), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def _created():
    return sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def downgrade():
    op.create_table('petitions', sa.Column('id', sa.Integer(), primary_key=True),
        _ref('author_id', 'users.id', True, 'SET NULL'), sa.Column('title', sa.String(160), nullable=False),
        sa.Column('description', sa.Text(), nullable=False), sa.Column('options', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), _created())
    op.create_table('petition_votes', sa.Column('id', sa.Integer(), primary_key=True),
        _ref('petition_id', 'petitions.id'), _ref('user_id', 'users.id'),
        sa.Column('option_index', sa.Integer(), nullable=False),
        sa.UniqueConstraint('petition_id', 'user_id', name='uq_petition_user_vote'))
    op.create_table('petition_comments', sa.Column('id', sa.Integer(), primary_key=True),
        _ref('petition_id', 'petitions.id'), _ref('author_id', 'users.id', True, 'SET NULL'),
        sa.Column('body', sa.Text(), nullable=False), _created())
    op.create_table('petition_reactions', sa.Column('id', sa.Integer(), primary_key=True),
        _ref('comment_id', 'petition_comments.id'), _ref('user_id', 'users.id'),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.UniqueConstraint('comment_id', 'user_id', name='uq_petition_comment_reaction'),
        sa.CheckConstraint('value IN (-1, 1)', name='ck_petition_reaction_value'))
    for table, column in (('petition_votes', 'petition_id'), ('petition_comments', 'petition_id'),
                          ('petition_reactions', 'comment_id')):
        op.create_index(f'ix_{table}_{column}', table, [column])

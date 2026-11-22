"""Закрепляет разведчика по ID и UUID без пересчёта старых запросов."""

from alembic import op
import sqlalchemy as sa

revision = 'q9f0g1h2i3j4'
down_revision = 'p8e9f0g1h2i3'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name']: column for column in inspector.get_columns('cycle_scout_requests')}
    for name, expected in (('scout_user_id', sa.Integer), ('scout_uuid', sa.String)):
        if name in columns and (not isinstance(columns[name]['type'], expected) or not columns[name]['nullable']):
            raise RuntimeError(f'Неожиданный существующий столбец {name}; нужна проверка схемы')
    foreign_keys = [key for key in inspector.get_foreign_keys('cycle_scout_requests')
                    if key['constrained_columns'] == ['scout_user_id']]
    if any(key['referred_table'] != 'users' or key['referred_columns'] != ['id'] for key in foreign_keys):
        raise RuntimeError('Неожиданная привязка разведчика; нужна проверка схемы')
    # В закрытой копии поля могли появиться до записи версии миграции.
    if {'scout_user_id', 'scout_uuid'} <= columns.keys() and foreign_keys:
        return
    with op.batch_alter_table('cycle_scout_requests') as batch:
        if 'scout_user_id' not in columns:
            batch.add_column(sa.Column('scout_user_id', sa.Integer(), nullable=True))
        if 'scout_uuid' not in columns:
            batch.add_column(sa.Column('scout_uuid', sa.String(128), nullable=True))
        if not foreign_keys:
            batch.create_foreign_key('fk_cycle_scout_player', 'users', ['scout_user_id'], ['id'], ondelete='RESTRICT')


def downgrade():
    foreign_keys = [key for key in sa.inspect(op.get_bind()).get_foreign_keys('cycle_scout_requests')
                    if key['constrained_columns'] == ['scout_user_id']]
    convention = {'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}
    with op.batch_alter_table('cycle_scout_requests', naming_convention=convention) as batch:
        for key in foreign_keys:
            batch.drop_constraint(key['name'] or 'fk_cycle_scout_requests_scout_user_id_users', type_='foreignkey')
        batch.drop_column('scout_uuid')
        batch.drop_column('scout_user_id')

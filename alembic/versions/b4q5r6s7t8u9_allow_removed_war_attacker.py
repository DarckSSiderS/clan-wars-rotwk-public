"""Keep opponent war history when a clan is permanently removed."""
from alembic import op
import sqlalchemy as sa

revision = "b4q5r6s7t8u9"
down_revision = "a3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("clan_wars") as batch:
        batch.alter_column("attacking_clan_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    if op.get_bind().execute(sa.text("SELECT count(*) FROM clan_wars WHERE attacking_clan_id IS NULL")).scalar():
        raise RuntimeError("Cannot restore required attacker while anonymized wars exist")
    with op.batch_alter_table("clan_wars") as batch:
        batch.alter_column("attacking_clan_id", existing_type=sa.Integer(), nullable=False)

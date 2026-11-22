"""Добавляет канонический ключ текущего ника BFME Arena."""

from hashlib import sha256
import unicodedata

from alembic import op
import sqlalchemy as sa


revision = "q3f4g5h6i7j8"
down_revision = "p2e3f4g5h6i7"
branch_labels = None
depends_on = None


def _nickname_key(nickname: str) -> str:
    canonical = unicodedata.normalize("NFKC", nickname.strip()).casefold()
    return sha256(canonical.encode("utf-8")).hexdigest()


def upgrade():
    with op.batch_alter_table("external_player_identities") as batch_op:
        batch_op.add_column(
            sa.Column(
                "current_nickname_key",
                sa.String(length=64),
                nullable=True,
            )
        )

    identities = sa.table(
        "external_player_identities",
        sa.column("id", sa.Integer()),
        sa.column("current_nickname", sa.String(length=120)),
        sa.column("current_nickname_key", sa.String(length=64)),
    )
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.select(identities.c.id, identities.c.current_nickname)
        ).mappings()
    )
    for row in rows:
        connection.execute(
            identities.update()
            .where(identities.c.id == row["id"])
            .values(
                current_nickname_key=_nickname_key(row["current_nickname"])
            )
        )

    with op.batch_alter_table("external_player_identities") as batch_op:
        batch_op.alter_column(
            "current_nickname_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.create_index(
            "ix_external_player_identities_current_nickname_key",
            ["current_nickname_key"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("external_player_identities") as batch_op:
        batch_op.drop_index(
            "ix_external_player_identities_current_nickname_key"
        )
        batch_op.drop_column("current_nickname_key")

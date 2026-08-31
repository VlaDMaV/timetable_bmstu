"""Store a stable Telegram ID for the owner of group settings."""

from alembic import op
import sqlalchemy as sa


revision = "c42d91e7a650"
down_revision = "b81e5a7c3d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("settings_owner_tg_id", sa.BigInteger(), nullable=True))
    connection = op.get_bind()
    users = sa.table(
        "users",
        sa.column("tg_id", sa.BigInteger()),
        sa.column("username", sa.String()),
        sa.column("settings_owner_tg_id", sa.BigInteger()),
    )
    # Legacy group rows contain the username of the person who registered them.
    # Recover only unambiguous associations; never let the next click claim a group.
    by_username = {}
    for tg_id, username in connection.execute(
        sa.select(users.c.tg_id, users.c.username).where(users.c.tg_id > 0)
    ):
        by_username.setdefault(username.lower(), set()).add(tg_id)
    groups = connection.execute(
        sa.select(users.c.tg_id, users.c.username).where(users.c.tg_id < 0)
    ).all()
    for tg_id, username in groups:
        candidates = set(by_username.get(username.lower(), set()))
        if username.startswith("user_") and username[5:].isascii() and username[5:].isdigit():
            encoded_id = int(username[5:])
            if 0 < encoded_id <= 9223372036854775807:
                candidates.add(encoded_id)
        if len(candidates) == 1:
            connection.execute(
                users.update().where(users.c.tg_id == tg_id).values(
                    settings_owner_tg_id=candidates.pop(),
                )
            )


def downgrade() -> None:
    op.drop_column("users", "settings_owner_tg_id")

"""add user notification settings

Revision ID: b81e5a7c3d42
Revises: 7a4f2d8c91e0
Create Date: 2026-08-29 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b81e5a7c3d42"
down_revision: Union[str, None] = "7a4f2d8c91e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notification_mode",
            sa.String(),
            server_default="same_day",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "notification_time",
            sa.Time(),
            server_default=sa.text("'08:00:00'::time"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_notification_date", sa.Date(), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_notification_mode",
        "users",
        "notification_mode IN ('hour_before', 'same_day', 'day_before')",
    )

    # Сохраняем старое общее время рассылки как персональное значение.
    op.execute(
        """
        UPDATE users
        SET notification_time = make_time(
            COALESCE((SELECT value::int FROM settings WHERE key = 'daily_timetable_hour'), 8),
            COALESCE((SELECT value::int FROM settings WHERE key = 'daily_timetable_minute'), 0),
            0
        )
        """
    )
    # Не отправляем повторное сообщение сразу после включения нового планировщика.
    op.execute(
        "UPDATE users SET last_notification_date = CURRENT_DATE WHERE is_active = 1"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_notification_mode", "users", type_="check")
    op.drop_column("users", "last_notification_date")
    op.drop_column("users", "notification_time")
    op.drop_column("users", "notification_mode")

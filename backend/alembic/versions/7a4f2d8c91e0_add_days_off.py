"""add calendar days off

Revision ID: 7a4f2d8c91e0
Revises: 46f7a7e6e5dd
Create Date: 2026-08-29 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a4f2d8c91e0"
down_revision: Union[str, None] = "46f7a7e6e5dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "days_off",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date"),
    )
    op.create_index("ix_days_off_id", "days_off", ["id"])
    op.create_index("ix_days_off_date", "days_off", ["date"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_days_off_date", table_name="days_off")
    op.drop_index("ix_days_off_id", table_name="days_off")
    op.drop_table("days_off")

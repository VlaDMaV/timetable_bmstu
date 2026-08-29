"""add schedule reviews

Revision ID: 46f7a7e6e5dd
Revises: a1bb4c7c08c4
Create Date: 2026-08-29 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "46f7a7e6e5dd"
down_revision: Union[str, None] = "a1bb4c7c08c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("telegram_summary_message_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_document_message_id", sa.BigInteger(), nullable=True),
        sa.Column("report_filename", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedule_reviews_id", "schedule_reviews", ["id"])
    op.create_index("ix_schedule_reviews_status", "schedule_reviews", ["status"])
    op.create_index(
        "ix_schedule_reviews_telegram_summary_message_id",
        "schedule_reviews",
        ["telegram_summary_message_id"],
    )
    op.create_index(
        "ix_schedule_reviews_telegram_document_message_id",
        "schedule_reviews",
        ["telegram_document_message_id"],
    )

    op.create_table(
        "schedule_review_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("source_uuid", sa.String(), nullable=False),
        sa.Column("source_payload", sa.Text(), nullable=False),
        sa.Column("added_count", sa.Integer(), nullable=False),
        sa.Column("removed_count", sa.Integer(), nullable=False),
        sa.Column("is_new_group", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["review_id"], ["schedule_reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", "group_name", name="uq_schedule_review_group"),
    )
    op.create_index("ix_schedule_review_groups_id", "schedule_review_groups", ["id"])
    op.create_index(
        "ix_schedule_review_groups_review_id", "schedule_review_groups", ["review_id"]
    )
    op.create_index(
        "ix_schedule_review_groups_group_name", "schedule_review_groups", ["group_name"]
    )
    op.create_index(
        "ix_schedule_review_groups_status", "schedule_review_groups", ["status"]
    )

    op.create_table(
        "schedule_monitor_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedule_monitor_runs_id", "schedule_monitor_runs", ["id"])
    op.create_index(
        "ix_schedule_monitor_runs_status", "schedule_monitor_runs", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_schedule_monitor_runs_status", table_name="schedule_monitor_runs")
    op.drop_index("ix_schedule_monitor_runs_id", table_name="schedule_monitor_runs")
    op.drop_table("schedule_monitor_runs")

    op.drop_index("ix_schedule_review_groups_status", table_name="schedule_review_groups")
    op.drop_index("ix_schedule_review_groups_group_name", table_name="schedule_review_groups")
    op.drop_index("ix_schedule_review_groups_review_id", table_name="schedule_review_groups")
    op.drop_index("ix_schedule_review_groups_id", table_name="schedule_review_groups")
    op.drop_table("schedule_review_groups")

    op.drop_index(
        "ix_schedule_reviews_telegram_document_message_id", table_name="schedule_reviews"
    )
    op.drop_index(
        "ix_schedule_reviews_telegram_summary_message_id", table_name="schedule_reviews"
    )
    op.drop_index("ix_schedule_reviews_status", table_name="schedule_reviews")
    op.drop_index("ix_schedule_reviews_id", table_name="schedule_reviews")
    op.drop_table("schedule_reviews")

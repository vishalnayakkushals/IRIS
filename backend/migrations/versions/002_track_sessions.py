"""Add onfly_track_sessions table for BoT-SORT session analytics.

Revision ID: 002
Revises: 001
Create Date: 2026-04-28

Stores per-track sessions produced by the BotSortTracker + SessionStateMachine.
One row per detected person track per pipeline run.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "onfly_track_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("store_id", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False, server_default=""),
        sa.Column("track_id_local", sa.Integer(), nullable=False),
        sa.Column("track_global_id", sa.Text(), nullable=False),
        # outside_passer | entry_candidate | active_customer | staff | static_object | exited
        sa.Column("status", sa.Text(), nullable=False, server_default="entry_candidate"),
        sa.Column("entry_frame_idx", sa.Integer(), nullable=True),
        sa.Column("exit_frame_idx", sa.Integer(), nullable=True),
        sa.Column("entry_image_id", sa.Text(), nullable=True),
        sa.Column("exit_image_id", sa.Text(), nullable=True),
        sa.Column("dwell_frames", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dwell_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column("staff_flag", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("gender", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_bbox_x1", sa.Float(), nullable=True),
        sa.Column("avg_bbox_y1", sa.Float(), nullable=True),
        sa.Column("avg_bbox_x2", sa.Float(), nullable=True),
        sa.Column("avg_bbox_y2", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_track_sessions_run_store",
        "onfly_track_sessions",
        ["run_id", "store_id"],
    )
    op.create_index(
        "idx_track_sessions_store_date",
        "onfly_track_sessions",
        ["store_id", "business_date"],
    )
    op.create_index(
        "idx_track_sessions_status",
        "onfly_track_sessions",
        ["store_id", "status", "business_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_track_sessions_status", table_name="onfly_track_sessions")
    op.drop_index("idx_track_sessions_store_date", table_name="onfly_track_sessions")
    op.drop_index("idx_track_sessions_run_store", table_name="onfly_track_sessions")
    op.drop_table("onfly_track_sessions")

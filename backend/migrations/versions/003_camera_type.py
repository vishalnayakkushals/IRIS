"""Add camera_type and sample_image_id to camera_configs.

Revision ID: 003
Revises: 002
Create Date: 2026-05-08

camera_type controls GPT exclusion in the pipeline:
  unlabeled — default, no exclusion yet
  floor     — inside sales floor, full analysis
  entry     — entry/exit gate, full analysis
  external  — outdoor / parking / non-retail, skip GPT
  skip      — explicitly excluded from all AI analysis

sample_image_id stores one representative image_id from onfly_image_state
so the UI can display a thumbnail for each camera during labeling.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "camera_configs",
        sa.Column("camera_type", sa.Text(), nullable=False, server_default="unlabeled"),
    )
    op.add_column(
        "camera_configs",
        sa.Column("sample_image_id", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("camera_configs", "sample_image_id")
    op.drop_column("camera_configs", "camera_type")

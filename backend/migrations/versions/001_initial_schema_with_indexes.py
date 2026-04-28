"""Initial schema with production indexes for 150-store scale.

Revision ID: 001
Revises:
Create Date: 2026-04-27

Scale target:
  - 150+ stores, 8-10 cameras/store
  - 1000-1500 images/day/store  → ~225K images/day
  - YOLO filters ~60-70%        → ~75K GPT calls/day
  - ~20-50 walkin sessions/store/day → ~7,500 sessions/day
  - Annual: ~82M images, ~2.7M sessions
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Core registry ────────────────────────────────────────────────────────
    op.create_table(
        "stores",
        sa.Column("store_id", sa.String(64), primary_key=True),
        sa.Column("store_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("drive_folder_url", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "store_master",
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), primary_key=True),
        sa.Column("short_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("gofrugal_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("outlet_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("city", sa.String(128), nullable=False, server_default=""),
        sa.Column("state", sa.String(128), nullable=False, server_default=""),
        sa.Column("zone", sa.String(128), nullable=False, server_default=""),
        sa.Column("country", sa.String(128), nullable=False, server_default=""),
        sa.Column("mobile_no", sa.String(64), nullable=False, server_default=""),
        sa.Column("store_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("cluster_manager", sa.String(255), nullable=False, server_default=""),
        sa.Column("area_manager", sa.String(255), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "store_sync_state",
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), primary_key=True),
        sa.Column("source_provider", sa.String(32), nullable=False, server_default="none"),
        sa.Column("source_uri", sa.Text, nullable=False, server_default=""),
        sa.Column("last_status", sa.String(32), nullable=False, server_default="never"),
        sa.Column("synced_files", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_message", sa.Text, nullable=False, server_default=""),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "store_source_file_index",
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("source_provider", sa.String(32), nullable=False),
        sa.Column("source_file_id", sa.String(255), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("relative_path", sa.Text, nullable=False, server_default=""),
        sa.Column("source_link", sa.Text, nullable=False, server_default=""),
        sa.Column("local_path", sa.Text, nullable=False, server_default=""),
        sa.Column("file_ext", sa.String(32), nullable=False, server_default=""),
        sa.Column("local_size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("is_present", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_download_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("store_id", "source_provider", "source_file_id"),
    )
    op.create_index("ix_ssfi_store_provider", "store_source_file_index", ["store_id", "source_provider"])

    op.create_table(
        "camera_configs",
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("camera_role", sa.String(64), nullable=False, server_default="INSIDE"),
        sa.Column("floor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("location_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("entry_line_x", sa.Numeric(5, 4), nullable=False, server_default="0.5"),
        sa.Column("entry_direction", sa.String(64), nullable=False, server_default="OUTSIDE_TO_INSIDE"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_id", "camera_id"),
    )

    op.create_table(
        "location_master",
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("floor_name", sa.String(128), nullable=False, server_default="Ground"),
        sa.Column("location_name", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_id", "floor_name", "location_name"),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("image_path", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employees_store", "employees", ["store_id"])

    # ── Access control ───────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("store_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")])

    op.create_table(
        "roles",
        sa.Column("role_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("role_name", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.BigInteger, sa.ForeignKey("roles.role_id"), nullable=False),
        sa.Column("permission_code", sa.String(64), nullable=False),
        sa.Column("can_read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("can_write", sa.Boolean, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("role_id", "permission_code"),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("role_id", sa.BigInteger, sa.ForeignKey("roles.role_id"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    op.create_table(
        "user_store_access",
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("store_id", sa.String(64), sa.ForeignKey("stores.store_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "store_id"),
    )

    op.create_table(
        "app_settings",
        sa.Column("setting_key", sa.String(255), primary_key=True),
        sa.Column("setting_value", sa.Text, nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Pipeline run tracking ────────────────────────────────────────────────
    op.create_table(
        "pipeline_run_log",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("job_key", sa.String(64), nullable=False),
        sa.Column("job_name", sa.String(255), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("remarks", sa.Text, nullable=False, server_default=""),
        sa.Column("triggered_by", sa.String(64), nullable=False, server_default="scheduler"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pipeline_run_log_job_created", "pipeline_run_log", ["job_key", sa.text("created_at DESC")])
    op.create_index("ix_pipeline_run_log_store_created", "pipeline_run_log", ["store_id", sa.text("created_at DESC")])

    op.create_table(
        "onfly_pipeline_runs",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="queued"),
        sa.Column("current_stage", sa.String(64), nullable=False, server_default=""),
        sa.Column("images_discovered", sa.Integer, nullable=False, server_default="0"),
        sa.Column("images_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("images_processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("images_relevant", sa.Integer, nullable=False, server_default="0"),
        sa.Column("images_irrelevant", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gpt_success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gpt_failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("report_image_results_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("report_walkin_sessions_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("report_store_date_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("error_message", sa.Text, nullable=False, server_default=""),
        sa.Column("error_trace", sa.Text, nullable=False, server_default=""),
        sa.Column("retry_status", sa.Text, nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_onfly_runs_store_started", "onfly_pipeline_runs", ["store_id", sa.text("started_at DESC")])
    op.create_index("ix_onfly_runs_status", "onfly_pipeline_runs", ["status"])

    # onfly_pipeline_run_events: 61K rows per 15 runs = ~4K/run. Partition by month.
    op.execute("""
        CREATE TABLE onfly_pipeline_run_events (
            event_id    BIGSERIAL,
            run_id      TEXT NOT NULL,
            stage       TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            image_id    TEXT NOT NULL DEFAULT '',
            image_name  TEXT NOT NULL DEFAULT '',
            message     TEXT NOT NULL DEFAULT '',
            payload_json JSONB NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            error_trace TEXT NOT NULL DEFAULT '',
            attempt_no  INTEGER NOT NULL DEFAULT 1,
            created_at  TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (event_id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE onfly_pipeline_run_events_default
        PARTITION OF onfly_pipeline_run_events DEFAULT
    """)
    op.create_index("ix_run_events_run_id", "onfly_pipeline_run_events", ["run_id"])
    op.create_index("ix_run_events_created", "onfly_pipeline_run_events", [sa.text("created_at DESC")])

    # ── Image state: 82M rows/year — partition by month ─────────────────────
    op.execute("""
        CREATE TABLE onfly_image_state (
            store_id        TEXT NOT NULL,
            image_id        TEXT NOT NULL,
            source_provider TEXT NOT NULL,
            source_uri      TEXT NOT NULL DEFAULT '',
            source_item_id  TEXT NOT NULL DEFAULT '',
            source_url      TEXT NOT NULL DEFAULT '',
            image_name      TEXT NOT NULL DEFAULT '',
            relative_path   TEXT NOT NULL DEFAULT '',
            date_source     TEXT NOT NULL DEFAULT '',
            date_display    TEXT NOT NULL DEFAULT '',
            camera_id       TEXT NOT NULL DEFAULT '',
            timestamp_hint  TEXT NOT NULL DEFAULT '',
            discovered_at   TIMESTAMPTZ NOT NULL,
            last_seen_at    TIMESTAMPTZ NOT NULL,
            pipeline_version TEXT NOT NULL DEFAULT '',
            yolo_version    TEXT NOT NULL DEFAULT '',
            gpt_version     TEXT NOT NULL DEFAULT '',
            yolo_status     TEXT NOT NULL DEFAULT 'pending',
            yolo_relevant   BOOLEAN NOT NULL DEFAULT FALSE,
            person_count    INTEGER NOT NULL DEFAULT 0,
            yolo_conf       FLOAT NOT NULL DEFAULT 0,
            yolo_error      TEXT NOT NULL DEFAULT '',
            gpt_status      TEXT NOT NULL DEFAULT 'pending',
            gpt_customer_count INTEGER NOT NULL DEFAULT 0,
            gpt_staff_count    INTEGER NOT NULL DEFAULT 0,
            gpt_conversions    INTEGER NOT NULL DEFAULT 0,
            gpt_bounce         INTEGER NOT NULL DEFAULT 0,
            gpt_result_json    JSONB NOT NULL DEFAULT '{}',
            gpt_error          TEXT NOT NULL DEFAULT '',
            last_run_id        TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (store_id, image_id)
        )
    """)
    op.create_index("ix_image_state_store_date", "onfly_image_state", ["store_id", "date_source"])
    op.create_index("ix_image_state_gpt_status", "onfly_image_state", ["gpt_status"])
    op.create_index("ix_image_state_yolo_relevant", "onfly_image_state", ["store_id", "yolo_relevant"])

    op.create_table(
        "onfly_task_queue",
        sa.Column("task_key", sa.String(255), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("image_id", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_queue_status", "onfly_task_queue", ["status", sa.text("created_at")])
    op.create_index("ix_task_queue_store", "onfly_task_queue", ["store_id", "status"])

    op.create_table(
        "onfly_run_metrics",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("run_mode", sa.String(64), nullable=False),
        sa.Column("source_provider", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_listed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("new_images", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_cached", sa.Integer, nullable=False, server_default="0"),
        sa.Column("yolo_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("yolo_relevant", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gpt_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("list_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("download_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("yolo_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("gpt_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("report_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.String(64), nullable=False, server_default="ok"),
        sa.Column("summary_json", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_run_metrics_store_started", "onfly_run_metrics", ["store_id", sa.text("started_at DESC")])

    op.create_table(
        "onfly_report_index",
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("image_results_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("walkin_sessions_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("store_date_csv", sa.Text, nullable=False, server_default=""),
        sa.Column("summary_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("store_id", "business_date"),
    )

    # ── Walk-in sessions: 2.7M rows/year — partition by month ───────────────
    op.execute("""
        CREATE TABLE onfly_walkin_sessions (
            id              BIGSERIAL,
            store_id        TEXT NOT NULL,
            run_id          TEXT NOT NULL DEFAULT '',
            image_id        TEXT NOT NULL DEFAULT '',
            source_image_name TEXT NOT NULL DEFAULT '',
            source_folder_name TEXT NOT NULL DEFAULT '',
            camera_id       TEXT NOT NULL DEFAULT '',
            business_date   TEXT NOT NULL DEFAULT '',
            date            TEXT NOT NULL DEFAULT '',
            event_type      TEXT NOT NULL DEFAULT '',
            event_time      TEXT NOT NULL DEFAULT '',
            walkin_id       TEXT NOT NULL DEFAULT '',
            group_id        TEXT NOT NULL DEFAULT '',
            role            TEXT NOT NULL DEFAULT '',
            entry_time      TEXT NOT NULL DEFAULT '',
            exit_time       TEXT NOT NULL DEFAULT '',
            time_spent_mins TEXT NOT NULL DEFAULT '',
            session_status  TEXT NOT NULL DEFAULT '',
            entry_type      TEXT NOT NULL DEFAULT '',
            first_seen_time TEXT NOT NULL DEFAULT '',
            last_seen_time  TEXT NOT NULL DEFAULT '',
            matched_session_id TEXT NOT NULL DEFAULT '',
            match_score     FLOAT NOT NULL DEFAULT 0,
            match_reason    TEXT NOT NULL DEFAULT '',
            direction_confidence TEXT NOT NULL DEFAULT '',
            match_fingerprint TEXT NOT NULL DEFAULT '',
            debug_parsed_time TEXT NOT NULL DEFAULT '',
            debug_gpt_event_type TEXT NOT NULL DEFAULT '',
            gender          TEXT NOT NULL DEFAULT '',
            age_band        TEXT NOT NULL DEFAULT '',
            attire_visual_marker TEXT NOT NULL DEFAULT '',
            primary_clothing TEXT NOT NULL DEFAULT '',
            jewellery_load  TEXT NOT NULL DEFAULT '',
            bag_type        TEXT NOT NULL DEFAULT '',
            clothing_style_archetype TEXT NOT NULL DEFAULT '',
            engagement_type TEXT NOT NULL DEFAULT '',
            engagement_depth TEXT NOT NULL DEFAULT '',
            purchase_signal_bag TEXT NOT NULL DEFAULT '',
            included_in_analytics TEXT NOT NULL DEFAULT '',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    op.execute("""
        CREATE TABLE onfly_walkin_sessions_default
        PARTITION OF onfly_walkin_sessions DEFAULT
    """)
    # Critical query indexes for dashboards
    op.create_index("ix_walkin_store_date", "onfly_walkin_sessions", ["store_id", "business_date"])
    op.create_index("ix_walkin_store_role", "onfly_walkin_sessions", ["store_id", "role"])
    op.create_index("ix_walkin_entry_type", "onfly_walkin_sessions", ["store_id", "entry_type"])
    op.create_index("ix_walkin_created", "onfly_walkin_sessions", [sa.text("created_at DESC")])

    # ── Report summary tables ────────────────────────────────────────────────
    op.create_table(
        "report_store_day_summary",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("summary_source", sa.String(64), nullable=False),
        sa.Column("walkins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversion_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("avg_dwell_mins", sa.Float, nullable=False, server_default="0"),
        sa.Column("relevant_images", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_images", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "business_date", "summary_source", name="uq_report_store_day_summary"),
    )
    op.create_index("ix_report_day_store_date", "report_store_day_summary", ["store_id", "business_date"])

    op.create_table(
        "report_image_scan_results",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.String(32), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("image_id", sa.String(255), nullable=False),
        sa.Column("image_name", sa.Text, nullable=False),
        sa.Column("camera_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("capture_time", sa.String(64), nullable=False, server_default=""),
        sa.Column("yolo_relevant", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("person_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gpt_status", sa.String(64), nullable=False, server_default=""),
        sa.Column("customer_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("staff_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversion_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("store_id", "image_id", name="uq_report_image_scan_store_image"),
    )
    op.create_index("ix_scan_results_store_date", "report_image_scan_results", ["store_id", "business_date"])

    # ── QA and audit tables ──────────────────────────────────────────────────
    op.create_table(
        "qa_feedback",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("store_id", sa.String(64), nullable=False),
        sa.Column("capture_date", sa.String(32), nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("camera_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("predicted_label", sa.String(128), nullable=False, server_default=""),
        sa.Column("corrected_label", sa.String(128), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.8"),
        sa.Column("review_status", sa.String(64), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text, nullable=False, server_default=""),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("reviewer_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_qa_feedback_store_date", "qa_feedback", ["store_id", "capture_date"])

    op.create_table(
        "user_activity",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_email", sa.String(255), nullable=False),
        sa.Column("action_code", sa.String(128), nullable=False),
        sa.Column("store_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("payload_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_activity_created", "user_activity", [sa.text("created_at DESC")])

    op.create_table(
        "model_versions",
        sa.Column("model_id", sa.String(128), primary_key=True),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("version_tag", sa.String(128), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("artifact_path", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("model_name", "version_tag", name="uq_model_versions_name_tag"),
    )

    # Enable pg_stat_statements for query performance monitoring
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")


def downgrade() -> None:
    tables = [
        "model_versions", "user_activity", "qa_feedback",
        "report_image_scan_results", "report_store_day_summary",
        "onfly_walkin_sessions", "onfly_report_index", "onfly_run_metrics",
        "onfly_task_queue", "onfly_image_state", "onfly_pipeline_run_events",
        "onfly_pipeline_runs", "pipeline_run_log", "app_settings",
        "user_store_access", "user_roles", "role_permissions", "roles", "users",
        "employees", "location_master", "camera_configs",
        "store_source_file_index", "store_sync_state", "store_master", "stores",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

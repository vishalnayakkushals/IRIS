from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, Numeric, PrimaryKeyConstraint, String, Table, Text, UniqueConstraint


metadata = MetaData()


# Core platform registry
stores = Table(
    "stores",
    metadata,
    Column("store_id", String(64), primary_key=True),
    Column("store_name", String(255), nullable=False),
    Column("email", String(255), nullable=False, unique=True),
    Column("drive_folder_url", Text, nullable=False, server_default=""),
    Column("sync_enabled", Boolean, nullable=False, server_default="0"),
    Column("sync_interval_hours", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

store_master = Table(
    "store_master",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), primary_key=True),
    Column("short_code", String(64), nullable=False, server_default=""),
    Column("gofrugal_name", String(255), nullable=False, server_default=""),
    Column("outlet_id", String(128), nullable=False, server_default=""),
    Column("city", String(128), nullable=False, server_default=""),
    Column("state", String(128), nullable=False, server_default=""),
    Column("zone", String(128), nullable=False, server_default=""),
    Column("country", String(128), nullable=False, server_default=""),
    Column("mobile_no", String(64), nullable=False, server_default=""),
    Column("store_email", String(255), nullable=False, server_default=""),
    Column("cluster_manager", String(255), nullable=False, server_default=""),
    Column("area_manager", String(255), nullable=False, server_default=""),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

store_sync_state = Table(
    "store_sync_state",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), primary_key=True),
    Column("source_provider", String(32), nullable=False, server_default="none"),
    Column("source_uri", Text, nullable=False, server_default=""),
    Column("last_status", String(32), nullable=False, server_default="never"),
    Column("synced_files", Integer, nullable=False, server_default="0"),
    Column("last_message", Text, nullable=False, server_default=""),
    Column("last_sync_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

store_source_file_index = Table(
    "store_source_file_index",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("source_provider", String(32), nullable=False),
    Column("source_file_id", String(255), nullable=False),
    Column("source_name", String(255), nullable=False, server_default=""),
    Column("relative_path", Text, nullable=False, server_default=""),
    Column("source_link", Text, nullable=False, server_default=""),
    Column("local_path", Text, nullable=False, server_default=""),
    Column("file_ext", String(32), nullable=False, server_default=""),
    Column("local_size_bytes", BigInteger, nullable=False, server_default="0"),
    Column("is_present", Boolean, nullable=False, server_default="0"),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("last_download_at", DateTime(timezone=True), nullable=True),
    PrimaryKeyConstraint("store_id", "source_provider", "source_file_id"),
)

employees = Table(
    "employees",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("employee_name", String(255), nullable=False),
    Column("image_path", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

camera_configs = Table(
    "camera_configs",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("camera_id", String(128), nullable=False),
    Column("camera_role", String(64), nullable=False, server_default="INSIDE"),
    Column("floor_name", String(128), nullable=False, server_default=""),
    Column("location_name", String(255), nullable=False, server_default=""),
    Column("entry_line_x", Numeric(5, 4), nullable=False, server_default="0.5"),
    Column("entry_direction", String(64), nullable=False, server_default="OUTSIDE_TO_INSIDE"),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("store_id", "camera_id"),
)

location_master = Table(
    "location_master",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("floor_name", String(128), nullable=False, server_default="Ground"),
    Column("location_name", String(255), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("store_id", "floor_name", "location_name"),
)


# Access control and sessions
users = Table(
    "users",
    metadata,
    Column("user_id", BigInteger, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("full_name", String(255), nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

roles = Table(
    "roles",
    metadata,
    Column("role_id", BigInteger, primary_key=True, autoincrement=True),
    Column("role_name", String(128), nullable=False, unique=True),
    Column("description", Text, nullable=False, server_default=""),
)

role_permissions = Table(
    "role_permissions",
    metadata,
    Column("role_id", BigInteger, ForeignKey("roles.role_id"), nullable=False),
    Column("permission_code", String(64), nullable=False),
    Column("can_read", Boolean, nullable=False, server_default="0"),
    Column("can_write", Boolean, nullable=False, server_default="0"),
    PrimaryKeyConstraint("role_id", "permission_code"),
)

user_roles = Table(
    "user_roles",
    metadata,
    Column("user_id", BigInteger, ForeignKey("users.user_id"), nullable=False),
    Column("role_id", BigInteger, ForeignKey("roles.role_id"), nullable=False),
    PrimaryKeyConstraint("user_id", "role_id"),
)

user_store_access = Table(
    "user_store_access",
    metadata,
    Column("user_id", BigInteger, ForeignKey("users.user_id"), nullable=False),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("user_id", "store_id"),
)

user_sessions = Table(
    "user_sessions",
    metadata,
    Column("token", Text, primary_key=True),
    Column("email", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

app_settings = Table(
    "app_settings",
    metadata,
    Column("setting_key", String(255), primary_key=True),
    Column("setting_value", Text, nullable=False, server_default=""),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


# Audit, licenses, alerts, and model registry
licenses = Table(
    "licenses",
    metadata,
    Column("license_id", String(128), primary_key=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("license_type", String(128), nullable=False),
    Column("status", String(64), nullable=False),
    Column("metadata_json", JSON, nullable=False),
    Column("created_by", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

license_audit = Table(
    "license_audit",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("license_id", String(128), ForeignKey("licenses.license_id"), nullable=False),
    Column("old_status", String(64), nullable=False),
    Column("new_status", String(64), nullable=False),
    Column("actor_email", String(255), nullable=False),
    Column("note", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

alert_routes = Table(
    "alert_routes",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("channel", String(64), nullable=False),
    Column("target", Text, nullable=False),
    Column("enabled", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("store_id", "channel", "target", name="uq_alert_routes_target"),
)

alert_events = Table(
    "alert_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("alert_type", String(128), nullable=False),
    Column("payload_json", JSON, nullable=False),
    Column("routed_to", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

user_activity = Table(
    "user_activity",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("actor_email", String(255), nullable=False),
    Column("action_code", String(128), nullable=False),
    Column("store_id", String(64), nullable=False, server_default=""),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

model_versions = Table(
    "model_versions",
    metadata,
    Column("model_id", String(128), primary_key=True),
    Column("model_name", String(255), nullable=False),
    Column("version_tag", String(128), nullable=False),
    Column("metrics_json", JSON, nullable=False),
    Column("status", String(64), nullable=False),
    Column("artifact_path", Text, nullable=False, server_default=""),
    Column("rollback_target_model_id", String(128), nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("model_name", "version_tag", name="uq_model_versions_name_tag"),
)


# QA and review
qa_feedback = Table(
    "qa_feedback",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("capture_date", String(32), nullable=False),
    Column("filename", Text, nullable=False),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("track_id", String(128), nullable=False, server_default=""),
    Column("predicted_label", String(128), nullable=False, server_default=""),
    Column("corrected_label", String(128), nullable=False, server_default=""),
    Column("confidence", Float, nullable=False, server_default="0.8"),
    Column("model_version", String(128), nullable=False, server_default=""),
    Column("drive_link", Text, nullable=False, server_default=""),
    Column("needs_review", Boolean, nullable=False, server_default="0"),
    Column("review_status", String(64), nullable=False, server_default="pending"),
    Column("comment", Text, nullable=False, server_default=""),
    Column("actor_email", String(255), nullable=False),
    Column("reviewer_email", String(255), nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
)

qa_false_positive_signatures = Table(
    "qa_false_positive_signatures",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("box_json", JSON, nullable=False),
    Column("hash64", String(255), nullable=False, server_default=""),
    Column("hash_size", Integer, nullable=False, server_default="64"),
    Column("hamming_threshold", Integer, nullable=False, server_default="10"),
    Column("source_feedback_id", BigInteger, nullable=False, server_default="0"),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


# Runtime pipeline state
pipeline_run_log = Table(
    "pipeline_run_log",
    metadata,
    Column("run_id", String(128), primary_key=True),
    Column("job_key", String(64), nullable=False),
    Column("job_name", String(255), nullable=False),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("status", String(64), nullable=False, server_default="queued"),
    Column("remarks", Text, nullable=False, server_default=""),
    Column("triggered_by", String(64), nullable=False, server_default="scheduler"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("result_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

onfly_image_state = Table(
    "onfly_image_state",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("image_id", String(255), nullable=False),
    Column("source_provider", String(32), nullable=False),
    Column("source_uri", Text, nullable=False),
    Column("source_item_id", String(255), nullable=False, server_default=""),
    Column("source_url", Text, nullable=False, server_default=""),
    Column("image_name", Text, nullable=False),
    Column("relative_path", Text, nullable=False, server_default=""),
    Column("date_source", String(64), nullable=False, server_default=""),
    Column("date_display", String(64), nullable=False, server_default=""),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("timestamp_hint", String(128), nullable=False, server_default=""),
    Column("discovered_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("pipeline_version", String(128), nullable=False, server_default=""),
    Column("yolo_version", String(128), nullable=False, server_default=""),
    Column("gpt_version", String(128), nullable=False, server_default=""),
    Column("yolo_status", String(64), nullable=False, server_default="pending"),
    Column("yolo_relevant", Boolean, nullable=False, server_default="0"),
    Column("person_count", Integer, nullable=False, server_default="0"),
    Column("yolo_conf", Float, nullable=False, server_default="0"),
    Column("yolo_error", Text, nullable=False, server_default=""),
    Column("gpt_status", String(64), nullable=False, server_default="pending"),
    Column("gpt_customer_count", Integer, nullable=False, server_default="0"),
    Column("gpt_staff_count", Integer, nullable=False, server_default="0"),
    Column("gpt_conversions", Integer, nullable=False, server_default="0"),
    Column("gpt_bounce", Integer, nullable=False, server_default="0"),
    Column("gpt_result_json", JSON, nullable=False),
    Column("gpt_error", Text, nullable=False, server_default=""),
    Column("last_run_id", String(128), nullable=False, server_default=""),
    PrimaryKeyConstraint("store_id", "image_id"),
)

onfly_task_queue = Table(
    "onfly_task_queue",
    metadata,
    Column("task_key", String(255), primary_key=True),
    Column("run_id", String(128), nullable=False),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("image_id", String(255), nullable=False),
    Column("stage", String(64), nullable=False),
    Column("status", String(64), nullable=False, server_default="pending"),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", Text, nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

onfly_run_metrics = Table(
    "onfly_run_metrics",
    metadata,
    Column("run_id", String(128), primary_key=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("run_mode", String(64), nullable=False),
    Column("source_provider", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=False),
    Column("total_listed", Integer, nullable=False, server_default="0"),
    Column("new_images", Integer, nullable=False, server_default="0"),
    Column("skipped_cached", Integer, nullable=False, server_default="0"),
    Column("yolo_done", Integer, nullable=False, server_default="0"),
    Column("yolo_relevant", Integer, nullable=False, server_default="0"),
    Column("gpt_done", Integer, nullable=False, server_default="0"),
    Column("total_ms", Float, nullable=False, server_default="0"),
    Column("list_ms", Float, nullable=False, server_default="0"),
    Column("download_ms", Float, nullable=False, server_default="0"),
    Column("yolo_ms", Float, nullable=False, server_default="0"),
    Column("gpt_ms", Float, nullable=False, server_default="0"),
    Column("report_ms", Float, nullable=False, server_default="0"),
    Column("status", String(64), nullable=False, server_default="ok"),
    Column("summary_json", JSON, nullable=False),
)

onfly_pipeline_runs = Table(
    "onfly_pipeline_runs",
    metadata,
    Column("run_id", String(128), primary_key=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False, server_default=""),
    Column("source_type", String(64), nullable=False),
    Column("source_uri", Text, nullable=False),
    Column("status", String(64), nullable=False, server_default="queued"),
    Column("current_stage", String(64), nullable=False, server_default=""),
    Column("images_discovered", Integer, nullable=False, server_default="0"),
    Column("images_skipped", Integer, nullable=False, server_default="0"),
    Column("images_processed", Integer, nullable=False, server_default="0"),
    Column("images_relevant", Integer, nullable=False, server_default="0"),
    Column("images_irrelevant", Integer, nullable=False, server_default="0"),
    Column("gpt_success_count", Integer, nullable=False, server_default="0"),
    Column("gpt_failed_count", Integer, nullable=False, server_default="0"),
    Column("report_image_results_csv", Text, nullable=False, server_default=""),
    Column("report_walkin_sessions_csv", Text, nullable=False, server_default=""),
    Column("report_store_date_csv", Text, nullable=False, server_default=""),
    Column("error_message", Text, nullable=False, server_default=""),
    Column("error_trace", Text, nullable=False, server_default=""),
    Column("retry_status", String(64), nullable=False, server_default=""),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("last_heartbeat_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

onfly_pipeline_run_events = Table(
    "onfly_pipeline_run_events",
    metadata,
    Column("event_id", BigInteger, primary_key=True, autoincrement=True),
    Column("run_id", String(128), ForeignKey("onfly_pipeline_runs.run_id"), nullable=False),
    Column("stage", String(64), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("image_id", String(255), nullable=False, server_default=""),
    Column("image_name", Text, nullable=False, server_default=""),
    Column("message", Text, nullable=False, server_default=""),
    Column("payload_json", JSON, nullable=False),
    Column("error_message", Text, nullable=False, server_default=""),
    Column("error_trace", Text, nullable=False, server_default=""),
    Column("attempt_no", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

onfly_report_index = Table(
    "onfly_report_index",
    metadata,
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False),
    Column("run_id", String(128), nullable=False, server_default=""),
    Column("image_results_csv", Text, nullable=False, server_default=""),
    Column("walkin_sessions_csv", Text, nullable=False, server_default=""),
    Column("store_date_csv", Text, nullable=False, server_default=""),
    Column("summary_json", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("store_id", "business_date"),
)

onfly_walkin_sessions = Table(
    "onfly_walkin_sessions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("run_id", String(128), nullable=False),
    Column("image_id", String(255), nullable=False),
    Column("source_image_name", Text, nullable=False, server_default=""),
    Column("source_folder_name", Text, nullable=False, server_default=""),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("business_date", String(32), nullable=False, server_default=""),
    Column("date", String(32), nullable=False, server_default=""),
    Column("event_type", String(64), nullable=False, server_default=""),
    Column("event_time", String(64), nullable=False, server_default=""),
    Column("walkin_id", String(128), nullable=False, server_default=""),
    Column("group_id", String(128), nullable=False, server_default=""),
    Column("role", String(64), nullable=False, server_default=""),
    Column("entry_time", String(64), nullable=False, server_default=""),
    Column("exit_time", String(64), nullable=False, server_default=""),
    Column("time_spent_mins", String(64), nullable=False, server_default=""),
    Column("session_status", String(64), nullable=False, server_default=""),
    Column("entry_type", String(64), nullable=False, server_default=""),
    Column("first_seen_time", String(64), nullable=False, server_default=""),
    Column("last_seen_time", String(64), nullable=False, server_default=""),
    Column("matched_session_id", String(128), nullable=False, server_default=""),
    Column("match_score", Float, nullable=False, server_default="0"),
    Column("match_reason", Text, nullable=False, server_default=""),
    Column("direction_confidence", String(64), nullable=False, server_default=""),
    Column("match_fingerprint", Text, nullable=False, server_default=""),
    Column("debug_parsed_time", String(64), nullable=False, server_default=""),
    Column("debug_gpt_event_type", String(64), nullable=False, server_default=""),
    Column("gender", String(64), nullable=False, server_default=""),
    Column("age_band", String(64), nullable=False, server_default=""),
    Column("attire_visual_marker", Text, nullable=False, server_default=""),
    Column("primary_clothing", Text, nullable=False, server_default=""),
    Column("jewellery_load", Text, nullable=False, server_default=""),
    Column("bag_type", Text, nullable=False, server_default=""),
    Column("clothing_style_archetype", Text, nullable=False, server_default=""),
    Column("engagement_type", Text, nullable=False, server_default=""),
    Column("engagement_depth", Text, nullable=False, server_default=""),
    Column("purchase_signal_bag", Text, nullable=False, server_default=""),
    Column("included_in_analytics", String(16), nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


# Canonical replacements for CSV-driven report facts
report_store_day_summary = Table(
    "report_store_day_summary",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False),
    Column("run_id", String(128), nullable=False, server_default=""),
    Column("summary_source", String(64), nullable=False),
    Column("walkins", Integer, nullable=False, server_default="0"),
    Column("conversions", Integer, nullable=False, server_default="0"),
    Column("conversion_rate", Float, nullable=False, server_default="0"),
    Column("avg_dwell_mins", Float, nullable=False, server_default="0"),
    Column("relevant_images", Integer, nullable=False, server_default="0"),
    Column("raw_images", Integer, nullable=False, server_default="0"),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("store_id", "business_date", "summary_source", name="uq_report_store_day_summary"),
)

report_image_scan_results = Table(
    "report_image_scan_results",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False),
    Column("run_id", String(128), nullable=False, server_default=""),
    Column("image_id", String(255), nullable=False),
    Column("image_name", Text, nullable=False),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("capture_time", String(64), nullable=False, server_default=""),
    Column("yolo_relevant", Boolean, nullable=False, server_default="0"),
    Column("person_count", Integer, nullable=False, server_default="0"),
    Column("gpt_status", String(64), nullable=False, server_default=""),
    Column("customer_count", Integer, nullable=False, server_default="0"),
    Column("staff_count", Integer, nullable=False, server_default="0"),
    Column("conversion_count", Integer, nullable=False, server_default="0"),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("store_id", "image_id", name="uq_report_image_scan_results_store_image"),
)

report_location_hotspots = Table(
    "report_location_hotspots",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False),
    Column("camera_id", String(128), nullable=False, server_default=""),
    Column("floor_name", String(128), nullable=False, server_default=""),
    Column("location_name", String(255), nullable=False),
    Column("heat_score", Float, nullable=False, server_default="0"),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

report_daily_proof = Table(
    "report_daily_proof",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("store_id", String(64), ForeignKey("stores.store_id"), nullable=False),
    Column("business_date", String(32), nullable=False),
    Column("proof_type", String(64), nullable=False),
    Column("proof_key", String(255), nullable=False),
    Column("payload_json", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("store_id", "business_date", "proof_type", "proof_key", name="uq_report_daily_proof"),
)

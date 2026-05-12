from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from typing import Any

PIPELINE_STAGES = (
    "LIST",
    "SKIP_CHECK",
    "DOWNLOAD",
    "YOLO",
    "GPT",
    "REPORT_WRITER",
    "DASHBOARD_INGEST",
)


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def ms_to_hms(ms: float) -> str:
    total_seconds = max(0, int(round(float(ms) / 1000.0)))
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_onfly_tables(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_image_state(
                store_id TEXT NOT NULL, image_id TEXT NOT NULL, source_provider TEXT NOT NULL, source_uri TEXT NOT NULL,
                source_item_id TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', image_name TEXT NOT NULL,
                relative_path TEXT NOT NULL DEFAULT '', date_source TEXT NOT NULL DEFAULT '', date_display TEXT NOT NULL DEFAULT '',
                camera_id TEXT NOT NULL DEFAULT '', timestamp_hint TEXT NOT NULL DEFAULT '', discovered_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                pipeline_version TEXT NOT NULL DEFAULT '', yolo_version TEXT NOT NULL DEFAULT '', gpt_version TEXT NOT NULL DEFAULT '',
                yolo_status TEXT NOT NULL DEFAULT 'pending', yolo_relevant INTEGER NOT NULL DEFAULT 0,
                person_count INTEGER NOT NULL DEFAULT 0, yolo_conf REAL NOT NULL DEFAULT 0, yolo_error TEXT NOT NULL DEFAULT '',
                gpt_status TEXT NOT NULL DEFAULT 'pending', gpt_customer_count INTEGER NOT NULL DEFAULT 0, gpt_staff_count INTEGER NOT NULL DEFAULT 0,
                gpt_conversions INTEGER NOT NULL DEFAULT 0, gpt_bounce INTEGER NOT NULL DEFAULT 0, gpt_result_json TEXT NOT NULL DEFAULT '{}',
                gpt_error TEXT NOT NULL DEFAULT '', last_run_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(store_id,image_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_task_queue(
                task_key TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                image_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        state_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(onfly_image_state)").fetchall()}
        additive_cols = [
            ("yolo_version", "TEXT NOT NULL DEFAULT ''"),
            ("gpt_version", "TEXT NOT NULL DEFAULT ''"),
            ("content_hash", "TEXT NOT NULL DEFAULT ''"),
            ("sampled_anchor_image_id", "TEXT NOT NULL DEFAULT ''"),
            ("sampled_signature", "TEXT NOT NULL DEFAULT ''"),
            ("sampled_skip_reason", "TEXT NOT NULL DEFAULT ''"),
        ]
        for col_name, col_def in additive_cols:
            if col_name not in state_cols:
                conn.execute(f"ALTER TABLE onfly_image_state ADD COLUMN {col_name} {col_def}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_hash ON onfly_image_state(store_id, content_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_sampled_anchor ON onfly_image_state(store_id, sampled_anchor_image_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_task_stage_status ON onfly_task_queue(stage,status,updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_run_metrics(
                run_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, run_mode TEXT NOT NULL, source_provider TEXT NOT NULL,
                started_at TEXT NOT NULL, ended_at TEXT NOT NULL, total_listed INTEGER NOT NULL DEFAULT 0,
                new_images INTEGER NOT NULL DEFAULT 0, skipped_cached INTEGER NOT NULL DEFAULT 0, yolo_done INTEGER NOT NULL DEFAULT 0,
                yolo_relevant INTEGER NOT NULL DEFAULT 0, gpt_done INTEGER NOT NULL DEFAULT 0, total_ms REAL NOT NULL DEFAULT 0,
                list_ms REAL NOT NULL DEFAULT 0, download_ms REAL NOT NULL DEFAULT 0, yolo_ms REAL NOT NULL DEFAULT 0, gpt_ms REAL NOT NULL DEFAULT 0,
                report_ms REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ok', summary_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_pipeline_runs (
                run_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                business_date TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                current_stage TEXT NOT NULL DEFAULT '',
                images_discovered INTEGER NOT NULL DEFAULT 0,
                images_skipped INTEGER NOT NULL DEFAULT 0,
                images_processed INTEGER NOT NULL DEFAULT 0,
                images_relevant INTEGER NOT NULL DEFAULT 0,
                images_irrelevant INTEGER NOT NULL DEFAULT 0,
                gpt_success_count INTEGER NOT NULL DEFAULT 0,
                gpt_failed_count INTEGER NOT NULL DEFAULT 0,
                gpt_cache_hits INTEGER NOT NULL DEFAULT 0,
                report_image_results_csv TEXT NOT NULL DEFAULT '',
                report_walkin_sessions_csv TEXT NOT NULL DEFAULT '',
                report_store_date_csv TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                error_trace TEXT NOT NULL DEFAULT '',
                retry_status TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL DEFAULT '',
                last_heartbeat_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_pipeline_run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                event_type TEXT NOT NULL,
                image_id TEXT NOT NULL DEFAULT '',
                image_name TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT NOT NULL DEFAULT '',
                error_trace TEXT NOT NULL DEFAULT '',
                attempt_no INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_pipeline_events_run_created ON onfly_pipeline_run_events(run_id, created_at ASC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_pipeline_events_run_stage ON onfly_pipeline_run_events(run_id, stage, created_at ASC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_report_index (
                store_id TEXT NOT NULL,
                business_date TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                image_results_csv TEXT NOT NULL DEFAULT '',
                walkin_sessions_csv TEXT NOT NULL DEFAULT '',
                store_date_csv TEXT NOT NULL DEFAULT '',
                summary_json TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, business_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_walkin_sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                image_id TEXT NOT NULL,
                source_image_name TEXT NOT NULL DEFAULT '',
                source_folder_name TEXT NOT NULL DEFAULT '',
                camera_id TEXT NOT NULL DEFAULT '',
                business_date TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT '',
                event_time TEXT NOT NULL DEFAULT '',
                walkin_id TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                entry_time TEXT NOT NULL DEFAULT '',
                exit_time TEXT NOT NULL DEFAULT '',
                time_spent_mins TEXT NOT NULL DEFAULT '',
                session_status TEXT NOT NULL DEFAULT '',
                entry_type TEXT NOT NULL DEFAULT '',
                first_seen_time TEXT NOT NULL DEFAULT '',
                last_seen_time TEXT NOT NULL DEFAULT '',
                matched_session_id TEXT NOT NULL DEFAULT '',
                match_score REAL NOT NULL DEFAULT 0,
                match_reason TEXT NOT NULL DEFAULT '',
                direction_confidence TEXT NOT NULL DEFAULT '',
                match_fingerprint TEXT NOT NULL DEFAULT '',
                debug_parsed_time TEXT NOT NULL DEFAULT '',
                debug_gpt_event_type TEXT NOT NULL DEFAULT '',
                gender TEXT NOT NULL DEFAULT '',
                age_band TEXT NOT NULL DEFAULT '',
                attire_visual_marker TEXT NOT NULL DEFAULT '',
                primary_clothing TEXT NOT NULL DEFAULT '',
                jewellery_load TEXT NOT NULL DEFAULT '',
                bag_type TEXT NOT NULL DEFAULT '',
                clothing_style_archetype TEXT NOT NULL DEFAULT '',
                engagement_type TEXT NOT NULL DEFAULT '',
                engagement_depth TEXT NOT NULL DEFAULT '',
                purchase_signal_bag TEXT NOT NULL DEFAULT '',
                included_in_analytics TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_walkin_store_date ON onfly_walkin_sessions(store_id, date, walkin_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store ON onfly_image_state(store_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store_seen ON onfly_image_state(store_id, last_seen_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store_date ON onfly_image_state(store_id, date_display, date_source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_walkin_store_image ON onfly_walkin_sessions(store_id, image_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_summary_cover ON onfly_image_state(store_id, date_display, yolo_relevant)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_walkin_bizdate ON onfly_walkin_sessions(store_id, business_date)")
        existing_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(onfly_walkin_sessions)").fetchall()}
        for col_name, col_def in [
            ("source_image_name", "TEXT NOT NULL DEFAULT ''"),
            ("source_folder_name", "TEXT NOT NULL DEFAULT ''"),
            ("camera_id", "TEXT NOT NULL DEFAULT ''"),
            ("business_date", "TEXT NOT NULL DEFAULT ''"),
            ("event_type", "TEXT NOT NULL DEFAULT ''"),
            ("event_time", "TEXT NOT NULL DEFAULT ''"),
            ("first_seen_time", "TEXT NOT NULL DEFAULT ''"),
            ("last_seen_time", "TEXT NOT NULL DEFAULT ''"),
            ("matched_session_id", "TEXT NOT NULL DEFAULT ''"),
            ("match_score", "REAL NOT NULL DEFAULT 0"),
            ("match_reason", "TEXT NOT NULL DEFAULT ''"),
            ("direction_confidence", "TEXT NOT NULL DEFAULT ''"),
            ("match_fingerprint", "TEXT NOT NULL DEFAULT ''"),
            ("debug_parsed_time", "TEXT NOT NULL DEFAULT ''"),
            ("debug_gpt_event_type", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE onfly_walkin_sessions ADD COLUMN {col_name} {col_def}")
        pr_cols = {r[1] for r in conn.execute("PRAGMA table_info(onfly_pipeline_runs)").fetchall()}
        if "gpt_cache_hits" not in pr_cols:
            conn.execute("ALTER TABLE onfly_pipeline_runs ADD COLUMN gpt_cache_hits INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_cost_metrics(
                metric_day TEXT NOT NULL,
                store_id TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                images_listed INTEGER NOT NULL DEFAULT 0,
                yolo_relevant INTEGER NOT NULL DEFAULT 0,
                gpt_calls INTEGER NOT NULL DEFAULT 0,
                hash_cache_hits INTEGER NOT NULL DEFAULT 0,
                sampled_skips INTEGER NOT NULL DEFAULT 0,
                duplicate_skips INTEGER NOT NULL DEFAULT 0,
                outside_hours_skips INTEGER NOT NULL DEFAULT 0,
                excluded_camera_skips INTEGER NOT NULL DEFAULT 0,
                quota_failures INTEGER NOT NULL DEFAULT 0,
                gpt_batch_images INTEGER NOT NULL DEFAULT 0,
                gpt_realtime_images INTEGER NOT NULL DEFAULT 0,
                est_cost_inr REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY(metric_day, store_id, run_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def queue_set(conn: sqlite3.Connection, *, run_id: str, store_id: str, image_id: str, stage: str, status: str, error: str = "") -> None:
    key = f"{run_id}|{store_id}|{image_id}|{stage}"
    now = now_iso()
    row = conn.execute("SELECT attempts FROM onfly_task_queue WHERE task_key=?", (key,)).fetchone()
    attempts = int(row[0] or 0) + 1 if row else 1
    conn.execute(
        "INSERT OR REPLACE INTO onfly_task_queue(task_key,run_id,store_id,image_id,stage,status,attempts,last_error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM onfly_task_queue WHERE task_key=?),?),?)",
        (key, run_id, store_id, image_id, stage, status, attempts, str(error or "")[:2000], key, now, now),
    )


def json_compact(payload: Any) -> str:
    try:
        return json.dumps(payload or {}, separators=(",", ":"))
    except Exception:
        return "{}"


def create_pipeline_run(conn: sqlite3.Connection, *, run_id: str, store_id: str, source_type: str, source_uri: str, started_at: str, business_date: str = "") -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO onfly_pipeline_runs(
            run_id,store_id,business_date,source_type,source_uri,status,current_stage,
            started_at,last_heartbeat_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            store_id,
            business_date,
            source_type,
            source_uri,
            "running",
            "LIST",
            started_at,
            started_at,
            started_at,
            started_at,
        ),
    )


def update_pipeline_run(conn: sqlite3.Connection, run_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields = {**fields, "updated_at": now_iso()}
    cols = ", ".join(f"{key}=?" for key in fields.keys())
    conn.execute(f"UPDATE onfly_pipeline_runs SET {cols} WHERE run_id=?", tuple(fields.values()) + (run_id,))


def append_pipeline_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    stage: str,
    event_type: str,
    image_id: str = "",
    image_name: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
    error_message: str = "",
    error_trace: str = "",
    attempt_no: int = 1,
) -> None:
    conn.execute(
        "INSERT INTO onfly_pipeline_run_events(run_id,stage,event_type,image_id,image_name,message,payload_json,error_message,error_trace,attempt_no,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            stage,
            event_type,
            str(image_id or ""),
            str(image_name or ""),
            str(message or "")[:2000],
            json_compact(payload),
            str(error_message or "")[:2000],
            str(error_trace or "")[:4000],
            max(1, int(attempt_no)),
            now_iso(),
        ),
    )

from __future__ import annotations

import concurrent.futures
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.config import get_settings
from backend.app.db.canonical_metadata import pipeline_run_log, store_sync_state

logger = logging.getLogger(__name__)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="iris-pipeline")
_active_runs: dict[str, dict[str, str]] = {}
_MANUAL_SYNC_MAX_IMAGES = 10000
_ACTIVE_RUN_GRACE_SECONDS = 30
_STALE_HEARTBEAT_SECONDS = 180


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _now_str() -> str:
    return _now().isoformat()


def _make_run_id(store_id: str) -> str:
    return f"onfly_{store_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def _parse_iso(value: str) -> datetime | None:
    try:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_terminal_run_status(value: str) -> bool:
    return str(value or "").strip().lower() in {"success", "done", "failed", "partial", "cancelled", "canceled", "abandoned"}


def _active_run_meta(store_id: str) -> dict[str, str]:
    raw = _active_runs.get(store_id)
    if isinstance(raw, dict):
        return {
            "run_id": str(raw.get("run_id") or "").strip(),
            "started_at": str(raw.get("started_at") or "").strip(),
        }
    text = str(raw or "").strip()
    return {"run_id": text, "started_at": ""}


def _set_active_run(store_id: str, run_id: str) -> None:
    _active_runs[store_id] = {"run_id": str(run_id or "").strip(), "started_at": _now_str()}


def _active_run_within_grace(store_id: str) -> bool:
    started_at = _active_run_meta(store_id).get("started_at", "")
    started_dt = _parse_iso(started_at)
    if started_dt is None:
        return False
    return (_now() - started_dt).total_seconds() <= _ACTIVE_RUN_GRACE_SECONDS


def _sqlite_row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _detect_source_provider(source_url: str) -> str:
    value = str(source_url or "").strip().lower()
    if "drive.google.com" in value:
        return "google_drive"
    if value.startswith("s3://"):
        return "s3"
    if value.startswith("http://") or value.startswith("https://"):
        return "remote"
    return "local"


def _normalize_manual_source(source_text: str) -> str:
    text = str(source_text or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://") or text.lower().startswith("file://"):
        return text
    from iris.store_registry import parse_drive_folder_id, parse_s3_location

    if parse_s3_location(text) is not None:
        return text
    if parse_drive_folder_id(text) or text.replace("-", "").replace("_", "").isalnum():
        return f"https://drive.google.com/drive/folders/{text}"
    return text


def _load_live_progress_from_sqlite(db_path: Path, store_id: str, run_id: str = "") -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    conn = _sqlite_connect(db_path)
    try:
        run_row = None
        run_id = str(run_id or "").strip()
        if run_id:
            run_row = conn.execute(
                """
                SELECT *
                FROM onfly_pipeline_runs
                WHERE run_id=? AND store_id=?
                LIMIT 1
                """,
                (run_id, store_id),
            ).fetchone()
        if run_row is None:
            run_row = conn.execute(
                """
                SELECT *
                FROM onfly_pipeline_runs
                WHERE store_id=?
                ORDER BY started_at DESC, created_at DESC
                LIMIT 1
                """,
                (store_id,),
            ).fetchone()
        if run_row is None:
            return None
        pending_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM onfly_task_queue
            WHERE store_id=? AND status='pending'
            """,
            (store_id,),
        ).fetchone()[0]
        latest_success = None
        if not any(str(run_row[col] or "").strip() for col in ("report_image_results_csv", "report_walkin_sessions_csv", "report_store_date_csv")):
            latest_success = conn.execute(
                """
                SELECT report_image_results_csv, report_walkin_sessions_csv, report_store_date_csv
                FROM onfly_pipeline_runs
                WHERE store_id=? AND status='success'
                ORDER BY started_at DESC, created_at DESC
                LIMIT 1
                """,
                (store_id,),
            ).fetchone()
        heartbeat_at = str(run_row["last_heartbeat_at"] or "")
        heartbeat_dt = _parse_iso(heartbeat_at)
        heartbeat_age = int((_now() - heartbeat_dt).total_seconds()) if heartbeat_dt else None
        stale = bool(
            heartbeat_age is not None
            and heartbeat_age > _STALE_HEARTBEAT_SECONDS
            and str(run_row["status"] or "") == "running"
        )
        return {
            "run_id": str(run_row["run_id"] or ""),
            "status": str(run_row["status"] or ""),
            "stage": str(run_row["current_stage"] or ""),
            "images_discovered": int(run_row["images_discovered"] or 0),
            "images_processed": int(run_row["images_processed"] or 0),
            "images_relevant": int(run_row["images_relevant"] or 0),
            "images_skipped": int(run_row["images_skipped"] or 0),
            "gpt_success": int(run_row["gpt_success_count"] or 0),
            "gpt_failed": int(run_row["gpt_failed_count"] or 0),
            "pending_tasks": int(pending_count or 0),
            "started_at": str(run_row["started_at"] or ""),
            "ended_at": str(run_row["ended_at"] or ""),
            "last_heartbeat_at": heartbeat_at,
            "heartbeat_age_seconds": heartbeat_age,
            "stale_heartbeat": stale,
            "error": str(run_row["error_message"] or ""),
            "report_image_results_csv": str(run_row["report_image_results_csv"] or (latest_success["report_image_results_csv"] if latest_success else "") or ""),
            "report_walkin_sessions_csv": str(run_row["report_walkin_sessions_csv"] or (latest_success["report_walkin_sessions_csv"] if latest_success else "") or ""),
            "report_store_date_csv": str(run_row["report_store_date_csv"] or (latest_success["report_store_date_csv"] if latest_success else "") or ""),
        }
    finally:
        conn.close()


def _sync_update_store_sync_state(
    store_id: str,
    status: str,
    message: str,
    file_count: int,
    *,
    source_uri: str = "",
    source_provider: str = "",
) -> None:
    import sqlalchemy as sa
    from backend.app.db.session import engine_sync

    vals = dict(
        last_status=status,
        last_message=message,
        synced_files=file_count,
        last_sync_at=_now(),
        updated_at=_now(),
    )
    with engine_sync.begin() as conn:
        existing = conn.execute(
            sa.select(store_sync_state.c.store_id).where(store_sync_state.c.store_id == store_id)
        ).first()
        if existing:
            if source_provider:
                vals["source_provider"] = source_provider
            if source_uri:
                vals["source_uri"] = source_uri
            conn.execute(sa.update(store_sync_state).where(store_sync_state.c.store_id == store_id).values(**vals))
        else:
            conn.execute(
                sa.insert(store_sync_state).values(
                    store_id=store_id,
                    source_provider=source_provider or "google_drive",
                    source_uri=source_uri,
                    **vals,
                )
            )


def _mark_stale_run_if_needed(db_path: Path, store_id: str, run_id: str = "") -> dict[str, Any] | None:
    progress = _load_live_progress_from_sqlite(db_path, store_id, run_id)
    if not progress or not progress.get("stale_heartbeat") or str(progress.get("status") or "") != "running":
        return progress
    now = _now_str()
    stale_msg = progress.get("error") or (
        f"Marked stale after {int(progress.get('heartbeat_age_seconds') or 0)}s without heartbeat "
        f"while in stage {progress.get('stage') or 'UNKNOWN'}."
    )
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            UPDATE onfly_pipeline_runs
            SET status='failed',
                error_message=?,
                ended_at=?,
                updated_at=?
            WHERE run_id=?
            """,
            (stale_msg, now, now, progress["run_id"]),
        )
        conn.execute(
            """
            INSERT INTO onfly_pipeline_run_events(
                run_id, stage, event_type, message, error_message, created_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                progress["run_id"],
                progress.get("stage") or "UNKNOWN",
                "failure",
                "Run watchdog marked pipeline stale",
                stale_msg,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    _active_runs.pop(store_id, None)
    _sync_update_store_sync_state(
        store_id=store_id,
        status="error",
        message=stale_msg,
        file_count=int(progress.get("images_processed") or 0),
    )
    return _load_live_progress_from_sqlite(db_path, store_id, "")


def _load_date_report_from_sqlite(db_path: Path, store_id: str) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT
                date_display,
                CASE
                    WHEN COALESCE(date_source, '') != '' THEN date_source
                    WHEN COALESCE(date_display, '') GLOB '??-??-????' THEN SUBSTR(date_display,7,4)||'-'||SUBSTR(date_display,4,2)||'-'||SUBSTR(date_display,1,2)
                    ELSE COALESCE(date_display, '')
                END AS sort_date,
                COUNT(*) AS total_images,
                SUM(CASE WHEN yolo_status != 'pending' THEN 1 ELSE 0 END) AS yolo_done,
                SUM(CASE WHEN yolo_relevant = 1 THEN 1 ELSE 0 END) AS yolo_relevant,
                SUM(CASE WHEN gpt_status = 'done' THEN 1 ELSE 0 END) AS gpt_done,
                SUM(CASE WHEN gpt_status IN ('failed','quota_pending_retry') THEN 1 ELSE 0 END) AS gpt_failed,
                SUM(CASE WHEN gpt_status = 'disabled' THEN 1 ELSE 0 END) AS gpt_disabled,
                SUM(COALESCE(gpt_customer_count, 0)) AS customers,
                SUM(COALESCE(gpt_staff_count, 0)) AS staff,
                SUM(CASE WHEN gpt_status = 'sampled_wait_anchor' THEN 1 ELSE 0 END) AS sampled_wait_anchor,
                SUM(CASE WHEN sampled_anchor_image_id != '' THEN 1 ELSE 0 END) AS sampled_total
            FROM onfly_image_state
            WHERE store_id=? AND date_display != ''
            GROUP BY date_display, sort_date
            ORDER BY sort_date DESC, date_display DESC
            """,
            (store_id,),
        )
        rows = _sqlite_row_dicts(cur)
    finally:
        conn.close()

    return [
        {
            "date": str(row.get("date_display") or ""),
            "total_images": int(row.get("total_images") or 0),
            "yolo_done": int(row.get("yolo_done") or 0),
            "yolo_relevant": int(row.get("yolo_relevant") or 0),
            "gpt_done": int(row.get("gpt_done") or 0),
            "gpt_failed": int(row.get("gpt_failed") or 0),
            "gpt_disabled": int(row.get("gpt_disabled") or 0),
            "customers": int(row.get("customers") or 0),
            "staff": int(row.get("staff") or 0),
            "sampled_total": int(row.get("sampled_total") or 0),
            "sampled_wait_anchor": int(row.get("sampled_wait_anchor") or 0),
            "pending_yolo": max(0, int(row.get("total_images") or 0) - int(row.get("yolo_done") or 0)),
        }
        for row in rows
    ]


def _sync_insert_run_log(run_id: str, store_id: str, triggered_by: str) -> None:
    import sqlalchemy as sa
    from backend.app.db.session import engine_sync

    with engine_sync.begin() as conn:
        conn.execute(
            sa.insert(pipeline_run_log).values(
                run_id=run_id,
                job_key="onfly_sync",
                job_name="On-Fly Pipeline Sync",
                store_id=store_id,
                status="running",
                triggered_by=triggered_by,
                started_at=_now(),
                created_at=_now(),
                result_json={},
                remarks="",
            )
        )


def _sync_update_run_log(run_id: str, status: str, remarks: str, result: dict) -> None:
    import sqlalchemy as sa
    from backend.app.db.session import engine_sync

    with engine_sync.begin() as conn:
        conn.execute(
            sa.update(pipeline_run_log)
            .where(pipeline_run_log.c.run_id == run_id)
            .values(status=status, remarks=remarks, result_json=result, completed_at=_now())
        )


def _run_pipeline_sync(
    run_id: str,
    store_id: str,
    source_url: str,
    triggered_by: str,
    gpt_enabled: bool,
    use_tracker: bool,
    max_images: int,
    force_reprocess: bool,
    gpt_batch_mode: bool = False,
) -> None:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    try:
        _sync_insert_run_log(run_id=run_id, store_id=store_id, triggered_by=triggered_by)
    except Exception as exc:
        logger.warning("Could not insert run log: %s", exc)

    settings = get_settings()
    out_dir = settings.data_root_obj / "exports" / "current" / "onfly"
    out_dir.mkdir(parents=True, exist_ok=True)
    _sync_update_store_sync_state(
        store_id=store_id,
        status="running",
        message="Pipeline started",
        file_count=0,
        source_uri=source_url,
        source_provider=_detect_source_provider(source_url),
    )

    try:
        from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline
        from iris.drive_review_export import drive_review_export_status

        drive_review_export_enabled, _ = drive_review_export_status()
        cfg = OnFlyConfig(
            run_id=run_id,
            store_id=store_id,
            source_uri=source_url,
            db_path=settings.db_path_obj,
            out_dir=out_dir,
            detector_type=os.getenv("ONFLY_DETECTOR", "onnx"),
            conf_threshold=settings.yolo_conf,
            max_images=max_images,
            gpt_enabled=gpt_enabled,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            google_api_key=settings.google_api_key,
            pipeline_version="onfly_v2",
            use_tracker=use_tracker,
            force_reprocess=force_reprocess,
            gpt_batch_mode=gpt_batch_mode,
            export_relevant_drive_images=drive_review_export_enabled,
        )
        summary = run_onfly_pipeline(cfg)
        remarks = (
            f"Listed: {summary.get('total_listed', summary.get('listed', 0))} | "
            f"New: {summary.get('new_images', 0)} | "
            f"YOLO relevant: {summary.get('yolo_relevant', 0)} | "
            f"GPT done: {summary.get('gpt_done', 0)} | "
            f"Sampled: {summary.get('smart_sampled', 0)}"
        )
        _sync_update_run_log(run_id=run_id, status="done", remarks=remarks, result=summary)
        _sync_update_store_sync_state(
            store_id=store_id,
            status="ok",
            message=remarks,
            file_count=int(summary.get("new_images", 0)),
            source_uri=source_url,
            source_provider=_detect_source_provider(source_url),
        )
    except Exception as exc:
        err_msg = str(exc)[:500]
        logger.exception("Pipeline failed for %s run %s", store_id, run_id)
        _sync_update_run_log(run_id=run_id, status="failed", remarks=f"Error: {err_msg}", result={})
        _sync_update_store_sync_state(
            store_id=store_id,
            status="error",
            message=err_msg,
            file_count=0,
            source_uri=source_url,
            source_provider=_detect_source_provider(source_url),
        )
    finally:
        _active_runs.pop(store_id, None)

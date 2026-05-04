"""Direct on-fly pipeline execution routes — no Celery required.
POST /api/onfly/sync/{store_id}  → runs pipeline in background thread
GET  /api/onfly/status/{store_id} → sync state for a store
GET  /api/onfly/stores            → all stores with Drive config + sync state
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import (
    pipeline_run_log,
    store_sync_state,
    stores,
)
from backend.app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onfly", tags=["onfly"])

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="iris-pipeline")
_active_runs: dict[str, dict[str, str]] = {}  # store_id → {run_id, started_at}
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
    return str(value or "").strip().lower() in {"success", "done", "failed", "partial", "cancelled", "canceled"}


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
        stale = bool(heartbeat_age is not None and heartbeat_age > 180 and str(run_row["status"] or "") == "running")
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
                COUNT(*) AS total_images,
                SUM(CASE WHEN yolo_status != 'pending' THEN 1 ELSE 0 END) AS yolo_done,
                SUM(CASE WHEN yolo_relevant = 1 THEN 1 ELSE 0 END) AS yolo_relevant,
                SUM(CASE WHEN gpt_status = 'done' THEN 1 ELSE 0 END) AS gpt_done,
                SUM(CASE WHEN gpt_status IN ('failed','quota_pending_retry') THEN 1 ELSE 0 END) AS gpt_failed,
                SUM(CASE WHEN gpt_status = 'disabled' THEN 1 ELSE 0 END) AS gpt_disabled,
                SUM(COALESCE(gpt_customer_count, 0)) AS customers,
                SUM(COALESCE(gpt_staff_count, 0)) AS staff
            FROM onfly_image_state
            WHERE store_id=? AND date_display != ''
            GROUP BY date_display
            ORDER BY date_display DESC
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
            "pending_yolo": max(0, int(row.get("total_images") or 0) - int(row.get("yolo_done") or 0)),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Sync state helpers (sync-safe, called from background thread)
# ---------------------------------------------------------------------------

def _sync_insert_run_log(run_id: str, store_id: str, triggered_by: str) -> None:
    """Insert a pipeline_run_log row using a new sync SQLAlchemy connection."""
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
            .values(
                status=status,
                remarks=remarks,
                result_json=result,
                completed_at=_now(),
            )
        )


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
        # upsert-style
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


# ---------------------------------------------------------------------------
# Pipeline runner (called in thread pool)
# ---------------------------------------------------------------------------

def _run_pipeline_sync(
    run_id: str,
    store_id: str,
    source_url: str,
    triggered_by: str,
    gpt_enabled: bool,
    use_tracker: bool,
    max_images: int,
    force_reprocess: bool,
) -> None:
    """Run OnFlyPipeline synchronously — called in thread pool worker."""
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[4]
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

        cfg = OnFlyConfig(
            run_id=run_id,
            store_id=store_id,
            source_uri=source_url,
            db_path=settings.db_path_obj,
            out_dir=out_dir,
            detector_type="yolo",
            conf_threshold=settings.yolo_conf,
            max_images=max_images,
            gpt_enabled=gpt_enabled,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            google_api_key=settings.google_api_key,
            pipeline_version="onfly_v2",
            use_tracker=use_tracker,
            force_reprocess=force_reprocess,
        )
        summary = run_onfly_pipeline(cfg)

        remarks = (
            f"Listed: {summary.get('listed', 0)} | "
            f"New: {summary.get('new_images', 0)} | "
            f"YOLO relevant: {summary.get('yolo_relevant', 0)} | "
            f"GPT done: {summary.get('gpt_done', 0)}"
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class SyncRequest(BaseModel):
    gpt_enabled: bool = False
    use_tracker: bool = False
    triggered_by: str = "manual"
    source_url: str = ""
    max_images: int | None = None
    force_reprocess: bool = False


@router.get("/stores")
async def list_onfly_stores(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """All stores with Drive URL and last sync state."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                stores.c.store_id,
                stores.c.store_name,
                stores.c.drive_folder_url,
            ).order_by(stores.c.store_id)
        )
        store_rows = [dict(r) for r in result.mappings().all()]

        sync_result = await session.execute(select(store_sync_state))
        sync_by_id = {r["store_id"]: dict(r) for r in sync_result.mappings().all()}

    for row in store_rows:
        sync = sync_by_id.get(row["store_id"], {})
        runtime_progress = _mark_stale_run_if_needed(get_settings().db_path_obj, row["store_id"], _active_run_meta(row["store_id"]).get("run_id", ""))
        row["last_status"] = sync.get("last_status", "never")
        row["last_sync_at"] = str(sync.get("last_sync_at") or "")
        row["last_message"] = sync.get("last_message", "")
        row["synced_files"] = sync.get("synced_files", 0)
        row["source_uri"] = sync.get("source_uri", "") or row.get("drive_folder_url", "")
        row["source_provider"] = sync.get("source_provider", "") or _detect_source_provider(row.get("drive_folder_url", ""))
        row["is_running"] = bool(_active_run_meta(row["store_id"]).get("run_id"))
        if runtime_progress:
            row["current_run_id"] = runtime_progress.get("run_id", "")
            row["current_stage"] = runtime_progress.get("stage", "")
            row["stale_heartbeat"] = bool(runtime_progress.get("stale_heartbeat"))
            row["heartbeat_age_seconds"] = runtime_progress.get("heartbeat_age_seconds")
            row["report_store_date_csv"] = runtime_progress.get("report_store_date_csv", "")
            row["report_walkin_sessions_csv"] = runtime_progress.get("report_walkin_sessions_csv", "")
            row["report_image_results_csv"] = runtime_progress.get("report_image_results_csv", "")
            if str(runtime_progress.get("status") or "") == "running":
                row["last_status"] = "running"
                row["last_sync_at"] = str(runtime_progress.get("started_at") or row["last_sync_at"])
                row["last_message"] = f"Current stage: {runtime_progress.get('stage') or 'LIST'}"
                row["is_running"] = True
            elif str(runtime_progress.get("status") or "") == "failed":
                row["last_status"] = "error"
                row["last_sync_at"] = str(runtime_progress.get("ended_at") or runtime_progress.get("last_heartbeat_at") or row["last_sync_at"])
                row["last_message"] = str(runtime_progress.get("error") or row["last_message"])

    return store_rows


@router.get("/status/{store_id}")
async def get_store_sync_status(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(store_sync_state).where(store_sync_state.c.store_id == store_id)
        )
        row = result.mappings().first()

    runtime_progress = _mark_stale_run_if_needed(get_settings().db_path_obj, store_id, _active_run_meta(store_id).get("run_id", ""))
    payload = {
        "store_id": store_id,
        "is_running": bool(_active_run_meta(store_id).get("run_id")),
        "run_id": _active_run_meta(store_id).get("run_id", ""),
        **(dict(row) if row else {"last_status": "never", "last_sync_at": None, "last_message": ""}),
    }
    payload["source_uri"] = payload.get("source_uri") or ""
    payload["source_provider"] = payload.get("source_provider") or _detect_source_provider(payload.get("source_uri", ""))
    if runtime_progress:
        payload["current_run"] = runtime_progress
        if str(runtime_progress.get("status") or "") == "running":
            payload["is_running"] = True
            payload["last_status"] = "running"
            payload["last_message"] = f"Current stage: {runtime_progress.get('stage') or 'LIST'}"
        elif str(runtime_progress.get("status") or "") == "failed":
            payload["last_status"] = "error"
            payload["last_message"] = str(runtime_progress.get("error") or payload.get("last_message") or "")
    return payload


@router.post("/sync/{store_id}")
async def trigger_onfly_sync(
    store_id: str,
    body: SyncRequest,
    actor: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger on-fly pipeline for a store. Runs in background thread — no Celery needed."""
    orphan_progress = _mark_stale_run_if_needed(get_settings().db_path_obj, store_id, "")
    if orphan_progress and str(orphan_progress.get("status") or "") == "running" and not _active_run_meta(store_id).get("run_id"):
        return {
            "run_id": orphan_progress.get("run_id", ""),
            "status": "already_running",
            "message": f"Sync already running for {store_id}",
        }
    if store_id in _active_runs:
        active_run_id = _active_run_meta(store_id).get("run_id", "")
        active_progress = _mark_stale_run_if_needed(get_settings().db_path_obj, store_id, active_run_id)
        if active_progress is None and _active_run_within_grace(store_id):
            return {
                "run_id": active_run_id,
                "status": "already_running",
                "message": f"Sync already running for {store_id}",
            }
        if active_progress is None or _is_terminal_run_status(active_progress.get("status", "")):
            _active_runs.pop(store_id, None)
        else:
            return {
                "run_id": active_run_id,
                "status": "already_running",
                "message": f"Sync already running for {store_id}",
            }

    # Fetch store source URL
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(stores.c.drive_folder_url, stores.c.store_name)
            .where(stores.c.store_id == store_id)
        )
        row = result.first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Store {store_id} was not found.")

    requested_source = _normalize_manual_source(body.source_url)
    if not row[0] and not requested_source:
        raise HTTPException(
            status_code=422,
            detail=f"Store {store_id} has no Drive URL configured. Go to Admin > Store Mapping first or provide a manual folder URL/ID.",
        )

    settings = get_settings()
    configured_source_url = str(row[0] or "").strip()
    source_url = requested_source or configured_source_url
    requested_cap = settings.max_images if body.max_images is None else int(body.max_images)
    max_images = 0 if requested_cap <= 0 else min(requested_cap, _MANUAL_SYNC_MAX_IMAGES)
    run_id = _make_run_id(store_id)
    _set_active_run(store_id, run_id)

    if source_url != configured_source_url:
        logger.info("Manual on-fly source override for %s -> %s", store_id, source_url)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_pipeline_sync,
        run_id,
        store_id,
        source_url,
        body.triggered_by,
        body.gpt_enabled,
        body.use_tracker,
        max_images,
        body.force_reprocess,
    )

    return {
        "run_id": run_id,
        "store_id": store_id,
        "source_url": source_url,
        "max_images": max_images,
        "force_reprocess": bool(body.force_reprocess),
        "status": "running",
        "message": (
            f"Pipeline started for {store_id} — GPT: {'on' if body.gpt_enabled else 'off'} | "
            f"Source: {'override' if source_url != configured_source_url else 'configured'} | "
            f"Max images: {'full folder' if max_images == 0 else max_images}"
        ),
    }


@router.get("/live-progress/{store_id}")
async def get_live_progress(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    """Live pipeline progress from the on-fly runtime DB (sqlite source-of-truth)."""
    active_run_id = _active_run_meta(store_id).get("run_id", "")
    is_running = bool(active_run_id)
    runtime_progress = _mark_stale_run_if_needed(get_settings().db_path_obj, store_id, active_run_id)
    if is_running and runtime_progress is None and _active_run_within_grace(store_id):
        return {
            "store_id": store_id,
            "is_running": True,
            "active_run_id": active_run_id,
            "run_id": active_run_id,
            "stage": "LIST",
            "status": "running",
            "images_discovered": 0,
            "images_processed": 0,
            "images_relevant": 0,
            "images_skipped": 0,
            "gpt_success": 0,
            "gpt_failed": 0,
            "pending_tasks": 0,
            "started_at": _active_run_meta(store_id).get("started_at", ""),
            "ended_at": "",
            "last_heartbeat_at": "",
            "heartbeat_age_seconds": 0,
            "stale_heartbeat": False,
            "error": "",
        }
    if is_running and (runtime_progress is None or _is_terminal_run_status(runtime_progress.get("status", ""))):
        _active_runs.pop(store_id, None)
        active_run_id = ""
        is_running = False
        runtime_progress = _load_live_progress_from_sqlite(get_settings().db_path_obj, store_id, "")
    if runtime_progress:
        return {
            "store_id": store_id,
            "is_running": is_running,
            "active_run_id": active_run_id,
            **runtime_progress,
        }
    if is_running:
        return {
            "store_id": store_id,
            "is_running": True,
            "active_run_id": active_run_id,
            "run_id": active_run_id,
            "stage": "LIST",
            "status": "running",
            "images_discovered": 0,
            "images_processed": 0,
            "images_relevant": 0,
            "images_skipped": 0,
            "gpt_success": 0,
            "gpt_failed": 0,
            "pending_tasks": 0,
            "started_at": "",
            "ended_at": "",
            "last_heartbeat_at": "",
            "heartbeat_age_seconds": None,
            "stale_heartbeat": False,
            "error": "",
        }
    return {"store_id": store_id, "is_running": False, "active_run_id": "", "stage": "", "status": "never"}


@router.get("/date-report/{store_id}")
async def get_date_report(store_id: str, _: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Date-wise image scan breakdown from the on-fly runtime DB (sqlite source-of-truth)."""
    return _load_date_report_from_sqlite(get_settings().db_path_obj, store_id)


@router.delete("/sync/{store_id}/cancel")
async def cancel_sync(store_id: str, _: str = Depends(get_current_user)) -> dict:
    """Mark a running sync as cancelled — clears in-memory state and marks DB record."""
    meta = _active_runs.pop(store_id, {})
    run_id = meta.get("run_id") if isinstance(meta, dict) else str(meta or "")
    # Also mark any running DB record for this store as cancelled
    db_path = get_settings().db_path_obj
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=10)
            now = _now_str()
            conn.execute(
                "UPDATE onfly_pipeline_runs SET status='cancelled', error_message='Cancelled by user', ended_at=?, updated_at=? WHERE store_id=? AND status='running'",
                (now, now, store_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Cancel DB update failed: %s", exc)
    return {"store_id": store_id, "cancelled": bool(run_id), "run_id": run_id or ""}


# ---------------------------------------------------------------------------
# Background auto-sync scheduler (called from main.py startup)
# ---------------------------------------------------------------------------

async def _check_and_trigger_auto_syncs() -> None:
    """Check all sync-enabled stores and trigger pipeline if interval has elapsed."""
    from datetime import timedelta

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                stores.c.store_id,
                stores.c.drive_folder_url,
                stores.c.sync_interval_hours,
                stores.c.gpt_enabled,
            ).where(
                stores.c.sync_enabled.is_(True),
                stores.c.drive_folder_url.isnot(None),
                stores.c.drive_folder_url != "",
            )
        )
        enabled_stores = [dict(r) for r in result.mappings().all()]

    now = _now()
    for s in enabled_stores:
        store_id = s["store_id"]
        if store_id in _active_runs:
            continue

        interval_hours = int(s.get("sync_interval_hours") or 1)

        async with AsyncSessionLocal() as session:
            sync_row = await session.execute(
                select(store_sync_state.c.last_sync_at)
                .where(store_sync_state.c.store_id == store_id)
            )
            sync_state = sync_row.first()

        if sync_state and sync_state[0]:
            last_sync = sync_state[0]
            if last_sync.tzinfo is None:
                from datetime import timezone as _tz
                last_sync = last_sync.replace(tzinfo=_tz.utc)
            elapsed = now - last_sync
            if elapsed.total_seconds() < interval_hours * 3600:
                continue

        run_id = _make_run_id(store_id)
        _set_active_run(store_id, run_id)
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            _run_pipeline_sync,
            run_id,
            store_id,
            s["drive_folder_url"],
            "scheduler",
            bool(s.get("gpt_enabled", True)),
            False,
            get_settings().max_images,
            False,
        )
        logger.info("Auto-sync triggered for %s (run_id=%s)", store_id, run_id)


async def auto_sync_loop() -> None:
    """Background task — wakes every 60 s and triggers any due auto-syncs."""
    logger.info("Auto-sync scheduler started")
    while True:
        await asyncio.sleep(60)
        try:
            await _check_and_trigger_auto_syncs()
        except Exception as exc:
            logger.exception("Auto-sync loop error: %s", exc)

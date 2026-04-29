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
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import insert, select, update

from sqlalchemy import Integer, func, text

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import (
    onfly_image_state,
    onfly_pipeline_runs,
    pipeline_run_log,
    store_sync_state,
    stores,
)
from backend.app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onfly", tags=["onfly"])

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3, thread_name_prefix="iris-pipeline")
_active_runs: dict[str, str] = {}  # store_id → run_id


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _now_str() -> str:
    return _now().isoformat()


def _make_run_id(store_id: str) -> str:
    return f"onfly_{store_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"


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


def _sync_update_store_sync_state(store_id: str, status: str, message: str, file_count: int) -> None:
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
            conn.execute(sa.update(store_sync_state).where(store_sync_state.c.store_id == store_id).values(**vals))
        else:
            conn.execute(
                sa.insert(store_sync_state).values(
                    store_id=store_id, source_provider="google_drive", source_uri="", **vals
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

    try:
        from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline

        cfg = OnFlyConfig(
            store_id=store_id,
            source_uri=source_url,
            db_path=settings.db_path_obj,
            out_dir=out_dir,
            detector_type="yolo",
            conf_threshold=settings.yolo_conf,
            max_images=settings.max_images,
            gpt_enabled=gpt_enabled,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            pipeline_version="onfly_v2",
            use_tracker=use_tracker,
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
        )

    except Exception as exc:
        err_msg = str(exc)[:500]
        logger.exception("Pipeline failed for %s run %s", store_id, run_id)
        _sync_update_run_log(run_id=run_id, status="failed", remarks=f"Error: {err_msg}", result={})
        _sync_update_store_sync_state(
            store_id=store_id, status="error", message=err_msg, file_count=0
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
        row["last_status"] = sync.get("last_status", "never")
        row["last_sync_at"] = str(sync.get("last_sync_at") or "")
        row["last_message"] = sync.get("last_message", "")
        row["synced_files"] = sync.get("synced_files", 0)
        row["is_running"] = _active_runs.get(row["store_id"]) is not None

    return store_rows


@router.get("/status/{store_id}")
async def get_store_sync_status(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(store_sync_state).where(store_sync_state.c.store_id == store_id)
        )
        row = result.mappings().first()

    return {
        "store_id": store_id,
        "is_running": _active_runs.get(store_id) is not None,
        "run_id": _active_runs.get(store_id),
        **(dict(row) if row else {"last_status": "never", "last_sync_at": None, "last_message": ""}),
    }


@router.post("/sync/{store_id}")
async def trigger_onfly_sync(
    store_id: str,
    body: SyncRequest,
    actor: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Trigger on-fly pipeline for a store. Runs in background thread — no Celery needed."""
    if store_id in _active_runs:
        return {
            "run_id": _active_runs[store_id],
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

    if not row or not row[0]:
        raise HTTPException(
            status_code=422,
            detail=f"Store {store_id} has no Drive URL configured. Go to Admin > Store Mapping first.",
        )

    source_url = row[0]
    run_id = _make_run_id(store_id)
    _active_runs[store_id] = run_id

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
    )

    return {
        "run_id": run_id,
        "store_id": store_id,
        "status": "running",
        "message": f"Pipeline started for {store_id} — GPT: {'on' if body.gpt_enabled else 'off'}",
    }


@router.get("/live-progress/{store_id}")
async def get_live_progress(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    """Live pipeline progress — read from onfly_pipeline_runs (updated by pipeline in real-time)."""
    async with AsyncSessionLocal() as session:
        # Active or most recent run
        run_result = await session.execute(
            select(onfly_pipeline_runs)
            .where(onfly_pipeline_runs.c.store_id == store_id)
            .order_by(onfly_pipeline_runs.c.created_at.desc())
            .limit(1)
        )
        run_row = run_result.mappings().first()

        # Pending tasks (images queued but not yet processed)
        from backend.app.db.canonical_metadata import onfly_task_queue
        pending_result = await session.execute(
            select(func.count()).where(
                onfly_task_queue.c.store_id == store_id,
                onfly_task_queue.c.status == "pending",
            )
        )
        pending_count = pending_result.scalar() or 0

    is_running = _active_runs.get(store_id) is not None
    if run_row:
        return {
            "store_id": store_id,
            "is_running": is_running,
            "run_id": run_row["run_id"],
            "status": run_row["status"],
            "stage": run_row["current_stage"],
            "images_discovered": run_row["images_discovered"],
            "images_processed": run_row["images_processed"],
            "images_relevant": run_row["images_relevant"],
            "images_skipped": run_row["images_skipped"],
            "gpt_success": run_row.get("gpt_success_count", 0),
            "gpt_failed": run_row.get("gpt_failed_count", 0),
            "pending_tasks": pending_count,
            "started_at": str(run_row["started_at"] or ""),
            "ended_at": str(run_row.get("ended_at") or ""),
            "error": run_row.get("error_message", ""),
        }
    return {"store_id": store_id, "is_running": is_running, "stage": "", "status": "never"}


@router.get("/date-report/{store_id}")
async def get_date_report(store_id: str, _: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Date-wise image scan breakdown for a store from onfly_image_state."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                onfly_image_state.c.date_display,
                func.count().label("total_images"),
                func.sum(
                    func.cast(onfly_image_state.c.yolo_status != "pending", Integer)
                ).label("yolo_done"),
                func.sum(
                    func.cast(onfly_image_state.c.yolo_relevant == True, Integer)  # noqa: E712
                ).label("yolo_relevant"),
                func.sum(
                    func.cast(onfly_image_state.c.gpt_status == "done", Integer)
                ).label("gpt_done"),
                func.sum(onfly_image_state.c.gpt_customer_count).label("customers"),
                func.sum(onfly_image_state.c.gpt_staff_count).label("staff"),
            )
            .where(onfly_image_state.c.store_id == store_id)
            .where(onfly_image_state.c.date_display != "")
            .group_by(onfly_image_state.c.date_display)
            .order_by(onfly_image_state.c.date_display.desc())
        )
        rows = result.mappings().all()

    return [
        {
            "date": r["date_display"],
            "total_images": int(r["total_images"] or 0),
            "yolo_done": int(r["yolo_done"] or 0),
            "yolo_relevant": int(r["yolo_relevant"] or 0),
            "gpt_done": int(r["gpt_done"] or 0),
            "customers": int(r["customers"] or 0),
            "staff": int(r["staff"] or 0),
            "pending_yolo": int(r["total_images"] or 0) - int(r["yolo_done"] or 0),
        }
        for r in rows
    ]


@router.delete("/sync/{store_id}/cancel")
async def cancel_sync(store_id: str, _: str = Depends(get_current_user)) -> dict:
    """Mark a running sync as cancelled (best-effort — thread continues but status is cleared)."""
    run_id = _active_runs.pop(store_id, None)
    return {"store_id": store_id, "cancelled": run_id is not None, "run_id": run_id}


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
        _active_runs[store_id] = run_id
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            _run_pipeline_sync,
            run_id,
            store_id,
            s["drive_folder_url"],
            "scheduler",
            False,
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

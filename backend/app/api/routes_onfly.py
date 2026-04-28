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

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import pipeline_run_log, store_sync_state, stores
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


@router.delete("/sync/{store_id}/cancel")
async def cancel_sync(store_id: str, _: str = Depends(get_current_user)) -> dict:
    """Mark a running sync as cancelled (best-effort — thread continues but status is cleared)."""
    run_id = _active_runs.pop(store_id, None)
    return {"store_id": store_id, "cancelled": run_id is not None, "run_id": run_id}

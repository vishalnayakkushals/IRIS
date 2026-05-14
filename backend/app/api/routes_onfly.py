"""Direct on-fly pipeline execution routes — no Celery required.
POST /api/onfly/sync/{store_id}  → runs pipeline in background thread
GET  /api/onfly/status/{store_id} → sync state for a store
GET  /api/onfly/stores            → all stores with Drive config + sync state
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.api.onfly_runtime import (
    _active_run_meta,
    _active_run_within_grace,
    _active_runs,
    _detect_source_provider,
    _executor,
    _is_terminal_run_status,
    _load_date_report_from_sqlite,
    _load_live_progress_from_sqlite,
    _make_run_id,
    _mark_stale_run_if_needed,
    _normalize_manual_source,
    _run_pipeline_sync,
    _set_active_run,
    _sqlite_connect,
    _sync_update_store_sync_state,
)
from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import store_sync_state, stores
from backend.app.db.session import AsyncSessionLocal
from iris.relevant_review_table import export_relevant_review_table, relevant_review_table_path

router = APIRouter(prefix="/onfly", tags=["onfly"])


class SyncRequest(BaseModel):
    gpt_enabled: bool = False
    use_tracker: bool = False
    triggered_by: str = "manual"
    source_url: str = ""
    max_images: int | None = None
    force_reprocess: bool = False
    gpt_batch_mode: bool = False


class GptControlRequest(BaseModel):
    enabled: bool = False


def _get_openai_calls_enabled() -> bool:
    from iris.store_registry import get_app_settings

    settings = get_settings()
    values = get_app_settings(settings.db_path_obj)
    return str(values.get("cfg_onfly_scheduler_enable_gpt", "0")).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _set_openai_calls_enabled(enabled: bool) -> None:
    from iris.store_registry import upsert_app_settings

    settings = get_settings()
    upsert_app_settings(settings.db_path_obj, {"cfg_onfly_scheduler_enable_gpt": "1" if enabled else "0"})


@router.get("/stores")
async def list_onfly_stores(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(stores.c.store_id, stores.c.store_name, stores.c.drive_folder_url).order_by(stores.c.store_id)
        )
        store_rows = [dict(r) for r in result.mappings().all()]
        sync_result = await session.execute(select(store_sync_state))
        sync_by_id = {r["store_id"]: dict(r) for r in sync_result.mappings().all()}

    db_path = get_settings().db_path_obj
    for row in store_rows:
        runtime_progress = _mark_stale_run_if_needed(db_path, row["store_id"], _active_run_meta(row["store_id"]).get("run_id", ""))
        sync = sync_by_id.get(row["store_id"], {})
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
        result = await session.execute(select(store_sync_state).where(store_sync_state.c.store_id == store_id))
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


@router.get("/gpt-control")
async def get_gpt_control(_: str = Depends(get_current_user)) -> dict[str, Any]:
    enabled = _get_openai_calls_enabled()
    return {
        "enabled": enabled,
        "setting_key": "cfg_onfly_scheduler_enable_gpt",
        "message": "OpenAI GPT calls are enabled" if enabled else "OpenAI GPT calls are disabled",
    }


@router.put("/gpt-control")
async def update_gpt_control(body: GptControlRequest, actor: str = Depends(get_current_user)) -> dict[str, Any]:
    _set_openai_calls_enabled(bool(body.enabled))
    enabled = _get_openai_calls_enabled()
    return {
        "enabled": enabled,
        "updated_by": actor,
        "message": "OpenAI GPT calls enabled" if enabled else "OpenAI GPT calls disabled",
    }


@router.post("/sync/{store_id}")
async def trigger_onfly_sync(store_id: str, body: SyncRequest, actor: str = Depends(get_current_user)) -> dict[str, Any]:
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
            return {"run_id": active_run_id, "status": "already_running", "message": f"Sync already running for {store_id}"}
        if active_progress is None or _is_terminal_run_status(active_progress.get("status", "")):
            _active_runs.pop(store_id, None)
        else:
            return {"run_id": active_run_id, "status": "already_running", "message": f"Sync already running for {store_id}"}

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(stores.c.drive_folder_url, stores.c.store_name).where(stores.c.store_id == store_id))
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
    max_images = max(0, requested_cap)
    openai_calls_enabled = _get_openai_calls_enabled()
    effective_gpt_enabled = bool(body.gpt_enabled and openai_calls_enabled)
    effective_gpt_batch_mode = bool(body.gpt_batch_mode and effective_gpt_enabled)
    run_id = _make_run_id(store_id)
    _set_active_run(store_id, run_id)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_pipeline_sync,
        run_id,
        store_id,
        source_url,
        body.triggered_by,
        effective_gpt_enabled,
        body.use_tracker,
        max_images,
        body.force_reprocess,
        effective_gpt_batch_mode,
    )
    return {
        "run_id": run_id,
        "store_id": store_id,
        "source_url": source_url,
        "max_images": max_images,
        "force_reprocess": bool(body.force_reprocess),
        "openai_calls_enabled": openai_calls_enabled,
        "gpt_enabled": effective_gpt_enabled,
        "gpt_batch_mode": effective_gpt_batch_mode,
        "status": "running",
        "message": (
            f"Pipeline started for {store_id} — GPT: {'batch' if effective_gpt_batch_mode else ('on' if effective_gpt_enabled else 'off')} | "
            f"Source: {'override' if source_url != configured_source_url else 'configured'} | "
            f"Max images: {'full folder' if max_images == 0 else max_images}"
        ),
    }


@router.get("/live-progress/{store_id}")
async def get_live_progress(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
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
        return {"store_id": store_id, "is_running": is_running, "active_run_id": active_run_id, **runtime_progress}
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
    return _load_date_report_from_sqlite(get_settings().db_path_obj, store_id)


@router.post("/relevant-review-table/{store_id}")
async def create_relevant_review_table(
    store_id: str,
    date: str = "",
    limit: int = 0,
    _: str = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    try:
        result = export_relevant_review_table(
            db_path=settings.db_path_obj,
            out_dir=settings.data_root_obj / "exports" / "current" / "onfly",
            store_id=store_id,
            date_filter=str(date or "").strip(),
            limit=max(0, int(limit)),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"Could not read YOLO scan state: {exc}") from exc
    result["message"] = f"Review table generated with {result['rows']} YOLO-relevant image row(s)."
    return result


@router.get("/relevant-review-table/{store_id}/download")
async def download_relevant_review_table(
    store_id: str,
    date: str = "",
    _: str = Depends(get_current_user),
) -> FileResponse:
    settings = get_settings()
    output = relevant_review_table_path(settings.data_root_obj / "exports" / "current" / "onfly", store_id, str(date or "").strip())
    if not output.exists():
        try:
            export_relevant_review_table(
                db_path=settings.db_path_obj,
                out_dir=settings.data_root_obj / "exports" / "current" / "onfly",
                store_id=store_id,
                date_filter=str(date or "").strip(),
                limit=0,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except sqlite3.Error as exc:
            raise HTTPException(status_code=500, detail=f"Could not read YOLO scan state: {exc}") from exc
    if not output.exists():
        raise HTTPException(status_code=404, detail="Review table was not generated.")
    return FileResponse(path=output, filename=output.name, media_type="text/csv")


@router.delete("/sync/{store_id}/cancel")
async def cancel_sync(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    meta = _active_runs.pop(store_id, {})
    run_id = meta.get("run_id") if isinstance(meta, dict) else str(meta or "")
    db_path = get_settings().db_path_obj
    if db_path.exists():
        conn = _sqlite_connect(db_path)
        try:
            conn.execute(
                "UPDATE onfly_pipeline_runs SET status='cancelled', error_message='Cancelled by user', ended_at=datetime('now'), updated_at=datetime('now') WHERE store_id=? AND status='running'",
                (store_id,),
            )
            conn.commit()
        finally:
            conn.close()
    return {"store_id": store_id, "cancelled": bool(run_id), "run_id": run_id or ""}


@router.get("/batch/status/{store_id}")
async def get_batch_status(store_id: str, _: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    repo_root = Path(__file__).resolve().parents[3]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from iris.gpt_batch import get_pending_batches, init_batch_tables

    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        init_batch_tables(conn)
        return get_pending_batches(conn, store_id=store_id)
    finally:
        conn.close()


@router.post("/batch/retrieve/{store_id}")
async def retrieve_batch_results(store_id: str, _: str = Depends(get_current_user)) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[3]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from iris.gpt_batch import apply_batch_results, check_batch_status, get_pending_batches, init_batch_tables

    db_path = get_settings().db_path_obj
    settings = get_settings()
    if not db_path.exists():
        return {"applied": 0, "pending": 0, "results": []}
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        init_batch_tables(conn)
        batches = get_pending_batches(conn, store_id=store_id)
        applied = 0
        results = []
        for batch in batches:
            batch_db_id = batch["batch_db_id"]
            status_info = check_batch_status(batch_db_id, settings.openai_api_key, conn)
            if status_info.get("openai_status") == "completed" and not batch.get("results_applied"):
                apply_info = apply_batch_results(batch_db_id, settings.openai_api_key, conn)
                applied += 1
                results.append({"batch_db_id": batch_db_id, "applied": True, **apply_info})
            else:
                results.append({"batch_db_id": batch_db_id, "applied": False, **status_info})
        conn.commit()
        return {"store_id": store_id, "applied": applied, "total": len(batches), "results": results}
    finally:
        conn.close()

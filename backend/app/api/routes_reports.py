"""Reports routes — walkin sessions, store day summaries, image scan results,
model version history, and pipeline run quality stats."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from backend.app.auth.dependencies import get_current_user
from backend.app.db.canonical_metadata import (
    model_versions,
    onfly_walkin_sessions,
    pipeline_run_log,
    report_image_scan_results,
    report_store_day_summary,
    stores,
)
from backend.app.db.session import AsyncSessionLocal
from .report_csv import (
    get_export_download,
    get_export_status,
    rows_to_csv_response,
    start_export_job,
)
from .report_queries import (
    sqlite_runtime_cost_metrics,
    sqlite_runtime_image_scans,
    sqlite_runtime_summary,
    sqlite_runtime_walkins,
)
from .report_validation import sqlite_walkin_image_map

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/walkins")
async def get_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = sqlite_runtime_walkins(store_id=store_id, business_date=business_date, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = select(onfly_walkin_sessions).order_by(onfly_walkin_sessions.c.created_at.desc()).limit(limit)
        if store_id:
            stmt = stmt.where(onfly_walkin_sessions.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(onfly_walkin_sessions.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/walkins-qa")
async def get_walkins_for_qa(
    store_id: str | None = None,
    limit: int = 100,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = sqlite_runtime_walkins(store_id=store_id, business_date=None, limit=limit)
    if not runtime_rows:
        return []
    qa_rows: list[dict[str, Any]] = []
    for row in runtime_rows:
        qa_rows.append(
            {
                "store_id": row.get("store_id", ""),
                "image_id": row.get("image_id", ""),
                "last_image_id": row.get("image_id", ""),
                "walkin_id": row.get("Walk-in ID", ""),
                "date": row.get("Date", ""),
                "role": row.get("Role", ""),
                "entry_time": row.get("Entry Time", ""),
                "exit_time": row.get("Exit Time", ""),
                "time_spent_mins": row.get("Time Spent (mins)", ""),
                "gender": row.get("Gender", ""),
                "age_band": row.get("Age Band", ""),
                "camera_id": row.get("Session Camera", row.get("camera_id", "")),
                "first_seen_time": row.get("Entry Time", ""),
                "last_seen_time": row.get("Exit Time", row.get("Entry Time", "")),
                "included_in_analytics": row.get("Included in Analytics", ""),
                "source_image_name": row.get("Source Image", ""),
            }
        )
    return qa_rows[: max(1, int(limit))]


@router.get("/summary")
async def get_store_day_summary(
    store_id: str | None = None,
    limit: int = 90,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = sqlite_runtime_summary(store_id=store_id, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = select(report_store_day_summary).order_by(
            report_store_day_summary.c.business_date.desc(),
            report_store_day_summary.c.store_id,
        ).limit(limit)
        if store_id:
            stmt = stmt.where(report_store_day_summary.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/image-scans")
async def get_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 50000,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = sqlite_runtime_image_scans(store_id=store_id, business_date=business_date, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = select(report_image_scan_results).order_by(report_image_scan_results.c.created_at.desc()).limit(limit)
        if store_id:
            stmt = stmt.where(report_image_scan_results.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(report_image_scan_results.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/model-accuracy")
async def get_model_accuracy(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(model_versions).order_by(model_versions.c.created_at.desc()).limit(50))
        return [dict(r) for r in result.mappings().all()]


@router.get("/stores-with-data")
async def get_stores_with_data(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        subq = select(report_store_day_summary.c.store_id).group_by(report_store_day_summary.c.store_id).subquery()
        result = await session.execute(
            select(stores.c.store_id, stores.c.store_name)
            .where(stores.c.store_id.in_(select(subq)))
            .order_by(stores.c.store_id)
        )
        return [dict(r) for r in result.mappings().all()]


@router.get("/pipeline-quality")
async def get_pipeline_quality(
    store_id: str | None = None,
    limit: int = 50,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(pipeline_run_log).order_by(pipeline_run_log.c.created_at.desc()).limit(limit)
        if store_id:
            stmt = stmt.where(pipeline_run_log.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/cost-metrics")
async def get_cost_metrics(
    store_id: str | None = None,
    limit: int = 90,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return sqlite_runtime_cost_metrics(store_id=store_id, limit=limit)


@router.get("/download/summary")
async def download_store_day_summary(
    store_id: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_store_day_summary(store_id=store_id, limit=limit, _="download")
    return rows_to_csv_response(rows, f"summary_{store_id or 'all'}.csv")


@router.get("/download/walkins")
async def download_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_walkins(store_id=store_id, business_date=business_date, limit=limit, _="download")
    return rows_to_csv_response(rows, f"walkins_{store_id or 'all'}_{business_date or 'all_dates'}.csv")


@router.get("/download/image-scans")
async def download_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_image_scans(store_id=store_id, business_date=business_date, limit=limit, _="download")
    return rows_to_csv_response(rows, f"image_scans_{store_id or 'all'}_{business_date or 'all_dates'}.csv")


def _exporters(store_id: str | None, business_date: str | None) -> dict[str, tuple[list[dict[str, Any]], str]]:
    raise RuntimeError("not used")


@router.post("/export/start")
async def start_export(
    export_type: str,
    store_id: str | None = None,
    business_date: str | None = None,
    _: str = Depends(get_current_user),
) -> dict[str, str]:
    exporters = {
        "summary": lambda sid, bdate: (sqlite_runtime_summary(store_id=sid, limit=100_000), f"summary_{sid or 'all'}.csv"),
        "walkins": lambda sid, bdate: (sqlite_runtime_walkins(store_id=sid, business_date=bdate, limit=100_000), f"walkins_{sid or 'all'}.csv"),
        "image_scans": lambda sid, bdate: (sqlite_runtime_image_scans(store_id=sid, business_date=bdate, limit=100_000), f"image_scans_{sid or 'all'}.csv"),
        "validation": lambda sid, bdate: (sqlite_walkin_image_map(store_id=sid, business_date=bdate, limit=100_000), f"validation_{sid or 'all'}.csv"),
    }
    return {"job_id": start_export_job(export_type=export_type, store_id=store_id, business_date=business_date, exporters=exporters)}


@router.get("/export/status/{job_id}")
async def export_status(job_id: str, _: str = Depends(get_current_user)) -> dict[str, str]:
    return get_export_status(job_id)


@router.get("/export/download/{job_id}")
async def export_download(job_id: str, _: str = Depends(get_current_user)) -> StreamingResponse:
    return get_export_download(job_id)


@router.get("/validation/walkin-image-map")
async def get_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 5000,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return sqlite_walkin_image_map(store_id=store_id, business_date=business_date, limit=limit)


@router.get("/download/walkin-image-map")
async def download_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = sqlite_walkin_image_map(store_id=store_id, business_date=business_date, limit=limit)
    return rows_to_csv_response(rows, f"validation_{store_id or 'all'}_{business_date or 'all_dates'}.csv")

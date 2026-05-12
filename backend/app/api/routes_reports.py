"""Reports routes — walkin sessions, store day summaries, image scan results,
model version history, and pipeline run quality stats."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from backend.app.auth.dependencies import get_current_user
from backend.app.db.canonical_metadata import (
    model_versions,
    onfly_walkin_sessions,
    pipeline_run_log,
    qa_feedback,
    report_image_scan_results,
    report_store_day_summary,
    stores,
)
from backend.app.config import get_settings
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
from .routes_qa import _display_date_to_iso, _iso_to_display

router = APIRouter(prefix="/reports", tags=["reports"])
_WALKIN_ISO_DATE = """
    CASE
        WHEN COALESCE(business_date, date, '') GLOB '??-??-????' THEN SUBSTR(COALESCE(business_date, date, ''),7,4)||'-'||SUBSTR(COALESCE(business_date, date, ''),4,2)||'-'||SUBSTR(COALESCE(business_date, date, ''),1,2)
        ELSE COALESCE(business_date, date, '')
    END
"""


def _sqlite_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_settings().db_path_obj), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _walkins_qa_rows(
    store_id: str | None = None,
    business_date: str | None = None,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect()
    try:
        where: list[str] = ["COALESCE(source_image_name, '') != ''"]
        params: list[Any] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append(f"{_WALKIN_ISO_DATE} = ?")
            params.append(business_date)
        cur = conn.execute(
            f"""
            SELECT
                store_id,
                image_id,
                COALESCE(image_id, '') AS last_image_id,
                COALESCE(walkin_id, '') AS walkin_id,
                {_WALKIN_ISO_DATE} AS iso_date,
                COALESCE(role, '') AS role,
                COALESCE(entry_time, '') AS entry_time,
                COALESCE(exit_time, '') AS exit_time,
                COALESCE(time_spent_mins, '') AS time_spent_mins,
                COALESCE(gender, '') AS gender,
                COALESCE(camera_id, '') AS camera_id,
                COALESCE(first_seen_time, '') AS first_seen_time,
                COALESCE(last_seen_time, '') AS last_seen_time,
                COALESCE(included_in_analytics, '') AS included_in_analytics,
                COALESCE(source_image_name, '') AS source_image_name,
                id
            FROM onfly_walkin_sessions
            WHERE {' AND '.join(where)}
            ORDER BY iso_date DESC, entry_time ASC, id ASC
            """,
            tuple(params),
        )
        return _row_dicts(cur)
    finally:
        conn.close()


def _walkins_qa_dates(store_id: str | None = None) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect()
    try:
        where = ["COALESCE(source_image_name, '') != ''"]
        params: list[Any] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        cur = conn.execute(
            f"""
            SELECT
                {_WALKIN_ISO_DATE} AS iso_date,
                COUNT(*) AS session_count
            FROM onfly_walkin_sessions
            WHERE {' AND '.join(where)}
              AND {_WALKIN_ISO_DATE} != ''
            GROUP BY iso_date
            ORDER BY iso_date DESC
            """,
            tuple(params),
        )
        return [
            {
                "value": str(row.get("iso_date") or ""),
                "label": _iso_to_display(str(row.get("iso_date") or "")),
                "session_count": int(row.get("session_count") or 0),
            }
            for row in _row_dicts(cur)
            if str(row.get("iso_date") or "").strip()
        ]
    finally:
        conn.close()


async def _latest_walkin_feedback_map(store_id: str | None = None) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(qa_feedback)
            .where((qa_feedback.c.track_id != "") & (qa_feedback.c.track_id != "FRAME"))
            .order_by(qa_feedback.c.created_at.desc())
        )
        if store_id:
            stmt = stmt.where(qa_feedback.c.store_id == store_id)
        result = await session.execute(stmt)
        rows = [dict(r) for r in result.mappings().all()]
    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("store_id") or ""),
            _display_date_to_iso(str(row.get("capture_date") or "")),
            str(row.get("track_id") or ""),
            str(row.get("filename") or "").strip(),
        )
        if key not in out:
            out[key] = row
    return out


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
    business_date: str | None = None,
    review_status: str | None = None,
    offset: int = 0,
    limit: int = 100,
    _: str = Depends(get_current_user),
) -> dict[str, Any]:
    normalized_review_status = "confirmed" if str(review_status or "").strip().lower() == "approved" else review_status
    rows = _walkins_qa_rows(store_id=store_id, business_date=business_date)
    feedback_map = await _latest_walkin_feedback_map(store_id=store_id)
    qa_rows_all: list[dict[str, Any]] = []
    for row in rows:
        feedback = feedback_map.get((
            str(row.get("store_id") or ""),
            str(row.get("iso_date") or ""),
            str(row.get("walkin_id") or ""),
            str(row.get("source_image_name") or "").strip(),
        ), {})
        status = str(feedback.get("review_status") or "pending")
        qa_rows_all.append(
            {
                "store_id": row.get("store_id", ""),
                "image_id": row.get("image_id", ""),
                "last_image_id": row.get("last_image_id", ""),
                "walkin_id": row.get("walkin_id", ""),
                "date": row.get("iso_date", ""),
                "role": row.get("role", ""),
                "predicted_label": str(feedback.get("predicted_label") or row.get("role") or ""),
                "corrected_label": str(feedback.get("corrected_label") or ""),
                "feedback_id": feedback.get("id"),
                "review_status": status,
                "entry_time": row.get("entry_time", ""),
                "exit_time": row.get("exit_time", ""),
                "time_spent_mins": row.get("time_spent_mins", ""),
                "gender": row.get("gender", ""),
                "camera_id": row.get("camera_id", ""),
                "first_seen_time": row.get("first_seen_time", ""),
                "last_seen_time": row.get("last_seen_time", ""),
                "included_in_analytics": row.get("included_in_analytics", ""),
                "source_image_name": row.get("source_image_name", ""),
            }
        )
    stats = {
        "pending": sum(1 for row in qa_rows_all if str(row.get("review_status") or "pending") == "pending"),
        "approved": sum(1 for row in qa_rows_all if str(row.get("review_status") or "") in {"approved", "confirmed"}),
        "rejected": sum(1 for row in qa_rows_all if str(row.get("review_status") or "") == "rejected"),
    }
    qa_rows = qa_rows_all
    if normalized_review_status:
        qa_rows = [
            row for row in qa_rows_all
            if str(row.get("review_status") or "").strip().lower() == str(normalized_review_status).strip().lower()
        ]
    page_start = max(0, int(offset))
    page_end = page_start + max(1, int(limit))
    return {
        "rows": qa_rows[page_start:page_end],
        "total": len(qa_rows),
        "offset": page_start,
        "limit": max(1, int(limit)),
        "dates": _walkins_qa_dates(store_id=store_id),
        "stats": stats,
    }


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

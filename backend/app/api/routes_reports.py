"""Reports routes — walkin sessions, store day summaries, image scan results,
model version history, and pipeline run quality stats."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import (
    model_versions,
    onfly_walkin_sessions,
    report_store_day_summary,
    report_image_scan_results,
    pipeline_run_log,
    stores,
)
from backend.app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/reports", tags=["reports"])


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _sqlite_runtime_summary(store_id: str | None = None, limit: int = 90) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where = ["img.date_display != ''"]
        if store_id:
            where.append("img.store_id = ?")
            params.append(store_id)
        where_sql = " AND ".join(where)
        cur = conn.execute(
            f"""
            WITH image_rollup AS (
                SELECT
                    img.store_id,
                    img.date_display AS business_date,
                    -- Normalise DD-MM-YYYY → YYYY-MM-DD for joining with walkin_sessions
                    CASE
                        WHEN img.date_display GLOB '??-??-????' THEN
                            SUBSTR(img.date_display,7,4)||'-'||SUBSTR(img.date_display,4,2)||'-'||SUBSTR(img.date_display,1,2)
                        ELSE img.date_display
                    END AS iso_date,
                    COUNT(*) AS raw_images,
                    SUM(CASE WHEN COALESCE(img.yolo_relevant, 0) = 1 THEN 1 ELSE 0 END) AS relevant_images
                FROM onfly_image_state img
                WHERE {where_sql}
                GROUP BY img.store_id, img.date_display
            ),
            walkin_rollup AS (
                SELECT
                    w.store_id,
                    w.business_date,
                    SUM(CASE WHEN UPPER(COALESCE(w.role, '')) = 'CUSTOMER' AND UPPER(COALESCE(w.included_in_analytics, '')) = 'YES' THEN 1 ELSE 0 END) AS walkins,
                    SUM(CASE WHEN UPPER(COALESCE(w.role, '')) = 'CUSTOMER' AND UPPER(COALESCE(w.included_in_analytics, '')) = 'YES' AND UPPER(COALESCE(w.purchase_signal_bag, '')) = 'YES' THEN 1 ELSE 0 END) AS conversions,
                    AVG(
                        CASE
                            WHEN TRIM(COALESCE(w.time_spent_mins, '')) GLOB '[0-9]*'
                            THEN CAST(w.time_spent_mins AS REAL)
                            ELSE NULL
                        END
                    ) AS avg_dwell_mins
                FROM onfly_walkin_sessions w
                WHERE COALESCE(w.business_date, '') != ''
                {f"AND w.store_id = ?" if store_id else ""}
                GROUP BY w.store_id, w.business_date
            )
            SELECT
                image_rollup.store_id,
                image_rollup.business_date,
                COALESCE(walkin_rollup.walkins, 0) AS walkins,
                COALESCE(walkin_rollup.conversions, 0) AS conversions,
                CASE
                    WHEN COALESCE(walkin_rollup.walkins, 0) > 0
                    THEN 1.0 * COALESCE(walkin_rollup.conversions, 0) / walkin_rollup.walkins
                    ELSE 0
                END AS conversion_rate,
                COALESCE(walkin_rollup.avg_dwell_mins, 0) AS avg_dwell_mins,
                image_rollup.relevant_images,
                image_rollup.raw_images
            FROM image_rollup
            LEFT JOIN walkin_rollup
              ON walkin_rollup.store_id = image_rollup.store_id
             AND walkin_rollup.business_date = image_rollup.iso_date
            ORDER BY image_rollup.iso_date DESC, image_rollup.store_id
            LIMIT ?
            """,
            tuple(params + ([store_id] if store_id else []) + [max(1, int(limit))]),
        )
        rows = _row_dicts(cur)
        return [
            {
                **row,
                "walkins": int(row.get("walkins") or 0),
                "conversions": int(row.get("conversions") or 0),
                "relevant_images": int(row.get("relevant_images") or 0),
                "raw_images": int(row.get("raw_images") or 0),
                "conversion_rate": float(row.get("conversion_rate") or 0.0),
                "avg_dwell_mins": float(row.get("avg_dwell_mins") or 0.0),
            }
            for row in rows
        ]
    finally:
        conn.close()


def _sqlite_runtime_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("(business_date = ? OR date = ?)")
            params.extend([business_date, business_date])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        cur = conn.execute(
            f"""
            SELECT
                store_id,
                COALESCE(business_date, date, '') AS "Date",
                COALESCE(walkin_id, '') AS "Walk-in ID",
                COALESCE(group_id, '') AS "Group ID",
                COALESCE(role, '') AS "Role",
                COALESCE(entry_time, '') AS "Entry Time",
                COALESCE(exit_time, '') AS "Exit Time",
                COALESCE(time_spent_mins, '') AS "Time Spent (mins)",
                COALESCE(session_status, '') AS "Session Status",
                COALESCE(entry_type, '') AS "Entry Type",
                COALESCE(gender, '') AS "Gender",
                COALESCE(age_band, '') AS "Age Band",
                COALESCE(attire_visual_marker, '') AS "Attire / Visual Marker",
                COALESCE(primary_clothing, '') AS "Primary Clothing",
                COALESCE(jewellery_load, '') AS "Jewellery Load",
                COALESCE(bag_type, '') AS "Bag Type",
                COALESCE(clothing_style_archetype, '') AS "Primary Clothing Style Archetype",
                COALESCE(engagement_type, '') AS "Engagement Type",
                COALESCE(engagement_depth, '') AS "Engagement Depth",
                COALESCE(purchase_signal_bag, '') AS "Purchase Signal (Bag)",
                COALESCE(included_in_analytics, '') AS "Included in Analytics",
                id
            FROM onfly_walkin_sessions
            {where_sql}
            ORDER BY business_date DESC, entry_time ASC, id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        return _row_dicts(cur)
    finally:
        conn.close()


def _sqlite_runtime_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = ["date_display != ''"]
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("date_display = ?")
            params.append(business_date)
        where_sql = " AND ".join(where)
        cur = conn.execute(
            f"""
            SELECT
                store_id,
                image_id,
                image_name,
                date_display AS business_date,
                camera_id,
                timestamp_hint AS capture_time,
                yolo_relevant,
                person_count,
                gpt_status,
                gpt_customer_count AS customer_count,
                gpt_staff_count AS staff_count,
                gpt_conversions AS conversion_count,
                last_run_id,
                discovered_at,
                last_seen_at
            FROM onfly_image_state
            WHERE {where_sql}
            ORDER BY last_seen_at DESC, image_name DESC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        rows = _row_dicts(cur)
        return [
            {
                "id": f"{row.get('store_id', '')}:{row.get('image_id', '')}",
                **row,
                "yolo_relevant": bool(row.get("yolo_relevant")),
                "person_count": int(row.get("person_count") or 0),
                "customer_count": int(row.get("customer_count") or 0),
                "staff_count": int(row.get("staff_count") or 0),
                "conversion_count": int(row.get("conversion_count") or 0),
            }
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/walkins")
async def get_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = _sqlite_runtime_walkins(store_id=store_id, business_date=business_date, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = (
            select(onfly_walkin_sessions)
            .order_by(onfly_walkin_sessions.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(onfly_walkin_sessions.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(onfly_walkin_sessions.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/summary")
async def get_store_day_summary(
    store_id: str | None = None,
    limit: int = 90,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = _sqlite_runtime_summary(store_id=store_id, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = (
            select(report_store_day_summary)
            .order_by(
                report_store_day_summary.c.business_date.desc(),
                report_store_day_summary.c.store_id,
            )
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(report_store_day_summary.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/image-scans")
async def get_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    runtime_rows = _sqlite_runtime_image_scans(store_id=store_id, business_date=business_date, limit=limit)
    if runtime_rows:
        return runtime_rows
    async with AsyncSessionLocal() as session:
        stmt = (
            select(report_image_scan_results)
            .order_by(report_image_scan_results.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(report_image_scan_results.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(report_image_scan_results.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/model-accuracy")
async def get_model_accuracy(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(model_versions).order_by(model_versions.c.created_at.desc()).limit(50)
        )
        return [dict(r) for r in result.mappings().all()]


@router.get("/stores-with-data")
async def get_stores_with_data(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List stores that have at least one day of report data."""
    async with AsyncSessionLocal() as session:
        subq = (
            select(report_store_day_summary.c.store_id)
            .group_by(report_store_day_summary.c.store_id)
            .subquery()
        )
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
        stmt = (
            select(pipeline_run_log)
            .order_by(pipeline_run_log.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(pipeline_run_log.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

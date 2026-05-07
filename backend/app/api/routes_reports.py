"""Reports routes — walkin sessions, store day summaries, image scan results,
model version history, and pipeline run quality stats."""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from datetime import datetime, time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select

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
_IMAGE_TIME_RE = re.compile(r"(?P<h>\d{2})-(?P<m>\d{2})-(?P<s>\d{2})")
_NEAREST_IMAGE_MATCH_SECONDS = 300


def _rows_to_csv_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    cols = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    if cols:
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write("")
    payload = io.BytesIO(buf.getvalue().encode("utf-8"))
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(payload, media_type="text/csv; charset=utf-8", headers=headers)


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _parse_clock(value: Any) -> time | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _parse_image_clock(image_name: Any, timestamp_hint: Any) -> time | None:
    name = str(image_name or "").strip()
    match = _IMAGE_TIME_RE.search(name)
    if match:
        return time(int(match.group("h")), int(match.group("m")), int(match.group("s")))
    return _parse_clock(timestamp_hint)


def _clock_seconds(value: time | None) -> int | None:
    if value is None:
        return None
    return value.hour * 3600 + value.minute * 60 + value.second


def _is_seeded_run(run_id: Any) -> bool:
    return "seeded" in str(run_id or "").lower()


def _load_image_contexts(
    conn: sqlite3.Connection,
    store_id: str,
    business_date: str,
) -> list[dict[str, Any]]:
    # Match on date_source (YYYY-MM-DD) OR date_display (DD-MM-YYYY or YYYY-MM-DD).
    # Convert DD-MM-YYYY display dates to ISO for comparison.
    cur = conn.execute(
        """
        SELECT
            image_id,
            image_name,
            relative_path,
            source_url,
            camera_id,
            timestamp_hint,
            yolo_relevant,
            person_count,
            gpt_customer_count,
            gpt_staff_count,
            gpt_status
        FROM onfly_image_state
        WHERE store_id = ?
          AND (
            date_source = ?
            OR date_display = ?
            OR (
              date_display GLOB '??-??-????' AND
              SUBSTR(date_display,7,4)||'-'||SUBSTR(date_display,4,2)||'-'||SUBSTR(date_display,1,2) = ?
            )
          )
        ORDER BY image_name ASC
        """,
        (store_id, business_date, business_date, business_date),
    )
    rows = _row_dicts(cur)
    contexts: list[dict[str, Any]] = []
    for row in rows:
        img_time = _parse_image_clock(row.get("image_name"), row.get("timestamp_hint"))
        seconds = _clock_seconds(img_time)
        rel_path = str(row.get("relative_path") or "")
        folder_name = rel_path.split("/", 1)[0] if "/" in rel_path else ""
        contexts.append(
            {
                **row,
                "drive_folder_name": folder_name,
                "drive_actual_image_name": str(row.get("image_name") or ""),
                "drive_image_link": str(row.get("source_url") or ""),
                "drive_relative_path": rel_path,
                "image_time": img_time.strftime("%H:%M:%S") if img_time else "",
                "_seconds": seconds,
            }
        )
    return contexts


def _resolve_session_images(
    session_row: dict[str, Any],
    image_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_image_name = str(session_row.get("source_image_name") or "").strip()
    source_image_id = str(session_row.get("image_id") or "").strip()
    session_camera = str(session_row.get("camera_id") or "").strip()

    start_clock = (
        _parse_clock(session_row.get("entry_time"))
        or _parse_clock(session_row.get("first_seen_time"))
        or _parse_clock(session_row.get("event_time"))
    )
    end_clock = (
        _parse_clock(session_row.get("exit_time"))
        or _parse_clock(session_row.get("last_seen_time"))
        or start_clock
    )
    start_sec = _clock_seconds(start_clock)
    end_sec = _clock_seconds(end_clock)

    # Pre-partition: images from the same camera vs all others
    same_cam_imgs = [
        img for img in image_contexts
        if session_camera and str(img.get("camera_id") or "") == session_camera
    ]
    # Use same-camera pool when available, fall back to all images
    preferred_pool = same_cam_imgs if same_cam_imgs else image_contexts

    # Step 1: Direct match by image name or ID (camera-agnostic, most precise)
    direct_matches = [
        img for img in image_contexts
        if (source_image_name and img["drive_actual_image_name"] == source_image_name)
        or (source_image_id and str(img.get("image_id") or "") == source_image_id)
    ]
    if direct_matches:
        return direct_matches

    def _in_window(img: dict[str, Any]) -> bool:
        s = img.get("_seconds")
        return (
            s is not None
            and start_sec is not None
            and end_sec is not None
            and start_sec <= int(s) <= end_sec
        )

    # Step 2: Time-window overlap — same camera only
    same_cam_window = [img for img in preferred_pool if _in_window(img)]
    if same_cam_window:
        return same_cam_window

    # Step 3: Time-window overlap — cross-camera fallback (clearly marked)
    if preferred_pool is not image_contexts:
        cross_cam_window = [img for img in image_contexts if _in_window(img)]
        if cross_cam_window:
            return [{**img, "_cross_camera": True} for img in cross_cam_window]

    # Step 4: Nearest-neighbour — prefer same camera, 5-minute tolerance
    if start_sec is not None:
        timed = [img for img in preferred_pool if img.get("_seconds") is not None]
        if timed:
            timed_sorted = sorted(timed, key=lambda img: abs(int(img["_seconds"]) - start_sec))
            if abs(int(timed_sorted[0]["_seconds"]) - start_sec) <= _NEAREST_IMAGE_MATCH_SECONDS:
                picked = [timed_sorted[0]]
                if end_sec is not None and end_sec != start_sec:
                    exit_sorted = sorted(timed, key=lambda img: abs(int(img["_seconds"]) - end_sec))
                    if (
                        exit_sorted
                        and abs(int(exit_sorted[0]["_seconds"]) - end_sec) <= _NEAREST_IMAGE_MATCH_SECONDS
                        and exit_sorted[0].get("image_id") != picked[0].get("image_id")
                    ):
                        picked.append(exit_sorted[0])
                return picked

    return []


def _enrich_walkin_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    image_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        store_id = str(row.get("store_id") or "")
        business_date = str(row.get("business_date") or row.get("Date") or row.get("date") or "")
        cache_key = (store_id, business_date)
        if cache_key not in image_cache:
            image_cache[cache_key] = _load_image_contexts(conn, store_id, business_date)
        matches = _resolve_session_images(row, image_cache[cache_key])
        primary = matches[0] if matches else {}
        base = {
            key: value
            for key, value in row.items()
            if key not in {
                "run_id",
                "image_id",
                "business_date",
                "source_image_name",
                "source_folder_name",
                "first_seen_time",
                "last_seen_time",
                "event_time",
            }
        }
        enriched.append(
            {
                **base,
                "Source Image": str(row.get("source_image_name") or ""),
                "Drive Actual Image Name": str(primary.get("drive_actual_image_name") or row.get("source_image_name") or ""),
                "Drive Folder Name": str(primary.get("drive_folder_name") or row.get("source_folder_name") or ""),
                "Drive Image Link": str(primary.get("drive_image_link") or ""),
                "Drive Relative Path": str(primary.get("drive_relative_path") or ""),
                "Seeded Data": "Yes" if _is_seeded_run(row.get("run_id")) else "No",
            }
        )
    return enriched


def _image_only_dates(
    conn: Any,
    store_id: str | None,
    business_date: str | None,
    exclude_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Return image-state summary for dates that have images but no sessions."""
    img_params: list[Any] = []
    img_where: list[str] = ["date_display != ''"]
    if store_id:
        img_where.append("store_id = ?")
        img_params.append(store_id)
    if business_date:
        img_where.append(
            "(date_display = ? OR "
            "(date_display GLOB '??-??-????' AND "
            "SUBSTR(date_display,7,4)||'-'||SUBSTR(date_display,4,2)||'-'||SUBSTR(date_display,1,2) = ?))"
        )
        img_params.extend([business_date, business_date])
    img_where_sql = " AND ".join(img_where)
    cur = conn.execute(
        f"""
        SELECT
            store_id,
            CASE WHEN date_display GLOB '??-??-????' THEN
                SUBSTR(date_display,7,4)||'-'||SUBSTR(date_display,4,2)||'-'||SUBSTR(date_display,1,2)
            ELSE date_display END AS iso_date,
            COUNT(*) AS total_images,
            SUM(CASE WHEN COALESCE(yolo_relevant, 0) = 1 THEN 1 ELSE 0 END) AS relevant_images
        FROM onfly_image_state
        WHERE {img_where_sql}
        GROUP BY store_id, date_display
        ORDER BY iso_date DESC
        """,
        tuple(img_params),
    )
    result = []
    for row in _row_dicts(cur):
        key = (str(row.get("store_id") or ""), str(row.get("iso_date") or ""))
        if key not in exclude_keys:
            result.append({
                "store_id": key[0],
                "iso_date": key[1],
                "total_images": int(row.get("total_images") or 0),
                "relevant_images": int(row.get("relevant_images") or 0),
            })
    return result


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
                run_id,
                image_id,
                COALESCE(business_date, date, '') AS "Date",
                COALESCE(business_date, date, '') AS business_date,
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
                COALESCE(source_image_name, '') AS source_image_name,
                COALESCE(source_folder_name, '') AS source_folder_name,
                COALESCE(first_seen_time, '') AS first_seen_time,
                COALESCE(last_seen_time, '') AS last_seen_time,
                COALESCE(event_time, '') AS event_time,
                id
            FROM onfly_walkin_sessions
            {where_sql}
            ORDER BY business_date DESC, entry_time ASC, id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        rows = _row_dicts(cur)
        enriched = _enrich_walkin_rows(conn, rows)

        # Add placeholder rows for dates that have images but no sessions,
        # so Footfall Detail covers the same date range as Store Summary.
        session_keys = {(str(r.get("store_id") or ""), str(r.get("Date") or "")) for r in enriched}
        for img in _image_only_dates(conn, store_id, business_date, session_keys):
            total, relevant = img["total_images"], img["relevant_images"]
            enriched.append({
                "store_id": img["store_id"],
                "Date": img["iso_date"],
                "business_date": img["iso_date"],
                "Walk-in ID": "—",
                "Group ID": "—",
                "Role": "—",
                "Entry Time": "—",
                "Exit Time": "—",
                "Time Spent (mins)": "—",
                "Session Status": "—",
                "Entry Type": "—",
                "Gender": "—",
                "Age Band": "—",
                "Attire / Visual Marker": "—",
                "Primary Clothing": "—",
                "Jewellery Load": "—",
                "Bag Type": "—",
                "Primary Clothing Style Archetype": "—",
                "Engagement Type": "—",
                "Engagement Depth": "—",
                "Purchase Signal (Bag)": "—",
                "Included in Analytics": "—",
                "Source Image": f"[{total} images scanned, {relevant} YOLO-relevant — 0 GPT sessions]",
                "Drive Actual Image Name": "—",
                "Drive Folder Name": "—",
                "Drive Image Link": "",
                "Drive Relative Path": "",
                "Seeded Data": "No",
            })
        enriched.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
        return enriched
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


@router.get("/walkins-qa")
async def get_walkins_for_qa(
    store_id: str | None = None,
    limit: int = 500,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Fast QA-Review endpoint — returns GPT-analysed walk-in sessions with image_id intact.
    Skips the expensive Drive enrichment loop; client uses image_id to fetch thumbnails directly."""
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = ["TRIM(COALESCE(role,'')) != ''"]
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        where_sql = f"WHERE {' AND '.join(where)}"
        # Prefix walkin columns with w. to avoid ambiguity in the JOIN
        w_where = " AND ".join(f"w.{c}" if c.startswith("store_id") else c for c in where)
        w_params = params.copy()
        if store_id:
            # replace bare store_id param with w.store_id
            w_where = w_where.replace("store_id = ?", "w.store_id = ?")
        cur = conn.execute(
            f"""
            WITH cam_images AS (
                -- First (entry) and last (exit) representative images per (store, date, camera)
                -- MIN/MAX on image_id approximates chronological order since IDs embed filenames
                SELECT store_id, date_source, camera_id,
                       MIN(image_id) AS rep_image_id,
                       MAX(image_id) AS last_image_id
                FROM onfly_image_state
                GROUP BY store_id, date_source, camera_id
            )
            SELECT
                w.store_id,
                -- Entry frame: earliest image for this camera+date
                COALESCE(ci.rep_image_id, w.image_id, '') AS image_id,
                -- Exit frame: latest image for this camera+date (NULL if same as entry)
                CASE WHEN ci.last_image_id != ci.rep_image_id THEN ci.last_image_id ELSE NULL END AS last_image_id,
                w.walkin_id,
                COALESCE(w.business_date, w.date, '') AS date,
                w.role,
                COALESCE(w.entry_time, '') AS entry_time,
                COALESCE(w.exit_time, '') AS exit_time,
                COALESCE(w.time_spent_mins, '') AS time_spent_mins,
                COALESCE(w.gender, '') AS gender,
                COALESCE(w.age_band, '') AS age_band,
                COALESCE(w.camera_id, '') AS camera_id,
                COALESCE(w.first_seen_time, '') AS first_seen_time,
                COALESCE(w.last_seen_time, '') AS last_seen_time,
                COALESCE(w.included_in_analytics, '') AS included_in_analytics,
                COALESCE(w.source_image_name, '') AS source_image_name
            FROM onfly_walkin_sessions w
            LEFT JOIN cam_images ci
              ON ci.store_id = w.store_id
             AND ci.date_source = COALESCE(w.business_date, w.date, '')
             AND ci.camera_id = w.camera_id
            WHERE TRIM(COALESCE(w.role,'')) != ''
            {"AND w.store_id = ?" if store_id else ""}
            ORDER BY w.business_date DESC, w.entry_time ASC
            LIMIT ?
            """,
            tuple(([store_id] if store_id else []) + [max(1, int(limit))]),
        )
        return _row_dicts(cur)
    finally:
        conn.close()


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


@router.get("/download/summary")
async def download_store_day_summary(
    store_id: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_store_day_summary(store_id=store_id, limit=limit, _="download")
    tag = store_id or "all"
    return _rows_to_csv_response(rows, f"summary_{tag}.csv")


@router.get("/download/walkins")
async def download_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_walkins(store_id=store_id, business_date=business_date, limit=limit, _="download")
    tag = store_id or "all"
    date_tag = business_date or "all_dates"
    return _rows_to_csv_response(rows, f"walkins_{tag}_{date_tag}.csv")


@router.get("/download/image-scans")
async def download_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = await get_image_scans(store_id=store_id, business_date=business_date, limit=limit, _="download")
    tag = store_id or "all"
    date_tag = business_date or "all_dates"
    return _rows_to_csv_response(rows, f"image_scans_{tag}_{date_tag}.csv")


# ---------------------------------------------------------------------------
# Validation — Walk-in ID ↔ Source Image cross-reference
# ---------------------------------------------------------------------------

def _sqlite_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = ["COALESCE(business_date, '') != ''"]
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("business_date = ?")
            params.append(business_date)
        where_sql = f"WHERE {' AND '.join(where)}"
        cur = conn.execute(
            f"""
            SELECT
                store_id,
                run_id,
                image_id,
                business_date,
                walkin_id,
                group_id,
                role,
                gender,
                age_band,
                entry_time,
                exit_time,
                time_spent_mins,
                included_in_analytics,
                purchase_signal_bag,
                camera_id,
                source_image_name,
                source_folder_name,
                first_seen_time,
                last_seen_time,
                event_time
            FROM onfly_walkin_sessions
            {where_sql}
            ORDER BY business_date DESC, walkin_id ASC, id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        session_rows = _row_dicts(cur)
        image_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        mapped_rows: list[dict[str, Any]] = []
        for session_row in session_rows:
            session_store = str(session_row.get("store_id") or "")
            session_date = str(session_row.get("business_date") or "")
            cache_key = (session_store, session_date)
            if cache_key not in image_cache:
                image_cache[cache_key] = _load_image_contexts(conn, session_store, session_date)
            matches = _resolve_session_images(session_row, image_cache[cache_key])
            base = {
                "store_id": session_store,
                "Date": session_date,
                "Walk-in ID": str(session_row.get("walkin_id") or ""),
                "Group ID": str(session_row.get("group_id") or ""),
                "Role": str(session_row.get("role") or ""),
                "Gender": str(session_row.get("gender") or ""),
                "Age Band": str(session_row.get("age_band") or ""),
                "Entry Time": str(session_row.get("entry_time") or ""),
                "Exit Time": str(session_row.get("exit_time") or ""),
                "Dwell (mins)": str(session_row.get("time_spent_mins") or ""),
                "In Analytics": str(session_row.get("included_in_analytics") or ""),
                "Purchase Signal": str(session_row.get("purchase_signal_bag") or ""),
                "Session Camera": str(session_row.get("camera_id") or ""),
                "Session Source Image": str(session_row.get("source_image_name") or ""),
                "Session Drive Folder": str(session_row.get("source_folder_name") or ""),
                "Seeded Data": "Yes" if _is_seeded_run(session_row.get("run_id")) else "No",
            }
            session_cam = str(session_row.get("camera_id") or "")
            if not matches:
                mapped_rows.append(
                    {
                        **base,
                        "Image Filename": "—",
                        "Drive Folder": "—",
                        "Drive Link": "",
                        "Image Camera": "—",
                        "Camera Match": "No images found",
                        "Image Time": "—",
                        "YOLO Relevant": "No",
                        "YOLO People": 0,
                        "GPT Customers": 0,
                        "GPT Staff": 0,
                        "GPT Status": "",
                    }
                )
                continue
            for match in matches:
                img_cam = str(match.get("camera_id") or "")
                if match.get("_cross_camera"):
                    cam_match = f"Cross-camera (session={session_cam}, image={img_cam})"
                elif img_cam and session_cam and img_cam == session_cam:
                    cam_match = "Exact"
                else:
                    cam_match = "Direct name match"
                mapped_rows.append(
                    {
                        **base,
                        "Image Filename": str(match.get("drive_actual_image_name") or "—"),
                        "Drive Folder": str(match.get("drive_folder_name") or "—"),
                        "Drive Link": str(match.get("drive_image_link") or ""),
                        "Image Camera": img_cam or "—",
                        "Camera Match": cam_match,
                        "Image Time": str(match.get("image_time") or "—"),
                        "YOLO Relevant": "Yes" if match.get("yolo_relevant") else "No",
                        "YOLO People": int(match.get("person_count") or 0),
                        "GPT Customers": int(match.get("gpt_customer_count") or 0),
                        "GPT Staff": int(match.get("gpt_staff_count") or 0),
                        "GPT Status": str(match.get("gpt_status") or ""),
                    }
                )
        # Add rows for dates that have images but no sessions, so Validation
        # covers the same date range as Store Summary.
        session_keys = {(r["store_id"], r["Date"]) for r in mapped_rows}
        for img in _image_only_dates(conn, store_id, business_date, session_keys):
            total, relevant = img["total_images"], img["relevant_images"]
            mapped_rows.append({
                "store_id": img["store_id"],
                "Date": img["iso_date"],
                "Walk-in ID": "—",
                "Group ID": "—",
                "Role": "—",
                "Gender": "—",
                "Age Band": "—",
                "Entry Time": "—",
                "Exit Time": "—",
                "Dwell (mins)": "—",
                "In Analytics": "—",
                "Purchase Signal": "—",
                "Session Camera": "—",
                "Session Source Image": f"{total} images scanned, {relevant} YOLO-relevant",
                "Session Drive Folder": "—",
                "Seeded Data": "No",
                "Image Filename": "—",
                "Drive Folder": "—",
                "Drive Link": "",
                "Image Camera": "—",
                "Camera Match": "No sessions generated for this date",
                "Image Time": "—",
                "YOLO Relevant": f"{relevant}/{total}",
                "YOLO People": 0,
                "GPT Customers": 0,
                "GPT Staff": 0,
                "GPT Status": "skipped",
            })
        mapped_rows.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
        return mapped_rows
    finally:
        conn.close()


@router.get("/validation/walkin-image-map")
async def get_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 5000,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return _sqlite_walkin_image_map(store_id=store_id, business_date=business_date, limit=limit)


@router.get("/download/walkin-image-map")
async def download_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 100000,
    _: str = Depends(get_current_user),
) -> StreamingResponse:
    rows = _sqlite_walkin_image_map(store_id=store_id, business_date=business_date, limit=limit)
    tag = store_id or "all"
    date_tag = business_date or "all_dates"
    return _rows_to_csv_response(rows, f"validation_{tag}_{date_tag}.csv")

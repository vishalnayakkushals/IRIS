from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from backend.app.config import get_settings
from .report_enrichment import enrich_walkin_rows, image_only_dates, row_dicts


def sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_runtime_summary(store_id: str | None = None, limit: int = 90) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where = ["img.date_display != ''"]
        if store_id:
            where.append("img.store_id = ?")
            params.append(store_id)
        cur = conn.execute(
            f"""
            WITH image_rollup AS (
                SELECT
                    img.store_id,
                    img.date_display AS business_date,
                    CASE
                        WHEN img.date_display GLOB '??-??-????' THEN SUBSTR(img.date_display,7,4)||'-'||SUBSTR(img.date_display,4,2)||'-'||SUBSTR(img.date_display,1,2)
                        ELSE img.date_display
                    END AS iso_date,
                    COUNT(*) AS raw_images,
                    SUM(CASE WHEN COALESCE(img.yolo_relevant, 0) = 1 THEN 1 ELSE 0 END) AS relevant_images
                FROM onfly_image_state img
                WHERE {' AND '.join(where)}
                GROUP BY img.store_id, img.date_display
            ),
            walkin_rollup AS (
                SELECT
                    w.store_id,
                    CASE
                        WHEN w.business_date GLOB '??-??-????' THEN SUBSTR(w.business_date,7,4)||'-'||SUBSTR(w.business_date,4,2)||'-'||SUBSTR(w.business_date,1,2)
                        ELSE w.business_date
                    END AS business_date,
                    SUM(CASE WHEN UPPER(COALESCE(w.role, '')) = 'CUSTOMER' AND UPPER(COALESCE(w.included_in_analytics, '')) = 'YES' THEN 1 ELSE 0 END) AS walkins,
                    SUM(CASE WHEN UPPER(COALESCE(w.role, '')) = 'CUSTOMER' AND UPPER(COALESCE(w.included_in_analytics, '')) = 'YES' AND w.entry_type = 'BILLING' THEN 1 ELSE 0 END) AS conversions,
                    AVG(CASE WHEN TRIM(COALESCE(w.time_spent_mins, '')) GLOB '[0-9]*' THEN CAST(w.time_spent_mins AS REAL) ELSE NULL END) AS avg_dwell_mins
                FROM onfly_walkin_sessions w
                WHERE COALESCE(w.business_date, '') != ''
                {f"AND w.store_id = ?" if store_id else ''}
                GROUP BY w.store_id, business_date
            )
            SELECT
                image_rollup.store_id,
                image_rollup.business_date,
                COALESCE(walkin_rollup.walkins, 0) AS walkins,
                COALESCE(walkin_rollup.conversions, 0) AS conversions,
                CASE
                    WHEN COALESCE(walkin_rollup.walkins, 0) > 0 THEN 1.0 * COALESCE(walkin_rollup.conversions, 0) / walkin_rollup.walkins
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
        rows = row_dicts(cur)
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


def sqlite_runtime_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("(business_date = ? OR date = ?)")
            params.extend([business_date, business_date])
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
            {f"WHERE {' AND '.join(where)}" if where else ''}
            ORDER BY business_date DESC, entry_time ASC, id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        rows = row_dicts(cur)
        enriched = enrich_walkin_rows(conn, rows)
        session_keys = {(str(r.get("store_id") or ""), str(r.get("Date") or "")) for r in enriched}
        for img in image_only_dates(conn, store_id, business_date, session_keys):
            total, relevant = img["total_images"], img["relevant_images"]
            enriched.append(
                {
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
                }
            )
        enriched.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
        return enriched
    finally:
        conn.close()


def sqlite_runtime_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 50000,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("(date_display = ? OR date_source = ?)")
            params.extend([business_date, business_date])
        cur = conn.execute(
            f"""
            SELECT
                store_id,
                image_id,
                image_name,
                COALESCE(date_display, date_source, '') AS business_date,
                camera_id,
                timestamp_hint AS capture_time,
                yolo_status,
                yolo_relevant,
                person_count,
                COALESCE(yolo_error, '') AS yolo_error,
                COALESCE(gpt_error, '') AS gpt_error,
                gpt_status,
                gpt_customer_count AS customer_count,
                gpt_staff_count AS staff_count,
                gpt_conversions AS conversion_count,
                CASE
                    WHEN yolo_status = 'camera_excluded' THEN 'Camera type excluded'
                    WHEN yolo_status = 'outside_hours' THEN 'Outside store hours'
                    WHEN yolo_status = 'skipped_irrelevant' THEN 'No people detected'
                    WHEN yolo_status = 'skipped_duplicate_sha256' THEN 'Duplicate image (skipped)'
                    WHEN yolo_status = 'failed_download' THEN 'Download failed'
                    WHEN yolo_status IS NULL OR yolo_status = '' OR yolo_status = 'pending' THEN 'Pending'
                    WHEN gpt_status = 'cached_from_hash' THEN 'GPT cached (duplicate)'
                    WHEN gpt_status = 'failed' THEN 'GPT analysis failed'
                    WHEN yolo_status = 'done' AND gpt_status = 'done' THEN 'Processed'
                    ELSE COALESCE(yolo_status, 'unknown')
                END AS rejection_reason,
                last_run_id,
                discovered_at,
                last_seen_at
            FROM onfly_image_state
            {f"WHERE {' AND '.join(where)}" if where else ''}
            ORDER BY last_seen_at DESC, image_name DESC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        rows = row_dicts(cur)
        return [
            {
                "id": f"{row.get('store_id', '')}:{row.get('image_id', '')}",
                **row,
                "yolo_relevant": bool(row.get("yolo_relevant")),
                "person_count": int(row.get("person_count") or 0),
                "customer_count": int(row.get("customer_count") or 0),
                "staff_count": int(row.get("staff_count") or 0),
                "conversion_count": int(row.get("conversion_count") or 0),
                "yolo_error": str(row.get("yolo_error") or ""),
                "gpt_error": str(row.get("gpt_error") or ""),
                "error_detail": str(row.get("gpt_error") or row.get("yolo_error") or ""),
            }
            for row in rows
        ]
    finally:
        conn.close()


def sqlite_runtime_cost_metrics(
    store_id: str | None = None,
    limit: int = 90,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = []
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        cur = conn.execute(
            f"""
            SELECT
                metric_day,
                store_id,
                SUM(images_listed) AS images_listed,
                SUM(yolo_relevant) AS yolo_relevant,
                SUM(gpt_calls) AS gpt_calls,
                SUM(hash_cache_hits) AS hash_cache_hits,
                SUM(sampled_skips) AS sampled_skips,
                SUM(duplicate_skips) AS duplicate_skips,
                SUM(outside_hours_skips) AS outside_hours_skips,
                SUM(excluded_camera_skips) AS excluded_camera_skips,
                SUM(quota_failures) AS quota_failures,
                SUM(gpt_batch_images) AS gpt_batch_images,
                SUM(gpt_realtime_images) AS gpt_realtime_images,
                SUM(est_cost_inr) AS est_cost_inr
            FROM onfly_cost_metrics
            {f"WHERE {' AND '.join(where)}" if where else ''}
            GROUP BY metric_day, store_id
            ORDER BY metric_day DESC, store_id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        rows = row_dicts(cur)
        out: list[dict[str, Any]] = []
        for row in rows:
            images_listed = int(row.get("images_listed") or 0)
            gpt_calls = int(row.get("gpt_calls") or 0)
            filtered_before_gpt = (
                int(row.get("hash_cache_hits") or 0)
                + int(row.get("sampled_skips") or 0)
                + int(row.get("duplicate_skips") or 0)
                + int(row.get("outside_hours_skips") or 0)
                + int(row.get("excluded_camera_skips") or 0)
            )
            out.append(
                {
                    "metric_day": str(row.get("metric_day") or ""),
                    "store_id": str(row.get("store_id") or ""),
                    "images_listed": images_listed,
                    "yolo_relevant": int(row.get("yolo_relevant") or 0),
                    "gpt_calls": gpt_calls,
                    "hash_cache_hits": int(row.get("hash_cache_hits") or 0),
                    "sampled_skips": int(row.get("sampled_skips") or 0),
                    "duplicate_skips": int(row.get("duplicate_skips") or 0),
                    "outside_hours_skips": int(row.get("outside_hours_skips") or 0),
                    "excluded_camera_skips": int(row.get("excluded_camera_skips") or 0),
                    "quota_failures": int(row.get("quota_failures") or 0),
                    "gpt_batch_images": int(row.get("gpt_batch_images") or 0),
                    "gpt_realtime_images": int(row.get("gpt_realtime_images") or 0),
                    "est_cost_inr": float(row.get("est_cost_inr") or 0.0),
                    "cache_hit_pct": round((int(row.get("hash_cache_hits") or 0) / gpt_calls) * 100, 2) if gpt_calls else 0.0,
                    "filtered_before_gpt": filtered_before_gpt,
                    "gpt_call_rate_pct": round((gpt_calls / images_listed) * 100, 2) if images_listed else 0.0,
                }
            )
        return out
    finally:
        conn.close()

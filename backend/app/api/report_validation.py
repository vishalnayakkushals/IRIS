from __future__ import annotations

from typing import Any

from backend.app.config import get_settings
from .report_enrichment import image_only_dates, is_seeded_run, load_image_contexts, resolve_session_images, row_dicts
from .report_queries import sqlite_connect


def sqlite_walkin_image_map(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where: list[str] = ["COALESCE(business_date, '') != ''"]
        if store_id:
            where.append("store_id = ?")
            params.append(store_id)
        if business_date:
            where.append("business_date = ?")
            params.append(business_date)
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
            WHERE {' AND '.join(where)}
            ORDER BY business_date DESC, walkin_id ASC, id ASC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        session_rows = row_dicts(cur)
        image_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        mapped_rows: list[dict[str, Any]] = []
        for session_row in session_rows:
            session_store = str(session_row.get("store_id") or "")
            session_date = str(session_row.get("business_date") or "")
            cache_key = (session_store, session_date)
            if cache_key not in image_cache:
                image_cache[cache_key] = load_image_contexts(conn, session_store, session_date)
            matches = resolve_session_images(session_row, image_cache[cache_key])
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
                "Seeded Data": "Yes" if is_seeded_run(session_row.get("run_id")) else "No",
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
        session_keys = {(r["store_id"], r["Date"]) for r in mapped_rows}
        for img in image_only_dates(conn, store_id, business_date, session_keys):
            total, relevant = img["total_images"], img["relevant_images"]
            mapped_rows.append(
                {
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
                }
            )
        mapped_rows.sort(key=lambda r: str(r.get("Date") or ""), reverse=True)
        return mapped_rows
    finally:
        conn.close()

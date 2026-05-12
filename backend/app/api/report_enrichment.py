from __future__ import annotations

import re
import sqlite3
from datetime import datetime, time
from typing import Any

_IMAGE_TIME_RE = re.compile(r"(?P<h>\d{2})-(?P<m>\d{2})-(?P<s>\d{2})")
_NEAREST_IMAGE_MATCH_SECONDS = 300


def parse_clock(value: Any) -> time | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def parse_image_clock(image_name: Any, timestamp_hint: Any) -> time | None:
    name = str(image_name or "").strip()
    match = _IMAGE_TIME_RE.search(name)
    if match:
        return time(int(match.group("h")), int(match.group("m")), int(match.group("s")))
    return parse_clock(timestamp_hint)


def clock_seconds(value: time | None) -> int | None:
    if value is None:
        return None
    return value.hour * 3600 + value.minute * 60 + value.second


def is_seeded_run(run_id: Any) -> bool:
    return "seeded" in str(run_id or "").lower()


def row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def load_image_contexts(conn: sqlite3.Connection, store_id: str, business_date: str) -> list[dict[str, Any]]:
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
    rows = row_dicts(cur)
    contexts: list[dict[str, Any]] = []
    for row in rows:
        img_time = parse_image_clock(row.get("image_name"), row.get("timestamp_hint"))
        seconds = clock_seconds(img_time)
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


def resolve_session_images(session_row: dict[str, Any], image_contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_image_name = str(session_row.get("source_image_name") or "").strip()
    source_image_id = str(session_row.get("image_id") or "").strip()
    session_camera = str(session_row.get("camera_id") or "").strip()

    start_clock = parse_clock(session_row.get("entry_time")) or parse_clock(session_row.get("first_seen_time")) or parse_clock(session_row.get("event_time"))
    end_clock = parse_clock(session_row.get("exit_time")) or parse_clock(session_row.get("last_seen_time")) or start_clock
    start_sec = clock_seconds(start_clock)
    end_sec = clock_seconds(end_clock)

    same_cam_imgs = [
        img for img in image_contexts if session_camera and str(img.get("camera_id") or "") == session_camera
    ]
    preferred_pool = same_cam_imgs if same_cam_imgs else image_contexts

    direct_matches = [
        img for img in image_contexts
        if (source_image_name and img["drive_actual_image_name"] == source_image_name)
        or (source_image_id and str(img.get("image_id") or "") == source_image_id)
    ]
    if direct_matches:
        return direct_matches

    def _in_window(img: dict[str, Any]) -> bool:
        s = img.get("_seconds")
        return s is not None and start_sec is not None and end_sec is not None and start_sec <= int(s) <= end_sec

    same_cam_window = [img for img in preferred_pool if _in_window(img)]
    if same_cam_window:
        return same_cam_window

    if preferred_pool is not image_contexts:
        cross_cam_window = [img for img in image_contexts if _in_window(img)]
        if cross_cam_window:
            return [{**img, "_cross_camera": True} for img in cross_cam_window]

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


def enrich_walkin_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    image_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        store_id = str(row.get("store_id") or "")
        business_date = str(row.get("business_date") or row.get("Date") or row.get("date") or "")
        cache_key = (store_id, business_date)
        if cache_key not in image_cache:
            image_cache[cache_key] = load_image_contexts(conn, store_id, business_date)
        matches = resolve_session_images(row, image_cache[cache_key])
        primary = matches[0] if matches else {}
        base = {
            key: value
            for key, value in row.items()
            if key
            not in {
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
                "Seeded Data": "Yes" if is_seeded_run(row.get("run_id")) else "No",
            }
        )
    return enriched


def image_only_dates(
    conn: sqlite3.Connection,
    store_id: str | None,
    business_date: str | None,
    exclude_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    img_params: list[Any] = []
    img_where: list[str] = ["date_display != ''"]
    if store_id:
        img_where.append("store_id = ?")
        img_params.append(store_id)
    if business_date:
        img_where.append(
            "(date_display = ? OR (date_display GLOB '??-??-????' AND SUBSTR(date_display,7,4)||'-'||SUBSTR(date_display,4,2)||'-'||SUBSTR(date_display,1,2) = ?))"
        )
        img_params.extend([business_date, business_date])
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
        WHERE {' AND '.join(img_where)}
        GROUP BY store_id, date_display
        ORDER BY iso_date DESC
        """,
        tuple(img_params),
    )
    result = []
    for row in row_dicts(cur):
        key = (str(row.get("store_id") or ""), str(row.get("iso_date") or ""))
        if key not in exclude_keys:
            result.append(
                {
                    "store_id": key[0],
                    "iso_date": key[1],
                    "total_images": int(row.get("total_images") or 0),
                    "relevant_images": int(row.get("relevant_images") or 0),
                }
            )
    return result

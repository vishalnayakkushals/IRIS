from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


REVIEW_TABLE_FIELDS = [
    "store_id",
    "date_folder",
    "date_display",
    "camera_id",
    "timestamp_hint",
    "image_name",
    "drive_link",
    "person_count",
    "yolo_conf",
    "yolo_status",
    "yolo_error",
    "gpt_status",
    "gpt_customer_count",
    "gpt_staff_count",
    "gpt_conversions",
    "gpt_bounce",
    "gpt_error",
    "relative_path",
    "source_item_id",
    "image_id",
    "last_run_id",
    "last_seen_at",
    "review_status",
    "reviewer_name",
    "reviewer_comment",
]


def safe_review_table_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "").strip())
    return token.strip("_") or "all_dates"


def relevant_review_table_path(out_dir: Path, store_id: str, date_filter: str = "") -> Path:
    store_dir = out_dir.resolve() / str(store_id).strip()
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir / f"yolo_relevant_review_table_{safe_review_table_token(date_filter)}.csv"


def fetch_relevant_review_rows(conn: sqlite3.Connection, store_id: str, date_filter: str = "", limit: int = 0) -> list[sqlite3.Row]:
    where = ["store_id = ?", "COALESCE(yolo_relevant, 0) = 1"]
    params: list[object] = [str(store_id).strip()]
    if date_filter:
        where.append("(date_display = ? OR date_source = ?)")
        params.extend([str(date_filter).strip(), str(date_filter).strip()])

    sql = f"""
        SELECT
            store_id,
            date_source,
            date_display,
            camera_id,
            timestamp_hint,
            image_name,
            relative_path,
            source_provider,
            source_item_id,
            source_url,
            image_id,
            yolo_status,
            yolo_relevant,
            person_count,
            yolo_conf,
            yolo_error,
            gpt_status,
            gpt_customer_count,
            gpt_staff_count,
            gpt_conversions,
            gpt_bounce,
            gpt_error,
            last_run_id,
            last_seen_at
        FROM onfly_image_state
        WHERE {" AND ".join(where)}
        ORDER BY date_source, timestamp_hint, camera_id, image_name, source_item_id
    """
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, tuple(params)).fetchall()


def review_row_to_csv_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "store_id": row["store_id"],
        "date_folder": row["date_source"],
        "date_display": row["date_display"],
        "camera_id": row["camera_id"],
        "timestamp_hint": row["timestamp_hint"],
        "image_name": row["image_name"],
        "drive_link": row["source_url"],
        "person_count": int(row["person_count"] or 0),
        "yolo_conf": row["yolo_conf"],
        "yolo_status": row["yolo_status"],
        "yolo_error": row["yolo_error"],
        "gpt_status": row["gpt_status"],
        "gpt_customer_count": int(row["gpt_customer_count"] or 0),
        "gpt_staff_count": int(row["gpt_staff_count"] or 0),
        "gpt_conversions": int(row["gpt_conversions"] or 0),
        "gpt_bounce": int(row["gpt_bounce"] or 0),
        "gpt_error": row["gpt_error"],
        "relative_path": row["relative_path"],
        "source_item_id": row["source_item_id"],
        "image_id": row["image_id"],
        "last_run_id": row["last_run_id"],
        "last_seen_at": row["last_seen_at"],
        "review_status": "",
        "reviewer_name": "",
        "reviewer_comment": "",
    }


def export_relevant_review_table(
    db_path: Path,
    out_dir: Path,
    store_id: str,
    date_filter: str = "",
    limit: int = 0,
) -> dict[str, Any]:
    resolved_db = db_path.resolve()
    if not resolved_db.exists():
        raise FileNotFoundError(f"SQLite DB not found: {resolved_db}")

    conn = sqlite3.connect(str(resolved_db), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = fetch_relevant_review_rows(conn, store_id, str(date_filter).strip(), max(0, int(limit)))
    finally:
        conn.close()

    output = relevant_review_table_path(out_dir, store_id, str(date_filter).strip())
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_TABLE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(review_row_to_csv_dict(row))

    return {
        "store_id": str(store_id).strip(),
        "date_filter": str(date_filter).strip(),
        "rows": len(rows),
        "output_path": str(output),
        "filename": output.name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

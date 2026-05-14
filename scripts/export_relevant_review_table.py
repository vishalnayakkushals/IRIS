from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a local CSV review table for YOLO-relevant images")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--date", default="", help="Optional date filter. Accepts display date like 10-05-2026 or folder date like 2026-05-10")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--limit", type=int, default=0, help="Optional row cap for quick review samples")
    return parser.parse_args()


def _safe_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "").strip())
    return token.strip("_") or "all_dates"


def _output_path(out_dir: Path, store_id: str, date_filter: str) -> Path:
    store_dir = out_dir.resolve() / store_id
    store_dir.mkdir(parents=True, exist_ok=True)
    date_token = _safe_token(date_filter)
    return store_dir / f"yolo_relevant_review_table_{date_token}.csv"


def _rows(conn: sqlite3.Connection, store_id: str, date_filter: str, limit: int) -> list[sqlite3.Row]:
    where = ["store_id = ?", "COALESCE(yolo_relevant, 0) = 1"]
    params: list[object] = [store_id]
    if date_filter:
        where.append("(date_display = ? OR date_source = ?)")
        params.extend([date_filter, date_filter])
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


def main() -> None:
    args = parse_args()
    db_path = args.db.resolve()
    if not db_path.exists():
        raise RuntimeError(f"SQLite DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = _rows(conn, str(args.store_id).strip(), str(args.date).strip(), max(0, int(args.limit)))
    finally:
        conn.close()

    output = _output_path(args.out_dir, str(args.store_id).strip(), str(args.date).strip())
    fields = [
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
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
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
            )
    print(f"rows={len(rows)}")
    print(f"output={output}")
    print(f"generated_at={datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()

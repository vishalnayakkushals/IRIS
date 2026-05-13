from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.runtime_bootstrap import load_env_file  # noqa: E402
from iris.drive_review_export import DriveRelevantImageExporter, drive_review_export_status  # noqa: E402
from iris.source_clients import SourceImage  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Google Drive Relevant image/<date>/ folders for YOLO relevant images")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--date", default="", help="Optional display date filter such as 01-05-2026")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--limit", type=int, default=0, help="Optional cap for backfill count")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file()
    ok, reason = drive_review_export_status()
    if not ok:
        raise RuntimeError(reason)
    db_path = args.db.resolve()

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        where = ["store_id=?", "yolo_relevant=1"]
        params: list[object] = [args.store_id]
        if args.date:
            where.append("date_display=?")
            params.append(str(args.date).strip())
        sql = (
            "SELECT store_id, image_id, image_name, relative_path, source_provider, source_item_id, "
            "source_url, source_uri, date_source, date_display, camera_id, timestamp_hint "
            "FROM onfly_image_state WHERE "
            + " AND ".join(where)
            + " ORDER BY date_display, image_name"
        )
        if int(args.limit) > 0:
            sql += f" LIMIT {int(args.limit)}"
        rows = conn.execute(sql, tuple(params)).fetchall()
    finally:
        conn.close()

    created = 0
    skipped = 0
    failed = 0
    exporter_cache: dict[str, DriveRelevantImageExporter] = {}
    for row in rows:
        item = SourceImage(
            image_id=str(row["image_id"]),
            image_name=str(row["image_name"]),
            relative_path=str(row["relative_path"] or ""),
            source_provider=str(row["source_provider"] or ""),
            source_item_id=str(row["source_item_id"] or ""),
            source_url=str(row["source_url"] or ""),
            date_source=str(row["date_source"] or ""),
            date_display=str(row["date_display"] or ""),
            camera_id=str(row["camera_id"] or ""),
            timestamp_hint=str(row["timestamp_hint"] or ""),
        )
        if item.source_provider.lower() != "gdrive":
            skipped += 1
            continue
        source_uri = str(row["source_uri"] or "").strip()
        exporter = exporter_cache.get(source_uri)
        if exporter is None:
            exporter = DriveRelevantImageExporter(source_uri)
            exporter_cache[source_uri] = exporter
        try:
            result = exporter.export_image(item)
        except Exception as exc:
            failed += 1
            print(f"failed image_id={item.image_id} image_name={item.image_name} error={str(exc)[:300]}")
            continue
        if result.get("status") == "created":
            created += 1
            if created % 100 == 0:
                print(f"created={created} skipped={skipped} failed={failed} last={item.image_name}")
        else:
            skipped += 1

    print(f"done created={created} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()

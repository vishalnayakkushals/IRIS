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
from iris.source_clients import GDriveClient, LocalClient, SourceImage, parse_drive_folder_id  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill local same-date folders for YOLO relevant images")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--date", default="", help="Optional display date filter such as 01-05-2026")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--limit", type=int, default=0, help="Optional cap for backfill count")
    return parser.parse_args()


def _build_client(row: sqlite3.Row, google_api_key: str):
    source_provider = str(row["source_provider"] or "").strip().lower()
    source_uri = str(row["source_uri"] or "").strip()
    if source_provider == "local":
        return LocalClient(source_uri)
    if source_provider == "gdrive" or parse_drive_folder_id(source_uri):
        return GDriveClient(source_uri, google_api_key)
    raise RuntimeError(f"Unsupported source provider for {row['image_id']}: {source_provider or source_uri}")


def _safe_date(row: sqlite3.Row) -> str:
    date_display = str(row["date_display"] or "").strip()
    if date_display:
        return date_display.replace("/", "-").replace("\\", "-").replace(":", "-")
    date_source = str(row["date_source"] or "").strip()
    if len(date_source) == 10 and date_source[4] == "-" and date_source[7] == "-":
        yyyy, mm, dd = date_source.split("-")
        return f"{dd}-{mm}-{yyyy}"
    return "unknown_date"


def main() -> None:
    args = parse_args()
    load_env_file()
    google_api_key = str(__import__("os").environ.get("GOOGLE_API_KEY", "")).strip()
    db_path = args.db.resolve()
    out_root = args.out_dir.resolve() / args.store_id / "yolo_review_images"
    out_root.mkdir(parents=True, exist_ok=True)

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

    written = 0
    skipped = 0
    client_cache: dict[tuple[str, str], object] = {}
    for row in rows:
        date_dir = out_root / _safe_date(row)
        date_dir.mkdir(parents=True, exist_ok=True)
        target = date_dir / str(row["image_name"])
        if target.exists():
            skipped += 1
            continue
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
        cache_key = (item.source_provider, str(row["source_uri"] or ""))
        client = client_cache.get(cache_key)
        if client is None:
            client = _build_client(row, google_api_key)
            client_cache[cache_key] = client
        image_bytes = client.fetch_bytes(item)
        target.write_bytes(image_bytes)
        written += 1
        if written % 100 == 0:
            print(f"written={written} skipped={skipped} last={target}")

    print(f"done written={written} skipped={skipped} out={out_root}")


if __name__ == "__main__":
    main()

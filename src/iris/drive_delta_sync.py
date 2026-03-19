from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
import csv
import re
import sqlite3
import time

from iris.store_registry import (
    StoreRecord,
    _drive_api_download_files,
    _drive_api_list_files_recursive,
    _drive_item_dest_path,
    _now_utc,
    _upsert_source_index_rows,
    ensure_store_snapshot_dir,
    init_db,
    list_stores,
    parse_drive_folder_id,
)

import requests


DATE_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class DeltaSyncResult:
    store_id: str
    mode: str
    scope_date: str
    listed_files: int
    active_before: int
    reused_existing: int
    downloaded_new: int
    marked_deleted: int
    elapsed_sec: float
    message: str


def _date_bucket_from_relative_path(relative_path: str) -> str:
    rel = str(relative_path or "").strip().replace("\\", "/")
    if not rel:
        return ""
    first = rel.split("/", 1)[0].strip()
    return first if DATE_FOLDER_PATTERN.match(first) else ""


def _list_drive_date_subfolders(parent_folder_id: str, api_key: str) -> list[tuple[str, str]]:
    subfolders: list[tuple[str, str]] = []
    token = None
    while True:
        params = {
            "q": (
                f"'{parent_folder_id}' in parents and trashed = false and "
                "mimeType = 'application/vnd.google-apps.folder'"
            ),
            "fields": "nextPageToken,files(id,name)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "key": api_key,
        }
        if token:
            params["pageToken"] = token
        resp = requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        for item in payload.get("files", []):
            name = str(item.get("name", "")).strip()
            file_id = str(item.get("id", "")).strip()
            if name and file_id and DATE_FOLDER_PATTERN.match(name):
                subfolders.append((name, file_id))
        token = payload.get("nextPageToken")
        if not token:
            break
    return sorted(subfolders, key=lambda x: x[0])


def _prepend_folder_prefix(items: list[dict[str, str]], folder_name: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        rel = str(item.get("relative_path", item.get("name", ""))).strip().replace("\\", "/")
        rel_with_prefix = f"{folder_name}/{rel}" if rel else folder_name
        out.append(
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "relative_path": rel_with_prefix,
                "drive_web_link": str(item.get("drive_web_link", "")),
            }
        )
    return out


def _list_present_index_rows(db_path: Path, store_id: str) -> list[tuple[str, str, str]]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_file_id, relative_path, local_path
            FROM store_source_file_index
            WHERE store_id=? AND source_provider='gdrive' AND is_present=1
            """,
            (store_id.strip(),),
        ).fetchall()
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]
    finally:
        conn.close()


def _mark_missing_in_scope(
    db_path: Path,
    store_id: str,
    missing_rows: list[tuple[str, str]],
    remove_local_files: bool = False,
) -> int:
    if not missing_rows:
        return 0
    now = _now_utc()
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            UPDATE store_source_file_index
            SET is_present=0, last_seen_at=?
            WHERE store_id=? AND source_provider='gdrive' AND source_file_id=?
            """,
            [(now, store_id.strip(), source_file_id) for source_file_id, _ in missing_rows],
        )
        conn.commit()
    finally:
        conn.close()
    if remove_local_files:
        for _, local_path in missing_rows:
            p = Path(local_path)
            if p.exists() and p.is_file():
                try:
                    p.unlink()
                except Exception:
                    pass
    return len(missing_rows)


def _write_manifest_from_active_index(db_path: Path, store_id: str, target_dir: Path) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_file_id, source_name, relative_path, source_link, local_path
            FROM store_source_file_index
            WHERE store_id=? AND source_provider='gdrive' AND is_present=1
            ORDER BY relative_path
            """,
            (store_id.strip(),),
        ).fetchall()
    finally:
        conn.close()
    manifest_path = target_dir / "_drive_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["file_id", "name", "relative_path", "drive_web_link", "local_path"],
        )
        writer.writeheader()
        for file_id, name, relative_path, source_link, local_path in rows:
            writer.writerow(
                {
                    "file_id": str(file_id),
                    "name": str(name),
                    "relative_path": str(relative_path),
                    "drive_web_link": str(source_link),
                    "local_path": str(local_path),
                }
            )


def _download_with_multi_queue(
    pending_items: list[dict[str, str]],
    target_dir: Path,
    api_key: str,
    workers: int = 6,
) -> tuple[int, list[dict[str, str]]]:
    if not pending_items:
        return 0, []
    # Prevent concurrent writes to same target when Drive contains duplicates.
    deduped: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for item in pending_items:
        rel = str(item.get("relative_path", item.get("name", ""))).strip().replace("\\", "/")
        key = rel or str(item.get("id", "")).strip()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)
    worker_count = max(1, int(workers))
    queues: list[list[dict[str, str]]] = [[] for _ in range(worker_count)]
    for idx, item in enumerate(deduped):
        queues[idx % worker_count].append(item)

    downloaded_total = 0
    rows_total: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_drive_api_download_files, queue_items, target_dir, api_key)
            for queue_items in queues
            if queue_items
        ]
        for fut in as_completed(futures):
            downloaded, rows = fut.result()
            downloaded_total += int(downloaded)
            rows_total.extend(rows)
    return downloaded_total, rows_total


def sync_store_gdrive_delta(
    db_path: Path,
    data_root: Path,
    store: StoreRecord,
    api_key: str,
    workers: int = 6,
    remove_local_deleted_files: bool = False,
) -> DeltaSyncResult:
    start = time.perf_counter()
    folder_id = parse_drive_folder_id(store.drive_folder_url)
    if not folder_id:
        return DeltaSyncResult(
            store_id=store.store_id,
            mode="error",
            scope_date="",
            listed_files=0,
            active_before=0,
            reused_existing=0,
            downloaded_new=0,
            marked_deleted=0,
            elapsed_sec=0.0,
            message=f"{store.store_id}: invalid Google Drive folder URL",
        )

    target_dir = ensure_store_snapshot_dir(data_root=data_root, store_id=store.store_id)
    active_rows = _list_present_index_rows(db_path=db_path, store_id=store.store_id)
    first_run = len(active_rows) == 0
    mode = "full_initial" if first_run else "latest_delta"

    if first_run:
        listed_items = _drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
        scope_date = "ALL"
    else:
        dated_folders = _list_drive_date_subfolders(parent_folder_id=folder_id, api_key=api_key)
        if not dated_folders:
            listed_items = _drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
            scope_date = "ALL_NO_DATE_FOLDERS"
            mode = "full_fallback"
        else:
            latest_date, latest_folder_id = dated_folders[-1]
            raw_items = _drive_api_list_files_recursive(folder_id=latest_folder_id, api_key=api_key)
            listed_items = _prepend_folder_prefix(raw_items, folder_name=latest_date)
            scope_date = latest_date

    listed_map = {str(item.get("id", "")).strip(): item for item in listed_items if str(item.get("id", "")).strip()}
    listed_ids = set(listed_map.keys())
    active_before = len(active_rows)
    active_in_scope: dict[str, tuple[str, str]] = {}
    for source_file_id, relative_path, local_path in active_rows:
        if mode.startswith("full") or scope_date in {"ALL", "ALL_NO_DATE_FOLDERS"}:
            in_scope = True
        else:
            in_scope = _date_bucket_from_relative_path(relative_path) == scope_date
        if in_scope:
            active_in_scope[source_file_id] = (relative_path, local_path)

    missing_in_drive = [
        (source_file_id, local_path)
        for source_file_id, (_, local_path) in active_in_scope.items()
        if source_file_id not in listed_ids
    ]
    marked_deleted = _mark_missing_in_scope(
        db_path=db_path,
        store_id=store.store_id,
        missing_rows=missing_in_drive,
        remove_local_files=remove_local_deleted_files,
    )

    pending_items: list[dict[str, str]] = []
    reused_existing = 0
    for item in listed_items:
        source_file_id = str(item.get("id", "")).strip()
        if not source_file_id:
            continue
        dest, _ = _drive_item_dest_path(target_dir=target_dir, item=item)
        if dest.exists() and dest.is_file() and dest.stat().st_size > 0:
            reused_existing += 1
            continue
        pending_items.append(item)

    downloaded_new, manifest_rows = _download_with_multi_queue(
        pending_items=pending_items,
        target_dir=target_dir,
        api_key=api_key,
        workers=workers,
    )

    now = _now_utc()
    downloaded_ids = {
        str(row.get("file_id", "")).strip()
        for row in manifest_rows
        if str(row.get("file_id", "")).strip()
    }
    upsert_rows: list[tuple[str, str, str, str, str, str, str, str, int, int, str, str, str]] = []
    for source_file_id, item in listed_map.items():
        dest, rel = _drive_item_dest_path(target_dir=target_dir, item=item)
        exists = dest.exists() and dest.is_file() and dest.stat().st_size > 0
        size = int(dest.stat().st_size) if exists else 0
        upsert_rows.append(
            (
                store.store_id,
                "gdrive",
                source_file_id,
                str(item.get("name", "")),
                rel,
                str(item.get("drive_web_link", "")),
                str(dest),
                dest.suffix.lower(),
                size,
                1 if exists else 0,
                now,
                now,
                now if source_file_id in downloaded_ids else "",
            )
        )
    _upsert_source_index_rows(db_path=db_path, rows=upsert_rows)
    _write_manifest_from_active_index(db_path=db_path, store_id=store.store_id, target_dir=target_dir)

    elapsed = time.perf_counter() - start
    return DeltaSyncResult(
        store_id=store.store_id,
        mode=mode,
        scope_date=scope_date,
        listed_files=len(listed_items),
        active_before=active_before,
        reused_existing=reused_existing,
        downloaded_new=downloaded_new,
        marked_deleted=marked_deleted,
        elapsed_sec=round(elapsed, 2),
        message=(
            f"{store.store_id}: mode={mode} scope={scope_date} listed={len(listed_items)} "
            f"reused={reused_existing} downloaded={downloaded_new} marked_deleted={marked_deleted} "
            f"elapsed_sec={round(elapsed, 2)}"
        ),
    )


def run_delta_sync_for_store(
    db_path: Path,
    data_root: Path,
    store_id: str,
    api_key: str,
    workers: int = 6,
    remove_local_deleted_files: bool = False,
) -> DeltaSyncResult:
    stores = list_stores(db_path)
    store = next((s for s in stores if s.store_id.strip().upper() == store_id.strip().upper()), None)
    if store is None:
        return DeltaSyncResult(
            store_id=store_id,
            mode="error",
            scope_date="",
            listed_files=0,
            active_before=0,
            reused_existing=0,
            downloaded_new=0,
            marked_deleted=0,
            elapsed_sec=0.0,
            message=f"{store_id}: store not found in DB",
        )
    return sync_store_gdrive_delta(
        db_path=db_path,
        data_root=data_root,
        store=store,
        api_key=api_key,
        workers=workers,
        remove_local_deleted_files=remove_local_deleted_files,
    )


def sleep_seconds_until_next_run(run_hhmm: str, tz_name: str) -> int:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz=tz)
    hh, mm = [int(x) for x in run_hhmm.split(":", 1)]
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1, int((target - now).total_seconds()))

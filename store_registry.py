from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import io
import os
import re
import sqlite3
from typing import Any
from uuid import uuid4

from PIL import Image
import requests


DRIVE_FOLDER_ID_PATTERN = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class StoreRecord:
    store_id: str
    store_name: str
    email: str
    drive_folder_url: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CameraConfig:
    store_id: str
    camera_id: str
    camera_role: str
    entry_line_x: float
    entry_direction: str
    updated_at: str


def _optimize_image_bytes(
    content: bytes,
    max_dimension: int = 1280,
    quality: int = 72,
) -> tuple[bytes, str]:
    """Normalize uploaded/synced images to optimized JPEG for lower storage usage."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGB")
            image.thumbnail((max_dimension, max_dimension))
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue(), ".jpg"
    except Exception:
        return content, ""


def optimize_store_image_files(
    store_dir: Path,
    max_dimension: int = 1280,
    quality: int = 72,
) -> tuple[int, int]:
    processed = 0
    failed = 0
    for path in sorted(store_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        try:
            optimized, ext = _optimize_image_bytes(
                path.read_bytes(), max_dimension=max_dimension, quality=quality
            )
            if ext == ".jpg":
                new_path = path.with_suffix(".jpg")
                new_path.write_bytes(optimized)
                if new_path != path and path.exists():
                    path.unlink()
            else:
                path.write_bytes(optimized)
            processed += 1
        except Exception:
            failed += 1
    return processed, failed


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stores (
                store_id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                drive_folder_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_employees_store_id ON employees(store_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS camera_configs (
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                camera_role TEXT NOT NULL DEFAULT 'INSIDE',
                entry_line_x REAL NOT NULL DEFAULT 0.5,
                entry_direction TEXT NOT NULL DEFAULT 'OUTSIDE_TO_INSIDE',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, camera_id),
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_store(
    db_path: Path, store_id: str, store_name: str, email: str, drive_folder_url: str
) -> None:
    init_db(db_path)
    normalized_store_id = store_id.strip()
    normalized_store_name = store_name.strip()
    normalized_email = email.strip().lower()
    normalized_drive_url = drive_folder_url.strip()
    if not normalized_store_id or not normalized_store_name or not normalized_email:
        raise ValueError("store_id, store_name, and email are required")

    now = _now_utc()
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT store_id FROM stores WHERE lower(email) = lower(?) AND store_id != ?",
            (normalized_email, normalized_store_id),
        ).fetchone()
        if existing:
            raise ValueError(f"Email '{email}' is already linked to store '{existing[0]}'")

        row = conn.execute(
            "SELECT store_id FROM stores WHERE store_id = ?", (normalized_store_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO stores (store_id, store_name, email, drive_folder_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_store_id,
                    normalized_store_name,
                    normalized_email,
                    normalized_drive_url,
                    now,
                    now,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE stores
                SET store_name = ?, email = ?, drive_folder_url = ?, updated_at = ?
                WHERE store_id = ?
                """,
                (
                    normalized_store_name,
                    normalized_email,
                    normalized_drive_url,
                    now,
                    normalized_store_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def list_stores(db_path: Path) -> list[StoreRecord]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT store_id, store_name, email, drive_folder_url, created_at, updated_at
            FROM stores
            ORDER BY store_id
            """
        ).fetchall()
        return [StoreRecord(*row) for row in rows]
    finally:
        conn.close()


def get_store_by_email(db_path: Path, email: str) -> StoreRecord | None:
    init_db(db_path)
    normalized_email = email.strip().lower()
    if not normalized_email:
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT store_id, store_name, email, drive_folder_url, created_at, updated_at
            FROM stores
            WHERE lower(email) = lower(?)
            """,
            (normalized_email,),
        ).fetchone()
        return StoreRecord(*row) if row else None
    finally:
        conn.close()


def list_employees(db_path: Path, store_id: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        if store_id:
            rows = conn.execute(
                """
                SELECT id, store_id, employee_name, image_path, created_at
                FROM employees
                WHERE store_id = ?
                ORDER BY id DESC
                """,
                (store_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, store_id, employee_name, image_path, created_at
                FROM employees
                ORDER BY id DESC
                """
            ).fetchall()
        return [
            {
                "id": row[0],
                "store_id": row[1],
                "employee_name": row[2],
                "image_path": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]
    finally:
        conn.close()


def add_employee_image(
    db_path: Path,
    employee_assets_root: Path,
    store_id: str,
    employee_name: str,
    original_filename: str,
    content: bytes,
) -> Path:
    init_db(db_path)
    normalized_store_id = store_id.strip()
    normalized_employee_name = employee_name.strip()
    if not normalized_store_id or not normalized_employee_name:
        raise ValueError("store_id and employee_name are required")

    conn = sqlite3.connect(db_path)
    try:
        exists = conn.execute(
            "SELECT 1 FROM stores WHERE store_id = ?", (normalized_store_id,)
        ).fetchone()
        if not exists:
            raise ValueError(f"Store '{normalized_store_id}' is not registered")
    finally:
        conn.close()

    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", normalized_employee_name).strip("_") or "employee"
    extension = Path(original_filename).suffix.lower() or ".jpg"
    if extension not in _IMAGE_EXTS:
        extension = ".jpg"

    optimized_content, optimized_ext = _optimize_image_bytes(content)
    if optimized_ext:
        extension = optimized_ext

    target_dir = employee_assets_root / normalized_store_id
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe_name}_{uuid4().hex[:8]}{extension}"
    target_path = target_dir / filename
    target_path.write_bytes(optimized_content)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO employees (store_id, employee_name, image_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (normalized_store_id, normalized_employee_name, str(target_path), _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()

    return target_path




def upsert_camera_config(
    db_path: Path,
    store_id: str,
    camera_id: str,
    camera_role: str = "INSIDE",
    entry_line_x: float = 0.5,
    entry_direction: str = "OUTSIDE_TO_INSIDE",
) -> None:
    init_db(db_path)
    role = camera_role.strip().upper()
    if role not in {"ENTRANCE", "INSIDE"}:
        raise ValueError("camera_role must be ENTRANCE or INSIDE")
    direction = entry_direction.strip().upper()
    if direction not in {"OUTSIDE_TO_INSIDE", "INSIDE_TO_OUTSIDE"}:
        raise ValueError("entry_direction must be OUTSIDE_TO_INSIDE or INSIDE_TO_OUTSIDE")
    x = float(entry_line_x)
    if x < 0 or x > 1:
        raise ValueError("entry_line_x must be between 0 and 1")

    conn = sqlite3.connect(db_path)
    try:
        exists = conn.execute("SELECT 1 FROM stores WHERE store_id = ?", (store_id.strip(),)).fetchone()
        if not exists:
            raise ValueError(f"Store '{store_id}' is not registered")
        conn.execute(
            """
            INSERT INTO camera_configs (store_id, camera_id, camera_role, entry_line_x, entry_direction, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(store_id, camera_id) DO UPDATE SET
              camera_role=excluded.camera_role,
              entry_line_x=excluded.entry_line_x,
              entry_direction=excluded.entry_direction,
              updated_at=excluded.updated_at
            """,
            (store_id.strip(), camera_id.strip().upper(), role, x, direction, _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def list_camera_configs(db_path: Path, store_id: str | None = None) -> list[CameraConfig]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        if store_id:
            rows = conn.execute(
                "SELECT store_id, camera_id, camera_role, entry_line_x, entry_direction, updated_at FROM camera_configs WHERE store_id = ? ORDER BY camera_id",
                (store_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT store_id, camera_id, camera_role, entry_line_x, entry_direction, updated_at FROM camera_configs ORDER BY store_id, camera_id"
            ).fetchall()
        return [CameraConfig(*row) for row in rows]
    finally:
        conn.close()


def camera_config_map(db_path: Path) -> dict[str, dict[str, CameraConfig]]:
    out: dict[str, dict[str, CameraConfig]] = {}
    for cfg in list_camera_configs(db_path=db_path):
        out.setdefault(cfg.store_id, {})[cfg.camera_id] = cfg
    return out

def parse_drive_folder_id(drive_folder_url: str) -> str | None:
    match = DRIVE_FOLDER_ID_PATTERN.search(drive_folder_url)
    if not match:
        return None
    return match.group(1)


def ensure_store_snapshot_dir(data_root: Path, store_id: str) -> Path:
    target = data_root / store_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _drive_api_list_files_recursive(
    folder_id: str,
    api_key: str,
) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    stack = [folder_id]

    while stack:
        current_folder = stack.pop()
        next_page_token = None
        while True:
            params = {
                "q": f"'{current_folder}' in parents and trashed = false",
                "fields": "nextPageToken,files(id,name,mimeType)",
                "pageSize": 1000,
                "key": api_key,
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            resp = requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            for item in payload.get("files", []):
                mime = item.get("mimeType", "")
                if mime == "application/vnd.google-apps.folder":
                    stack.append(item["id"])
                else:
                    files.append({"id": item["id"], "name": item.get("name", item["id"])})
            next_page_token = payload.get("nextPageToken")
            if not next_page_token:
                break

    return files


def _drive_api_download_files(file_items: list[dict[str, str]], target_dir: Path, api_key: str) -> int:
    downloaded = 0
    for item in file_items:
        name = Path(item["name"]).name
        dest = target_dir / name
        url = f"https://www.googleapis.com/drive/v3/files/{item['id']}"
        resp = requests.get(url, params={"alt": "media", "key": api_key}, timeout=60)
        if resp.status_code != 200:
            continue
        dest.write_bytes(resp.content)
        downloaded += 1
    return downloaded


def _sync_store_from_drive_api(store: StoreRecord, target_dir: Path, api_key: str) -> tuple[bool, str]:
    folder_id = parse_drive_folder_id(store.drive_folder_url)
    if not folder_id:
        return False, f"{store.store_id}: invalid Google Drive folder URL"
    try:
        items = _drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
        if not items:
            return False, f"{store.store_id}: no files found via Drive API"
        downloaded = _drive_api_download_files(items, target_dir=target_dir, api_key=api_key)
        processed, failed = optimize_store_image_files(target_dir)
        return (
            True,
            f"{store.store_id}: api_sync downloaded={downloaded} optimized={processed} failed={failed} dir={target_dir}",
        )
    except Exception as exc:
        return False, f"{store.store_id}: Drive API sync failed ({exc})"


def sync_store_from_drive(store: StoreRecord, data_root: Path) -> tuple[bool, str]:
    if not store.drive_folder_url.strip():
        return False, f"{store.store_id}: no drive folder URL configured"

    folder_id = parse_drive_folder_id(store.drive_folder_url)
    if folder_id is None:
        return False, f"{store.store_id}: invalid Google Drive folder URL"

    target_dir = ensure_store_snapshot_dir(data_root=data_root, store_id=store.store_id)

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if api_key:
        ok, msg = _sync_store_from_drive_api(store=store, target_dir=target_dir, api_key=api_key)
        if ok:
            return ok, msg

    try:
        import gdown  # type: ignore
    except Exception as exc:
        return False, f"{store.store_id}: gdown not available ({exc})"

    try:
        gdown.download_folder(
            url=store.drive_folder_url,
            output=str(target_dir),
            quiet=True,
            remaining_ok=False,
        )
        processed, failed = optimize_store_image_files(target_dir)
        if not api_key:
            return (
                True,
                f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed} (tip: set GOOGLE_API_KEY to bypass 50-file gdown limit)",
            )
        return True, f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed}"
    except Exception as exc:
        hint = "Set GOOGLE_API_KEY for full Drive API sync support on large folders."
        return (
            False,
            f"{store.store_id}: sync failed ({exc}). {hint}",
        )

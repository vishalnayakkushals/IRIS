from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any


DRIVE_FOLDER_ID_PATTERN = re.compile(r"/folders/([a-zA-Z0-9_-]+)")


@dataclass(frozen=True)
class StoreRecord:
    store_id: str
    store_name: str
    email: str
    drive_folder_url: str
    created_at: str
    updated_at: str


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
        conn.commit()
    finally:
        conn.close()


def upsert_store(
    db_path: Path, store_id: str, store_name: str, email: str, drive_folder_url: str
) -> None:
    init_db(db_path)
    now = _now_utc()
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT store_id FROM stores WHERE email = ? AND store_id != ?", (email, store_id)
        ).fetchone()
        if existing:
            raise ValueError(f"Email '{email}' is already linked to store '{existing[0]}'")

        row = conn.execute("SELECT store_id FROM stores WHERE store_id = ?", (store_id,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO stores (store_id, store_name, email, drive_folder_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (store_id, store_name, email, drive_folder_url, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE stores
                SET store_name = ?, email = ?, drive_folder_url = ?, updated_at = ?
                WHERE store_id = ?
                """,
                (store_name, email, drive_folder_url, now, store_id),
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
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT store_id, store_name, email, drive_folder_url, created_at, updated_at
            FROM stores
            WHERE lower(email) = lower(?)
            """,
            (email,),
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
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", employee_name.strip()).strip("_")
    if not safe_name:
        safe_name = "employee"
    extension = Path(original_filename).suffix.lower() or ".jpg"
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        extension = ".jpg"

    target_dir = employee_assets_root / store_id
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}{extension}"
    target_path = target_dir / filename
    target_path.write_bytes(content)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO employees (store_id, employee_name, image_path, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (store_id, employee_name, str(target_path), _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()

    return target_path


def parse_drive_folder_id(drive_folder_url: str) -> str | None:
    match = DRIVE_FOLDER_ID_PATTERN.search(drive_folder_url)
    if not match:
        return None
    return match.group(1)


def ensure_store_snapshot_dir(data_root: Path, store_id: str) -> Path:
    target = data_root / store_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def sync_store_from_drive(store: StoreRecord, data_root: Path) -> tuple[bool, str]:
    if not store.drive_folder_url.strip():
        return False, f"{store.store_id}: no drive folder URL configured"

    folder_id = parse_drive_folder_id(store.drive_folder_url)
    if folder_id is None:
        return False, f"{store.store_id}: invalid Google Drive folder URL"

    try:
        import gdown  # type: ignore
    except Exception as exc:
        return False, f"{store.store_id}: gdown not available ({exc})"

    target_dir = ensure_store_snapshot_dir(data_root=data_root, store_id=store.store_id)
    try:
        gdown.download_folder(
            url=store.drive_folder_url,
            output=str(target_dir),
            quiet=True,
            remaining_ok=True,
        )
        return True, f"{store.store_id}: synced snapshots into {target_dir}"
    except Exception as exc:
        return False, f"{store.store_id}: sync failed ({exc})"

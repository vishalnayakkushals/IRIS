from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from typing import Any
from uuid import uuid4

from PIL import Image
import requests

DRIVE_FOLDER_ID_PATTERN = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
S3_BUCKET_URL_PATTERN = re.compile(
    r"^https?://(?P<bucket>[a-zA-Z0-9.\-_]+)\.s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com/(?P<prefix>.*)$"
)
S3_PATH_URL_PATTERN = re.compile(
    r"^https?://s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com/(?P<bucket>[a-zA-Z0-9.\-_]+)/(?P<prefix>.*)$"
)
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_PERMISSION_CODES = ("config", "dashboard", "licenses", "roles", "stores", "users")
_SQLITE_TRANSIENT_ERRORS = (
    "disk i/o error",
    "database is locked",
    "database is busy",
)


@dataclass(frozen=True)
class StoreRecord:
    store_id: str
    store_name: str
    email: str
    drive_folder_url: str
    created_at: str
    updated_at: str


from pydantic import BaseModel, Field, field_validator

class CameraConfig(BaseModel):
    store_id: str
    camera_id: str
    camera_role: str = Field(pattern="^(INSIDE|BILLING|BACKROOM|ENTRANCE)$")
    floor_name: str
    location_name: str
    entry_line_x: float = Field(ge=0.0, le=1.0)
    entry_direction: str = Field(pattern="^(OUTSIDE_TO_INSIDE|INSIDE_TO_OUTSIDE)$")
    updated_at: str



@dataclass(frozen=True)
class UserRecord:
    user_id: int
    email: str
    full_name: str
    is_active: int
    store_id: str
    created_at: str


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _sqlite_connect(db_path: Path, timeout: float = 30.0, retries: int = 6) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, max(1, int(retries)) + 1):
        try:
            conn = sqlite3.connect(db_path, timeout=float(timeout))
            conn.execute("PRAGMA busy_timeout=30000")
            return conn
        except sqlite3.OperationalError as exc:
            last_error = exc
            text = str(exc).lower()
            transient = any(token in text for token in _SQLITE_TRANSIENT_ERRORS)
            if transient and attempt < retries:
                time.sleep(0.2 * attempt)
                continue
            break
    free_gb = -1.0
    try:
        free_gb = round(float(shutil.disk_usage(db_path.parent).free) / (1024 ** 3), 2)
    except Exception:
        pass
    raise sqlite3.OperationalError(
        f"SQLite connect failed for '{db_path}' after retries; last_error={last_error!r}; free_disk_gb={free_gb}"
    )


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _pbkdf2_hash(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return dk.hex()


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return f"pbkdf2_sha256${salt}${_pbkdf2_hash(password, salt)}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, salt, digest = password_hash.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        got = _pbkdf2_hash(password, salt)
        return hmac.compare_digest(got, digest)
    except Exception:
        return False


def _optimize_image_bytes(content: bytes, max_dimension: int = 1280, quality: int = 72) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGB")
            image.thumbnail((max_dimension, max_dimension))
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue(), ".jpg"
    except Exception:
        return content, ""


def optimize_store_image_files(store_dir: Path, max_dimension: int = 1280, quality: int = 72) -> tuple[int, int]:
    processed = 0
    failed = 0
    for path in sorted(store_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        try:
            optimized, ext = _optimize_image_bytes(path.read_bytes(), max_dimension=max_dimension, quality=quality)
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


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite_connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stores (
                store_id TEXT PRIMARY KEY,
                store_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                drive_folder_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS store_master (
                store_id TEXT PRIMARY KEY,
                short_code TEXT,
                gofrugal_name TEXT,
                outlet_id TEXT,
                city TEXT,
                state TEXT,
                zone TEXT,
                country TEXT,
                mobile_no TEXT,
                store_email TEXT,
                cluster_manager TEXT,
                area_manager TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS store_sync_state (
                store_id TEXT PRIMARY KEY,
                source_provider TEXT NOT NULL DEFAULT 'none',
                source_uri TEXT NOT NULL DEFAULT '',
                last_status TEXT NOT NULL DEFAULT 'never',
                synced_files INTEGER NOT NULL DEFAULT 0,
                last_message TEXT NOT NULL DEFAULT '',
                last_sync_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS store_source_file_index (
                store_id TEXT NOT NULL,
                source_provider TEXT NOT NULL,
                source_file_id TEXT NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                relative_path TEXT NOT NULL DEFAULT '',
                source_link TEXT NOT NULL DEFAULT '',
                local_path TEXT NOT NULL DEFAULT '',
                file_ext TEXT NOT NULL DEFAULT '',
                local_size_bytes INTEGER NOT NULL DEFAULT 0,
                is_present INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_download_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(store_id, source_provider, source_file_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_file_index_store_provider_present "
            "ON store_source_file_index(store_id, source_provider, is_present)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_employees_store_id ON employees(store_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS camera_configs (
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                camera_role TEXT NOT NULL DEFAULT 'INSIDE',
                floor_name TEXT NOT NULL DEFAULT '',
                location_name TEXT NOT NULL DEFAULT '',
                entry_line_x REAL NOT NULL DEFAULT 0.5,
                entry_direction TEXT NOT NULL DEFAULT 'OUTSIDE_TO_INSIDE',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, camera_id),
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS location_master (
                store_id TEXT NOT NULL,
                floor_name TEXT NOT NULL DEFAULT 'Ground',
                location_name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, floor_name, location_name),
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                store_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                role_id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id INTEGER NOT NULL,
                permission_code TEXT NOT NULL,
                can_read INTEGER NOT NULL DEFAULT 0,
                can_write INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(role_id, permission_code),
                FOREIGN KEY(role_id) REFERENCES roles(role_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY(user_id, role_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(role_id) REFERENCES roles(role_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_store_access (
                user_id INTEGER NOT NULL,
                store_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, store_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                license_type TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(store_id) REFERENCES stores(store_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS license_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id TEXT NOT NULL,
                old_status TEXT NOT NULL,
                new_status TEXT NOT NULL,
                actor_email TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(license_id) REFERENCES licenses(license_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                target TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                UNIQUE(store_id, channel, target)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                routed_to TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_email TEXT NOT NULL,
                action_code TEXT NOT NULL,
                store_id TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_versions (
                model_id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                version_tag TEXT NOT NULL,
                metrics_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                artifact_path TEXT NOT NULL DEFAULT '',
                rollback_target_model_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(model_name, version_tag)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qa_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                capture_date TEXT NOT NULL,
                filename TEXT NOT NULL,
                camera_id TEXT NOT NULL DEFAULT '',
                track_id TEXT NOT NULL DEFAULT '',
                predicted_label TEXT NOT NULL DEFAULT '',
                corrected_label TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.8,
                model_version TEXT NOT NULL DEFAULT '',
                drive_link TEXT NOT NULL DEFAULT '',
                needs_review INTEGER NOT NULL DEFAULT 0,
                review_status TEXT NOT NULL DEFAULT 'pending',
                comment TEXT NOT NULL DEFAULT '',
                actor_email TEXT NOT NULL,
                reviewer_email TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qa_false_positive_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL DEFAULT '',
                box_json TEXT NOT NULL DEFAULT '[]',
                hash64 TEXT NOT NULL DEFAULT '',
                hash_size INTEGER NOT NULL DEFAULT 64,
                hamming_threshold INTEGER NOT NULL DEFAULT 10,
                source_feedback_id INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fp_sig_store_camera_active "
            "ON qa_false_positive_signatures(store_id, camera_id, is_active)"
        )
        if "is_active" not in _table_columns(conn, "employees"):
            conn.execute("ALTER TABLE employees ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "updated_at" not in _table_columns(conn, "employees"):
            conn.execute("ALTER TABLE employees ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE employees SET updated_at = created_at WHERE updated_at = ''")
        if "floor_name" not in _table_columns(conn, "camera_configs"):
            conn.execute("ALTER TABLE camera_configs ADD COLUMN floor_name TEXT NOT NULL DEFAULT ''")
        if "location_name" not in _table_columns(conn, "camera_configs"):
            conn.execute("ALTER TABLE camera_configs ADD COLUMN location_name TEXT NOT NULL DEFAULT ''")
        qa_feedback_cols = _table_columns(conn, "qa_feedback")
        if "model_version" not in qa_feedback_cols:
            conn.execute("ALTER TABLE qa_feedback ADD COLUMN model_version TEXT NOT NULL DEFAULT ''")
        if "drive_link" not in qa_feedback_cols:
            conn.execute("ALTER TABLE qa_feedback ADD COLUMN drive_link TEXT NOT NULL DEFAULT ''")
        _seed_defaults(conn)
        for commit_attempt in range(1, 8):
            try:
                conn.commit()
                break
            except sqlite3.OperationalError as exc:
                text = str(exc).lower()
                transient = any(token in text for token in _SQLITE_TRANSIENT_ERRORS)
                if transient and commit_attempt < 7:
                    time.sleep(0.2 * commit_attempt)
                    continue
                raise
    finally:
        conn.close()


def _seed_defaults(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('admin','Full access')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('store_user','Store-level operations')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('management_viewer','Read-only analytics')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('cluster_manager','Cluster-level store dashboard access')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('area_manager','Area-level store dashboard access')")
    perms = {
        "admin": [("dashboard",1,1),("config",1,1),("stores",1,1),("users",1,1),("roles",1,1),("licenses",1,1)],
        "store_user": [("dashboard",1,1),("config",1,0),("stores",1,0),("users",1,0),("roles",0,0),("licenses",1,1)],
        "management_viewer": [("dashboard",1,0),("config",1,0),("stores",1,0),("users",0,0),("roles",0,0),("licenses",1,0)],
        "cluster_manager": [("dashboard",1,0),("stores",1,0),("licenses",1,0)],
        "area_manager": [("dashboard",1,0),("stores",1,0),("licenses",1,0)],
    }
    for role_name, rows in perms.items():
        role_id = conn.execute("SELECT role_id FROM roles WHERE role_name=?", (role_name,)).fetchone()[0]
        for code,r,w in rows:
            conn.execute("INSERT OR IGNORE INTO role_permissions(role_id, permission_code, can_read, can_write) VALUES(?,?,?,?)",(role_id,code,r,w))


def create_user(db_path: Path, email: str, full_name: str, password: str, store_id: str = "", role_names: list[str] | None = None) -> int:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        normalized_roles = [r.strip().lower() for r in (role_names or ["store_user"]) if r.strip()]
        if not normalized_roles:
            normalized_roles = ["store_user"]
        role_ids: list[int] = []
        for role in normalized_roles:
            row = conn.execute("SELECT role_id FROM roles WHERE role_name=?", (role,)).fetchone()
            if not row:
                raise ValueError(f"role '{role}' not found")
            role_ids.append(int(row[0]))
        now = _now_utc()
        conn.execute(
            "INSERT INTO users(email, full_name, password_hash, is_active, store_id, created_at) VALUES(?,?,?,?,?,?)",
            (email.strip().lower(), full_name.strip(), _hash_password(password), 1, store_id.strip(), now),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        for role_id in role_ids:
            conn.execute("INSERT OR IGNORE INTO user_roles(user_id, role_id) VALUES(?,?)", (user_id, role_id))
        conn.commit()
        return user_id
    finally:
        conn.close()


def set_user_password(db_path: Path, email: str, new_password: str) -> None:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        conn.execute("UPDATE users SET password_hash=? WHERE lower(email)=lower(?)", (_hash_password(new_password), email.strip()))
        conn.commit()
    finally:
        conn.close()


def authenticate_user(db_path: Path, email: str, password: str) -> UserRecord | None:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute("SELECT user_id,email,full_name,password_hash,is_active,store_id,created_at FROM users WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
        if not row:
            return None
        if int(row[4]) != 1:
            return None
        if not verify_password(password, row[3]):
            return None
        return UserRecord(user_id=int(row[0]), email=row[1], full_name=row[2], is_active=int(row[4]), store_id=row[5], created_at=row[6])
    finally:
        conn.close()


def list_users(db_path: Path) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute("SELECT user_id,email,full_name,is_active,store_id,created_at FROM users ORDER BY email").fetchall()
        out=[]
        for r in rows:
            roles = [x[0] for x in conn.execute("SELECT roles.role_name FROM user_roles JOIN roles ON roles.role_id=user_roles.role_id WHERE user_roles.user_id=? ORDER BY roles.role_name", (r[0],)).fetchall()]
            out.append({"user_id":r[0],"email":r[1],"full_name":r[2],"is_active":r[3],"store_id":r[4],"created_at":r[5],"roles":"|".join(roles)})
        return out
    finally:
        conn.close()


def create_role(db_path: Path, role_name: str, description: str = "") -> None:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        conn.execute("INSERT OR IGNORE INTO roles(role_name,description) VALUES(?,?)", (role_name.strip().lower(), description.strip()))
        conn.commit()
    finally:
        conn.close()


def set_role_permissions(db_path: Path, role_name: str, permissions: list[tuple[str, int, int]]) -> None:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        row=conn.execute("SELECT role_id FROM roles WHERE role_name=?", (role_name.strip().lower(),)).fetchone()
        if not row:
            raise ValueError("role not found")
        rid=int(row[0])
        conn.execute("DELETE FROM role_permissions WHERE role_id=?", (rid,))
        for code,r,w in permissions:
            conn.execute("INSERT INTO role_permissions(role_id, permission_code, can_read, can_write) VALUES(?,?,?,?)", (rid, code, int(r), int(w)))
        conn.commit()
    finally:
        conn.close()


def list_roles(db_path: Path) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        rows=conn.execute("SELECT role_id,role_name,description FROM roles ORDER BY role_name").fetchall()
        out=[]
        for rid,name,desc in rows:
            perms=conn.execute("SELECT permission_code,can_read,can_write FROM role_permissions WHERE role_id=? ORDER BY permission_code",(rid,)).fetchall()
            out.append({"role_name":name,"description":desc,"permissions":"|".join([f"{p[0]}:{p[1]}:{p[2]}" for p in perms])})
        return out
    finally:
        conn.close()


def list_role_names(db_path: Path) -> list[str]:
    return [row["role_name"] for row in list_roles(db_path)]


def list_permission_codes(db_path: Path) -> list[str]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT permission_code FROM role_permissions ORDER BY permission_code"
        ).fetchall()
        dynamic_codes = [str(r[0]).strip().lower() for r in rows if str(r[0]).strip()]
    finally:
        conn.close()
    all_codes = sorted(set(DEFAULT_PERMISSION_CODES).union(dynamic_codes))
    return all_codes


def delete_role(db_path: Path, role_name: str) -> tuple[bool, str]:
    init_db(db_path)
    normalized_role = role_name.strip().lower()
    if not normalized_role:
        raise ValueError("role_name is required")
    if normalized_role == "admin":
        return False, "admin role is protected and cannot be deleted"
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT role_id FROM roles WHERE role_name=?",
            (normalized_role,),
        ).fetchone()
        if not row:
            return False, f"role '{normalized_role}' not found"
        role_id = int(row[0])
        assigned_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM user_roles WHERE role_id=?",
                (role_id,),
            ).fetchone()[0]
        )
        if assigned_count > 0:
            return False, f"role '{normalized_role}' is assigned to {assigned_count} user(s)"
        conn.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
        conn.execute("DELETE FROM user_roles WHERE role_id=?", (role_id,))
        conn.execute("DELETE FROM roles WHERE role_id=?", (role_id,))
        conn.commit()
        return True, f"role '{normalized_role}' deleted"
    finally:
        conn.close()


def user_permissions(db_path: Path, email: str) -> dict[str, dict[str, bool]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        u=conn.execute("SELECT user_id FROM users WHERE lower(email)=lower(?)",(email.strip(),)).fetchone()
        if not u:
            return {}
        rows=conn.execute(
            """
            SELECT permission_code, max(can_read), max(can_write)
            FROM role_permissions rp
            JOIN user_roles ur ON ur.role_id=rp.role_id
            WHERE ur.user_id=?
            GROUP BY permission_code
            """,
            (u[0],),
        ).fetchall()
        return {r[0]: {"read": bool(r[1]), "write": bool(r[2])} for r in rows}
    finally:
        conn.close()


def user_role_names(db_path: Path, email: str) -> list[str]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT roles.role_name
            FROM users
            JOIN user_roles ON user_roles.user_id = users.user_id
            JOIN roles ON roles.role_id = user_roles.role_id
            WHERE lower(users.email)=lower(?)
            ORDER BY roles.role_name
            """,
            (email.strip(),),
        ).fetchall()
        return [str(r[0]) for r in rows]
    finally:
        conn.close()


def upsert_user_account(
    db_path: Path,
    email: str,
    full_name: str,
    role_names: list[str],
    password: str = "ChangeMe123!",
    force_password_reset: bool = False,
    is_active: bool = True,
) -> tuple[int, bool]:
    init_db(db_path)
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    normalized_roles = [r.strip().lower() for r in role_names if r.strip()]
    if not normalized_roles:
        raise ValueError("at least one role is required")
    conn = _sqlite_connect(db_path)
    try:
        role_ids: list[int] = []
        for role_name in normalized_roles:
            role_row = conn.execute(
                "SELECT role_id FROM roles WHERE role_name=?",
                (role_name,),
            ).fetchone()
            if not role_row:
                raise ValueError(f"role '{role_name}' not found")
            role_ids.append(int(role_row[0]))

        user_row = conn.execute(
            "SELECT user_id, full_name FROM users WHERE lower(email)=lower(?)",
            (normalized_email,),
        ).fetchone()
        created = False
        if user_row is None:
            now = _now_utc()
            conn.execute(
                """
                INSERT INTO users(email,full_name,password_hash,is_active,store_id,created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    normalized_email,
                    full_name.strip() or normalized_email.split("@")[0],
                    _hash_password(password),
                    1 if is_active else 0,
                    "",
                    now,
                ),
            )
            user_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            created = True
        else:
            user_id = int(user_row[0])
            updated_name = full_name.strip() or str(user_row[1]).strip()
            conn.execute(
                "UPDATE users SET full_name=?, is_active=? WHERE user_id=?",
                (updated_name, 1 if is_active else 0, user_id),
            )
            if force_password_reset and password.strip():
                conn.execute(
                    "UPDATE users SET password_hash=? WHERE user_id=?",
                    (_hash_password(password), user_id),
                )

        for role_id in role_ids:
            conn.execute(
                "INSERT OR IGNORE INTO user_roles(user_id, role_id) VALUES(?,?)",
                (user_id, role_id),
            )
        conn.commit()
        return user_id, created
    finally:
        conn.close()


def replace_user_store_access(db_path: Path, email: str, store_ids: list[str]) -> None:
    init_db(db_path)
    normalized_email = email.strip().lower()
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT user_id FROM users WHERE lower(email)=lower(?)",
            (normalized_email,),
        ).fetchone()
        if not row:
            raise ValueError(f"user '{normalized_email}' not found")
        user_id = int(row[0])
        normalized_stores = sorted({sid.strip() for sid in store_ids if sid and sid.strip()})
        # Validate stores to avoid invalid mappings.
        if normalized_stores:
            placeholders = ",".join(["?"] * len(normalized_stores))
            valid_rows = conn.execute(
                f"SELECT store_id FROM stores WHERE store_id IN ({placeholders})",
                tuple(normalized_stores),
            ).fetchall()
            valid_store_ids = {str(r[0]) for r in valid_rows}
            missing = [sid for sid in normalized_stores if sid not in valid_store_ids]
            if missing:
                raise ValueError(f"unknown store_id(s): {', '.join(missing)}")

        conn.execute("DELETE FROM user_store_access WHERE user_id=?", (user_id,))
        now = _now_utc()
        for sid in normalized_stores:
            conn.execute(
                "INSERT INTO user_store_access(user_id,store_id,created_at) VALUES(?,?,?)",
                (user_id, sid, now),
            )
        primary_store = normalized_stores[0] if len(normalized_stores) == 1 else ""
        conn.execute(
            "UPDATE users SET store_id=? WHERE user_id=?",
            (primary_store, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_user_store_access(db_path: Path, email: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        base_query = (
            "SELECT users.email, users.full_name, stores.store_id, stores.store_name, usa.created_at "
            "FROM user_store_access usa "
            "JOIN users ON users.user_id = usa.user_id "
            "JOIN stores ON stores.store_id = usa.store_id "
        )
        params: tuple[Any, ...] = ()
        if email and email.strip():
            base_query += "WHERE lower(users.email)=lower(?) "
            params = (email.strip(),)
        base_query += "ORDER BY users.email, stores.store_id"
        rows = conn.execute(base_query, params).fetchall()
        return [
            {
                "email": str(r[0]),
                "full_name": str(r[1]),
                "store_id": str(r[2]),
                "store_name": str(r[3]),
                "mapped_at": str(r[4]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def user_store_scope(db_path: Path, email: str) -> dict[str, Any]:
    init_db(db_path)
    normalized_email = email.strip().lower()
    if not normalized_email:
        return {"restricted": True, "store_ids": [], "roles": []}
    conn = _sqlite_connect(db_path)
    try:
        user_row = conn.execute(
            "SELECT user_id, store_id FROM users WHERE lower(email)=lower(?)",
            (normalized_email,),
        ).fetchone()
        if not user_row:
            return {"restricted": True, "store_ids": [], "roles": []}
        user_id = int(user_row[0])
        direct_store_id = str(user_row[1] or "").strip()
        role_rows = conn.execute(
            """
            SELECT roles.role_name
            FROM user_roles
            JOIN roles ON roles.role_id = user_roles.role_id
            WHERE user_roles.user_id=?
            ORDER BY roles.role_name
            """,
            (user_id,),
        ).fetchall()
        roles = [str(r[0]) for r in role_rows]
        if "admin" in roles:
            return {"restricted": False, "store_ids": [], "roles": roles}
        mapped_rows = conn.execute(
            "SELECT store_id FROM user_store_access WHERE user_id=? ORDER BY store_id",
            (user_id,),
        ).fetchall()
        mapped_stores = {str(r[0]).strip() for r in mapped_rows if str(r[0]).strip()}
        if direct_store_id:
            mapped_stores.add(direct_store_id)
        return {"restricted": True, "store_ids": sorted(mapped_stores), "roles": roles}
    finally:
        conn.close()


def ensure_store_login(
    db_path: Path,
    store_id: str,
    store_email: str,
    store_name: str,
    default_password: str = "ChangeMe123!",
) -> dict[str, Any]:
    sid = store_id.strip()
    semail = store_email.strip().lower()
    sname = store_name.strip() or sid
    if not sid or not semail:
        raise ValueError("store_id and store_email are required")
    _user_id, created = upsert_user_account(
        db_path=db_path,
        email=semail,
        full_name=f"{sname} User",
        role_names=["store_user"],
        password=default_password,
        force_password_reset=False,
        is_active=True,
    )
    replace_user_store_access(db_path=db_path, email=semail, store_ids=[sid])
    return {
        "email": semail,
        "store_id": sid,
        "created": created,
        "default_password": default_password,
    }


def upsert_manager_access(
    db_path: Path,
    manager_type: str,
    email: str,
    full_name: str,
    store_ids: list[str],
    default_password: str = "ChangeMe123!",
    force_password_reset: bool = False,
) -> dict[str, Any]:
    mtype = manager_type.strip().lower()
    if mtype not in {"cluster_manager", "area_manager"}:
        raise ValueError("manager_type must be cluster_manager or area_manager")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email is required")
    _user_id, created = upsert_user_account(
        db_path=db_path,
        email=normalized_email,
        full_name=full_name.strip() or normalized_email.split("@")[0],
        role_names=[mtype],
        password=default_password,
        force_password_reset=force_password_reset,
        is_active=True,
    )
    replace_user_store_access(db_path=db_path, email=normalized_email, store_ids=store_ids)
    return {
        "email": normalized_email,
        "manager_type": mtype,
        "created": created,
        "stores_mapped": len({sid.strip() for sid in store_ids if sid.strip()}),
    }


def bulk_upsert_store_access_rows(
    db_path: Path,
    rows: list[dict[str, Any]],
    default_password: str = "ChangeMe123!",
) -> dict[str, int]:
    summary = {"processed": 0, "created_users": 0, "updated_users": 0, "failed": 0}
    for row in rows:
        manager_type = str(row.get("manager_type", "")).strip().lower()
        email = str(row.get("email", "")).strip().lower()
        full_name = str(row.get("full_name", "")).strip()
        store_ids_raw = str(row.get("store_ids", "")).strip()
        store_ids = [x.strip() for x in store_ids_raw.replace(",", "|").split("|") if x.strip()]
        if manager_type == "store_user":
            store_id = str(row.get("store_id", "")).strip() or (store_ids[0] if store_ids else "")
            try:
                store_row = get_store_master_by_id(db_path=db_path, store_id=store_id) if store_id else None
                store_name = str(store_row.get("gofrugal_name", "")) if store_row else store_id
                result = ensure_store_login(
                    db_path=db_path,
                    store_id=store_id,
                    store_email=email,
                    store_name=store_name,
                    default_password=default_password,
                )
                summary["processed"] += 1
                if bool(result.get("created")):
                    summary["created_users"] += 1
                else:
                    summary["updated_users"] += 1
            except Exception:
                summary["failed"] += 1
            continue
        try:
            result = upsert_manager_access(
                db_path=db_path,
                manager_type=manager_type,
                email=email,
                full_name=full_name,
                store_ids=store_ids,
                default_password=default_password,
                force_password_reset=False,
            )
            summary["processed"] += 1
            if bool(result.get("created")):
                summary["created_users"] += 1
            else:
                summary["updated_users"] += 1
        except Exception:
            summary["failed"] += 1
    return summary


def ensure_default_admins(
    db_path: Path,
    admin_emails: list[str],
    default_password: str = "ChangeMe123!",
) -> None:
    pwd = (default_password or "ChangeMe123!").strip() or "ChangeMe123!"
    for email in admin_emails:
        try:
            create_user(db_path, email=email, full_name=email.split("@")[0], password=pwd, role_names=["admin"])
        except Exception:
            pass


def create_user_session(db_path: Path, email: str, ttl_days: int = 14) -> str:
    init_db(db_path)
    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    expires_at = (now + timedelta(days=max(1, ttl_days))).isoformat()
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user_sessions(token,email,expires_at,created_at) VALUES(?,?,?,?)",
            (token, normalized_email, expires_at, now.isoformat()),
        )
        conn.execute(
            "DELETE FROM user_sessions WHERE datetime(expires_at) < datetime('now')"
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_user_by_session_token(db_path: Path, token: str) -> UserRecord | None:
    init_db(db_path)
    tok = token.strip()
    if not tok:
        return None
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT email, expires_at FROM user_sessions WHERE token=?",
            (tok,),
        ).fetchone()
        if not row:
            return None
        email = str(row[0]).strip().lower()
        expires_at = datetime.fromisoformat(str(row[1]))
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            conn.execute("DELETE FROM user_sessions WHERE token=?", (tok,))
            conn.commit()
            return None
        user_row = conn.execute(
            """
            SELECT user_id,email,full_name,is_active,store_id,created_at
            FROM users
            WHERE lower(email)=lower(?)
            """,
            (email,),
        ).fetchone()
        if not user_row or int(user_row[3]) != 1:
            return None
        return UserRecord(
            user_id=int(user_row[0]),
            email=str(user_row[1]),
            full_name=str(user_row[2]),
            is_active=int(user_row[3]),
            store_id=str(user_row[4]),
            created_at=str(user_row[5]),
        )
    finally:
        conn.close()


def revoke_user_session(db_path: Path, token: str) -> None:
    init_db(db_path)
    tok = token.strip()
    if not tok:
        return
    conn = _sqlite_connect(db_path)
    try:
        conn.execute("DELETE FROM user_sessions WHERE token=?", (tok,))
        conn.commit()
    finally:
        conn.close()


def get_app_settings(db_path: Path) -> dict[str, str]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT setting_key, setting_value FROM app_settings ORDER BY setting_key"
        ).fetchall()
        return {str(k): str(v) for k, v in rows}
    finally:
        conn.close()


def upsert_app_settings(db_path: Path, settings: dict[str, str]) -> None:
    init_db(db_path)
    now = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        for key, value in settings.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            conn.execute(
                """
                INSERT INTO app_settings(setting_key, setting_value, updated_at)
                VALUES(?,?,?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value=excluded.setting_value,
                    updated_at=excluded.updated_at
                """,
                (normalized_key, str(value).strip(), now),
            )
        conn.commit()
    finally:
        conn.close()


def add_qa_feedback(
    db_path: Path,
    store_id: str,
    capture_date: str,
    filename: str,
    camera_id: str,
    track_id: str,
    predicted_label: str,
    corrected_label: str,
    confidence: float,
    needs_review: bool,
    actor_email: str,
    model_version: str = "",
    drive_link: str = "",
    comment: str = "",
    review_status: str = "pending",
    reviewer_email: str = "",
) -> int:
    init_db(db_path)
    now = _now_utc()
    status = str(review_status or "pending").strip().lower()
    if status not in {"pending", "confirmed", "rejected"}:
        raise ValueError("review_status must be pending, confirmed, or rejected")
    normalized_reviewer = str(reviewer_email or "").strip().lower()
    if status != "pending" and not normalized_reviewer:
        normalized_reviewer = actor_email.strip().lower()
    reviewed_at = now if status in {"confirmed", "rejected"} else ""
    needs_review_value = 1 if bool(needs_review) else 0
    if status != "pending":
        needs_review_value = 0
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO qa_feedback(
                store_id,capture_date,filename,camera_id,track_id,predicted_label,corrected_label,
                confidence,model_version,drive_link,needs_review,review_status,comment,
                actor_email,reviewer_email,created_at,reviewed_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                store_id.strip(),
                capture_date.strip(),
                filename.strip(),
                camera_id.strip(),
                track_id.strip(),
                predicted_label.strip().lower(),
                corrected_label.strip().lower(),
                float(confidence),
                model_version.strip(),
                drive_link.strip(),
                int(needs_review_value),
                status,
                comment.strip(),
                actor_email.strip().lower(),
                normalized_reviewer,
                now,
                reviewed_at,
            ),
        )
        feedback_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
        return feedback_id
    finally:
        conn.close()


def list_qa_feedback(
    db_path: Path,
    store_id: str | None = None,
    review_status: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        query = (
            "SELECT id,store_id,capture_date,filename,camera_id,track_id,predicted_label,corrected_label,"
            "confidence,model_version,drive_link,needs_review,review_status,comment,"
            "actor_email,reviewer_email,created_at,reviewed_at "
            "FROM qa_feedback"
        )
        where: list[str] = []
        params: list[Any] = []
        if store_id and store_id.strip():
            where.append("store_id=?")
            params.append(store_id.strip())
        if review_status and review_status.strip():
            where.append("lower(review_status)=lower(?)")
            params.append(review_status.strip())
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(query, tuple(params)).fetchall()
        cols = [
            "id",
            "store_id",
            "capture_date",
            "filename",
            "camera_id",
            "track_id",
            "predicted_label",
            "corrected_label",
            "confidence",
            "model_version",
            "drive_link",
            "needs_review",
            "review_status",
            "comment",
            "actor_email",
            "reviewer_email",
            "created_at",
            "reviewed_at",
        ]
        out = [dict(zip(cols, r)) for r in rows]
        for row in out:
            row["needs_review"] = bool(row.get("needs_review"))
        return out
    finally:
        conn.close()


def update_qa_feedback_review(
    db_path: Path,
    feedback_id: int,
    review_status: str,
    reviewer_email: str,
) -> None:
    init_db(db_path)
    status = review_status.strip().lower()
    if status not in {"pending", "confirmed", "rejected"}:
        raise ValueError("review_status must be pending, confirmed, or rejected")
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            UPDATE qa_feedback
            SET review_status=?, reviewer_email=?, reviewed_at=?
            WHERE id=?
            """,
            (status, reviewer_email.strip().lower(), _now_utc(), int(feedback_id)),
        )
        conn.commit()
    finally:
        conn.close()


def update_qa_feedback_entry(
    db_path: Path,
    feedback_id: int,
    corrected_label: str,
    comment: str,
    confidence: float,
    reviewer_email: str,
    review_status: str | None = None,
) -> None:
    init_db(db_path)
    status = str(review_status or "").strip().lower()
    if status and status not in {"pending", "confirmed", "rejected"}:
        raise ValueError("review_status must be pending, confirmed, or rejected")
    reviewed_at = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        if status:
            conn.execute(
                """
                UPDATE qa_feedback
                SET corrected_label=?, comment=?, confidence=?, reviewer_email=?, reviewed_at=?,
                    review_status=?, needs_review=?
                WHERE id=?
                """,
                (
                    corrected_label.strip().lower(),
                    comment.strip(),
                    float(max(0.0, min(1.0, confidence))),
                    reviewer_email.strip().lower(),
                    reviewed_at,
                    status,
                    1 if status == "pending" else 0,
                    int(feedback_id),
                ),
            )
        else:
            conn.execute(
                """
                UPDATE qa_feedback
                SET corrected_label=?, comment=?, confidence=?, reviewer_email=?, reviewed_at=?
                WHERE id=?
                """,
                (
                    corrected_label.strip().lower(),
                    comment.strip(),
                    float(max(0.0, min(1.0, confidence))),
                    reviewer_email.strip().lower(),
                    reviewed_at,
                    int(feedback_id),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def add_false_positive_signature(
    db_path: Path,
    store_id: str,
    camera_id: str,
    box_json: str,
    hash64: str,
    source_feedback_id: int = 0,
    hamming_threshold: int = 10,
) -> int:
    init_db(db_path)
    now = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO qa_false_positive_signatures(
                store_id,camera_id,box_json,hash64,hash_size,hamming_threshold,
                source_feedback_id,is_active,created_at,updated_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                store_id.strip(),
                camera_id.strip(),
                box_json.strip(),
                hash64.strip().lower(),
                64,
                max(1, int(hamming_threshold)),
                max(0, int(source_feedback_id)),
                1,
                now,
                now,
            ),
        )
        row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.commit()
        return row_id
    finally:
        conn.close()


def list_false_positive_signatures(
    db_path: Path,
    store_id: str | None = None,
    camera_id: str | None = None,
    active_only: bool = True,
    limit: int = 100000,
) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        query = (
            "SELECT id,store_id,camera_id,box_json,hash64,hash_size,hamming_threshold,"
            "source_feedback_id,is_active,created_at,updated_at "
            "FROM qa_false_positive_signatures"
        )
        where: list[str] = []
        params: list[Any] = []
        if store_id and store_id.strip():
            where.append("store_id=?")
            params.append(store_id.strip())
        if camera_id and camera_id.strip():
            where.append("camera_id=?")
            params.append(camera_id.strip())
        if active_only:
            where.append("is_active=1")
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = conn.execute(query, tuple(params)).fetchall()
        cols = [
            "id",
            "store_id",
            "camera_id",
            "box_json",
            "hash64",
            "hash_size",
            "hamming_threshold",
            "source_feedback_id",
            "is_active",
            "created_at",
            "updated_at",
        ]
        out = [dict(zip(cols, r)) for r in rows]
        for row in out:
            row["is_active"] = bool(row.get("is_active"))
        return out
    finally:
        conn.close()


def upsert_store_master_rows(db_path: Path, rows: list[dict[str, str]]) -> int:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        now=_now_utc()
        n=0
        for r in rows:
            sid=r.get("Short code","").strip() or r.get("store_id","").strip()
            if not sid:
                continue
            conn.execute(
                """
                INSERT INTO store_master(store_id, short_code, gofrugal_name, outlet_id, city, state, zone, country, mobile_no, store_email, cluster_manager, area_manager, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(store_id) DO UPDATE SET
                  short_code=excluded.short_code,
                  gofrugal_name=excluded.gofrugal_name,
                  outlet_id=excluded.outlet_id,
                  city=excluded.city,
                  state=excluded.state,
                  zone=excluded.zone,
                  country=excluded.country,
                  mobile_no=excluded.mobile_no,
                  store_email=excluded.store_email,
                  cluster_manager=excluded.cluster_manager,
                  area_manager=excluded.area_manager,
                  updated_at=excluded.updated_at
                """,
                (sid,sid,r.get("GoFrugal Name","").strip(),r.get("Outlet id","").strip(),r.get("City","").strip(),r.get("State","").strip(),r.get("Zone","").strip(),r.get("Country","").strip(),r.get("Mobile no.","").strip(),r.get("Store Email","").strip().lower(),r.get("Cluster Manager","").strip(),r.get("Area Manager","").strip(),now),
            )
            n+=1
        conn.commit()
        return n
    finally:
        conn.close()


def list_store_master(db_path: Path) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        cols=["store_id","short_code","gofrugal_name","outlet_id","city","state","zone","country","mobile_no","store_email","cluster_manager","area_manager","updated_at"]
        rows=conn.execute("SELECT store_id,short_code,gofrugal_name,outlet_id,city,state,zone,country,mobile_no,store_email,cluster_manager,area_manager,updated_at FROM store_master ORDER BY store_id").fetchall()
        return [dict(zip(cols,r)) for r in rows]
    finally:
        conn.close()


def get_store_master_by_id(db_path: Path, store_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    sid = store_id.strip()
    if not sid:
        return None
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT store_id,short_code,gofrugal_name,outlet_id,city,state,zone,country,mobile_no,store_email,cluster_manager,area_manager,updated_at
            FROM store_master
            WHERE store_id=?
            """,
            (sid,),
        ).fetchone()
        if not row:
            return None
        cols = [
            "store_id",
            "short_code",
            "gofrugal_name",
            "outlet_id",
            "city",
            "state",
            "zone",
            "country",
            "mobile_no",
            "store_email",
            "cluster_manager",
            "area_manager",
            "updated_at",
        ]
        return dict(zip(cols, row))
    finally:
        conn.close()


def create_license(db_path: Path, store_id: str, license_type: str, actor_email: str, metadata_json: str = "{}") -> str:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        lid=f"lic_{uuid4().hex[:12]}"
        now=_now_utc()
        conn.execute("INSERT INTO licenses(license_id,store_id,license_type,status,metadata_json,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (lid, store_id.strip(), license_type.strip(), "draft", metadata_json, actor_email.strip().lower(), now, now))
        conn.execute("INSERT INTO license_audit(license_id,old_status,new_status,actor_email,note,created_at) VALUES(?,?,?,?,?,?)", (lid, "none", "draft", actor_email.strip().lower(), "created", now))
        conn.commit()
        return lid
    finally:
        conn.close()


def transition_license(db_path: Path, license_id: str, new_status: str, actor_email: str, note: str = "") -> None:
    allowed={"draft":{"review"},"review":{"approved","rejected"},"approved":{"expired"},"rejected":{"review"},"expired":set()}
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        row=conn.execute("SELECT status FROM licenses WHERE license_id=?", (license_id,)).fetchone()
        if not row:
            raise ValueError("license not found")
        old=row[0]
        ns=new_status.strip().lower()
        if ns not in allowed.get(old, set()):
            raise ValueError(f"invalid transition {old}->{ns}")
        now=_now_utc()
        conn.execute("UPDATE licenses SET status=?, updated_at=? WHERE license_id=?", (ns, now, license_id))
        conn.execute("INSERT INTO license_audit(license_id,old_status,new_status,actor_email,note,created_at) VALUES(?,?,?,?,?,?)", (license_id, old, ns, actor_email.strip().lower(), note.strip(), now))
        conn.commit()
    finally:
        conn.close()


def list_licenses(db_path: Path, store_id: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        if store_id:
            rows=conn.execute("SELECT license_id,store_id,license_type,status,metadata_json,created_by,created_at,updated_at FROM licenses WHERE store_id=? ORDER BY updated_at DESC", (store_id,)).fetchall()
        else:
            rows=conn.execute("SELECT license_id,store_id,license_type,status,metadata_json,created_by,created_at,updated_at FROM licenses ORDER BY updated_at DESC").fetchall()
        cols=["license_id","store_id","license_type","status","metadata_json","created_by","created_at","updated_at"]
        return [dict(zip(cols,r)) for r in rows]
    finally:
        conn.close()


def list_license_audit(db_path: Path, license_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        rows=conn.execute("SELECT license_id,old_status,new_status,actor_email,note,created_at FROM license_audit WHERE license_id=? ORDER BY id", (license_id,)).fetchall()
        cols=["license_id","old_status","new_status","actor_email","note","created_at"]
        return [dict(zip(cols,r)) for r in rows]
    finally:
        conn.close()


def upsert_alert_route(db_path: Path, store_id: str, channel: str, target: str, enabled: bool = True) -> None:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        conn.execute(
            "INSERT INTO alert_routes(store_id,channel,target,enabled,created_at) VALUES(?,?,?,?,?) ON CONFLICT(store_id,channel,target) DO UPDATE SET enabled=excluded.enabled",
            (store_id.strip(), channel.strip().lower(), target.strip(), int(enabled), _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def list_alert_routes(db_path: Path, store_id: str) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        rows=conn.execute("SELECT channel,target,enabled,created_at FROM alert_routes WHERE store_id=? ORDER BY channel,target", (store_id,)).fetchall()
        return [{"channel":r[0],"target":r[1],"enabled":bool(r[2]),"created_at":r[3]} for r in rows]
    finally:
        conn.close()


def route_alert(db_path: Path, store_id: str, alert_type: str, payload_json: str) -> list[str]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    delivered=[]
    try:
        routes=conn.execute("SELECT channel,target FROM alert_routes WHERE store_id=? AND enabled=1", (store_id,)).fetchall()
        now=_now_utc()
        for ch,target in routes:
            delivered.append(f"{ch}:{target}")
            conn.execute("INSERT INTO alert_events(store_id,alert_type,payload_json,routed_to,created_at) VALUES(?,?,?,?,?)", (store_id, alert_type, payload_json, f"{ch}:{target}", now))
        conn.commit()
        return delivered
    finally:
        conn.close()

# Existing functions kept for compatibility

def upsert_store(db_path: Path, store_id: str, store_name: str, email: str, drive_folder_url: str) -> None:
    init_db(db_path)
    sid, sn, em, du = store_id.strip(), store_name.strip(), email.strip().lower(), drive_folder_url.strip()
    if not sid or not sn or not em:
        raise ValueError("store_id, store_name, and email are required")
    now=_now_utc()
    conn=_sqlite_connect(db_path)
    try:
        ex=conn.execute("SELECT store_id FROM stores WHERE lower(email)=lower(?) AND store_id!=?",(em,sid)).fetchone()
        if ex:
            raise ValueError(f"Email '{email}' is already linked to store '{ex[0]}'")
        row=conn.execute("SELECT store_id FROM stores WHERE store_id=?",(sid,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO stores(store_id,store_name,email,drive_folder_url,created_at,updated_at) VALUES(?,?,?,?,?,?)", (sid,sn,em,du,now,now))
        else:
            conn.execute("UPDATE stores SET store_name=?,email=?,drive_folder_url=?,updated_at=? WHERE store_id=?", (sn,em,du,now,sid))
        conn.commit()
    finally:
        conn.close()


def delete_store(db_path: Path, store_id: str) -> None:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        sid = store_id.strip()
        conn.execute("DELETE FROM stores WHERE store_id=?", (sid,))
        conn.execute("DELETE FROM camera_configs WHERE store_id=?", (sid,))
        conn.execute("DELETE FROM location_master WHERE store_id=?", (sid,))
        conn.execute("DELETE FROM employees WHERE store_id=?", (sid,))
        conn.execute("DELETE FROM user_store_access WHERE store_id=?", (sid,))
        conn.commit()
    finally:
        conn.close()


def list_stores(db_path: Path) -> list[StoreRecord]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        rows=conn.execute("SELECT store_id,store_name,email,drive_folder_url,created_at,updated_at FROM stores ORDER BY store_id").fetchall()
        return [StoreRecord(*r) for r in rows]
    finally:
        conn.close()


def _upsert_store_sync_state(
    db_path: Path,
    store_id: str,
    source_provider: str,
    source_uri: str,
    ok: bool,
    synced_files: int,
    message: str,
) -> None:
    init_db(db_path)
    now = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO store_sync_state(
                store_id,source_provider,source_uri,last_status,synced_files,last_message,last_sync_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(store_id) DO UPDATE SET
                source_provider=excluded.source_provider,
                source_uri=excluded.source_uri,
                last_status=excluded.last_status,
                synced_files=excluded.synced_files,
                last_message=excluded.last_message,
                last_sync_at=excluded.last_sync_at,
                updated_at=excluded.updated_at
            """,
            (
                store_id.strip(),
                source_provider.strip(),
                source_uri.strip(),
                "ok" if ok else "failed",
                int(synced_files),
                message.strip(),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_synced_stores(db_path: Path, provider_filter: str | None = "gdrive") -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        query = (
            "SELECT s.store_id,s.store_name,s.email,s.drive_folder_url,s.created_at,s.updated_at,"
            "ss.source_provider,ss.last_status,ss.synced_files,ss.last_message,ss.last_sync_at "
            "FROM stores s JOIN store_sync_state ss ON ss.store_id=s.store_id WHERE ss.last_status='ok'"
        )
        params: list[Any] = []
        if provider_filter:
            query += " AND lower(ss.source_provider)=lower(?)"
            params.append(provider_filter.strip())
        query += " ORDER BY s.store_id"
        rows = conn.execute(query, tuple(params)).fetchall()
        cols = [
            "store_id",
            "store_name",
            "email",
            "source_url",
            "created_at",
            "updated_at",
            "source_provider",
            "last_status",
            "synced_files",
            "last_message",
            "last_sync_at",
        ]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()


def get_store_by_email(db_path: Path, email: str) -> StoreRecord | None:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        row=conn.execute("SELECT store_id,store_name,email,drive_folder_url,created_at,updated_at FROM stores WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
        return StoreRecord(*row) if row else None
    finally:
        conn.close()


def add_employee_image(db_path: Path, employee_assets_root: Path, store_id: str, employee_name: str, filename: str = "", content: bytes = b"", original_filename: str | None = None) -> str:
    init_db(db_path)
    sid, en = store_id.strip(), employee_name.strip()
    if not sid or not en:
        raise ValueError("store_id and employee_name are required")
    source_name = (original_filename or filename or "").strip()
    if not source_name:
        raise ValueError("filename is required")
    ext = Path(source_name).suffix.lower() or ".jpg"
    optimized_content, optimized_ext = _optimize_image_bytes(content)
    if optimized_ext:
        ext = optimized_ext
        content_to_write = optimized_content
    else:
        content_to_write = content
    conn_chk = _sqlite_connect(db_path)
    try:
        exists = conn_chk.execute("SELECT 1 FROM stores WHERE store_id=?", (sid,)).fetchone()
    finally:
        conn_chk.close()
    if not exists:
        raise ValueError(f"store_id '{sid}' is not registered")

    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", en).strip("_") or "employee"
    unique_name = f"{safe_name}_{uuid4().hex[:8]}{ext}"
    store_dir = employee_assets_root / sid
    store_dir.mkdir(parents=True, exist_ok=True)
    image_path = store_dir / unique_name
    image_path.write_bytes(content_to_write)
    conn=_sqlite_connect(db_path)
    try:
        now = _now_utc()
        conn.execute(
            "INSERT INTO employees(store_id,employee_name,image_path,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (sid, en, str(image_path), 1, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return image_path


def list_employees(db_path: Path, store_id: str | None = None, include_inactive: bool = True) -> list[dict[str, Any]]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        query = (
            "SELECT id,store_id,employee_name,image_path,is_active,created_at,updated_at "
            "FROM employees"
        )
        params: list[Any] = []
        where: list[str] = []
        if store_id:
            where.append("store_id=?")
            params.append(store_id.strip())
        if not include_inactive:
            where.append("is_active=1")
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY id DESC"
        rows=conn.execute(query, tuple(params)).fetchall()
        return [
            {
                "id": r[0],
                "store_id": r[1],
                "employee_name": r[2],
                "image_path": r[3],
                "is_active": bool(r[4]),
                "created_at": r[5],
                "updated_at": r[6],
            }
            for r in rows
        ]
    finally:
        conn.close()


def set_employee_active(db_path: Path, employee_id: int, is_active: bool) -> None:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            "UPDATE employees SET is_active=?, updated_at=? WHERE id=?",
            (1 if is_active else 0, _now_utc(), int(employee_id)),
        )
        conn.commit()
    finally:
        conn.close()


def delete_employee(db_path: Path, employee_id: int, delete_file: bool = True) -> bool:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT image_path FROM employees WHERE id=?",
            (int(employee_id),),
        ).fetchone()
        if not row:
            return False
        image_path = Path(str(row[0]))
        conn.execute("DELETE FROM employees WHERE id=?", (int(employee_id),))
        conn.commit()
    finally:
        conn.close()
    if delete_file and image_path.exists():
        try:
            image_path.unlink()
        except Exception:
            pass
    return True


def upsert_camera_config(
    db_path: Path,
    store_id: str,
    camera_id: str,
    camera_role: str = "INSIDE",
    floor_name: str = "",
    location_name: str = "",
    entry_line_x: float = 0.5,
    entry_direction: str = "OUTSIDE_TO_INSIDE",
) -> None:
    init_db(db_path)
    role=(camera_role or "INSIDE").strip().upper() or "INSIDE"
    floor=(floor_name or "").strip()
    location=(location_name or "").strip()
    direction=(entry_direction or "OUTSIDE_TO_INSIDE").strip().upper()
    if direction not in {"OUTSIDE_TO_INSIDE","INSIDE_TO_OUTSIDE"}:
        direction="OUTSIDE_TO_INSIDE"
    x=float(entry_line_x)
    if x<0 or x>1:
        raise ValueError("entry_line_x must be between 0 and 1")
    conn=_sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO camera_configs(store_id,camera_id,camera_role,floor_name,location_name,entry_line_x,entry_direction,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(store_id,camera_id) DO UPDATE SET
              camera_role=excluded.camera_role,
              floor_name=excluded.floor_name,
              location_name=excluded.location_name,
              entry_line_x=excluded.entry_line_x,
              entry_direction=excluded.entry_direction,
              updated_at=excluded.updated_at
            """,
            (store_id.strip(), camera_id.strip().upper(), role, floor, location, x, direction, _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def list_camera_configs(db_path: Path, store_id: str | None = None) -> list[CameraConfig]:
    init_db(db_path)
    conn=_sqlite_connect(db_path)
    try:
        if store_id:
            rows=conn.execute("SELECT store_id,camera_id,camera_role,floor_name,location_name,entry_line_x,entry_direction,updated_at FROM camera_configs WHERE store_id=? ORDER BY camera_id", (store_id,)).fetchall()
        else:
            rows=conn.execute("SELECT store_id,camera_id,camera_role,floor_name,location_name,entry_line_x,entry_direction,updated_at FROM camera_configs ORDER BY store_id,camera_id").fetchall()
        return [
            CameraConfig(
                store_id=r[0],
                camera_id=r[1],
                camera_role=r[2],
                floor_name=r[3],
                location_name=r[4],
                entry_line_x=float(r[5]),
                entry_direction=r[6],
                updated_at=r[7],
            )
            for r in rows
        ]
    finally:
        conn.close()


def _safe_relative_parts(relative_path: str, fallback_name: str) -> list[str]:
    relative_obj = Path(relative_path)
    safe_parts = [p for p in relative_obj.parts if p not in {"", ".", ".."}]
    if safe_parts:
        return safe_parts
    return [Path(str(fallback_name or "image.jpg")).name]


def _drive_item_dest_path(target_dir: Path, item: dict[str, str]) -> tuple[Path, str]:
    relative_path = str(item.get("relative_path", item.get("name", ""))).strip()
    safe_parts = _safe_relative_parts(relative_path=relative_path, fallback_name=str(item.get("name", "image.jpg")))
    rel = str(Path(*safe_parts)).replace("\\", "/")
    return target_dir.joinpath(*safe_parts), rel


def _list_indexed_source_file_ids(db_path: Path, store_id: str, source_provider: str) -> set[str]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT source_file_id
            FROM store_source_file_index
            WHERE store_id=? AND source_provider=? AND is_present=1
            """,
            (store_id.strip(), source_provider.strip()),
        ).fetchall()
        return {str(row[0]) for row in rows if str(row[0]).strip()}
    finally:
        conn.close()


def _upsert_source_index_rows(
    db_path: Path,
    rows: list[tuple[str, str, str, str, str, str, str, str, int, int, str, str, str]],
) -> None:
    if not rows:
        return
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO store_source_file_index(
                store_id,source_provider,source_file_id,source_name,relative_path,source_link,
                local_path,file_ext,local_size_bytes,is_present,first_seen_at,last_seen_at,last_download_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(store_id,source_provider,source_file_id) DO UPDATE SET
                source_name=excluded.source_name,
                relative_path=excluded.relative_path,
                source_link=excluded.source_link,
                local_path=excluded.local_path,
                file_ext=excluded.file_ext,
                local_size_bytes=excluded.local_size_bytes,
                is_present=excluded.is_present,
                last_seen_at=excluded.last_seen_at,
                last_download_at=CASE
                    WHEN excluded.last_download_at<>'' THEN excluded.last_download_at
                    ELSE store_source_file_index.last_download_at
                END
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def camera_config_map(db_path: Path) -> dict[str, dict[str, CameraConfig]]:
    out: dict[str, dict[str, CameraConfig]] = {}
    for cfg in list_camera_configs(db_path=db_path):
        out.setdefault(cfg.store_id, {})[cfg.camera_id] = cfg
    return out


def upsert_location_master(
    db_path: Path,
    store_id: str,
    location_name: str,
    floor_name: str = "Ground",
) -> None:
    init_db(db_path)
    sid = store_id.strip()
    lname = location_name.strip()
    fname = floor_name.strip() or "Ground"
    if not sid or not lname:
        raise ValueError("store_id and location_name are required")
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO location_master(store_id, floor_name, location_name, updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(store_id, floor_name, location_name) DO UPDATE SET
              updated_at=excluded.updated_at
            """,
            (sid, fname, lname, _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_location_master(
    db_path: Path,
    store_id: str,
    location_name: str,
    floor_name: str = "Ground",
) -> bool:
    init_db(db_path)
    sid = store_id.strip()
    lname = location_name.strip()
    fname = floor_name.strip() or "Ground"
    conn = _sqlite_connect(db_path)
    try:
        before = conn.total_changes
        conn.execute(
            "DELETE FROM location_master WHERE store_id=? AND floor_name=? AND location_name=?",
            (sid, fname, lname),
        )
        conn.commit()
        return conn.total_changes > before
    finally:
        conn.close()


def list_location_master(db_path: Path, store_id: str | None = None) -> list[dict[str, str]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        if store_id:
            rows = conn.execute(
                "SELECT store_id,floor_name,location_name,updated_at FROM location_master WHERE store_id=? ORDER BY floor_name,location_name",
                (store_id.strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT store_id,floor_name,location_name,updated_at FROM location_master ORDER BY store_id,floor_name,location_name"
            ).fetchall()
        out: list[dict[str, str]] = []
        for row in rows:
            out.append(
                {
                    "store_id": str(row[0]),
                    "floor_name": str(row[1]),
                    "location_name": str(row[2]),
                    "updated_at": str(row[3]),
                }
            )
        return out
    finally:
        conn.close()


def parse_drive_folder_id(drive_folder_url: str) -> str | None:
    m=DRIVE_FOLDER_ID_PATTERN.search(drive_folder_url)
    return m.group(1) if m else None


def parse_s3_location(source_uri: str) -> tuple[str, str] | None:
    text = (source_uri or "").strip()
    if not text:
        return None
    if text.lower().startswith("s3://"):
        parsed = re.match(r"^s3://([^/]+)/?(.*)$", text)
        if not parsed:
            return None
        return str(parsed.group(1)).strip(), str(parsed.group(2)).strip().lstrip("/")
    m = S3_BUCKET_URL_PATTERN.match(text)
    if m:
        return m.group("bucket"), m.group("prefix").lstrip("/")
    m = S3_PATH_URL_PATTERN.match(text)
    if m:
        return m.group("bucket"), m.group("prefix").lstrip("/")
    return None


def _normalize_local_source(source_uri: str) -> Path:
    text = (source_uri or "").strip()
    if text.lower().startswith("file://"):
        text = text[7:]
    return Path(text).expanduser()


def detect_source_provider(source_uri: str) -> str:
    text = (source_uri or "").strip()
    if not text:
        return "none"
    if parse_drive_folder_id(text):
        return "gdrive"
    if parse_s3_location(text):
        return "s3"
    p = _normalize_local_source(text)
    if p.exists():
        return "local"
    return "unknown"


def ensure_store_snapshot_dir(data_root: Path, store_id: str) -> Path:
    target = data_root / store_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _requests_get_with_retry(
    url: str,
    *,
    params: dict[str, str],
    timeout: int = 30,
    max_attempts: int = 5,
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= max_attempts:
                raise
            time.sleep(min(8.0, 1.25 * attempt))
    raise RuntimeError(f"HTTP GET retry failed for {url}: {last_exc}")


def _drive_api_list_files_recursive(folder_id: str, api_key: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    stack: list[tuple[str, list[str]]] = [(folder_id, [])]
    while stack:
        cur, rel_parts = stack.pop()
        token = None
        while True:
            params={
                "q":f"'{cur}' in parents and trashed = false",
                "fields":"nextPageToken,files(id,name,mimeType)",
                "pageSize":1000,
                "supportsAllDrives":"true",
                "includeItemsFromAllDrives":"true",
                "key":api_key,
            }
            if token: params["pageToken"]=token
            resp = _requests_get_with_retry(
                "https://www.googleapis.com/drive/v3/files",
                params=params,
                timeout=30,
            )
            try:
                payload=resp.json()
            except (JSONDecodeError, ValueError) as exc:
                snippet = (resp.text or "")[:180].replace("\n", " ")
                raise RuntimeError(
                    "Drive API returned a non-JSON response. "
                    "Check GOOGLE_API_KEY validity, API quota, and folder sharing. "
                    f"response_snippet='{snippet}'"
                ) from exc
            for item in payload.get("files", []):
                item_name = str(item.get("name", item.get("id", ""))).strip()
                if not item_name:
                    continue
                if item.get("mimeType","")=="application/vnd.google-apps.folder":
                    stack.append((item["id"], rel_parts + [item_name]))
                elif Path(item.get("name", "")).suffix.lower() in _IMAGE_EXTS:
                    rel_path = Path(*rel_parts) / item_name if rel_parts else Path(item_name)
                    files.append(
                        {
                            "id": str(item["id"]),
                            "name": item_name,
                            "relative_path": str(rel_path).replace("\\", "/"),
                            "drive_web_link": f"https://drive.google.com/file/d/{item['id']}/view",
                        }
                    )
            token=payload.get("nextPageToken")
            if not token: break
    return files


def _drive_api_download_files(file_items: list[dict[str, str]], target_dir: Path, api_key: str) -> tuple[int, list[dict[str, str]]]:
    n = 0
    manifest_rows: list[dict[str, str]] = []
    media_blocked = False
    for item in file_items:
        dest, rel = _drive_item_dest_path(target_dir=target_dir, item=item)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            continue

        file_id = str(item.get("id", "")).strip()
        if not file_id:
            continue

        payload: bytes | None = None
        name = Path(str(item.get("name", "image.jpg"))).name

        if not media_blocked:
            try:
                resp = _requests_get_with_retry(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    params={"alt": "media", "key": api_key},
                    timeout=30,
                    max_attempts=4,
                )
                headers = getattr(resp, "headers", {}) or {}
                ctype = (headers.get("content-type") or "").lower()
                if resp.status_code == 200 and "text/html" not in ctype:
                    payload = resp.content
                elif (
                    resp.status_code in {403, 429}
                    and "automated queries" in str(getattr(resp, "text", "")).lower()
                ):
                    # Corporate/shared networks can trigger this block. Fall back to uc download.
                    media_blocked = True
            except requests.RequestException:
                pass

        if payload is None:
            try:
                fallback = _requests_get_with_retry(
                    "https://drive.google.com/uc",
                    params={"id": file_id, "export": "download"},
                    timeout=30,
                    max_attempts=4,
                )
                fallback_headers = getattr(fallback, "headers", {}) or {}
                fallback_type = (fallback_headers.get("content-type") or "").lower()
                if fallback.status_code == 200 and (
                    "image/" in fallback_type or Path(name).suffix.lower() in _IMAGE_EXTS
                ):
                    payload = fallback.content
            except requests.RequestException:
                pass

        if payload is None:
            continue

        try:
            dest.write_bytes(payload)
        except OSError:
            continue
        n += 1
        manifest_rows.append(
            {
                "file_id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "relative_path": rel,
                "drive_web_link": str(item.get("drive_web_link", "")),
                "local_path": str(dest),
            }
        )
    return n, manifest_rows


def _sync_store_from_drive_api(
    store: StoreRecord,
    target_dir: Path,
    api_key: str,
    db_path: Path | None = None,
) -> tuple[bool, str]:
    folder_id=parse_drive_folder_id(store.drive_folder_url)
    if not folder_id:
        return False, f"{store.store_id}: invalid Google Drive folder URL"
    try:
        items=_drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
        if not items:
            return False, f"{store.store_id}: no files found via Drive API"
        known_ids = (
            _list_indexed_source_file_ids(db_path=db_path, store_id=store.store_id, source_provider="gdrive")
            if db_path is not None
            else set()
        )
        pending_items: list[dict[str, str]] = []
        reused = 0
        for item in items:
            source_file_id = str(item.get("id", "")).strip()
            dest, _ = _drive_item_dest_path(target_dir=target_dir, item=item)
            if dest.exists() and dest.stat().st_size > 0 and (not source_file_id or source_file_id in known_ids):
                reused += 1
                continue
            if dest.exists() and dest.stat().st_size > 0:
                reused += 1
                continue
            pending_items.append(item)

        downloaded, manifest_rows = _drive_api_download_files(pending_items, target_dir=target_dir, api_key=api_key)
        downloaded_ids = {str(row.get("file_id", "")).strip() for row in manifest_rows if str(row.get("file_id", "")).strip()}
        if db_path is not None:
            now = _now_utc()
            index_rows: list[tuple[str, str, str, str, str, str, str, str, int, int, str, str, str]] = []
            for item in items:
                source_file_id = str(item.get("id", "")).strip()
                if not source_file_id:
                    continue
                dest, rel = _drive_item_dest_path(target_dir=target_dir, item=item)
                exists = dest.exists() and dest.stat().st_size > 0
                size = int(dest.stat().st_size) if exists else 0
                index_rows.append(
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
            _upsert_source_index_rows(db_path=db_path, rows=index_rows)
        if manifest_rows:
            manifest_path = target_dir / "_drive_manifest.csv"
            with manifest_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["file_id", "name", "relative_path", "drive_web_link", "local_path"],
                )
                writer.writeheader()
                writer.writerows(manifest_rows)
        if downloaded > 0:
            processed,failed=optimize_store_image_files(target_dir)
        else:
            processed, failed = 0, 0
        return True, (
            f"{store.store_id}: api_sync listed={len(items)} reused={reused} "
            f"downloaded={downloaded} optimized={processed} failed={failed} dir={target_dir}"
        )
    except Exception as exc:
        return False, f"{store.store_id}: Drive API sync failed ({exc})"


def _sync_store_from_s3_uri(store: StoreRecord, target_dir: Path) -> tuple[bool, str, int]:
    parsed = parse_s3_location(store.drive_folder_url)
    if parsed is None:
        return False, f"{store.store_id}: invalid S3 source URL", 0
    bucket, prefix = parsed
    try:
        import boto3  # type: ignore
    except Exception as exc:
        return False, f"{store.store_id}: boto3 not available ({exc})", 0

    try:
        client = boto3.client("s3")
        paginator = client.get_paginator("list_objects_v2")
        downloaded = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", "")).strip()
                if not key or key.endswith("/"):
                    continue
                if Path(key).suffix.lower() not in _IMAGE_EXTS:
                    continue
                rel = key[len(prefix):].lstrip("/") if prefix and key.startswith(prefix) else Path(key).name
                dest = target_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(dest))
                downloaded += 1
        processed, failed = optimize_store_image_files(target_dir)
        return True, (
            f"{store.store_id}: s3_sync bucket={bucket} downloaded={downloaded} "
            f"optimized={processed} failed={failed} dir={target_dir}"
        ), downloaded
    except Exception as exc:
        return False, f"{store.store_id}: S3 sync failed ({exc})", 0


def _sync_store_from_local_path(store: StoreRecord, target_dir: Path) -> tuple[bool, str, int]:
    source = _normalize_local_source(store.drive_folder_url)
    if not source.exists():
        return False, f"{store.store_id}: local source not found ({source})", 0
    downloaded = 0
    for path in source.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
            continue
        rel = path.relative_to(source)
        dest = target_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        downloaded += 1
    processed, failed = optimize_store_image_files(target_dir)
    return True, (
        f"{store.store_id}: local_sync copied={downloaded} "
        f"optimized={processed} failed={failed} dir={target_dir}"
    ), downloaded


def sync_store_from_source(store: StoreRecord, data_root: Path, db_path: Path | None = None) -> tuple[bool, str]:
    source_uri = (store.drive_folder_url or "").strip()
    provider = detect_source_provider(source_uri)
    target_dir = ensure_store_snapshot_dir(data_root=data_root, store_id=store.store_id)
    ok = False
    msg = f"{store.store_id}: no source URL configured"
    synced_files = 0

    if provider == "gdrive":
        api_key=os.getenv("GOOGLE_API_KEY","").strip()
        if api_key:
            ok,msg=_sync_store_from_drive_api(store=store, target_dir=target_dir, api_key=api_key, db_path=db_path)
            if ok:
                synced_files = len([p for p in target_dir.rglob("*") if p.is_file() and p.suffix.lower() in _IMAGE_EXTS])
        if not ok:
            try:
                import gdown  # type: ignore
            except Exception as exc:
                msg = f"{store.store_id}: gdown not available ({exc})"
            else:
                try:
                    gdown.download_folder(url=store.drive_folder_url, output=str(target_dir), quiet=True, remaining_ok=True)
                    processed,failed=optimize_store_image_files(target_dir)
                    synced_files = len([p for p in target_dir.rglob("*") if p.is_file() and p.suffix.lower() in _IMAGE_EXTS])
                    ok = True
                    if not api_key:
                        msg = (
                            f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed} "
                            "(tip: set GOOGLE_API_KEY to bypass 50-file gdown limit)"
                        )
                    else:
                        msg = f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed}"
                except Exception as exc:
                    error_text = str(exc)
                    if "Expecting value" in error_text:
                        msg = (
                            f"{store.store_id}: sync failed because Drive returned non-JSON content. "
                            "Please ensure folder is shared as 'Anyone with the link (Viewer)' and "
                            "configure GOOGLE_API_KEY for reliable Drive API sync."
                        )
                    else:
                        msg = (
                            f"{store.store_id}: sync failed ({exc}). "
                            "Set GOOGLE_API_KEY for full Drive API sync support on large folders."
                        )
    elif provider == "s3":
        ok, msg, synced_files = _sync_store_from_s3_uri(store=store, target_dir=target_dir)
    elif provider == "local":
        ok, msg, synced_files = _sync_store_from_local_path(store=store, target_dir=target_dir)
    elif provider == "none":
        msg = f"{store.store_id}: no source URL configured"
    else:
        msg = (
            f"{store.store_id}: unsupported source URL. "
            "Supported: Google Drive folder URL, s3://bucket/prefix (or S3 HTTPS), local folder path."
        )

    if db_path is not None:
        _upsert_store_sync_state(
            db_path=db_path,
            store_id=store.store_id,
            source_provider=provider,
            source_uri=source_uri,
            ok=ok,
            synced_files=synced_files,
            message=msg,
        )
    return ok, msg


def sync_store_from_drive(store: StoreRecord, data_root: Path, db_path: Path | None = None) -> tuple[bool, str]:
    # Backward-compatible name. Supports Google Drive + AWS S3 + local path sources.
    return sync_store_from_source(store=store, data_root=data_root, db_path=db_path)


def log_user_activity(db_path: Path, actor_email: str, action_code: str, store_id: str = "", payload_json: str = "{}") -> None:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user_activity(actor_email, action_code, store_id, payload_json, created_at) VALUES(?,?,?,?,?)",
            (actor_email.strip().lower(), action_code.strip(), store_id.strip(), payload_json, _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def list_user_activity(db_path: Path, actor_email: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        if actor_email:
            rows = conn.execute(
                "SELECT actor_email,action_code,store_id,payload_json,created_at FROM user_activity WHERE lower(actor_email)=lower(?) ORDER BY id DESC LIMIT ?",
                (actor_email.strip(), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT actor_email,action_code,store_id,payload_json,created_at FROM user_activity ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        cols=["actor_email","action_code","store_id","payload_json","created_at"]
        return [dict(zip(cols,r)) for r in rows]
    finally:
        conn.close()


def register_model_version(
    db_path: Path,
    model_name: str,
    version_tag: str,
    metrics_json: str,
    artifact_path: str,
    status: str = "candidate",
    rollback_target_model_id: str = "",
) -> str:
    init_db(db_path)
    model_id = f"mdl_{uuid4().hex[:12]}"
    now = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO model_versions(model_id,model_name,version_tag,metrics_json,status,artifact_path,rollback_target_model_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                model_id,
                model_name.strip(),
                version_tag.strip(),
                metrics_json,
                status.strip(),
                artifact_path.strip(),
                rollback_target_model_id.strip(),
                now,
                now,
            ),
        )
        conn.commit()
        return model_id
    finally:
        conn.close()


def promote_model_version(db_path: Path, model_name: str, model_id: str) -> None:
    init_db(db_path)
    now = _now_utc()
    conn = _sqlite_connect(db_path)
    try:
        conn.execute(
            "UPDATE model_versions SET status='archived', updated_at=? WHERE model_name=? AND status='active'",
            (now, model_name.strip()),
        )
        conn.execute(
            "UPDATE model_versions SET status='active', updated_at=? WHERE model_id=?",
            (now, model_id.strip()),
        )
        conn.commit()
    finally:
        conn.close()


def maybe_auto_rollback_model(
    db_path: Path,
    model_name: str,
    max_error_rate: float = 0.35,
) -> tuple[bool, str]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT model_id,metrics_json,rollback_target_model_id FROM model_versions WHERE model_name=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
            (model_name.strip(),),
        ).fetchone()
        if not row:
            return False, "no active model"
        model_id, metrics_json, rollback_target = row
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            metrics = {}
        error_rate = float(metrics.get("error_rate", 0.0))
        if error_rate <= max_error_rate:
            return False, f"active model healthy ({error_rate:.3f})"
        if rollback_target:
            promote_model_version(db_path, model_name, rollback_target)
            return True, f"rolled back from {model_id} to {rollback_target}"
        return False, "rollback target not configured"
    finally:
        conn.close()


def list_model_versions(db_path: Path, model_name: str | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    conn = _sqlite_connect(db_path)
    try:
        if model_name:
            rows = conn.execute(
                "SELECT model_id,model_name,version_tag,metrics_json,status,artifact_path,rollback_target_model_id,created_at,updated_at FROM model_versions WHERE model_name=? ORDER BY updated_at DESC",
                (model_name.strip(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT model_id,model_name,version_tag,metrics_json,status,artifact_path,rollback_target_model_id,created_at,updated_at FROM model_versions ORDER BY updated_at DESC"
            ).fetchall()
        cols = [
            "model_id",
            "model_name",
            "version_tag",
            "metrics_json",
            "status",
            "artifact_path",
            "rollback_target_model_id",
            "created_at",
            "updated_at",
        ]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()

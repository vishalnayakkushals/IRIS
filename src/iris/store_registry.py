from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from pathlib import Path
import hashlib
import hmac
import io
import json
import os
import re
import secrets
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
    location_name: str
    entry_line_x: float
    entry_direction: str
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
    for path in sorted(store_dir.iterdir()):
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
    conn = sqlite3.connect(db_path)
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
                location_name TEXT NOT NULL DEFAULT '',
                entry_line_x REAL NOT NULL DEFAULT 0.5,
                entry_direction TEXT NOT NULL DEFAULT 'OUTSIDE_TO_INSIDE',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, camera_id),
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
        if "is_active" not in _table_columns(conn, "employees"):
            conn.execute("ALTER TABLE employees ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "updated_at" not in _table_columns(conn, "employees"):
            conn.execute("ALTER TABLE employees ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE employees SET updated_at = created_at WHERE updated_at = ''")
        if "location_name" not in _table_columns(conn, "camera_configs"):
            conn.execute("ALTER TABLE camera_configs ADD COLUMN location_name TEXT NOT NULL DEFAULT ''")
        _seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_defaults(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('admin','Full access')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('store_user','Store-level operations')")
    conn.execute("INSERT OR IGNORE INTO roles(role_name, description) VALUES('management_viewer','Read-only analytics')")
    perms = {
        "admin": [("dashboard",1,1),("config",1,1),("stores",1,1),("users",1,1),("roles",1,1),("licenses",1,1)],
        "store_user": [("dashboard",1,1),("config",1,0),("stores",1,0),("users",1,0),("roles",0,0),("licenses",1,1)],
        "management_viewer": [("dashboard",1,0),("config",1,0),("stores",1,0),("users",0,0),("roles",0,0),("licenses",1,0)],
    }
    for role_name, rows in perms.items():
        role_id = conn.execute("SELECT role_id FROM roles WHERE role_name=?", (role_name,)).fetchone()[0]
        for code,r,w in rows:
            conn.execute("INSERT OR IGNORE INTO role_permissions(role_id, permission_code, can_read, can_write) VALUES(?,?,?,?)",(role_id,code,r,w))


def create_user(db_path: Path, email: str, full_name: str, password: str, store_id: str = "", role_names: list[str] | None = None) -> int:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        now = _now_utc()
        conn.execute(
            "INSERT INTO users(email, full_name, password_hash, is_active, store_id, created_at) VALUES(?,?,?,?,?,?)",
            (email.strip().lower(), full_name.strip(), _hash_password(password), 1, store_id.strip(), now),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        for role in (role_names or ["store_user"]):
            row = conn.execute("SELECT role_id FROM roles WHERE role_name=?", (role.strip(),)).fetchone()
            if row:
                conn.execute("INSERT OR IGNORE INTO user_roles(user_id, role_id) VALUES(?,?)", (user_id, int(row[0])))
        conn.commit()
        return user_id
    finally:
        conn.close()


def set_user_password(db_path: Path, email: str, new_password: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE users SET password_hash=? WHERE lower(email)=lower(?)", (_hash_password(new_password), email.strip()))
        conn.commit()
    finally:
        conn.close()


def authenticate_user(db_path: Path, email: str, password: str) -> UserRecord | None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
    try:
        conn.execute("INSERT OR IGNORE INTO roles(role_name,description) VALUES(?,?)", (role_name.strip().lower(), description.strip()))
        conn.commit()
    finally:
        conn.close()


def set_role_permissions(db_path: Path, role_name: str, permissions: list[tuple[str, int, int]]) -> None:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
    try:
        rows=conn.execute("SELECT role_id,role_name,description FROM roles ORDER BY role_name").fetchall()
        out=[]
        for rid,name,desc in rows:
            perms=conn.execute("SELECT permission_code,can_read,can_write FROM role_permissions WHERE role_id=? ORDER BY permission_code",(rid,)).fetchall()
            out.append({"role_name":name,"description":desc,"permissions":"|".join([f"{p[0]}:{p[1]}:{p[2]}" for p in perms])})
        return out
    finally:
        conn.close()


def user_permissions(db_path: Path, email: str) -> dict[str, dict[str, bool]]:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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


def ensure_default_admins(db_path: Path, admin_emails: list[str]) -> None:
    for email in admin_emails:
        try:
            create_user(db_path, email=email, full_name=email.split("@")[0], password="ChangeMe123!", role_names=["admin"])
        except Exception:
            pass


def create_user_session(db_path: Path, email: str, ttl_days: int = 14) -> str:
    init_db(db_path)
    normalized_email = email.strip().lower()
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    expires_at = (now + timedelta(days=max(1, ttl_days))).isoformat()
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM user_sessions WHERE token=?", (tok,))
        conn.commit()
    finally:
        conn.close()


def upsert_store_master_rows(db_path: Path, rows: list[dict[str, str]]) -> int:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
    try:
        rows=conn.execute("SELECT license_id,old_status,new_status,actor_email,note,created_at FROM license_audit WHERE license_id=? ORDER BY id", (license_id,)).fetchall()
        cols=["license_id","old_status","new_status","actor_email","note","created_at"]
        return [dict(zip(cols,r)) for r in rows]
    finally:
        conn.close()


def upsert_alert_route(db_path: Path, store_id: str, channel: str, target: str, enabled: bool = True) -> None:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
    try:
        rows=conn.execute("SELECT channel,target,enabled,created_at FROM alert_routes WHERE store_id=? ORDER BY channel,target", (store_id,)).fetchall()
        return [{"channel":r[0],"target":r[1],"enabled":bool(r[2]),"created_at":r[3]} for r in rows]
    finally:
        conn.close()


def route_alert(db_path: Path, store_id: str, alert_type: str, payload_json: str) -> list[str]:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM stores WHERE store_id=?", (store_id.strip(),))
        conn.execute("DELETE FROM camera_configs WHERE store_id=?", (store_id.strip(),))
        conn.execute("DELETE FROM employees WHERE store_id=?", (store_id.strip(),))
        conn.commit()
    finally:
        conn.close()


def list_stores(db_path: Path) -> list[StoreRecord]:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
    try:
        rows=conn.execute("SELECT store_id,store_name,email,drive_folder_url,created_at,updated_at FROM stores ORDER BY store_id").fetchall()
        return [StoreRecord(*r) for r in rows]
    finally:
        conn.close()


def get_store_by_email(db_path: Path, email: str) -> StoreRecord | None:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
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
    conn_chk = sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn=sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    location_name: str = "",
    entry_line_x: float = 0.5,
    entry_direction: str = "OUTSIDE_TO_INSIDE",
) -> None:
    init_db(db_path)
    role=(camera_role or "INSIDE").strip().upper() or "INSIDE"
    location=(location_name or "").strip()
    direction=(entry_direction or "OUTSIDE_TO_INSIDE").strip().upper()
    if direction not in {"OUTSIDE_TO_INSIDE","INSIDE_TO_OUTSIDE"}:
        direction="OUTSIDE_TO_INSIDE"
    x=float(entry_line_x)
    if x<0 or x>1:
        raise ValueError("entry_line_x must be between 0 and 1")
    conn=sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO camera_configs(store_id,camera_id,camera_role,location_name,entry_line_x,entry_direction,updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(store_id,camera_id) DO UPDATE SET
              camera_role=excluded.camera_role,
              location_name=excluded.location_name,
              entry_line_x=excluded.entry_line_x,
              entry_direction=excluded.entry_direction,
              updated_at=excluded.updated_at
            """,
            (store_id.strip(), camera_id.strip().upper(), role, location, x, direction, _now_utc()),
        )
        conn.commit()
    finally:
        conn.close()


def list_camera_configs(db_path: Path, store_id: str | None = None) -> list[CameraConfig]:
    init_db(db_path)
    conn=sqlite3.connect(db_path)
    try:
        if store_id:
            rows=conn.execute("SELECT store_id,camera_id,camera_role,location_name,entry_line_x,entry_direction,updated_at FROM camera_configs WHERE store_id=? ORDER BY camera_id", (store_id,)).fetchall()
        else:
            rows=conn.execute("SELECT store_id,camera_id,camera_role,location_name,entry_line_x,entry_direction,updated_at FROM camera_configs ORDER BY store_id,camera_id").fetchall()
        return [CameraConfig(*r) for r in rows]
    finally:
        conn.close()


def camera_config_map(db_path: Path) -> dict[str, dict[str, CameraConfig]]:
    out: dict[str, dict[str, CameraConfig]] = {}
    for cfg in list_camera_configs(db_path=db_path):
        out.setdefault(cfg.store_id, {})[cfg.camera_id] = cfg
    return out


def parse_drive_folder_id(drive_folder_url: str) -> str | None:
    m=DRIVE_FOLDER_ID_PATTERN.search(drive_folder_url)
    return m.group(1) if m else None


def ensure_store_snapshot_dir(data_root: Path, store_id: str) -> Path:
    target = data_root / store_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _drive_api_list_files_recursive(folder_id: str, api_key: str) -> list[dict[str, str]]:
    files=[]; stack=[folder_id]
    while stack:
        cur=stack.pop(); token=None
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
            resp=requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=30)
            resp.raise_for_status()
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
                if item.get("mimeType","")=="application/vnd.google-apps.folder": stack.append(item["id"])
                elif Path(item.get("name", "")).suffix.lower() in _IMAGE_EXTS:
                    files.append({"id":item["id"],"name":item.get("name", item["id"])})
            token=payload.get("nextPageToken")
            if not token: break
    return files


def _drive_api_download_files(file_items: list[dict[str, str]], target_dir: Path, api_key: str) -> int:
    n=0
    for item in file_items:
        dest=target_dir / Path(item["name"]).name
        resp=requests.get(f"https://www.googleapis.com/drive/v3/files/{item['id']}", params={"alt":"media","key":api_key}, timeout=60)
        if resp.status_code!=200: continue
        dest.write_bytes(resp.content); n+=1
    return n


def _sync_store_from_drive_api(store: StoreRecord, target_dir: Path, api_key: str) -> tuple[bool, str]:
    folder_id=parse_drive_folder_id(store.drive_folder_url)
    if not folder_id:
        return False, f"{store.store_id}: invalid Google Drive folder URL"
    try:
        items=_drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
        if not items:
            return False, f"{store.store_id}: no files found via Drive API"
        downloaded=_drive_api_download_files(items, target_dir=target_dir, api_key=api_key)
        processed,failed=optimize_store_image_files(target_dir)
        return True, f"{store.store_id}: api_sync downloaded={downloaded} optimized={processed} failed={failed} dir={target_dir}"
    except Exception as exc:
        return False, f"{store.store_id}: Drive API sync failed ({exc})"


def sync_store_from_drive(store: StoreRecord, data_root: Path) -> tuple[bool, str]:
    if not store.drive_folder_url.strip():
        return False, f"{store.store_id}: no drive folder URL configured"
    folder_id=parse_drive_folder_id(store.drive_folder_url)
    if folder_id is None:
        return False, f"{store.store_id}: invalid Google Drive folder URL"
    target_dir=ensure_store_snapshot_dir(data_root=data_root, store_id=store.store_id)
    api_key=os.getenv("GOOGLE_API_KEY","").strip()
    if api_key:
        ok,msg=_sync_store_from_drive_api(store=store, target_dir=target_dir, api_key=api_key)
        if ok: return ok,msg
    try:
        import gdown  # type: ignore
    except Exception as exc:
        return False, f"{store.store_id}: gdown not available ({exc})"
    try:
        gdown.download_folder(url=store.drive_folder_url, output=str(target_dir), quiet=True, remaining_ok=True)
        processed,failed=optimize_store_image_files(target_dir)
        if not api_key:
            return True, f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed} (tip: set GOOGLE_API_KEY to bypass 50-file gdown limit)"
        return True, f"{store.store_id}: synced snapshots into {target_dir} | optimized={processed} failed={failed}"
    except Exception as exc:
        error_text = str(exc)
        if "Expecting value" in error_text:
            return False, (
                f"{store.store_id}: sync failed because Drive returned non-JSON content. "
                "Please ensure folder is shared as 'Anyone with the link (Viewer)' and "
                "configure GOOGLE_API_KEY for reliable Drive API sync."
            )
        return False, f"{store.store_id}: sync failed ({exc}). Set GOOGLE_API_KEY for full Drive API sync support on large folders."


def log_user_activity(db_path: Path, actor_email: str, action_code: str, store_id: str = "", payload_json: str = "{}") -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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
    conn = sqlite3.connect(db_path)
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

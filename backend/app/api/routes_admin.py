"""Admin CRUD routes — stores, users, roles, employees, cameras, locations,
org settings, store access, activity log, store master."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from backend.app.auth.dependencies import get_current_user
from backend.app.db.canonical_metadata import (
    app_settings,
    camera_configs,
    employees,
    location_master,
    role_permissions,
    roles,
    store_master,
    stores,
    user_activity,
    user_roles,
    user_store_access,
    users,
)
from backend.app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


async def _log_activity(actor_email: str, action_code: str, store_id: str = "", payload: dict | None = None) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            insert(user_activity).values(
                actor_email=actor_email,
                action_code=action_code,
                store_id=store_id,
                payload_json=payload or {},
                created_at=_now(),
            )
        )
        await session.commit()


_STORE_MASTER_HEADER_ALIASES = {
    "storeid": "store_id",
    "store_id": "store_id",
    "storename": "store_name",
    "store_name": "store_name",
    "outletname": "store_name",
    "outlet_name": "store_name",
    "branch": "store_name",
    "branchname": "store_name",
    "branch_name": "store_name",
    "locationname": "store_name",
    "location_name": "store_name",
    "name": "store_name",
    "shortcode": "short_code",
    "short_code": "short_code",
    "gofrugalname": "gofrugal_name",
    "gofrugal_name": "gofrugal_name",
    "outletid": "outlet_id",
    "outlet_id": "outlet_id",
    "city": "city",
    "state": "state",
    "zone": "zone",
    "country": "country",
    "mobileno": "mobile_no",
    "mobile_no": "mobile_no",
    "storeemail": "store_email",
    "store_email": "store_email",
    "clustermanager": "cluster_manager",
    "cluster_manager": "cluster_manager",
    "areamanager": "area_manager",
    "area_manager": "area_manager",
}


def _normalize_store_master_header(value: str) -> str:
    compact = "".join(ch if ch.isalnum() else "_" for ch in str(value or "").strip().lower()).strip("_")
    while "__" in compact:
        compact = compact.replace("__", "_")
    return _STORE_MASTER_HEADER_ALIASES.get(compact, _STORE_MASTER_HEADER_ALIASES.get(compact.replace("_", ""), compact))


def _clean_store_master_value(value: Any) -> str:
    return str(value or "").strip()


def _normalized_store_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean_store_master_value(value).lower())


def _looks_like_email(value: str) -> bool:
    return "@" in value and "." in value.split("@", 1)[-1]


def _make_store_id_seed(*values: Any) -> str:
    for value in values:
        cleaned = _clean_store_master_value(value)
        if cleaned:
            return cleaned
    return ""


def _generate_store_id(*values: Any) -> str:
    seed = _make_store_id_seed(*values)
    normalized = re.sub(r"[^A-Za-z0-9]+", "", seed).upper()
    if not normalized:
        return ""
    return normalized[:24]


def _placeholder_store_email(store_id: str) -> str:
    local = re.sub(r"[^a-z0-9]+", "-", store_id.lower()).strip("-") or "store"
    return f"{local}@iris.local"


def _store_master_row_has_data(row: dict[str, str]) -> bool:
    keys = ("store_id", "store_name", "short_code", "gofrugal_name", "outlet_id", "store_email")
    return any(_clean_store_master_value(row.get(key, "")) for key in keys)


def _register_store_identity(identity_map: dict[str, str], value: Any, store_id: str) -> None:
    key = _normalized_store_identity(value)
    if key and key not in identity_map:
        identity_map[key] = store_id


def _parse_store_master_upload(content: bytes, filename: str) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    sample = "\n".join(lines[:5])
    if filename.lower().endswith(".tsv"):
        dialect = csv.excel_tab
    else:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel_tab if "\t" in lines[0] else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    normalized_headers = [_normalize_store_master_header(name) for name in reader.fieldnames]
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row: dict[str, str] = {}
        for index, key in enumerate(normalized_headers):
            if not key:
                continue
            original_key = reader.fieldnames[index]
            row[key] = _clean_store_master_value(raw_row.get(original_key, ""))
        if not _store_master_row_has_data(row):
            continue
        # When CSV has no store_id column (e.g. only Short code / GoFrugal Name),
        # promote short_code → store_id and gofrugal_name → store_name so the
        # upsert logic has something to work with.
        if not row.get("store_id") and row.get("short_code"):
            row["store_id"] = row["short_code"]
        if not row.get("store_name") and row.get("gofrugal_name"):
            row["store_name"] = row["gofrugal_name"]
        # Sanitise any placeholder "–" / "-" / "N/A" manager values
        for mgr_key in ("cluster_manager", "area_manager"):
            val = row.get(mgr_key, "")
            if val in ("-", "–", "N/A", "n/a", "NA"):
                row[mgr_key] = ""
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

class StoreIn(BaseModel):
    store_id: str
    store_name: str
    email: str
    drive_folder_url: str = ""


@router.get("/stores")
async def list_stores(_: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(stores).order_by(stores.c.store_id)
        )
        return [dict(r) for r in result.mappings().all()]


@router.post("/stores", status_code=status.HTTP_201_CREATED)
async def create_store(body: StoreIn, actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(stores.c.store_id).where(stores.c.store_id == body.store_id)
        )
        if existing.first():
            raise HTTPException(status_code=409, detail="Store ID already exists")
        await session.execute(
            insert(stores).values(
                store_id=body.store_id,
                store_name=body.store_name,
                email=body.email,
                drive_folder_url=body.drive_folder_url,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    await _log_activity(actor, "store.create", body.store_id, {"store_name": body.store_name})
    return {"store_id": body.store_id, "created": True}


@router.put("/stores/{store_id}")
async def update_store(store_id: str, body: StoreIn, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(stores)
            .where(stores.c.store_id == store_id)
            .values(
                store_name=body.store_name,
                email=body.email,
                drive_folder_url=body.drive_folder_url,
                updated_at=_now(),
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Store not found")
        await session.commit()
    await _log_activity(actor, "store.update", store_id, {"store_name": body.store_name})
    return {"store_id": store_id, "updated": True}


@router.delete("/stores/{store_id}")
async def delete_store(store_id: str, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(stores).where(stores.c.store_id == store_id))
        await session.commit()
    await _log_activity(actor, "store.delete", store_id)
    return {"store_id": store_id, "deleted": True}


class SyncToggleIn(BaseModel):
    sync_enabled: bool
    sync_interval_hours: int = 1


@router.put("/stores/{store_id}/sync")
async def toggle_store_sync(store_id: str, body: SyncToggleIn, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(stores)
            .where(stores.c.store_id == store_id)
            .values(
                sync_enabled=body.sync_enabled,
                sync_interval_hours=body.sync_interval_hours,
                updated_at=_now(),
            )
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Store not found")
        await session.commit()
    await _log_activity(actor, "store.sync_toggle", store_id, {
        "sync_enabled": body.sync_enabled,
        "sync_interval_hours": body.sync_interval_hours,
    })
    return {"store_id": store_id, "sync_enabled": body.sync_enabled, "sync_interval_hours": body.sync_interval_hours}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserIn(BaseModel):
    email: str
    full_name: str
    password: str = ""
    store_id: str = ""
    is_active: bool = True
    role_names: list[str] = []


class PasswordReset(BaseModel):
    new_password: str


@router.get("/users")
async def list_users(_: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                users.c.user_id,
                users.c.email,
                users.c.full_name,
                users.c.is_active,
                users.c.store_id,
                users.c.created_at,
                users.c.password_hint,
            ).order_by(users.c.email)
        )
        result = await session.execute(stmt)
        rows = [dict(r) for r in result.mappings().all()]

        # attach role names
        for row in rows:
            uid = row["user_id"]
            r2 = await session.execute(
                select(roles.c.role_name)
                .join(user_roles, user_roles.c.role_id == roles.c.role_id)
                .where(user_roles.c.user_id == uid)
            )
            row["roles"] = [r[0] for r in r2.all()]
        return rows


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserIn, actor: str = Depends(get_current_user)) -> dict:
    if not body.password:
        raise HTTPException(status_code=422, detail="password is required")
    now = _now()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(users.c.user_id).where(func.lower(users.c.email) == body.email.lower())
        )
        if existing.first():
            raise HTTPException(status_code=409, detail="Email already exists")
        result = await session.execute(
            insert(users).values(
                email=body.email,
                full_name=body.full_name,
                password_hash=_hash_password(body.password),
                password_hint=body.password,
                is_active=body.is_active,
                store_id=body.store_id,
                created_at=now,
            ).returning(users.c.user_id)
        )
        user_id = result.scalar_one()

        for role_name in body.role_names:
            r2 = await session.execute(
                select(roles.c.role_id).where(roles.c.role_name == role_name)
            )
            role_row = r2.first()
            if role_row:
                await session.execute(
                    insert(user_roles).values(user_id=user_id, role_id=role_row[0])
                )

        # Auto-grant access to assigned store
        if body.store_id:
            await session.execute(
                insert(user_store_access)
                .values(user_id=user_id, store_id=body.store_id, created_at=now)
                .on_conflict_do_nothing()
            )

        await session.commit()
    await _log_activity(actor, "user.create", body.store_id, {"email": body.email})
    return {"user_id": user_id, "email": body.email, "created": True}


@router.put("/users/{email}")
async def update_user(email: str, body: UserIn, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(users)
            .where(func.lower(users.c.email) == email.lower())
            .values(
                full_name=body.full_name,
                is_active=body.is_active,
                store_id=body.store_id,
            )
            .returning(users.c.user_id)
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = row[0]

        # replace roles
        await session.execute(delete(user_roles).where(user_roles.c.user_id == user_id))
        for role_name in body.role_names:
            r2 = await session.execute(
                select(roles.c.role_id).where(roles.c.role_name == role_name)
            )
            role_row = r2.first()
            if role_row:
                await session.execute(
                    insert(user_roles).values(user_id=user_id, role_id=role_row[0])
                )
        await session.commit()
    await _log_activity(actor, "user.update", body.store_id, {"email": email})
    return {"email": email, "updated": True}


@router.post("/users/{email}/password")
async def reset_password(email: str, body: PasswordReset, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(users)
            .where(func.lower(users.c.email) == email.lower())
            .values(password_hash=_hash_password(body.new_password), password_hint=body.new_password)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        await session.commit()
    await _log_activity(actor, "user.password_reset", "", {"email": email})
    return {"email": email, "reset": True}


class BulkPasswordReset(BaseModel):
    new_password: str = "user12345"


@router.post("/users/bulk-reset-password")
async def bulk_reset_password(body: BulkPasswordReset, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(users).values(
                password_hash=_hash_password(body.new_password),
                password_hint=body.new_password,
            )
        )
        await session.commit()
    await _log_activity(actor, "user.bulk_password_reset", "", {"count": result.rowcount})
    return {"reset": result.rowcount, "new_password": body.new_password}


@router.delete("/users/{email}")
async def delete_user(email: str, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(users).where(func.lower(users.c.email) == email.lower())
        )
        await session.commit()
    await _log_activity(actor, "user.delete", "", {"email": email})
    return {"email": email, "deleted": True}


# ---------------------------------------------------------------------------
# Roles + permissions
# ---------------------------------------------------------------------------

class RoleIn(BaseModel):
    role_name: str
    description: str = ""


class PermissionRow(BaseModel):
    permission_code: str
    can_read: bool = False
    can_write: bool = False


KNOWN_PERMISSIONS = [
    "stores", "users", "roles", "employees", "cameras", "settings",
    "reports", "pipelines", "qa_review", "store_access", "activity_logs",
    "store_master",
]


@router.get("/roles")
async def list_roles_endpoint(_: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(roles).order_by(roles.c.role_name))
        role_rows = [dict(r) for r in result.mappings().all()]
        for row in role_rows:
            perms = await session.execute(
                select(role_permissions).where(role_permissions.c.role_id == row["role_id"])
            )
            row["permissions"] = [dict(p) for p in perms.mappings().all()]
        return role_rows


@router.post("/roles", status_code=status.HTTP_201_CREATED)
async def create_role(body: RoleIn, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            insert(roles).values(role_name=body.role_name, description=body.description)
            .returning(roles.c.role_id)
        )
        role_id = result.scalar_one()
        await session.commit()
    await _log_activity(actor, "role.create", "", {"role_name": body.role_name})
    return {"role_id": role_id, "role_name": body.role_name, "created": True}


@router.delete("/roles/{role_name}")
async def delete_role(role_name: str, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(roles).where(roles.c.role_name == role_name))
        await session.commit()
    await _log_activity(actor, "role.delete", "", {"role_name": role_name})
    return {"role_name": role_name, "deleted": True}


@router.put("/roles/{role_name}/permissions")
async def set_permissions(
    role_name: str,
    perms: list[PermissionRow],
    actor: str = Depends(get_current_user),
) -> dict:
    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(roles.c.role_id).where(roles.c.role_name == role_name)
        )
        row = r.first()
        if not row:
            raise HTTPException(status_code=404, detail="Role not found")
        role_id = row[0]
        await session.execute(
            delete(role_permissions).where(role_permissions.c.role_id == role_id)
        )
        for p in perms:
            await session.execute(
                insert(role_permissions).values(
                    role_id=role_id,
                    permission_code=p.permission_code,
                    can_read=p.can_read,
                    can_write=p.can_write,
                )
            )
        await session.commit()
    await _log_activity(actor, "role.permissions_set", "", {"role_name": role_name})
    return {"role_name": role_name, "permissions_count": len(perms)}


@router.get("/permissions/codes")
async def list_permission_codes(_: str = Depends(get_current_user)) -> list[str]:
    return KNOWN_PERMISSIONS


# ---------------------------------------------------------------------------
# App settings (organisation)
# ---------------------------------------------------------------------------

@router.get("/settings")
async def get_settings_endpoint(_: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(app_settings))
        rows = result.mappings().all()
    return {r["setting_key"]: r["setting_value"] for r in rows}


@router.put("/settings")
async def update_settings(body: dict[str, str], actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    async with AsyncSessionLocal() as session:
        for key, value in body.items():
            existing = await session.execute(
                select(app_settings.c.setting_key).where(app_settings.c.setting_key == key)
            )
            if existing.first():
                await session.execute(
                    update(app_settings)
                    .where(app_settings.c.setting_key == key)
                    .values(setting_value=str(value), updated_at=now)
                )
            else:
                await session.execute(
                    insert(app_settings).values(
                        setting_key=key, setting_value=str(value), updated_at=now
                    )
                )
        await session.commit()
    await _log_activity(actor, "settings.update", "", {"keys": list(body.keys())})
    return {"updated": len(body)}


@router.post("/settings/logo")
async def upload_logo(file: UploadFile, actor: str = Depends(get_current_user)) -> dict:
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Logo too large (max 5 MB)")
    ext = (file.filename or "png").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "png"
    media_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "svg": "image/svg+xml"}
    media = media_map.get(ext, "image/png")

    # Auto-resize to 500px wide (preserving aspect ratio) for non-SVG images
    if ext != "svg":
        try:
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(content))
            orig_w, orig_h = img.size
            if orig_w > 500:
                new_h = max(1, round(orig_h * 500 / orig_w))
                img = img.resize((500, new_h), PILImage.LANCZOS)
            pil_fmt = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}.get(ext, "PNG")
            if pil_fmt == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format=pil_fmt, optimize=True)
            content = buf.getvalue()
        except Exception:
            pass  # Fall back to storing original if resize fails

    data_url = f"data:{media};base64,{base64.b64encode(content).decode()}"
    now = _now()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(app_settings.c.setting_key).where(app_settings.c.setting_key == "logo_url")
        )
        if existing.first():
            await session.execute(
                update(app_settings).where(app_settings.c.setting_key == "logo_url")
                .values(setting_value=data_url, updated_at=now)
            )
        else:
            await session.execute(
                insert(app_settings).values(setting_key="logo_url", setting_value=data_url, updated_at=now)
            )
        await session.commit()
    await _log_activity(actor, "settings.logo_upload", "", {"size": len(content), "media_type": media})
    return {"logo_url": data_url}


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@router.get("/employees/{store_id}")
async def list_employees_endpoint(store_id: str, _: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(employees).where(employees.c.store_id == store_id).order_by(employees.c.employee_name)
        )
        return [dict(r) for r in result.mappings().all()]


@router.post("/employees/{store_id}", status_code=status.HTTP_201_CREATED)
async def create_employee(
    store_id: str,
    file: UploadFile,
    actor: str = Depends(get_current_user),
) -> dict:
    from backend.app.config import get_settings
    settings = get_settings()
    content = await file.read()
    employee_name = (file.filename or "unknown").rsplit(".", 1)[0]
    ext = (file.filename or "jpg").rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    emp_id = str(uuid.uuid4())
    rel_path = f"employee_assets/{store_id}/{emp_id}.{ext}"
    full_path = settings.data_root_obj / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)

    now = _now()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            insert(employees).values(
                store_id=store_id,
                employee_name=employee_name,
                image_path=str(full_path),
                is_active=True,
                created_at=now,
                updated_at=now,
            ).returning(employees.c.id)
        )
        emp_db_id = result.scalar_one()
        await session.commit()
    await _log_activity(actor, "employee.create", store_id, {"name": employee_name})
    return {"id": emp_db_id, "employee_name": employee_name, "created": True}


@router.delete("/employees/{store_id}/{employee_id}")
async def delete_employee_endpoint(
    store_id: str,
    employee_id: int,
    actor: str = Depends(get_current_user),
) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(employees.c.image_path, employees.c.employee_name)
            .where(employees.c.id == employee_id, employees.c.store_id == store_id)
        )
        row = result.first()
        if row:
            try:
                import os as _os
                _os.unlink(row[0])
            except Exception:
                pass
        await session.execute(
            delete(employees).where(employees.c.id == employee_id, employees.c.store_id == store_id)
        )
        await session.commit()
    await _log_activity(actor, "employee.delete", store_id, {"id": employee_id})
    return {"id": employee_id, "deleted": True}


# ---------------------------------------------------------------------------
# Camera configs
# ---------------------------------------------------------------------------

class CameraIn(BaseModel):
    camera_id: str
    camera_role: str = "INSIDE"
    floor_name: str = ""
    location_name: str = ""
    entry_line_x: float = 0.5
    entry_direction: str = "OUTSIDE_TO_INSIDE"


@router.get("/cameras/{store_id}")
async def list_cameras(store_id: str, _: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(camera_configs).where(camera_configs.c.store_id == store_id).order_by(camera_configs.c.camera_id)
        )
        return [dict(r) for r in result.mappings().all()]


@router.post("/cameras/{store_id}", status_code=status.HTTP_201_CREATED)
async def upsert_camera(store_id: str, body: CameraIn, actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(camera_configs.c.camera_id).where(
                camera_configs.c.store_id == store_id, camera_configs.c.camera_id == body.camera_id
            )
        )
        if existing.first():
            await session.execute(
                update(camera_configs)
                .where(camera_configs.c.store_id == store_id, camera_configs.c.camera_id == body.camera_id)
                .values(
                    camera_role=body.camera_role,
                    floor_name=body.floor_name,
                    location_name=body.location_name,
                    entry_line_x=body.entry_line_x,
                    entry_direction=body.entry_direction,
                    updated_at=now,
                )
            )
        else:
            await session.execute(
                insert(camera_configs).values(
                    store_id=store_id,
                    camera_id=body.camera_id,
                    camera_role=body.camera_role,
                    floor_name=body.floor_name,
                    location_name=body.location_name,
                    entry_line_x=body.entry_line_x,
                    entry_direction=body.entry_direction,
                    updated_at=now,
                )
            )
        await session.commit()
    await _log_activity(actor, "camera.upsert", store_id, {"camera_id": body.camera_id})
    return {"store_id": store_id, "camera_id": body.camera_id, "saved": True}


@router.delete("/cameras/{store_id}/{camera_id}")
async def delete_camera(store_id: str, camera_id: str, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(camera_configs).where(
                camera_configs.c.store_id == store_id, camera_configs.c.camera_id == camera_id
            )
        )
        await session.commit()
    await _log_activity(actor, "camera.delete", store_id, {"camera_id": camera_id})
    return {"camera_id": camera_id, "deleted": True}


# ---------------------------------------------------------------------------
# Location master
# ---------------------------------------------------------------------------

class LocationIn(BaseModel):
    floor_name: str = "Ground"
    location_name: str


@router.get("/locations/{store_id}")
async def list_locations(store_id: str, _: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(location_master)
            .where(location_master.c.store_id == store_id)
            .order_by(location_master.c.floor_name, location_master.c.location_name)
        )
        return [dict(r) for r in result.mappings().all()]


@router.post("/locations/{store_id}", status_code=status.HTTP_201_CREATED)
async def upsert_location(store_id: str, body: LocationIn, actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(location_master.c.store_id).where(
                location_master.c.store_id == store_id,
                location_master.c.floor_name == body.floor_name,
                location_master.c.location_name == body.location_name,
            )
        )
        if not existing.first():
            await session.execute(
                insert(location_master).values(
                    store_id=store_id,
                    floor_name=body.floor_name,
                    location_name=body.location_name,
                    updated_at=now,
                )
            )
            await session.commit()
    await _log_activity(actor, "location.upsert", store_id, {"location": body.location_name})
    return {"store_id": store_id, "floor_name": body.floor_name, "location_name": body.location_name, "saved": True}


@router.delete("/locations/{store_id}")
async def delete_location(
    store_id: str,
    floor_name: str,
    location_name: str,
    actor: str = Depends(get_current_user),
) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(location_master).where(
                location_master.c.store_id == store_id,
                location_master.c.floor_name == floor_name,
                location_master.c.location_name == location_name,
            )
        )
        await session.commit()
    await _log_activity(actor, "location.delete", store_id, {"location": location_name})
    return {"deleted": True}


# ---------------------------------------------------------------------------
# User store access
# ---------------------------------------------------------------------------

class StoreAccessIn(BaseModel):
    store_ids: list[str]


@router.get("/store-access/{email}")
async def get_store_access(email: str, _: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                user_store_access.c.store_id,
                stores.c.store_name,
                user_store_access.c.created_at,
            )
            .join(stores, stores.c.store_id == user_store_access.c.store_id)
            .join(users, users.c.user_id == user_store_access.c.user_id)
            .where(func.lower(users.c.email) == email.lower())
        )
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.post("/store-access/{email}")
async def replace_store_access(
    email: str,
    body: StoreAccessIn,
    actor: str = Depends(get_current_user),
) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(users.c.user_id).where(func.lower(users.c.email) == email.lower())
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = row[0]
        await session.execute(
            delete(user_store_access).where(user_store_access.c.user_id == user_id)
        )
        now = _now()
        for sid in body.store_ids:
            await session.execute(
                insert(user_store_access).values(user_id=user_id, store_id=sid, created_at=now)
            )
        await session.commit()
    await _log_activity(actor, "store_access.replace", "", {"email": email, "stores": body.store_ids})
    return {"email": email, "store_ids": body.store_ids, "updated": True}


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@router.get("/activity")
async def list_activity(
    actor_email: str | None = None,
    limit: int = 100,
    _: str = Depends(get_current_user),
) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = select(user_activity).order_by(user_activity.c.created_at.desc()).limit(limit)
        if actor_email:
            stmt = stmt.where(user_activity.c.actor_email == actor_email)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


# ---------------------------------------------------------------------------
# Store master
# ---------------------------------------------------------------------------

_STORE_MASTER_KNOWN_FIELDS = frozenset({
    "store_id", "store_name", "short_code", "gofrugal_name", "outlet_id",
    "city", "state", "zone", "country", "mobile_no", "store_email",
    "cluster_manager", "area_manager",
})


class StoreMasterRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_id: str = ""
    store_name: str = ""
    short_code: str = ""
    gofrugal_name: str = ""
    outlet_id: str = ""
    city: str = ""
    state: str = ""
    zone: str = ""
    country: str = ""
    mobile_no: str = ""
    store_email: str = ""
    cluster_manager: str = ""
    area_manager: str = ""


@router.get("/store-master")
async def list_store_master_endpoint(_: str = Depends(get_current_user)) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                store_master.c.store_id,
                stores.c.store_name,
                store_master.c.short_code,
                store_master.c.gofrugal_name,
                store_master.c.outlet_id,
                store_master.c.city,
                store_master.c.state,
                store_master.c.zone,
                store_master.c.country,
                store_master.c.mobile_no,
                store_master.c.store_email,
                store_master.c.cluster_manager,
                store_master.c.area_manager,
                store_master.c.updated_at,
            )
            .select_from(store_master.outerjoin(stores, stores.c.store_id == store_master.c.store_id))
            .order_by(func.coalesce(stores.c.store_name, store_master.c.store_id), store_master.c.store_id)
        )
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.post("/store-master", status_code=status.HTTP_201_CREATED)
async def upsert_store_master(rows: list[StoreMasterRow], actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    processed = 0
    created_stores = 0
    matched_existing = 0
    generated_store_ids = 0
    row_errors: list[dict] = []

    async with AsyncSessionLocal() as session:
        identity_map: dict[str, str] = {}

        existing_stores_result = await session.execute(select(stores))
        for store_row in existing_stores_result.mappings().all():
            store_id = str(store_row["store_id"])
            _register_store_identity(identity_map, store_id, store_id)
            _register_store_identity(identity_map, store_row.get("store_name", ""), store_id)
            _register_store_identity(identity_map, store_row.get("email", ""), store_id)

        existing_master_result = await session.execute(select(store_master))
        for master_row in existing_master_result.mappings().all():
            store_id = str(master_row["store_id"])
            _register_store_identity(identity_map, master_row.get("short_code", ""), store_id)
            _register_store_identity(identity_map, master_row.get("gofrugal_name", ""), store_id)
            _register_store_identity(identity_map, master_row.get("outlet_id", ""), store_id)

        for row_idx, row in enumerate(rows):
            row_label = (
                row.short_code or row.gofrugal_name or row.outlet_id or row.store_id
                or f"row #{row_idx + 1}"
            )

            # Resolve store ID before touching the DB (pure logic, no exception expected)
            explicit_store_id = _clean_store_master_value(row.store_id)
            inferred_store_id = explicit_store_id or identity_map.get(_normalized_store_identity(row.store_name), "")
            if not inferred_store_id:
                for candidate in (row.short_code, row.gofrugal_name, row.outlet_id):
                    inferred_store_id = identity_map.get(_normalized_store_identity(candidate), "")
                    if inferred_store_id:
                        matched_existing += 1
                        break
            if not inferred_store_id:
                inferred_store_id = _generate_store_id(row.short_code, row.outlet_id, row.store_name, row.gofrugal_name)
                if inferred_store_id:
                    generated_store_ids += 1
            if not inferred_store_id:
                row_errors.append({
                    "row": row_label,
                    "index": row_idx + 1,
                    "error": "Could not determine store ID — no short_code, outlet_id, or gofrugal_name found",
                })
                continue

            # store_name is NEVER required from the CSV — derive from gofrugal_name or fall back to store_id
            store_display_name = (
                _clean_store_master_value(row.store_name)
                or
                _clean_store_master_value(row.gofrugal_name)
                or inferred_store_id
            )
            store_contact_email = _clean_store_master_value(row.store_email)

            # Use a savepoint so a DB error on one row doesn't invalidate the whole transaction
            try:
                async with session.begin_nested():
                    existing_store = await session.execute(
                        select(stores).where(stores.c.store_id == inferred_store_id)
                    )
                    existing_store_row = existing_store.mappings().first()
                    if existing_store_row:
                        update_store_values: dict[str, Any] = {"updated_at": now}
                        current_name = _clean_store_master_value(existing_store_row.get("store_name", ""))
                        current_email = _clean_store_master_value(existing_store_row.get("email", ""))
                        if store_display_name and (not current_name or current_name == inferred_store_id):
                            update_store_values["store_name"] = store_display_name
                        if store_contact_email and _looks_like_email(store_contact_email) and (not current_email or current_email.endswith("@iris.local")):
                            conflict = await session.execute(
                                select(stores.c.store_id).where(
                                    stores.c.email == store_contact_email,
                                    stores.c.store_id != inferred_store_id,
                                )
                            )
                            if conflict.first() is None:
                                update_store_values["email"] = store_contact_email
                        if len(update_store_values) > 1:
                            await session.execute(
                                update(stores).where(stores.c.store_id == inferred_store_id).values(**update_store_values)
                            )
                    else:
                        # Check if the email is already claimed by a different store
                        insert_email = _placeholder_store_email(inferred_store_id)
                        if _looks_like_email(store_contact_email):
                            conflict = await session.execute(
                                select(stores.c.store_id).where(stores.c.email == store_contact_email)
                            )
                            if conflict.first() is None:
                                insert_email = store_contact_email
                        await session.execute(
                            insert(stores).values(
                                store_id=inferred_store_id,
                                store_name=store_display_name,
                                email=insert_email,
                                drive_folder_url="",
                                sync_enabled=False,
                                sync_interval_hours=1,
                                created_at=now,
                                updated_at=now,
                            )
                        )
                        created_stores += 1

                    existing_master_check = await session.execute(
                        select(store_master.c.store_id).where(store_master.c.store_id == inferred_store_id)
                    )
                    def _title(v: str) -> str:
                        return v.strip().title() if v and v.strip() else v

                    vals = dict(
                        short_code=row.short_code,
                        gofrugal_name=row.gofrugal_name,
                        outlet_id=row.outlet_id,
                        city=_title(row.city),
                        state=_title(row.state),
                        zone=_title(row.zone),
                        country=row.country,
                        mobile_no=row.mobile_no,
                        store_email=row.store_email,
                        cluster_manager=_title(row.cluster_manager),
                        area_manager=_title(row.area_manager),
                        updated_at=now,
                    )
                    if existing_master_check.first():
                        await session.execute(
                            update(store_master).where(store_master.c.store_id == inferred_store_id).values(**vals)
                        )
                    else:
                        await session.execute(
                            insert(store_master).values(store_id=inferred_store_id, **vals)
                        )

                # savepoint committed — update identity map so later rows can match against this store
                _register_store_identity(identity_map, inferred_store_id, inferred_store_id)
                _register_store_identity(identity_map, store_display_name, inferred_store_id)
                _register_store_identity(identity_map, row.short_code, inferred_store_id)
                _register_store_identity(identity_map, row.gofrugal_name, inferred_store_id)
                _register_store_identity(identity_map, row.outlet_id, inferred_store_id)
                processed += 1

            except Exception as exc:  # noqa: BLE001
                row_errors.append({
                    "row": row_label,
                    "index": row_idx + 1,
                    "error": str(exc).split("\n")[0],
                })

        await session.commit()

    await _log_activity(actor, "store_master.upsert", "", {
        "count": processed,
        "created_stores": created_stores,
        "matched_existing": matched_existing,
        "generated_store_ids": generated_store_ids,
        "row_errors": len(row_errors),
    })
    return {
        "processed": processed,
        "created_stores": created_stores,
        "matched_existing": matched_existing,
        "generated_store_ids": generated_store_ids,
        "errors": row_errors,
    }


@router.post("/store-master/normalize-text")
async def normalize_store_master_text(actor: str = Depends(get_current_user)) -> dict:
    """Title-case city, state, zone, cluster_manager, area_manager for all existing rows."""
    def _tc(v: str | None) -> str | None:
        if not v or not v.strip():
            return v
        return v.strip().title()

    updated = 0
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(store_master))).mappings().all()
        for row in rows:
            new_vals = {
                "city": _tc(row.get("city")),
                "state": _tc(row.get("state")),
                "zone": _tc(row.get("zone")),
                "cluster_manager": _tc(row.get("cluster_manager")),
                "area_manager": _tc(row.get("area_manager")),
            }
            changed = any(new_vals[k] != row.get(k) for k in new_vals)
            if changed:
                await session.execute(
                    update(store_master)
                    .where(store_master.c.store_id == row["store_id"])
                    .values(**new_vals)
                )
                updated += 1
        await session.commit()
    await _log_activity(actor, "store_master.normalize_text", "all", {"updated": updated})
    return {"updated": updated}


@router.post("/cleanup-zombie-runs")
async def cleanup_zombie_runs(actor: str = Depends(get_current_user)) -> dict:
    """Mark any 'running' pipeline run that has no heartbeat (or stale heartbeat) as abandoned."""
    import sqlite3
    from backend.app.config import get_settings
    cfg = get_settings()
    db_path = cfg.db_path_obj
    if not db_path.exists():
        return {"cleaned": 0}
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path), timeout=10)
    result = conn.execute(
        """
        UPDATE onfly_pipeline_runs
        SET status='abandoned',
            error_message='Manually cleaned — run was stuck in running state',
            ended_at=?, updated_at=?
        WHERE status='running'
          AND (
            last_heartbeat_at IS NULL
            OR last_heartbeat_at < datetime('now', '-5 minutes')
          )
          AND (
            started_at IS NULL
            OR started_at < datetime('now', '-3 minutes')
          )
        """,
        (now, now),
    )
    cleaned = result.rowcount
    conn.commit()
    conn.close()
    await _log_activity(actor, "admin.cleanup_zombie_runs", "all", {"cleaned": cleaned})
    return {"cleaned": cleaned}


@router.delete("/store-master/{store_id}")
async def delete_store_master_row(store_id: str, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(store_master).where(store_master.c.store_id == store_id)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Store master row not found")
        await session.commit()
    await _log_activity(actor, "store_master.delete", store_id, {"store_id": store_id})
    return {"store_id": store_id, "deleted": True}


@router.post("/store-master/upload", status_code=status.HTTP_201_CREATED)
async def upload_store_master_file(file: UploadFile, actor: str = Depends(get_current_user)) -> dict:
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(status_code=422, detail="Use a CSV or TSV file")

    content = await file.read()
    try:
        parsed_rows = _parse_store_master_upload(content, filename)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded") from exc

    if not parsed_rows:
        raise HTTPException(status_code=422, detail="No recognizable store rows found. Include store name, short code, outlet ID, gofrugal name, or store ID columns.")

    rows = [StoreMasterRow(**row) for row in parsed_rows]
    return await upsert_store_master(rows, actor)

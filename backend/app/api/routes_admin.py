"""Admin CRUD routes — stores, users, roles, employees, cameras, locations,
org settings, store access, activity log, store master."""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, update

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
            .values(password_hash=_hash_password(body.new_password))
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="User not found")
        await session.commit()
    await _log_activity(actor, "user.password_reset", "", {"email": email})
    return {"email": email, "reset": True}


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

class StoreMasterRow(BaseModel):
    store_id: str
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
        result = await session.execute(
            select(store_master).order_by(store_master.c.store_id)
        )
        return [dict(r) for r in result.mappings().all()]


@router.post("/store-master", status_code=status.HTTP_201_CREATED)
async def upsert_store_master(rows: list[StoreMasterRow], actor: str = Depends(get_current_user)) -> dict:
    now = _now()
    processed = 0
    async with AsyncSessionLocal() as session:
        for row in rows:
            existing = await session.execute(
                select(store_master.c.store_id).where(store_master.c.store_id == row.store_id)
            )
            vals = dict(
                short_code=row.short_code,
                gofrugal_name=row.gofrugal_name,
                outlet_id=row.outlet_id,
                city=row.city,
                state=row.state,
                zone=row.zone,
                country=row.country,
                mobile_no=row.mobile_no,
                store_email=row.store_email,
                cluster_manager=row.cluster_manager,
                area_manager=row.area_manager,
                updated_at=now,
            )
            if existing.first():
                await session.execute(
                    update(store_master).where(store_master.c.store_id == row.store_id).values(**vals)
                )
            else:
                await session.execute(
                    insert(store_master).values(store_id=row.store_id, **vals)
                )
            processed += 1
        await session.commit()
    await _log_activity(actor, "store_master.upsert", "", {"count": processed})
    return {"processed": processed}

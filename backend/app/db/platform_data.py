from __future__ import annotations

import hashlib
import hmac
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, select, text


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        parts = (hashed or "").split("$", 2)
        if len(parts) == 3 and parts[0] == "pbkdf2_sha256":
            _algo, salt, digest = parts
            got = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
            return hmac.compare_digest(got, digest)
        from passlib.context import CryptContext
        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return ctx.verify(plain, hashed)
    except Exception:
        return False


async def authenticate_platform_user(email: str, password: str) -> dict[str, Any] | None:
    from backend.app.db.canonical_metadata import users
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                users.c.user_id,
                users.c.email,
                users.c.full_name,
                users.c.password_hash,
                users.c.is_active,
                users.c.store_id,
                users.c.created_at,
            )
            .where(func.lower(users.c.email) == str(email or "").strip().lower())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.mappings().first()

    if row is None:
        return None
    if not bool(row.get("is_active", 0)):
        return None
    if not _verify_password(str(password or ""), str(row.get("password_hash", "") or "")):
        return None
    return dict(row)


async def get_platform_user_profile(email: str) -> dict[str, Any] | None:
    from backend.app.db.canonical_metadata import users
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = (
            select(
                users.c.user_id,
                users.c.email,
                users.c.full_name,
                users.c.is_active,
                users.c.store_id,
                users.c.created_at,
            )
            .where(func.lower(users.c.email) == str(email or "").strip().lower())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.mappings().first()
    return dict(row) if row is not None else None


async def get_overview_metrics() -> dict[str, Any]:
    from backend.app.db.canonical_metadata import onfly_walkin_sessions
    from backend.app.db.session import AsyncSessionLocal

    staff_case = case((func.upper(onfly_walkin_sessions.c.role) == "STAFF", 1), else_=0)
    customer_case = case((func.upper(onfly_walkin_sessions.c.role) == "STAFF", 0), else_=1)
    conversion_case = case((func.upper(onfly_walkin_sessions.c.entry_type) == "BILLING", 1), else_=0)

    async with AsyncSessionLocal() as session:
        stmt = select(
            func.count().label("total_walkins"),
            func.coalesce(func.sum(customer_case), 0).label("total_customers"),
            func.coalesce(func.sum(staff_case), 0).label("total_staff"),
            func.coalesce(func.sum(conversion_case), 0).label("total_conversions"),
        )
        result = await session.execute(stmt)
        row = result.mappings().first()

    if not row:
        return {"total_walkins": 0, "total_customers": 0, "total_staff": 0, "conversion_rate": "0%"}

    total_customers = int(row["total_customers"] or 0)
    total_conversions = int(row["total_conversions"] or 0)
    conversion_rate = f"{((total_conversions / max(total_customers, 1)) * 100.0):.1f}%"
    return {
        "total_walkins": int(row["total_walkins"] or 0),
        "total_customers": total_customers,
        "total_staff": int(row["total_staff"] or 0),
        "conversion_rate": conversion_rate,
    }


def _safe_float(value: object) -> float | None:
    try:
        text_val = str(value or "").strip()
        if not text_val:
            return None
        number = float(text_val)
        if math.isnan(number):
            return None
        return number
    except Exception:
        return None


def _summarize_store_metrics(store_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "store_id": store_id,
            "footfall": 0,
            "bounce_rate": "0%",
            "dwell_time": "0 min",
            "status": "No activity recorded.",
        }
    footfall = len(rows)
    conversions = sum(1 for row in rows if str(row.get("entry_type", "") or "").strip().upper() == "BILLING")
    dwell_values = [_safe_float(row.get("time_spent_mins")) for row in rows]
    dwell_values = [v for v in dwell_values if v is not None]
    avg_dwell = float(sum(dwell_values) / len(dwell_values)) if dwell_values else 0.0
    bounce_rate = ((max(footfall - conversions, 0) / max(footfall, 1)) * 100.0)
    return {
        "store_id": store_id,
        "footfall": int(footfall),
        "bounce_rate": f"{bounce_rate:.1f}%",
        "dwell_time": f"{avg_dwell:.1f} min",
        "status": "Success",
    }


async def get_store_metrics(store_id: str) -> dict[str, Any]:
    from backend.app.db.canonical_metadata import onfly_walkin_sessions
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(
            onfly_walkin_sessions.c.role,
            onfly_walkin_sessions.c.entry_type,
            onfly_walkin_sessions.c.time_spent_mins,
        ).where(onfly_walkin_sessions.c.store_id == str(store_id or "").strip())
        result = await session.execute(stmt)
        rows = [dict(r) for r in result.mappings().all()]
    return _summarize_store_metrics(store_id, rows)


async def get_traffic_series(store_id: str | None = None, days: int = 30) -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import onfly_walkin_sessions
    from backend.app.db.session import AsyncSessionLocal

    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    customer_case = case((func.upper(onfly_walkin_sessions.c.role) == "CUSTOMER", 1), else_=0)
    staff_case = case((func.upper(onfly_walkin_sessions.c.role) == "STAFF", 1), else_=0)
    conversion_case = case((func.upper(onfly_walkin_sessions.c.entry_type) == "BILLING", 1), else_=0)

    stmt = (
        select(
            onfly_walkin_sessions.c.business_date.label("date"),
            func.count().label("total"),
            func.coalesce(func.sum(customer_case), 0).label("customers"),
            func.coalesce(func.sum(staff_case), 0).label("staff"),
            func.coalesce(func.sum(conversion_case), 0).label("conversions"),
        )
        .where(onfly_walkin_sessions.c.business_date != "")
        .where(onfly_walkin_sessions.c.business_date >= cutoff)
        .group_by(onfly_walkin_sessions.c.business_date)
        .order_by(onfly_walkin_sessions.c.business_date.desc())
        .limit(days)
    )

    if store_id:
        stmt = stmt.where(onfly_walkin_sessions.c.store_id == str(store_id).strip())

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


async def get_pipeline_runs(limit: int = 50) -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    stmt = (
        select(pipeline_run_log)
        .order_by(pipeline_run_log.c.created_at.desc())
        .limit(int(limit))
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


async def get_walkin_sessions(store_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import onfly_walkin_sessions
    from backend.app.db.session import AsyncSessionLocal

    stmt = (
        select(onfly_walkin_sessions)
        .order_by(onfly_walkin_sessions.c.created_at.desc())
        .limit(int(limit))
    )
    if store_id:
        stmt = stmt.where(onfly_walkin_sessions.c.store_id == str(store_id).strip())

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


async def list_store_registry_stores() -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import stores
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                stores.c.store_id,
                stores.c.store_name,
                stores.c.email,
                stores.c.drive_folder_url,
                stores.c.created_at,
                stores.c.updated_at,
            ).order_by(stores.c.store_id)
        )
        return [dict(r) for r in result.mappings().all()]

from __future__ import annotations

import asyncio
import math
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _run_sync(coro):
    return asyncio.run(coro)


async def _pg_fetch_user_row(email: str) -> dict[str, Any] | None:
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
        return dict(row) if row else None


def authenticate_platform_user(db_path: Path, email: str, password: str) -> dict[str, Any] | None:
    from iris.store_registry import authenticate_user, verify_password

    try:
        row = _run_sync(_pg_fetch_user_row(email))
        if row and bool(row.get("is_active", 0)) and verify_password(password, str(row.get("password_hash", "") or "")):
            return row
    except Exception:
        pass

    user = authenticate_user(db_path, email, password)
    if not user:
        return None
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "store_id": user.store_id,
        "created_at": user.created_at,
    }


def get_platform_user_profile(db_path: Path, email: str) -> dict[str, Any] | None:
    try:
        row = _run_sync(_pg_fetch_user_row(email))
        if row:
            return row
    except Exception:
        pass

    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            "SELECT user_id,email,full_name,is_active,store_id,created_at FROM users WHERE lower(email)=lower(?)",
            (str(email or "").strip(),),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row is not None else None


async def _pg_overview_metrics() -> dict[str, Any]:
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
            return {}
        total_customers = int(row["total_customers"] or 0)
        total_conversions = int(row["total_conversions"] or 0)
        conversion_rate = f"{((total_conversions / max(total_customers, 1)) * 100.0):.1f}%"
        return {
            "total_walkins": int(row["total_walkins"] or 0),
            "total_customers": total_customers,
            "total_staff": int(row["total_staff"] or 0),
            "conversion_rate": conversion_rate,
            "status": "Success",
            "data_source": "postgres",
        }


def _sqlite_overview_metrics(db_path: Path) -> dict[str, Any]:
    conn = _sqlite_connect(db_path)
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='onfly_walkin_sessions'"
        ).fetchone()
        if has_table:
            rows = conn.execute(
                "SELECT role, entry_type FROM onfly_walkin_sessions"
            ).fetchall()
            total_people = int(len(rows))
            staff = sum(1 for row in rows if str(row["role"] or "").strip().upper() == "STAFF")
            customers = total_people - staff
            conversions = sum(1 for row in rows if str(row["entry_type"] or "").strip().upper() == "BILLING")
            return {
                "total_walkins": total_people,
                "total_customers": customers,
                "total_staff": staff,
                "conversion_rate": f"{((conversions / max(customers, 1)) * 100.0):.1f}%",
                "status": "Success",
                "data_source": "sqlite",
            }
    finally:
        conn.close()
    return {
        "total_walkins": 0,
        "total_customers": 0,
        "total_staff": 0,
        "conversion_rate": "0%",
        "status": "No data available.",
        "data_source": "sqlite",
    }


async def get_overview_metrics(db_path: Path) -> dict[str, Any]:
    try:
        pg_metrics = await _pg_overview_metrics()
        if pg_metrics.get("total_walkins", 0):
            return pg_metrics
    except Exception:
        pass
    return _sqlite_overview_metrics(db_path)


async def _pg_store_metrics(store_id: str) -> dict[str, Any]:
    from backend.app.db.canonical_metadata import onfly_walkin_sessions
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(
            onfly_walkin_sessions.c.role,
            onfly_walkin_sessions.c.entry_type,
            onfly_walkin_sessions.c.time_spent_mins,
        ).where(onfly_walkin_sessions.c.store_id == str(store_id or "").strip())
        result = await session.execute(stmt)
        rows = [dict(row) for row in result.mappings().all()]
    return _summarize_store_metrics(store_id, rows, "postgres")


def _safe_float(value: object) -> float | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        number = float(text)
        if math.isnan(number):
            return None
        return number
    except Exception:
        return None


def _summarize_store_metrics(store_id: str, rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
    if not rows:
        return {
            "store_id": store_id,
            "footfall": 0,
            "bounce_rate": "0%",
            "dwell_time": "0 min",
            "status": "No activity recorded.",
            "data_source": source,
        }
    footfall = len(rows)
    conversions = sum(1 for row in rows if str(row.get("entry_type", "") or "").strip().upper() == "BILLING")
    dwell_values = [_safe_float(row.get("time_spent_mins")) for row in rows]
    dwell_values = [value for value in dwell_values if value is not None]
    avg_dwell = float(sum(dwell_values) / len(dwell_values)) if dwell_values else 0.0
    bounce_rate = ((max(footfall - conversions, 0) / max(footfall, 1)) * 100.0)
    return {
        "store_id": store_id,
        "footfall": int(footfall),
        "bounce_rate": f"{bounce_rate:.1f}%",
        "dwell_time": f"{avg_dwell:.1f} min",
        "status": "Success",
        "data_source": source,
    }


def _sqlite_store_metrics(db_path: Path, store_id: str) -> dict[str, Any]:
    conn = _sqlite_connect(db_path)
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='onfly_walkin_sessions'"
        ).fetchone()
        if not has_table:
            return {
                "store_id": store_id,
                "footfall": 0,
                "bounce_rate": "0%",
                "dwell_time": "0 min",
                "status": "No data available.",
                "data_source": "sqlite",
            }
        rows = conn.execute(
            "SELECT role, entry_type, time_spent_mins FROM onfly_walkin_sessions WHERE store_id=?",
            (str(store_id or "").strip(),),
        ).fetchall()
    finally:
        conn.close()
    return _summarize_store_metrics(store_id, [dict(row) for row in rows], "sqlite")


async def get_store_metrics(db_path: Path, store_id: str) -> dict[str, Any]:
    try:
        pg_metrics = await _pg_store_metrics(store_id)
        if pg_metrics.get("footfall", 0):
            return pg_metrics
    except Exception:
        pass
    return _sqlite_store_metrics(db_path, store_id)


def list_store_registry_stores(db_path: Path) -> list[dict[str, Any]]:
    try:
        from backend.app.db.canonical_metadata import stores
        from backend.app.db.session import AsyncSessionLocal

        async def _pg_rows() -> list[dict[str, Any]]:
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
                return [dict(row) for row in result.mappings().all()]

        rows = _run_sync(_pg_rows())
        if rows:
            return rows
    except Exception:
        pass

    conn = _sqlite_connect(db_path)
    try:
        rows = conn.execute(
            "SELECT store_id,store_name,email,drive_folder_url,created_at,updated_at FROM stores ORDER BY store_id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]

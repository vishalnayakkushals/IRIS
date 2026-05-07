from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.platform_data import list_store_registry_stores

router = APIRouter()

_ISO_DATE = """
    CASE
        WHEN business_date GLOB '??-??-????' THEN
            SUBSTR(business_date,7,4)||'-'||SUBSTR(business_date,4,2)||'-'||SUBSTR(business_date,1,2)
        ELSE business_date
    END
"""


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _sqlite_store_metrics(store_id: str) -> dict[str, Any]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return {"store_id": store_id, "footfall": 0, "bounce_rate": "0%", "dwell_time": "0 min", "status": "No data"}
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(f"""
            SELECT
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES' THEN 1 END) AS walkins,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND UPPER(COALESCE(purchase_signal_bag,'')) = 'YES' THEN 1 END) AS conversions,
                AVG(CASE
                    WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND TRIM(COALESCE(time_spent_mins,'')) GLOB '[0-9]*'
                    THEN CAST(time_spent_mins AS REAL) END) AS avg_dwell
            FROM onfly_walkin_sessions
            WHERE store_id = ?
            AND COALESCE(business_date,'') != ''
            AND {_ISO_DATE} >= DATE('now', '-30 days')
        """, (store_id,)).fetchone()
        walkins = int(row["walkins"] or 0)
        conversions = int(row["conversions"] or 0)
        avg_dwell = float(row["avg_dwell"] or 0)
        bounce = round((max(walkins - conversions, 0) / max(walkins, 1)) * 100, 1) if walkins > 0 else 0.0
        return {
            "store_id": store_id,
            "footfall": walkins,
            "bounce_rate": f"{bounce}%",
            "dwell_time": f"{avg_dwell:.1f} min",
            "status": "Success" if walkins > 0 else "No walk-ins recorded yet.",
        }
    finally:
        conn.close()


def _sqlite_walkin_sessions(store_id: str | None, limit: int) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        where = "WHERE COALESCE(business_date,'') != ''"
        params: list[Any] = []
        if store_id:
            where += " AND store_id = ?"
            params.append(store_id)
        params.append(int(limit))
        cur = conn.execute(f"""
            SELECT
                id,
                walkin_id,
                group_id,
                store_id,
                business_date AS date,
                role,
                entry_time,
                exit_time,
                time_spent_mins,
                session_status,
                entry_type,
                gender,
                age_band,
                clothing_style_archetype,
                engagement_type,
                engagement_depth,
                purchase_signal_bag,
                included_in_analytics,
                created_at
            FROM onfly_walkin_sessions
            {where}
            ORDER BY {_ISO_DATE} DESC, entry_time DESC
            LIMIT ?
        """, tuple(params))
        cols = [d[0] for d in (cur.description or [])]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


@router.get("/stores")
async def list_store_options(
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await list_store_registry_stores()
    return {"stores": rows, "total": len(rows)}


@router.get("/walkins")
async def get_walkin_sessions_route(
    store_id: str | None = None,
    limit: int = 500,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = _sqlite_walkin_sessions(store_id, limit)
    return {"sessions": rows, "total": len(rows), "store_id": store_id or "all"}


@router.get("/{store_id}/walkins")
async def get_store_walkin_sessions_route(
    store_id: str,
    limit: int = 500,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = _sqlite_walkin_sessions(store_id, limit)
    return {"sessions": rows, "total": len(rows), "store_id": store_id}


@router.get("/{store_id}/metrics")
async def get_store_metrics_route(
    store_id: str,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    return _sqlite_store_metrics(store_id)

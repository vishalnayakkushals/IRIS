from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.platform_data import get_overview_metrics, get_pipeline_runs, get_traffic_series

router = APIRouter()


# ---------------------------------------------------------------------------
# SQLite helpers — all pipeline analytics come from store_registry.db
# ---------------------------------------------------------------------------

def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# Normalize stored business_date to ISO (YYYY-MM-DD) for date comparisons.
# Pipeline writes DD-MM-YYYY; some older runs wrote YYYY-MM-DD.
# String comparison only works correctly on YYYY-MM-DD, so we convert inline.
_ISO_DATE = """
    CASE
        WHEN business_date GLOB '??-??-????' THEN
            SUBSTR(business_date,7,4)||'-'||SUBSTR(business_date,4,2)||'-'||SUBSTR(business_date,1,2)
        ELSE business_date
    END
"""


def _parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value}. Expected YYYY-MM-DD.") from exc


def _normalize_date_range(
    days: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[str, list[Any], dict[str, Any]]:
    has_from = bool(date_from)
    has_to = bool(date_to)
    if has_from or has_to:
        start = _parse_iso_date(date_from or date_to or "")
        end = _parse_iso_date(date_to or date_from or "")
        if start > end:
            start, end = end, start
        return (
            f"AND {_ISO_DATE} >= ? AND {_ISO_DATE} <= ?",
            [start.isoformat(), end.isoformat()],
            {"mode": "absolute", "date_from": start, "date_to": end, "span_days": (end - start).days + 1},
        )

    if days < 1:
        raise HTTPException(status_code=400, detail="days must be >= 1")

    return (
        "AND {iso_date} >= DATE('now', '-' || ? || ' days')".format(iso_date=_ISO_DATE),
        [days],
        {"mode": "relative", "days": days},
    )


def _sqlite_analytics(
    store_id: str | None = None,
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return {}
    conn = _sqlite_connect(db_path)
    try:
        store_filter = "AND store_id = ?" if store_id else ""
        date_clause, date_params, _ = _normalize_date_range(days=days, date_from=date_from, date_to=date_to)
        params: list[Any] = []
        if store_id:
            params.append(store_id)
        params.extend(date_params)

        # Core KPIs: groups, walkins, avg dwell, conversion rate
        kpi = conn.execute(f"""
            SELECT
                COUNT(DISTINCT CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND COALESCE(group_id,'') != '' THEN group_id END) AS total_groups,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES' THEN 1 END) AS total_walkins,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND entry_type = 'BILLING' THEN 1 END) AS total_conversions,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'STAFF' THEN 1 END) AS total_staff,
                AVG(CASE
                    WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND TRIM(COALESCE(time_spent_mins,'')) GLOB '[0-9]*'
                    THEN CAST(time_spent_mins AS REAL) END) AS avg_dwell_mins
            FROM onfly_walkin_sessions
            WHERE COALESCE(business_date,'') != ''
            {store_filter}
            {date_clause}
        """, tuple(params)).fetchone()

        # Gender breakdown
        gender_rows = conn.execute(f"""
            SELECT
                UPPER(COALESCE(gender,'Unknown')) AS gender,
                COUNT(*) AS cnt
            FROM onfly_walkin_sessions
            WHERE UPPER(COALESCE(role,'')) = 'CUSTOMER'
            AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
            AND COALESCE(business_date,'') != ''
            {store_filter}
            {date_clause}
            GROUP BY gender ORDER BY cnt DESC
        """, tuple(params)).fetchall()

        # Age band breakdown
        age_rows = conn.execute(f"""
            SELECT
                COALESCE(NULLIF(TRIM(age_band),''),'Unknown') AS age_band,
                COUNT(*) AS cnt
            FROM onfly_walkin_sessions
            WHERE UPPER(COALESCE(role,'')) = 'CUSTOMER'
            AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
            AND COALESCE(business_date,'') != ''
            {store_filter}
            {date_clause}
            GROUP BY age_band ORDER BY cnt DESC
        """, tuple(params)).fetchall()

        # Engagement type breakdown
        engagement_rows = conn.execute(f"""
            SELECT
                COALESCE(NULLIF(TRIM(engagement_type),''),'Unknown') AS engagement_type,
                COUNT(*) AS cnt
            FROM onfly_walkin_sessions
            WHERE UPPER(COALESCE(role,'')) = 'CUSTOMER'
            AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
            AND COALESCE(business_date,'') != ''
            {store_filter}
            {date_clause}
            GROUP BY engagement_type ORDER BY cnt DESC LIMIT 8
        """, tuple(params)).fetchall()

        total_walkins = int(kpi["total_walkins"] or 0) if kpi else 0
        total_conversions = int(kpi["total_conversions"] or 0) if kpi else 0

        return {
            "total_groups": int(kpi["total_groups"] or 0) if kpi else 0,
            "total_walkins": total_walkins,
            "total_conversions": total_conversions,
            "total_staff": int(kpi["total_staff"] or 0) if kpi else 0,
            "avg_dwell_mins": round(float(kpi["avg_dwell_mins"] or 0), 1) if kpi else 0,
            "conversion_rate": round(total_conversions / max(total_walkins, 1) * 100, 1),
            "gender": [{"label": r["gender"] or "Unknown", "value": int(r["cnt"])} for r in gender_rows],
            "age_bands": [{"label": r["age_band"], "value": int(r["cnt"])} for r in age_rows],
            "engagement": [{"label": r["engagement_type"], "value": int(r["cnt"])} for r in engagement_rows],
        }
    finally:
        conn.close()


def _sqlite_trend(
    store_id: str | None = None,
    days: int = 30,
    group_by: str = "day",
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        store_filter = "AND store_id = ?" if store_id else ""
        date_clause, date_params, _ = _normalize_date_range(days=days, date_from=date_from, date_to=date_to)
        params: list[Any] = []
        if store_id:
            params.append(store_id)
        params.extend(date_params)

        iso_date = _ISO_DATE
        if group_by == "month":
            period_expr = f"SUBSTR(({iso_date}),1,7)"
        elif group_by == "week":
            period_expr = f"STRFTIME('%Y-W%W', ({iso_date}))"
        else:
            period_expr = f"({iso_date})"

        rows = conn.execute(f"""
            SELECT
                {period_expr} AS period,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES' THEN 1 END) AS walkins,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND entry_type = 'BILLING' THEN 1 END) AS conversions,
                COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'STAFF' THEN 1 END) AS staff,
                AVG(CASE
                    WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                    AND TRIM(COALESCE(time_spent_mins,'')) GLOB '[0-9]*'
                    THEN CAST(time_spent_mins AS REAL) END) AS avg_dwell
            FROM onfly_walkin_sessions
            WHERE COALESCE(business_date,'') != ''
            {store_filter}
            {date_clause}
            GROUP BY period
            ORDER BY period ASC
        """, tuple(params)).fetchall()

        return [
            {
                "period": r["period"],
                "walkins": int(r["walkins"] or 0),
                "conversions": int(r["conversions"] or 0),
                "staff": int(r["staff"] or 0),
                "avg_dwell": round(float(r["avg_dwell"] or 0), 1),
                "conversion_rate": round(int(r["conversions"] or 0) / max(int(r["walkins"] or 0), 1) * 100, 1),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _sqlite_leaderboard(
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        date_clause, date_params, _ = _normalize_date_range(days=days, date_from=date_from, date_to=date_to)
        rows = conn.execute(f"""
            SELECT
                w.store_id,
                s.store_name,
                COUNT(CASE WHEN UPPER(COALESCE(w.role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(w.included_in_analytics,'')) = 'YES' THEN 1 END) AS walkins,
                COUNT(CASE WHEN UPPER(COALESCE(w.role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(w.included_in_analytics,'')) = 'YES'
                    AND w.entry_type = 'BILLING' THEN 1 END) AS conversions,
                COUNT(DISTINCT CASE WHEN UPPER(COALESCE(w.role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(w.included_in_analytics,'')) = 'YES'
                    AND COALESCE(w.group_id,'') != '' THEN w.group_id END) AS groups,
                AVG(CASE
                    WHEN UPPER(COALESCE(w.role,'')) = 'CUSTOMER'
                    AND UPPER(COALESCE(w.included_in_analytics,'')) = 'YES'
                    AND TRIM(COALESCE(w.time_spent_mins,'')) GLOB '[0-9]*'
                    THEN CAST(w.time_spent_mins AS REAL) END) AS avg_dwell
            FROM onfly_walkin_sessions w
            LEFT JOIN stores s ON s.store_id = w.store_id
            WHERE COALESCE(w.business_date,'') != ''
            {date_clause.replace(_ISO_DATE, "(CASE WHEN w.business_date GLOB '??-??-????' THEN SUBSTR(w.business_date,7,4)||'-'||SUBSTR(w.business_date,4,2)||'-'||SUBSTR(w.business_date,1,2) ELSE w.business_date END)")}
            GROUP BY w.store_id, s.store_name
            HAVING walkins > 0
            ORDER BY walkins DESC
            LIMIT 20
        """, tuple(date_params)).fetchall()

        result = []
        for r in rows:
            walkins = int(r["walkins"] or 0)
            conversions = int(r["conversions"] or 0)
            result.append({
                "store_id": r["store_id"],
                "store_name": r["store_name"] or r["store_id"],
                "walkins": walkins,
                "conversions": conversions,
                "groups": int(r["groups"] or 0),
                "avg_dwell": round(float(r["avg_dwell"] or 0), 1),
                "conversion_rate": round(conversions / max(walkins, 1) * 100, 1),
            })
        return result
    finally:
        conn.close()


def _sqlite_delta(
    store_id: str | None,
    current_days: int,
    prior_days: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Compare current period vs prior period."""
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return {}
    conn = _sqlite_connect(db_path)
    try:
        store_filter = "AND store_id = ?" if store_id else ""

        def _fetch_relative_range(start_offset: int, end_offset: int) -> dict:
            p2: list[Any] = []
            if store_id:
                p2.append(store_id)
            p2.extend([start_offset, end_offset])
            row = conn.execute(f"""
                SELECT
                    COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                        AND UPPER(COALESCE(included_in_analytics,'')) = 'YES' THEN 1 END) AS walkins,
                    COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                        AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                        AND entry_type = 'BILLING' THEN 1 END) AS conversions
                FROM onfly_walkin_sessions
                WHERE COALESCE(business_date,'') != ''
                {store_filter}
                AND {_ISO_DATE} >= DATE('now', '-' || ? || ' days')
                AND {_ISO_DATE} < DATE('now', '-' || ? || ' days')
            """, tuple(p2)).fetchone()
            w = int(row["walkins"] or 0)
            c = int(row["conversions"] or 0)
            return {"walkins": w, "conversions": c, "conversion_rate": round(c / max(w, 1) * 100, 1)}

        def _fetch_absolute_range(start: date, end: date) -> dict:
            p3: list[Any] = []
            if store_id:
                p3.append(store_id)
            p3.extend([start.isoformat(), end.isoformat()])
            row = conn.execute(f"""
                SELECT
                    COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                        AND UPPER(COALESCE(included_in_analytics,'')) = 'YES' THEN 1 END) AS walkins,
                    COUNT(CASE WHEN UPPER(COALESCE(role,'')) = 'CUSTOMER'
                        AND UPPER(COALESCE(included_in_analytics,'')) = 'YES'
                        AND entry_type = 'BILLING' THEN 1 END) AS conversions
                FROM onfly_walkin_sessions
                WHERE COALESCE(business_date,'') != ''
                {store_filter}
                AND {_ISO_DATE} >= ?
                AND {_ISO_DATE} <= ?
            """, tuple(p3)).fetchone()
            w = int(row["walkins"] or 0)
            c = int(row["conversions"] or 0)
            return {"walkins": w, "conversions": c, "conversion_rate": round(c / max(w, 1) * 100, 1)}

        if date_from or date_to:
            _, _, range_meta = _normalize_date_range(days=current_days, date_from=date_from, date_to=date_to)
            current_from = range_meta["date_from"]
            current_to = range_meta["date_to"]
            span_days = range_meta["span_days"]
            prior_to_date = current_from - timedelta(days=1)
            prior_from_date = prior_to_date - timedelta(days=span_days - 1)
            current = _fetch_absolute_range(current_from, current_to)
            prior = _fetch_absolute_range(prior_from_date, prior_to_date)
        else:
            current = _fetch_relative_range(current_days, 0)
            prior = _fetch_relative_range(current_days + prior_days, current_days)

        def _delta(curr: float, prev: float) -> float:
            if prev == 0:
                return 0.0
            return round((curr - prev) / prev * 100, 1)

        return {
            "current": current,
            "prior": prior,
            "delta_walkins_pct": _delta(current["walkins"], prior["walkins"]),
            "delta_conversions_pct": _delta(current["conversions"], prior["conversions"]),
            "delta_rate_pct": _delta(current["conversion_rate"], prior["conversion_rate"]),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/traffic")
async def get_traffic_data(
    store_id: str | None = None,
    days: int = 30,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    series = await get_traffic_series(store_id, days)
    series.sort(key=lambda x: x.get("date", ""))
    return {"series": series, "store_id": store_id or "all", "days": days}


@router.get("/pipeline-runs")
async def get_pipeline_runs_route(
    limit: int = 50,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    runs = await get_pipeline_runs(limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/overview")
async def get_dashboard_overview(
    store_id: str | None = None,
    days: int = 90,
    date_from: str | None = None,
    date_to: str | None = None,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    # Read from SQLite (pipeline writes walkin sessions there, not PostgreSQL)
    return _sqlite_analytics(store_id=store_id or None, days=days, date_from=date_from, date_to=date_to)


@router.get("/analytics")
async def get_analytics(
    store_id: str | None = None,
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    return _sqlite_analytics(store_id=store_id, days=days, date_from=date_from, date_to=date_to)


@router.get("/trend")
async def get_trend(
    store_id: str | None = None,
    days: int = 30,
    group_by: str = "day",
    date_from: str | None = None,
    date_to: str | None = None,
    _email: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return _sqlite_trend(store_id=store_id, days=days, group_by=group_by, date_from=date_from, date_to=date_to)


@router.get("/leaderboard")
async def get_leaderboard(
    days: int = 30,
    date_from: str | None = None,
    date_to: str | None = None,
    _email: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return _sqlite_leaderboard(days=days, date_from=date_from, date_to=date_to)


@router.get("/delta")
async def get_delta(
    store_id: str | None = None,
    current_days: int = 7,
    prior_days: int = 7,
    date_from: str | None = None,
    date_to: str | None = None,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    return _sqlite_delta(
        store_id=store_id,
        current_days=current_days,
        prior_days=prior_days,
        date_from=date_from,
        date_to=date_to,
    )

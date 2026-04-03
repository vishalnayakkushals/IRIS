from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def insert_run_log(
    db_path: Path,
    run_id: str,
    job_key: str,
    job_name: str,
    store_id: str,
    triggered_by: str = "scheduler",
    status: str = "running",
) -> None:
    conn = _connect(db_path)
    try:
        now = _now()
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_run_log
                (run_id, job_key, job_name, store_id, status, triggered_by, started_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, job_key, job_name, store_id, status, triggered_by, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def update_run_log_status(
    db_path: Path,
    run_id: str,
    status: str,
    remarks: str = "",
    result_json: str = "{}",
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE pipeline_run_log
               SET status=?, remarks=?, result_json=?, completed_at=?
             WHERE run_id=?
            """,
            (status, remarks, result_json, _now(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_per_job(db_path: Path) -> list[dict[str, Any]]:
    """Return one row per job_key (the most recent run for each job)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT r.*
              FROM pipeline_run_log r
             INNER JOIN (
                 SELECT job_key, MAX(created_at) AS max_at
                   FROM pipeline_run_log
                  GROUP BY job_key
             ) latest ON r.job_key = latest.job_key AND r.created_at = latest.max_at
             ORDER BY r.job_key
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_runs(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_run_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

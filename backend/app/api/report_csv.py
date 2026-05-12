from __future__ import annotations

import csv
import io
import threading
import uuid
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


_EXPORT_TTL_SECONDS = 600
_export_jobs: dict[str, dict[str, Any]] = {}
_export_jobs_lock = threading.Lock()


def rows_to_csv_response(rows: list[dict[str, Any]], filename: str) -> StreamingResponse:
    cols = list(rows[0].keys()) if rows else []
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols)
    if cols:
        writer.writeheader()
        writer.writerows(rows)
    payload = io.BytesIO(buf.getvalue().encode("utf-8"))
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(payload, media_type="text/csv; charset=utf-8", headers=headers)


def cleanup_old_export_jobs() -> None:
    cutoff = datetime.utcnow().timestamp() - _EXPORT_TTL_SECONDS
    with _export_jobs_lock:
        stale = [jid for jid, job in _export_jobs.items() if job["ts"] < cutoff]
        for jid in stale:
            _export_jobs.pop(jid, None)


def start_export_job(
    *,
    export_type: str,
    store_id: str | None,
    business_date: str | None,
    exporters: dict[str, Callable[[str | None, str | None], tuple[list[dict[str, Any]], str]]],
) -> str:
    cleanup_old_export_jobs()
    job_id = uuid.uuid4().hex[:20]
    with _export_jobs_lock:
        _export_jobs[job_id] = {"status": "pending", "data": None, "filename": "", "ts": datetime.utcnow().timestamp()}

    def _runner() -> None:
        try:
            exporter = exporters[export_type]
            rows, filename = exporter(store_id, business_date)
            cols = list(rows[0].keys()) if rows else []
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=cols)
            if cols:
                writer.writeheader()
                writer.writerows(rows)
            data = buf.getvalue().encode("utf-8")
            with _export_jobs_lock:
                _export_jobs[job_id].update({"status": "ready", "data": data, "filename": filename})
        except Exception as exc:
            with _export_jobs_lock:
                if job_id in _export_jobs:
                    _export_jobs[job_id].update({"status": "failed", "error": str(exc)})

    threading.Thread(target=_runner, daemon=True).start()
    return job_id


def get_export_status(job_id: str) -> dict[str, str]:
    job = _export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found or expired")
    return {
        "status": str(job["status"]),
        "filename": str(job.get("filename", "")),
        "error": str(job.get("error", "")),
    }


def get_export_download(job_id: str) -> StreamingResponse:
    job = _export_jobs.get(job_id)
    if not job or job["status"] != "ready" or not job.get("data"):
        raise HTTPException(status_code=404, detail="Export not ready or expired")
    data: bytes = job["data"]
    filename = str(job.get("filename", "export.csv"))
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(data), media_type="text/csv; charset=utf-8", headers=headers)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings, get_settings
from backend.app.db.pipeline_log import get_latest_per_job, insert_run_log
from backend.app.models.jobs import JobStatus, TriggerResponse

router = APIRouter()

# Static job definitions — display order matches the scheduler dashboard table
JOBS: list[dict[str, str]] = [
    {"key": "drive_sync",   "name": "Pull Images From Drive"},
    {"key": "yolo_scan",    "name": "Run YOLO Relevance Scan"},
    {"key": "gpt_analysis", "name": "Run GPT Vision Analysis"},
    {"key": "report",       "name": "Generate Report"},
]


def _make_run_id(job_key: str) -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{job_key}_{ts}"


def _enrich_jobs(latest: list[dict[str, Any]]) -> list[JobStatus]:
    by_key = {r["job_key"]: r for r in latest}
    result = []
    for job in JOBS:
        row = by_key.get(job["key"])
        if row:
            js = JobStatus(
                key=job["key"],
                name=job["name"],
                status=row["status"],
                remarks=row.get("remarks", ""),
                last_run_at=row.get("started_at") or row.get("created_at"),
                triggered_by=row.get("triggered_by"),
                run_id=row.get("run_id"),
            )
        else:
            js = JobStatus(
                key=job["key"],
                name=job["name"],
                status="idle",
                remarks="Never run",
                last_run_at=None,
                triggered_by=None,
                run_id=None,
            )
        result.append(js)
    return result


@router.get("/jobs", response_model=list[JobStatus])
def list_jobs(
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> list[JobStatus]:
    latest = get_latest_per_job(settings.db_path_obj)
    return _enrich_jobs(latest)


@router.post("/jobs/trigger-all", response_model=TriggerResponse)
def trigger_all(
    email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TriggerResponse:
    from backend.app.celery_app.tasks.drive_sync import drive_sync_task

    run_id = _make_run_id("drive_sync")
    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="drive_sync",
        job_name="Pull Images From Drive",
        store_id=settings.store_id,
        triggered_by="manual",
        status="queued",
    )
    drive_sync_task.delay(
        store_id=settings.store_id,
        triggered_by="manual",
        chain=True,
        run_id=run_id,
    )
    return TriggerResponse(
        run_id=run_id,
        job_key="drive_sync",
        status="queued",
        message="Full pipeline queued: Drive Sync → YOLO → GPT → Report",
    )


@router.post("/jobs/{job_key}/trigger", response_model=TriggerResponse)
def trigger_job(
    job_key: str,
    email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TriggerResponse:
    job_map = {j["key"]: j["name"] for j in JOBS}
    if job_key not in job_map:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown job: {job_key}")

    run_id = _make_run_id(job_key)
    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key=job_key,
        job_name=job_map[job_key],
        store_id=settings.store_id,
        triggered_by="manual",
        status="queued",
    )

    if job_key == "drive_sync":
        from backend.app.celery_app.tasks.drive_sync import drive_sync_task
        drive_sync_task.delay(store_id=settings.store_id, triggered_by="manual", chain=False, run_id=run_id)
    elif job_key == "yolo_scan":
        from backend.app.celery_app.tasks.yolo_scan import yolo_scan_task
        yolo_scan_task.delay(store_id=settings.store_id, triggered_by="manual", chain=False, run_id=run_id)
    elif job_key == "gpt_analysis":
        from backend.app.celery_app.tasks.gpt_analysis import gpt_analysis_task
        gpt_analysis_task.delay(store_id=settings.store_id, triggered_by="manual", run_id=run_id)
    elif job_key == "report":
        from backend.app.celery_app.tasks.report import report_task
        report_task.delay(store_id=settings.store_id, triggered_by="manual", run_id=run_id)

    return TriggerResponse(
        run_id=run_id,
        job_key=job_key,
        status="queued",
        message=f"{job_map[job_key]} queued successfully",
    )

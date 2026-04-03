from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "iris_pipeline",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "backend.app.celery_app.tasks.drive_sync",
        "backend.app.celery_app.tasks.yolo_scan",
        "backend.app.celery_app.tasks.gpt_analysis",
        "backend.app.celery_app.tasks.report",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_default_retry_delay=60,
    task_max_retries=2,
    worker_max_tasks_per_child=50,
    task_annotations={
        "backend.app.celery_app.tasks.gpt_analysis.gpt_analysis_task": {"rate_limit": "10/m"}
    },
    beat_schedule={
        # Hourly: lightweight YOLO check for new images
        "hourly-yolo-scan": {
            "task": "backend.app.celery_app.tasks.yolo_scan.yolo_scan_task",
            "schedule": crontab(minute=0),
            "kwargs": {
                "store_id": os.getenv("STORE_ID", "TEST_STORE_D07"),
                "triggered_by": "scheduler",
                "chain": True,
            },
        },
        # Midnight IST: full pipeline (Drive Sync → YOLO → GPT → Report)
        "midnight-full-pipeline": {
            "task": "backend.app.celery_app.tasks.drive_sync.drive_sync_task",
            "schedule": crontab(hour=0, minute=0),
            "kwargs": {
                "store_id": os.getenv("STORE_ID", "TEST_STORE_D07"),
                "triggered_by": "scheduler",
                "chain": True,
            },
        },
    },
)

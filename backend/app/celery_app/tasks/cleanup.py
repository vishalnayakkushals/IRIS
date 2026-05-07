from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[4] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from backend.app.celery_app.worker import celery_app
from backend.app.config import get_settings
from backend.app.db.pipeline_log import insert_run_log, update_run_log_status


def _now_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


@celery_app.task(bind=True, max_retries=1, name="backend.app.celery_app.tasks.cleanup.cleanup_old_images_task")
def cleanup_old_images_task(
    self,
    store_id: str = "ALL",
    triggered_by: str = "scheduler",
    retention_days: int = 7,
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not run_id:
        run_id = f"cleanup_{store_id}_{_now_id()}"

    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="cleanup",
        job_name=f"Short Retention Image Cleanup ({retention_days} days)",
        store_id=store_id,
        triggered_by=triggered_by,
        status="running",
    )

    try:
        data_root = settings.data_root_obj / "stores"
        if not data_root.exists():
            update_run_log_status(settings.db_path_obj, run_id, "done", remarks="No stores directory found.")
            return {"run_id": run_id, "status": "done", "deleted": 0}

        now = time.time()
        cutoff = now - (retention_days * 86400)
        
        deleted_count = 0
        freed_bytes = 0

        store_dirs = [d for d in data_root.iterdir() if d.is_dir()]
        if store_id != "ALL":
            store_dirs = [d for d in store_dirs if d.name == store_id]

        for s_dir in store_dirs:
            for p in s_dir.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    try:
                        stat = p.stat()
                        # If file is older than retention_days
                        if stat.st_mtime < cutoff:
                            freed_bytes += stat.st_size
                            p.unlink()
                            deleted_count += 1
                    except Exception:
                        pass
        
        freed_mb = freed_bytes / (1024 * 1024)
        remarks = f"Deleted {deleted_count} files older than {retention_days} days. Freed {freed_mb:.2f} MB."
        
        result_json = json.dumps({
            "deleted_count": deleted_count,
            "freed_mb": round(freed_mb, 2),
            "retention_days": retention_days
        })
        
        update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks, result_json=result_json)
        return {"run_id": run_id, "status": "done", "deleted": deleted_count, "freed_mb": freed_mb}

    except Exception as exc:
        err = str(exc)
        update_run_log_status(
            settings.db_path_obj, run_id, "failed", remarks=f"Cleanup failed: {err}"
        )
        return {"run_id": run_id, "status": "failed", "error": err}

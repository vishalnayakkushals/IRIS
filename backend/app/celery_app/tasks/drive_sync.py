from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing src/iris modules
_SRC = Path(__file__).resolve().parents[4] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from backend.app.celery_app.worker import celery_app
from backend.app.config import get_settings
from backend.app.db.pipeline_log import insert_run_log, update_run_log_status


def _now_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


@celery_app.task(bind=True, max_retries=2, name="backend.app.celery_app.tasks.drive_sync.drive_sync_task")
def drive_sync_task(
    self,
    store_id: str = "TEST_STORE_D07",
    triggered_by: str = "scheduler",
    chain: bool = False,
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not run_id:
        run_id = f"drive_sync_{store_id}_{_now_id()}"

    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="drive_sync",
        job_name="Pull Images From Drive",
        store_id=store_id,
        triggered_by=triggered_by,
        status="running",
    )

    try:
        from iris.store_registry import list_stores
        from iris.drive_delta_sync import sync_store_gdrive_delta

        api_key = settings.google_api_key or os.getenv("GOOGLE_API_KEY", "")
        data_root = settings.data_root_obj / "stores"
        data_root.mkdir(parents=True, exist_ok=True)

        stores = list_stores(settings.db_path_obj)
        target = next((s for s in stores if s.store_id == store_id), None)

        if not target or not target.drive_folder_url:
            # No store configured — skip gracefully
            remarks = f"No Drive URL configured for store {store_id}. Skipped sync."
            update_run_log_status(
                settings.db_path_obj, run_id, "done", remarks=remarks, result_json=json.dumps({"skipped": True})
            )
            if chain:
                from backend.app.celery_app.tasks.yolo_scan import yolo_scan_task
                yolo_scan_task.delay(store_id=store_id, triggered_by=triggered_by, chain=True)
            return {"run_id": run_id, "status": "done", "skipped": True, "remarks": remarks}

        result = sync_store_gdrive_delta(
            db_path=settings.db_path_obj,
            data_root=data_root,
            store=target,
            api_key=api_key,
            workers=4,
        )

        remarks = (
            f"Synced {result.downloaded_new} new files | "
            f"Listed: {result.listed_files} | "
            f"Reused: {result.reused_existing} | "
            f"Scope: {result.scope_date}"
        )
        result_json = json.dumps({
            "downloaded_new": result.downloaded_new,
            "listed_files": result.listed_files,
            "reused_existing": result.reused_existing,
            "scope_date": result.scope_date,
            "elapsed_sec": result.elapsed_sec,
        })
        update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks, result_json=result_json)

        if chain:
            from backend.app.celery_app.tasks.yolo_scan import yolo_scan_task
            yolo_scan_task.delay(store_id=store_id, triggered_by=triggered_by, chain=True)

        return {"run_id": run_id, "status": "done", "downloaded_new": result.downloaded_new}

    except Exception as exc:
        err = str(exc)
        update_run_log_status(
            settings.db_path_obj, run_id, "failed", remarks=f"Drive sync failed: {err}"
        )
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            return {"run_id": run_id, "status": "failed", "error": err}

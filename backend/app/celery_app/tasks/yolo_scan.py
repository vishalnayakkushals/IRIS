from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[5] / "src"
_SCRIPTS = Path(__file__).resolve().parents[5] / "scripts"
for _p in (_SRC, _SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backend.app.celery_app.worker import celery_app
from backend.app.config import get_settings
from backend.app.db.pipeline_log import insert_run_log, update_run_log_status


def _now_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


@celery_app.task(bind=True, max_retries=2, name="backend.app.celery_app.tasks.yolo_scan.yolo_scan_task")
def yolo_scan_task(
    self,
    store_id: str = "TEST_STORE_D07",
    triggered_by: str = "scheduler",
    chain: bool = False,
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not run_id:
        run_id = f"yolo_scan_{store_id}_{_now_id()}"

    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="yolo_scan",
        job_name="Run YOLO Relevance Scan",
        store_id=store_id,
        triggered_by=triggered_by,
        status="running",
    )

    try:
        from yolo_relevance_scan import run_stage1_scan  # noqa: E402

        root_dir = settings.data_root_obj / "test_stores"
        out_dir = settings.data_root_obj / "exports" / "current" / "stage1_relevance"
        store_report = settings.data_root_obj / "exports" / "current" / "vision_eval" / "store_report.csv"

        args = argparse.Namespace(
            root=root_dir,
            out_dir=out_dir,
            store_id=store_id,
            conf=settings.yolo_conf,
            detector="yolo",
            allow_detector_fallback=False,
            max_images=0,
            gzip_exports=False,
            drop_plain_csv=False,
            store_report=store_report,
        )

        summary = run_stage1_scan(args)

        total = summary.get("total_images_discovered", 0)
        relevant = summary.get("relevant_images", 0)
        capture_date = summary.get("latest_date", "")

        date_part = f"Date: {capture_date} | " if capture_date else ""
        remarks = f"{date_part}{relevant} relevant of {total} images scanned"

        result_json = json.dumps({
            "total": total,
            "relevant": relevant,
            "irrelevant": summary.get("irrelevant_images", 0),
            "relevant_pct": summary.get("relevant_percent", 0.0),
            "capture_date": capture_date,
        })
        update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks, result_json=result_json)

        if chain and relevant > 0:
            from backend.app.celery_app.tasks.gpt_analysis import gpt_analysis_task
            gpt_analysis_task.delay(
                store_id=store_id,
                relevant_count=relevant,
                triggered_by=triggered_by,
                chain=True,
            )

        return {"run_id": run_id, "status": "done", "total": total, "relevant": relevant}

    except Exception as exc:
        err = str(exc)
        update_run_log_status(
            settings.db_path_obj, run_id, "failed",
            remarks=f"YOLO scan failed: {err}",
        )
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            return {"run_id": run_id, "status": "failed", "error": err}

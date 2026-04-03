from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[5] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from backend.app.celery_app.worker import celery_app
from backend.app.config import get_settings
from backend.app.db.pipeline_log import insert_run_log, update_run_log_status


def _now_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


@celery_app.task(
    bind=True,
    max_retries=2,
    rate_limit="10/m",
    name="backend.app.celery_app.tasks.gpt_analysis.gpt_analysis_task",
)
def gpt_analysis_task(
    self,
    store_id: str = "TEST_STORE_D07",
    relevant_count: int = 0,
    triggered_by: str = "scheduler",
    chain: bool = False,
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not run_id:
        run_id = f"gpt_analysis_{store_id}_{_now_id()}"

    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="gpt_analysis",
        job_name="Run GPT Vision Analysis",
        store_id=store_id,
        triggered_by=triggered_by,
        status="running",
    )

    try:
        openai_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        source_url = settings.onfly_source_url or os.getenv("ONFLY_SOURCE_URL", "")

        if not openai_key:
            remarks = "GPT skipped: OPENAI_API_KEY not set"
            update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks)
            if chain:
                from backend.app.celery_app.tasks.report import report_task
                report_task.delay(store_id=store_id, triggered_by=triggered_by)
            return {"run_id": run_id, "status": "done", "skipped": True, "remarks": remarks}

        if not source_url:
            remarks = "GPT skipped: ONFLY_SOURCE_URL not configured"
            update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks)
            if chain:
                from backend.app.celery_app.tasks.report import report_task
                report_task.delay(store_id=store_id, triggered_by=triggered_by)
            return {"run_id": run_id, "status": "done", "skipped": True, "remarks": remarks}

        from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline  # noqa: E402

        out_dir = settings.data_root_obj / "exports" / "current" / "onfly"
        cfg = OnFlyConfig(
            store_id=store_id,
            source_uri=source_url,
            db_path=settings.db_path_obj,
            out_dir=out_dir,
            detector_type="yolo",
            conf_threshold=settings.yolo_conf,
            max_images=settings.max_images,
            gpt_enabled=True,
            openai_api_key=openai_key,
            openai_model=settings.openai_model,
            pipeline_version=f"celery_v1_{run_id}",
            allow_detector_fallback=False,
            force_reprocess=False,
            run_mode="manual" if triggered_by == "manual" else "scheduled",
        )

        result = run_onfly_pipeline(cfg)

        customers = result.get("gpt_customer_count_total", 0)
        staff = result.get("gpt_staff_count_total", 0)
        gpt_done = result.get("gpt_done", 0)
        capture_date = result.get("latest_date", "")

        date_part = f"{capture_date}: " if capture_date else ""
        remarks = (
            f"{date_part}{customers} customers, {staff} staff identified. "
            f"{gpt_done} images analysed via GPT."
        )
        result_json = json.dumps({
            "customers": customers,
            "staff": staff,
            "gpt_done": gpt_done,
            "capture_date": capture_date,
            "yolo_relevant": result.get("yolo_relevant", 0),
        })
        update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks, result_json=result_json)

        if chain:
            from backend.app.celery_app.tasks.report import report_task
            report_task.delay(store_id=store_id, triggered_by=triggered_by)

        return {"run_id": run_id, "status": "done", "customers": customers, "staff": staff}

    except Exception as exc:
        err = str(exc)
        is_rate_limit = "rate limit" in err.lower() or "429" in err
        countdown = 120 if is_rate_limit else 60
        update_run_log_status(
            settings.db_path_obj, run_id, "failed",
            remarks=f"GPT analysis failed: {err}",
        )
        try:
            raise self.retry(exc=exc, countdown=countdown * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {"run_id": run_id, "status": "failed", "error": err}

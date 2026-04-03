from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[5] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from backend.app.celery_app.worker import celery_app
from backend.app.config import get_settings
from backend.app.db.pipeline_log import insert_run_log, update_run_log_status


def _now_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")


@celery_app.task(bind=True, max_retries=1, name="backend.app.celery_app.tasks.report.report_task")
def report_task(
    self,
    store_id: str = "TEST_STORE_D07",
    triggered_by: str = "scheduler",
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    if not run_id:
        run_id = f"report_{store_id}_{_now_id()}"

    insert_run_log(
        settings.db_path_obj,
        run_id=run_id,
        job_key="report",
        job_name="Generate Report",
        store_id=store_id,
        triggered_by=triggered_by,
        status="running",
    )

    try:
        from stage1_store_report import run_stage1_report  # noqa: E402

        out_dir = settings.data_root_obj / "exports" / "current" / "vision_eval"
        report_csv = out_dir / "store_report.csv"
        relevance_csv = settings.data_root_obj / "exports" / "current" / "stage1_relevance" / "stage1_relevance_all.csv"

        if not relevance_csv.exists():
            relevance_csv_gz = relevance_csv.with_suffix(".csv.gz")
            if relevance_csv_gz.exists():
                relevance_csv = relevance_csv_gz

        if not relevance_csv.exists():
            remarks = "No relevance data found — run YOLO scan first"
            update_run_log_status(settings.db_path_obj, run_id, "done", remarks=remarks)
            return {"run_id": run_id, "status": "done", "skipped": True}

        run_stage1_report(
            relevance_csv=str(relevance_csv),
            report_csv=str(report_csv),
        )

        remarks = f"Report saved: {report_csv}"
        update_run_log_status(
            settings.db_path_obj, run_id, "done", remarks=remarks,
            result_json=json.dumps({"report_path": str(report_csv)})
        )
        return {"run_id": run_id, "status": "done", "report_path": str(report_csv)}

    except Exception as exc:
        err = str(exc)
        update_run_log_status(
            settings.db_path_obj, run_id, "failed",
            remarks=f"Report generation failed: {err}",
        )
        return {"run_id": run_id, "status": "failed", "error": err}

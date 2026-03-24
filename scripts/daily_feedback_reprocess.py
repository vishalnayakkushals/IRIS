from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd

from iris.iris_analysis import analyze_root, export_analysis
from iris.store_registry import (
    get_app_settings,
    list_qa_feedback,
    list_stores,
    promote_model_version,
    register_model_version,
    upsert_app_settings,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily feedback-aware retrain + reprocess cycle")
    p.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    p.add_argument("--root", type=Path, default=Path("data/stores"))
    p.add_argument("--out", type=Path, default=Path("data/exports/current"))
    p.add_argument("--store-id", default="", help="Optional single-store run")
    p.add_argument("--min-new-feedback", type=int, default=10)
    p.add_argument("--detector", choices=["yolo", "mock"], default="yolo")
    p.add_argument("--conf", type=float, default=0.18)
    p.add_argument(
        "--capture-date",
        default="",
        help="Optional capture date filter (YYYY-MM-DD or YYYYMMDD). Empty = all dates.",
    )
    p.add_argument("--summary", type=Path, default=Path("data/exports/current/eod_feedback_summary.json"))
    p.add_argument(
        "--force-retrain",
        action="store_true",
        help="Ignore feedback watermark and retrain from all confirmed feedback rows.",
    )
    return p.parse_args()


def _retrain_store_feedback_rules(
    db_path: Path,
    store_id: str,
    min_new_feedback: int,
    force_retrain: bool = False,
) -> dict[str, object]:
    settings = get_app_settings(db_path)
    key_last = f"qa_last_retrain_feedback_id__{store_id}"
    key_model = f"qa_active_model_id__{store_id}"
    try:
        last_feedback_id = int(str(settings.get(key_last, "0") or "0"))
    except Exception:
        last_feedback_id = 0
    confirmed_rows = list_qa_feedback(
        db_path=db_path,
        store_id=store_id,
        review_status="confirmed",
        limit=200000,
    )
    new_rows = [row for row in confirmed_rows if int(row.get("id", 0) or 0) > last_feedback_id]
    eligible_rows = confirmed_rows if bool(force_retrain) else new_rows
    eligible_ids = sorted(int(row.get("id", 0) or 0) for row in eligible_rows)
    payload: dict[str, object] = {
        "store_id": store_id,
        "retrain_mode": "force_all_confirmed" if bool(force_retrain) else "incremental_new_only",
        "last_retrain_feedback_id": int(last_feedback_id),
        "confirmed_total": int(len(confirmed_rows)),
        "new_confirmed_rows": int(len(new_rows)),
        "eligible_feedback_rows": int(len(eligible_rows)),
        "eligible_feedback_ids_sample": eligible_ids[:20],
        "retrained": False,
        "model_id": "",
    }
    if len(eligible_rows) < int(max(1, min_new_feedback)):
        payload["skip_reason"] = (
            f"eligible_feedback_rows<{int(max(1, min_new_feedback))}"
        )
        return payload

    label_counts: dict[str, int] = {}
    for row in eligible_rows:
        label = str(row.get("corrected_label", "") or "").strip().lower() or "unknown"
        label_counts[label] = int(label_counts.get(label, 0)) + 1
    version_tag = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    artifact_path = db_path.parent / "models" / f"qa_feedback_rules_{store_id}_{version_tag}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "store_id": store_id,
        "version_tag": version_tag,
        "new_feedback_rows": len(new_rows),
        "eligible_feedback_rows": len(eligible_rows),
        "force_retrain": bool(force_retrain),
        "last_retrain_feedback_id": int(last_feedback_id),
        "label_counts": label_counts,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    artifact_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    model_name = f"iris_feedback_rules_{store_id}"
    model_id = register_model_version(
        db_path=db_path,
        model_name=model_name,
        version_tag=version_tag,
        metrics_json=json.dumps(metrics),
        status="candidate",
        artifact_path=str(artifact_path),
    )
    promote_model_version(db_path=db_path, model_name=model_name, model_id=model_id)
    max_feedback_id = max(int(row.get("id", 0) or 0) for row in eligible_rows)
    upsert_app_settings(
        db_path=db_path,
        settings={
            key_last: str(max_feedback_id),
            key_model: str(model_id),
        },
    )
    payload["retrained"] = True
    payload["model_id"] = str(model_id)
    payload["artifact_path"] = str(artifact_path)
    payload["label_counts"] = label_counts
    payload["used_feedback_rows"] = int(len(eligible_rows))
    payload["new_watermark_feedback_id"] = int(max_feedback_id)
    return payload


def main() -> None:
    args = parse_args()
    capture_date_filter: date | None = None
    raw_capture_date = str(args.capture_date or "").strip()
    if raw_capture_date:
        normalized = raw_capture_date
        if len(normalized) == 8 and normalized.isdigit():
            normalized = f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}"
        try:
            capture_date_filter = date.fromisoformat(normalized)
        except ValueError as exc:
            raise SystemExit(
                f"Invalid --capture-date '{raw_capture_date}'. Use YYYY-MM-DD or YYYYMMDD."
            ) from exc

    if args.store_id.strip():
        target_stores = [args.store_id.strip()]
    else:
        target_stores = [store.store_id for store in list_stores(args.db)]
    retrain_summary = [
        _retrain_store_feedback_rules(
            db_path=args.db,
            store_id=store_id,
            min_new_feedback=int(args.min_new_feedback),
            force_retrain=bool(args.force_retrain),
        )
        for store_id in target_stores
    ]

    output = analyze_root(
        root_dir=args.root,
        detector_type=args.detector,
        conf_threshold=float(args.conf),
        store_filter=args.store_id.strip() or None,
        capture_date_filter=capture_date_filter,
        max_images_per_store=None,
    )
    export_analysis(output=output, out_dir=args.out)

    summary = {
        "run_at": pd.Timestamp.utcnow().isoformat(),
        "stores_considered": target_stores,
        "capture_date_filter": capture_date_filter.isoformat() if capture_date_filter else "",
        "retrain_summary": retrain_summary,
        "stores_analyzed": int(len(output.stores)),
        "detector_warning": str(output.detector_warning or ""),
        "summary_csv": str((args.out / "all_stores_summary.csv").resolve()),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

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
    p.add_argument("--summary", type=Path, default=Path("data/exports/current/eod_feedback_summary.json"))
    return p.parse_args()


def _retrain_store_feedback_rules(
    db_path: Path,
    store_id: str,
    min_new_feedback: int,
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
    payload: dict[str, object] = {
        "store_id": store_id,
        "confirmed_total": int(len(confirmed_rows)),
        "new_confirmed_rows": int(len(new_rows)),
        "retrained": False,
        "model_id": "",
    }
    if len(new_rows) < int(max(1, min_new_feedback)):
        return payload

    label_counts: dict[str, int] = {}
    for row in new_rows:
        label = str(row.get("corrected_label", "") or "").strip().lower() or "unknown"
        label_counts[label] = int(label_counts.get(label, 0)) + 1
    version_tag = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    artifact_path = db_path.parent / "models" / f"qa_feedback_rules_{store_id}_{version_tag}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "store_id": store_id,
        "version_tag": version_tag,
        "new_feedback_rows": len(new_rows),
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
    max_feedback_id = max(int(row.get("id", 0) or 0) for row in new_rows)
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
    return payload


def main() -> None:
    args = parse_args()
    if args.store_id.strip():
        target_stores = [args.store_id.strip()]
    else:
        target_stores = [store.store_id for store in list_stores(args.db)]
    retrain_summary = [
        _retrain_store_feedback_rules(
            db_path=args.db,
            store_id=store_id,
            min_new_feedback=int(args.min_new_feedback),
        )
        for store_id in target_stores
    ]

    output = analyze_root(
        root_dir=args.root,
        detector_type=args.detector,
        conf_threshold=float(args.conf),
        store_filter=args.store_id.strip() or None,
        capture_date_filter=date.today(),
        max_images_per_store=None,
    )
    export_analysis(output=output, out_dir=args.out)

    summary = {
        "run_at": pd.Timestamp.utcnow().isoformat(),
        "stores_considered": target_stores,
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

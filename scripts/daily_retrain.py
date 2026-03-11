from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.store_registry import register_model_version, promote_model_version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily lightweight retrain/calibration job")
    p.add_argument("--dataset", type=Path, default=Path("data/training/daily_dataset.csv"))
    p.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    p.add_argument("--model-name", default="iris_customer_model")
    p.add_argument("--artifact", type=Path, default=Path("data/models/iris_customer_model_latest.json"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dataset.exists():
        raise FileNotFoundError(f"dataset not found: {args.dataset}")

    df = pd.read_csv(args.dataset)
    total = max(1, len(df))
    valid_rate = float(df.get("is_valid", pd.Series(dtype=float)).fillna(0).mean()) if "is_valid" in df.columns else 0.0
    relevant_rate = float(df.get("relevant", pd.Series(dtype=float)).fillna(0).mean()) if "relevant" in df.columns else 0.0
    avg_people = float(df.get("person_count", pd.Series(dtype=float)).fillna(0).mean()) if "person_count" in df.columns else 0.0

    error_rate = max(0.0, 1.0 - valid_rate)
    model_payload = {
        "valid_rate": valid_rate,
        "relevant_rate": relevant_rate,
        "avg_people": avg_people,
        "error_rate": error_rate,
        "trained_rows": total,
    }

    args.artifact.parent.mkdir(parents=True, exist_ok=True)
    args.artifact.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")

    version_tag = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    model_id = register_model_version(
        db_path=args.db,
        model_name=args.model_name,
        version_tag=version_tag,
        metrics_json=json.dumps(model_payload),
        artifact_path=str(args.artifact),
        status="candidate",
    )
    promote_model_version(args.db, args.model_name, model_id)
    print(f"Registered and promoted model {model_id} with metrics={model_payload}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from yolo_relevance_scan import _build_store_date_report, _upsert_store_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate Stage-1 store/date aggregated report from relevance output.")
    parser.add_argument(
        "--stage1-all",
        type=Path,
        default=app_dir / "data" / "exports" / "current" / "stage1_relevance" / "stage1_relevance_all.csv.gz",
        help="Input Stage-1 all-images file (.csv or .csv.gz).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=app_dir / "data" / "exports" / "current" / "vision_eval" / "store_report.csv",
        help="Output aggregated report CSV path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stage1_all = args.stage1_all.resolve()
    if not stage1_all.exists():
        raise FileNotFoundError(f"Stage-1 all-images file not found: {stage1_all}")
    stage1_df = pd.read_csv(stage1_all)
    report_df = _build_store_date_report(stage1_df=stage1_df)
    merged, csv_path, json_path = _upsert_store_report(report_df=report_df, report_path=args.out)
    print("Stage-1 store report generated.")
    print(f"Rows: {len(merged)}")
    print(f"CSV: {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()

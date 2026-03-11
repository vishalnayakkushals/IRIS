from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build training dataset from per-store image insights exports")
    p.add_argument("--out", type=Path, default=Path("data/exports/current"))
    p.add_argument("--dataset", type=Path, default=Path("data/training/daily_dataset.csv"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.dataset.parent.mkdir(parents=True, exist_ok=True)
    rows: list[pd.DataFrame] = []
    for path in sorted(args.out.glob("store_*_image_insights.csv")):
        df = pd.read_csv(path)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["day"] = df["timestamp"].dt.date.astype("string")
        else:
            df["day"] = ""
        keep = [c for c in ["store_id", "camera_id", "day", "person_count", "relevant", "is_valid", "bag_count", "track_ids"] if c in df.columns]
        rows.append(df[keep].copy())

    if not rows:
        pd.DataFrame(columns=["store_id", "camera_id", "day", "person_count", "relevant", "is_valid", "bag_count", "track_ids"]).to_csv(args.dataset, index=False)
        print(f"No source files found. Empty dataset created at {args.dataset}")
        return

    dataset = pd.concat(rows, ignore_index=True)
    dataset.to_csv(args.dataset, index=False)
    print(f"Dataset rows={len(dataset)} written to {args.dataset}")


if __name__ == "__main__":
    main()

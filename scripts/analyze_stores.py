from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.iris_analysis import analyze_root, export_analysis


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Analyze store folders and export customer/hotspot insights."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=app_dir / "data" / "stores",
        help="Root folder containing one subfolder per store.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=app_dir / "data" / "exports" / "current",
        help="Output folder where CSV exports will be written.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Person detection confidence threshold.",
    )
    parser.add_argument(
        "--detector",
        choices=["yolo", "mock"],
        default="yolo",
        help="Detector backend. 'yolo' uses YOLOv8n; 'mock' is deterministic local fallback.",
    )
    parser.add_argument(
        "--time-bucket",
        type=int,
        default=1,
        help="Time bucket in minutes for peak-time aggregation.",
    )
    parser.add_argument(
        "--bounce-threshold-sec",
        type=int,
        default=120,
        help="Bounce threshold in seconds for estimated visit sessions.",
    )
    parser.add_argument(
        "--session-gap-sec",
        type=int,
        default=30,
        help="Gap in seconds to split estimated visit sessions.",
    )
    parser.add_argument(
        "--max-images-per-store",
        type=int,
        default=20,
        help="Sample limit per store for faster first-pass runs. Use 0 to process all images.",
    )
    parser.add_argument(
        "--gzip-exports",
        action="store_true",
        help="Also write gzip-compressed CSV exports to reduce storage footprint.",
    )
    parser.add_argument(
        "--drop-plain-csv",
        action="store_true",
        help="Do not write plain CSV files; keep only .csv.gz exports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = analyze_root(
        root_dir=args.root,
        conf_threshold=args.conf,
        detector_type=args.detector,
        time_bucket_minutes=args.time_bucket,
        bounce_threshold_sec=args.bounce_threshold_sec,
        session_gap_sec=args.session_gap_sec,
        max_images_per_store=(None if args.max_images_per_store == 0 else args.max_images_per_store),
    )
    export_analysis(output=output, out_dir=args.out, write_gzip_exports=args.gzip_exports, keep_plain_csv=not args.drop_plain_csv)

    print(f"Stores analyzed: {len(output.stores)}")
    print(f"Summary CSV: {(args.out / 'all_stores_summary.csv').resolve()}")
    if output.used_root_fallback_store:
        print(
            "No subfolders found in root. Used root folder as a single store for compatibility."
        )
    if output.detector_warning:
        print(f"WARNING: {output.detector_warning}")

    if output.all_stores_summary.empty:
        print("No stores or images found.")
        return

    print("Per-store summary:")
    for _, row in output.all_stores_summary.iterrows():
        print(
            f"  {row['store_id']}: "
            f"total={int(row['total_images'])}, "
            f"valid={int(row['valid_images'])}, "
            f"relevant={int(row['relevant_images'])}, "
            f"people={int(row['total_people'])}, "
            f"top_hotspot={row['top_camera_hotspot'] or '-'}, "
            f"peak={row['peak_time_bucket'] or '-'}"
        )


if __name__ == "__main__":
    main()

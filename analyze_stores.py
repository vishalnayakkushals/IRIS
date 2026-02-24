from __future__ import annotations

import argparse
from pathlib import Path

from iris_analysis import analyze_root, export_analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze store folders and export customer/hotspot insights."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Root folder containing one subfolder per store.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("exports"),
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = analyze_root(
        root_dir=args.root,
        conf_threshold=args.conf,
        detector_type=args.detector,
        time_bucket_minutes=args.time_bucket,
    )
    export_analysis(output=output, out_dir=args.out)

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

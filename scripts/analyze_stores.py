from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.iris_analysis import analyze_root, export_analysis, export_store_day_artifacts


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
        "--store-id",
        default="",
        help="Optional single store filter (e.g., BLRJAY).",
    )
    parser.add_argument(
        "--date",
        default="",
        help="Optional capture date filter in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--full-day",
        action="store_true",
        help="Ignore sampling and process full-day data for selected filters.",
    )
    parser.add_argument(
        "--session-timeout-sec",
        type=int,
        default=180,
        help="Session timeout for store-day customer id closure fallback.",
    )
    parser.add_argument(
        "--enable-age-gender",
        action="store_true",
        help="Enable DeepFace age/gender likelihood analysis for customer crops.",
    )
    parser.add_argument(
        "--expected-cameras",
        default="D02,D03,D04,D05,D06,D07,D09,D11,D12,D13,D15,D16,D17",
        help="Comma-separated cameras for date-distribution validation.",
    )
    parser.add_argument(
        "--expected-min-count",
        type=int,
        default=0,
        help="Expected minimum image count per camera for validation.",
    )
    parser.add_argument(
        "--expected-max-count",
        type=int,
        default=0,
        help="Expected maximum image count per camera for validation.",
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


def _parse_capture_date(text: str) -> date | None:
    value = text.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"--date must be YYYY-MM-DD, got '{text}'") from exc


def main() -> None:
    args = parse_args()
    capture_date = _parse_capture_date(args.date)
    max_images_per_store = (None if args.max_images_per_store == 0 else args.max_images_per_store)
    if args.full_day:
        max_images_per_store = None

    output = analyze_root(
        root_dir=args.root,
        conf_threshold=args.conf,
        detector_type=args.detector,
        time_bucket_minutes=args.time_bucket,
        bounce_threshold_sec=args.bounce_threshold_sec,
        session_gap_sec=args.session_gap_sec,
        max_images_per_store=max_images_per_store,
        store_filter=args.store_id.strip() or None,
        capture_date_filter=capture_date,
        session_timeout_sec=int(args.session_timeout_sec),
        enable_age_gender=bool(args.enable_age_gender),
    )
    export_analysis(output=output, out_dir=args.out, write_gzip_exports=args.gzip_exports, keep_plain_csv=not args.drop_plain_csv)
    if args.store_id.strip() and capture_date is not None:
        created = export_store_day_artifacts(
            output=output,
            out_dir=args.out,
            store_id=args.store_id.strip(),
            capture_date=capture_date.isoformat(),
            write_gzip_exports=args.gzip_exports,
            keep_plain_csv=not args.drop_plain_csv,
        )
        if created:
            print("Date-scoped artifacts:")
            for path in created:
                print(f"  - {path.resolve()}")

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

    if args.store_id.strip() and capture_date is not None and args.store_id.strip() in output.stores:
        image_df = output.stores[args.store_id.strip()].image_insights.copy()
        day_df = image_df[image_df["capture_date"].astype(str) == capture_date.isoformat()].copy()
        if day_df.empty:
            print(f"Validation: no rows found for {args.store_id.strip()} on {capture_date.isoformat()}")
            return
        counts = (
            day_df.groupby("camera_id", as_index=False)
            .agg(image_count=("filename", "count"))
            .sort_values("camera_id")
        )
        print(f"Camera counts for {args.store_id.strip()} on {capture_date.isoformat()}:")
        for _, row in counts.iterrows():
            print(f"  {row['camera_id']}: {int(row['image_count'])}")
        if int(args.expected_min_count) > 0 and int(args.expected_max_count) > 0:
            expected_cameras = [c.strip().upper() for c in str(args.expected_cameras).split(",") if c.strip()]
            count_map = {
                str(r["camera_id"]).strip().upper(): int(r["image_count"]) for _, r in counts.iterrows()
            }
            failures: list[str] = []
            for cam in expected_cameras:
                cam_count = count_map.get(cam, 0)
                if cam_count < int(args.expected_min_count) or cam_count > int(args.expected_max_count):
                    failures.append(f"{cam}={cam_count}")
            if failures:
                print(
                    "Validation FAIL: camera counts outside expected range "
                    f"[{int(args.expected_min_count)}, {int(args.expected_max_count)}]: {', '.join(failures)}"
                )
            else:
                print(
                    "Validation PASS: all expected cameras within range "
                    f"[{int(args.expected_min_count)}, {int(args.expected_max_count)}]"
                )


if __name__ == "__main__":
    main()

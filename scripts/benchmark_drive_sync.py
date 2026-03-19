from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.drive_delta_sync import _download_with_multi_queue
from iris.store_registry import _drive_api_list_files_recursive, parse_drive_folder_id


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Benchmark Drive image sync throughput")
    p.add_argument("--drive-folder-url", required=True)
    p.add_argument("--sample-size", type=int, default=300)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--out", type=Path, default=app_dir / "data" / "cache" / "bench_sync")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GOOGLE_API_KEY is required")
    folder_id = parse_drive_folder_id(args.drive_folder_url)
    if not folder_id:
        raise SystemExit("Invalid --drive-folder-url")

    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    items = _drive_api_list_files_recursive(folder_id=folder_id, api_key=api_key)
    list_sec = time.perf_counter() - t0
    if not items:
        raise SystemExit("No image files found")
    sample = items[: max(1, min(int(args.sample_size), len(items)))]

    t1 = time.perf_counter()
    downloaded, _ = _download_with_multi_queue(
        pending_items=sample,
        target_dir=args.out,
        api_key=api_key,
        workers=int(args.workers),
    )
    dl_sec = time.perf_counter() - t1
    throughput = (float(downloaded) / dl_sec) if dl_sec > 0 else 0.0
    est_full_sec = (len(items) / throughput) if throughput > 0 else 0.0

    print(f"Listed files: {len(items)} in {list_sec:.2f}s")
    print(f"Downloaded sample: {downloaded}/{len(sample)} in {dl_sec:.2f}s with workers={args.workers}")
    print(f"Throughput: {throughput:.2f} images/sec")
    print(f"Estimated first full extraction: {est_full_sec/60:.2f} minutes ({est_full_sec:.0f}s)")


if __name__ == "__main__":
    main()

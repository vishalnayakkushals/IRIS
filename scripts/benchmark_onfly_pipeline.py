from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time

import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark legacy-like vs optimized on-the-fly pipeline")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--detector", default="yolo")
    parser.add_argument("--conf", type=float, default=0.18)
    parser.add_argument("--allow-detector-fallback", action="store_true")
    return parser.parse_args()


def _run_profile(*, args: argparse.Namespace, profile_name: str, force_reprocess: bool) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(1, max(1, int(args.runs)) + 1):
        started = time.perf_counter()
        summary = run_onfly_pipeline(
            OnFlyConfig(
                store_id=str(args.store_id).strip(),
                source_uri=str(args.source_url).strip(),
                db_path=args.db.resolve(),
                out_dir=args.out_dir.resolve(),
                detector_type=str(args.detector).strip(),
                conf_threshold=float(args.conf),
                max_images=max(1, int(args.limit)),
                gpt_enabled=False,
                force_reprocess=force_reprocess,
                pipeline_version="onfly_v1",
                run_mode=f"benchmark_{profile_name}",
                allow_detector_fallback=bool(args.allow_detector_fallback),
            )
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        t = summary.get("timings_ms", {}) if isinstance(summary, dict) else {}
        rows.append(
            {
                "profile": profile_name,
                "run_no": idx,
                "elapsed_ms": elapsed_ms,
                "list_ms": float(t.get("list_ms", 0.0) or 0.0),
                "detector_init_ms": float(t.get("detector_init_ms", 0.0) or 0.0),
                "download_ms": float(t.get("download_ms", 0.0) or 0.0),
                "yolo_ms": float(t.get("yolo_ms", 0.0) or 0.0),
                "report_ms": float(t.get("report_ms", 0.0) or 0.0),
                "total_ms": float(t.get("total_ms", elapsed_ms) or elapsed_ms),
                "new_images": int(summary.get("new_images", 0) or 0),
                "skipped_cached": int(summary.get("skipped_cached", 0) or 0),
            }
        )
    return rows


def main() -> None:
    args = parse_args()
    args.db = args.db.resolve()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    before_rows = _run_profile(args=args, profile_name="before_full_reprocess", force_reprocess=True)
    after_rows = _run_profile(args=args, profile_name="after_idempotent", force_reprocess=False)
    all_rows = before_rows + after_rows
    df = pd.DataFrame(all_rows)

    before_ms = [float(r["total_ms"]) for r in before_rows]
    after_ms = [float(r["total_ms"]) for r in after_rows]
    before_avg = statistics.mean(before_ms) if before_ms else 0.0
    after_avg = statistics.mean(after_ms) if after_ms else 0.0
    improve_pct = round(((before_avg - after_avg) / before_avg) * 100.0, 2) if before_avg > 0 else 0.0

    aggregate = pd.DataFrame(
        [
            {"profile": "before_full_reprocess", "runs": len(before_rows), "avg_total_ms": round(before_avg, 2), "min_total_ms": round(min(before_ms), 2) if before_ms else 0.0, "max_total_ms": round(max(before_ms), 2) if before_ms else 0.0},
            {"profile": "after_idempotent", "runs": len(after_rows), "avg_total_ms": round(after_avg, 2), "min_total_ms": round(min(after_ms), 2) if after_ms else 0.0, "max_total_ms": round(max(after_ms), 2) if after_ms else 0.0},
            {"profile": "improvement", "runs": 0, "avg_total_ms": round(before_avg - after_avg, 2), "min_total_ms": improve_pct, "max_total_ms": 0.0},
        ]
    )

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    bench_dir = args.out_dir / "benchmarks"
    bench_dir.mkdir(parents=True, exist_ok=True)
    runs_csv = bench_dir / f"onfly_runs_{stamp}.csv"
    agg_csv = bench_dir / f"onfly_summary_{stamp}.csv"
    json_path = bench_dir / f"onfly_summary_{stamp}.json"
    df.to_csv(runs_csv, index=False)
    aggregate.to_csv(agg_csv, index=False)
    payload = {
        "run_at": datetime.now(tz=timezone.utc).isoformat(),
        "store_id": args.store_id,
        "source_url": args.source_url,
        "runs": int(args.runs),
        "before_avg_total_ms": round(before_avg, 2),
        "after_avg_total_ms": round(after_avg, 2),
        "improvement_pct": improve_pct,
        "runs_csv": str(runs_csv),
        "summary_csv": str(agg_csv),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["summary_json"] = str(json_path)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="On-the-fly retail vision pipeline (YOLO -> GPT on relevant)")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--source-url", required=True, help="Google Drive folder URL or local path")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--detector", default="yolo", choices=["yolo", "opencv_hog", "mock"])
    parser.add_argument("--conf", type=float, default=0.18)
    parser.add_argument("--max-images", type=int, default=int(os.getenv("ONFLY_MAX_IMAGES", "100")))
    parser.add_argument("--run-mode", default="hourly")
    parser.add_argument("--pipeline-version", default=os.getenv("ONFLY_PIPELINE_VERSION", "onfly_v1"))
    parser.add_argument("--yolo-version", default=os.getenv("ONFLY_YOLO_VERSION", ""))
    parser.add_argument("--gpt-version", default=os.getenv("ONFLY_GPT_VERSION", ""))
    parser.add_argument("--allow-detector-fallback", action="store_true")
    parser.add_argument("--force-reprocess", action="store_true")
    parser.add_argument("--enable-gpt", action="store_true")
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--openai-api-base", default=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"))
    parser.add_argument("--gpt-rate-limit-rps", type=float, default=float(os.getenv("GPT_RATE_LIMIT_RPS", "1.0")))
    parser.add_argument("--keep-relevant-dir", type=Path, default=None, help="Optional local review cache for relevant images only")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = OnFlyConfig(
        store_id=str(args.store_id).strip(),
        source_uri=str(args.source_url).strip(),
        db_path=args.db.resolve(),
        out_dir=args.out_dir.resolve(),
        detector_type=str(args.detector).strip().lower(),
        conf_threshold=float(args.conf),
        max_images=max(0, int(args.max_images)),
        gpt_enabled=bool(args.enable_gpt),
        openai_api_key=str(os.getenv("OPENAI_API_KEY", "")).strip(),
        openai_model=str(args.openai_model).strip(),
        openai_api_base=str(args.openai_api_base).strip(),
        gpt_rate_limit_rps=max(0.01, float(args.gpt_rate_limit_rps)),
        pipeline_version=str(args.pipeline_version).strip() or "onfly_v1",
        yolo_version=str(args.yolo_version).strip(),
        gpt_version=str(args.gpt_version).strip(),
        allow_detector_fallback=bool(args.allow_detector_fallback),
        force_reprocess=bool(args.force_reprocess),
        keep_relevant_dir=args.keep_relevant_dir.resolve() if args.keep_relevant_dir is not None else None,
        run_mode=str(args.run_mode).strip() or "hourly",
    )
    summary = run_onfly_pipeline(cfg)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

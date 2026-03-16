from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.event_queue import JsonlEventQueue
from iris.iris_analysis import analyze_root, export_analysis
from iris.store_registry import (
    camera_config_map,
    log_user_activity,
    maybe_auto_rollback_model,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run async analysis worker over queued frame events")
    p.add_argument("--queue-file", type=Path, default=Path("data/queue/frame_events.jsonl"))
    p.add_argument("--root", type=Path, default=Path("data/stores"))
    p.add_argument("--out", type=Path, default=Path("data/exports/current"))
    p.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    p.add_argument("--detector", choices=["yolo", "mock"], default="mock")
    p.add_argument("--conf", type=float, default=0.18)
    p.add_argument("--idle-sleep", type=float, default=1.0)
    p.add_argument("--max-events", type=int, default=0, help="Stop after processing N events. 0 means run forever.")
    p.add_argument(
        "--max-images-per-store",
        type=int,
        default=20,
        help="Sample limit per store during each analysis cycle. 0 means process all.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    q = JsonlEventQueue(args.queue_file)
    print(f"Worker started. queue={args.queue_file}")
    processed = 0

    while True:
        evt = q.pull(timeout_sec=0.1)
        if evt is None:
            time.sleep(args.idle_sleep)
            continue

        print(f"Processing event {evt.event_id} store={evt.store_id} camera={evt.camera_id}")
        cfg_map = {
            store_id: {cid: cfg.__dict__ for cid, cfg in cams.items()}
            for store_id, cams in camera_config_map(args.db).items()
        }

        output = analyze_root(
            root_dir=args.root,
            detector_type=args.detector,
            conf_threshold=args.conf,
            camera_configs_by_store=cfg_map,
            max_images_per_store=(None if args.max_images_per_store == 0 else args.max_images_per_store),
        )
        export_analysis(output, out_dir=args.out, write_gzip_exports=True, keep_plain_csv=True)

        rolled, msg = maybe_auto_rollback_model(args.db, model_name="iris_customer_model")
        log_user_activity(
            db_path=args.db,
            actor_email="worker@iris.local",
            action_code="ASYNC_ANALYSIS_EVENT",
            store_id=evt.store_id,
            payload_json=json.dumps({"event_id": evt.event_id, "rollback": rolled, "rollback_message": msg}),
        )
        processed += 1
        if args.max_events > 0 and processed >= args.max_events:
            print(f"Processed {processed} events. Exiting worker by --max-events.")
            return


if __name__ == "__main__":
    main()

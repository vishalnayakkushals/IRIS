from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.event_queue import JsonlEventQueue, new_frame_event
from iris.iris_analysis import IMAGE_EXTENSIONS, parse_filename, validate_image


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Queue snapshot frame events for async worker.")
    p.add_argument("--root", type=Path, default=Path("data/stores"))
    p.add_argument("--queue-file", type=Path, default=Path("data/queue/frame_events.jsonl"))
    p.add_argument("--store-id", default="", help="Optional single store_id to enqueue.")
    p.add_argument(
        "--max-images-per-store",
        type=int,
        default=20,
        help="Queue up to N valid frames per store. Use 0 for all.",
    )
    return p.parse_args()


def _store_dirs(root: Path, only_store: str) -> list[Path]:
    dirs = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    if only_store:
        dirs = [p for p in dirs if p.name == only_store]
    return dirs


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    queue = JsonlEventQueue(args.queue_file.resolve())
    total_enqueued = 0

    for store_dir in _store_dirs(root, args.store_id.strip()):
        candidates = sorted(
            [
                path
                for path in store_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ],
            key=lambda p: str(p.relative_to(store_dir)),
        )

        enqueued_for_store = 0
        invalid_for_store = 0
        for path in candidates:
            parsed = parse_filename(path.name)
            if parsed is None:
                invalid_for_store += 1
                continue
            is_valid, _reason = validate_image(path)
            if not is_valid:
                invalid_for_store += 1
                continue

            queue.publish(
                new_frame_event(
                    store_id=store_dir.name,
                    camera_id=parsed.camera_id,
                    image_path=str(path),
                    payload={"timestamp": parsed.timestamp.isoformat()},
                )
            )
            enqueued_for_store += 1
            total_enqueued += 1
            if args.max_images_per_store > 0 and enqueued_for_store >= args.max_images_per_store:
                break

        print(
            f"{store_dir.name}: queued={enqueued_for_store}, "
            f"skipped_invalid_or_bad_filename={invalid_for_store}"
        )

    print(f"Total queued events: {total_enqueued}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.drive_delta_sync import run_delta_sync_for_store, sleep_seconds_until_next_run
from iris.secret_store import load_google_api_key, save_google_api_key


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Daily Google Drive delta sync scheduler")
    p.add_argument("--db", type=Path, default=app_dir / "data" / "store_registry.db")
    p.add_argument("--data-root", type=Path, default=app_dir / "data" / "stores")
    p.add_argument("--store-id", required=True, help="Store ID in store_registry DB")
    p.add_argument("--run-at", default="06:00", help="Daily local run time HH:MM (default 06:00)")
    p.add_argument("--tz", default="Asia/Kolkata", help="Timezone for scheduler (default Asia/Kolkata)")
    p.add_argument("--workers", type=int, default=6, help="Parallel download queues")
    p.add_argument(
        "--remove-local-deleted-files",
        action="store_true",
        help="Physically delete local files when removed from Drive (default: keep files, mark deleted in index).",
    )
    p.add_argument("--run-once", action="store_true", help="Run one sync cycle and exit")
    return p.parse_args()


def _validate_time(run_at: str) -> str:
    text = str(run_at).strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError("--run-at must be HH:MM")
    hh = int(parts[0])
    mm = int(parts[1])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise ValueError("--run-at must be HH:MM in 24h format")
    return f"{hh:02d}:{mm:02d}"


def run_once(args: argparse.Namespace) -> int:
    env_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if env_key:
        try:
            save_google_api_key(env_key, data_dir=args.data_root.parent)
        except Exception:
            pass
    api_key = env_key or load_google_api_key(data_dir=args.data_root.parent)
    if not api_key:
        print("ERROR: GOOGLE_API_KEY is required for Drive API sync (env var or encrypted data/secrets store)")
        return 2
    result = run_delta_sync_for_store(
        db_path=args.db,
        data_root=args.data_root,
        store_id=args.store_id,
        api_key=api_key,
        workers=int(args.workers),
        remove_local_deleted_files=bool(args.remove_local_deleted_files),
    )
    print(result.message)
    return 0 if result.mode != "error" else 1


def main() -> None:
    args = parse_args()
    args.run_at = _validate_time(args.run_at)
    args.data_root.mkdir(parents=True, exist_ok=True)
    if args.run_once:
        raise SystemExit(run_once(args))

    print(
        f"Scheduler started: store={args.store_id} run_at={args.run_at} tz={args.tz} workers={args.workers}"
    )
    while True:
        sleep_sec = sleep_seconds_until_next_run(args.run_at, args.tz)
        print(f"Next sync in {sleep_sec} seconds")
        time.sleep(sleep_sec)
        code = run_once(args)
        if code != 0:
            print("Sync cycle failed; retrying next schedule window.")


if __name__ == "__main__":
    main()

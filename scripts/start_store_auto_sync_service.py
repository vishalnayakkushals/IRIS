from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start IRIS store auto-sync worker without Docker")
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("IRIS_STORE_AUTO_SYNC_POLL_SECONDS", "60") or 60))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths

    env_file = load_env_file()
    runtime = resolve_runtime_paths()
    runtime["data_dir"].mkdir(parents=True, exist_ok=True)
    runtime["exports_dir"].mkdir(parents=True, exist_ok=True)
    runtime["db_path"].parent.mkdir(parents=True, exist_ok=True)

    print(f"[iris-store-auto-sync] env={env_file or 'none'} db={runtime['db_path']} poll={int(args.poll_seconds)}")

    from backend.app.workers.store_auto_sync import auto_sync_loop
    asyncio.run(auto_sync_loop(int(args.poll_seconds)))


if __name__ == "__main__":
    main()

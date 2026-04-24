from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start IRIS on-fly scheduler without Docker")
    parser.add_argument("--poll-seconds", type=int, default=int(os.getenv("IRIS_ONFLY_POLL_SECONDS", "30") or 30))
    parser.add_argument("--run-once", action="store_true")
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

    env = os.environ.copy()
    existing_pythonpath = str(env.get("PYTHONPATH", "") or "").strip()
    env["PYTHONPATH"] = str(src_dir) if not existing_pythonpath else f"{src_dir}{os.pathsep}{existing_pythonpath}"

    command = [
        sys.executable,
        str(repo_root / "scripts" / "onfly_scheduler.py"),
        "--db",
        str(runtime["db_path"]),
        "--poll-seconds",
        str(int(args.poll_seconds)),
    ]
    if args.run_once:
        command.append("--run-once")
    print(f"[iris-onfly-scheduler] env={env_file or 'none'} db={runtime['db_path']} poll={int(args.poll_seconds)}")
    raise SystemExit(subprocess.call(command, cwd=str(repo_root), env=env))


if __name__ == "__main__":
    main()

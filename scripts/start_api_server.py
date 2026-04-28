from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    backend_dir = repo_root / "backend"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths

    env_file = load_env_file()
    runtime = resolve_runtime_paths()
    runtime["data_dir"].mkdir(parents=True, exist_ok=True)
    runtime["db_path"].parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    existing_pythonpath = str(env.get("PYTHONPATH", "") or "").strip()
    paths = [str(repo_root), str(src_dir)]
    env["PYTHONPATH"] = os.pathsep.join(paths) if not existing_pythonpath else f"{os.pathsep.join(paths)}{os.pathsep}{existing_pythonpath}"
    env.setdefault("API_HOST", "0.0.0.0")
    env.setdefault("API_PORT", "8767")
    env.setdefault("API_RELOAD", "0")

    host = env["API_HOST"]
    port = env["API_PORT"]
    reload_enabled = str(env.get("API_RELOAD", "0")).strip().lower() in {"1", "true", "yes", "on"}

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host", host,
        "--port", port,
    ]
    if reload_enabled:
        command.append("--reload")
    print(f"[iris-api] env={env_file or 'none'} db={runtime['db_path']} port={port} reload={reload_enabled}")
    raise SystemExit(subprocess.call(command, cwd=str(repo_root), env=env))


if __name__ == "__main__":
    main()

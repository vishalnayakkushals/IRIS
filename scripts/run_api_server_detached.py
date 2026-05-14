from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    runtime_log_dir = repo_root / "deploy" / "no_docker" / "runtime_logs"
    runtime_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = runtime_log_dir / "api_live_uvicorn.log"

    with log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
        sys.stdout = log_handle
        sys.stderr = log_handle

        from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths
        from backend.app.runtime_startup import prepare_runtime
        import uvicorn

        load_env_file()
        runtime = resolve_runtime_paths()
        runtime["data_dir"].mkdir(parents=True, exist_ok=True)
        runtime["db_path"].parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(prepare_runtime(runtime["db_path"]))

        host = os.environ.get("API_HOST", "0.0.0.0")
        port = int(os.environ.get("API_PORT", "8767"))
        print(f"[iris-api] detached uvicorn starting host={host} port={port}", flush=True)
        uvicorn.run("backend.app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

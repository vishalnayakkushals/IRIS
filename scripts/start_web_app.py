from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths

    env_file = load_env_file()
    runtime = resolve_runtime_paths()
    runtime["data_dir"].mkdir(parents=True, exist_ok=True)
    runtime["stores_root"].mkdir(parents=True, exist_ok=True)
    runtime["exports_dir"].mkdir(parents=True, exist_ok=True)
    runtime["employee_assets_dir"].mkdir(parents=True, exist_ok=True)
    runtime["db_path"].parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    existing_pythonpath = str(env.get("PYTHONPATH", "") or "").strip()
    env["PYTHONPATH"] = str(src_dir) if not existing_pythonpath else f"{src_dir}{os.pathsep}{existing_pythonpath}"
    env.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    env.setdefault("IRIS_STREAMLIT_HOST", "0.0.0.0")
    env.setdefault("IRIS_STREAMLIT_PORT", "8765")

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(repo_root / "src" / "run_dashboard.py"),
        "--server.address",
        str(env["IRIS_STREAMLIT_HOST"]),
        "--server.port",
        str(env["IRIS_STREAMLIT_PORT"]),
        "--server.headless",
        str(env["STREAMLIT_SERVER_HEADLESS"]).lower(),
    ]
    print(f"[iris-web] env={env_file or 'none'} db={runtime['db_path']} data={runtime['data_dir']} port={env['IRIS_STREAMLIT_PORT']}")
    raise SystemExit(subprocess.call(command, cwd=str(repo_root), env=env))


if __name__ == "__main__":
    main()

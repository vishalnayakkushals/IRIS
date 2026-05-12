from __future__ import annotations

import os
import signal
import sys
import asyncio
from pathlib import Path
import subprocess


def _kill_old_server(pid_file: Path) -> None:
    """Kill the previously recorded uvicorn process if still running."""
    if not pid_file.exists():
        return
    try:
        old_pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return
    try:
        if sys.platform == "win32":
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, old_pid)
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 0)
                ctypes.windll.kernel32.CloseHandle(handle)
                print(f"[iris-api] Killed old server PID {old_pid}")
        else:
            os.kill(old_pid, signal.SIGTERM)
            print(f"[iris-api] Sent SIGTERM to old server PID {old_pid}")
    except (ProcessLookupError, PermissionError, OSError):
        pass


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths
    from backend.app.runtime_startup import prepare_runtime

    env_file = load_env_file()
    runtime = resolve_runtime_paths()
    runtime["data_dir"].mkdir(parents=True, exist_ok=True)
    runtime["db_path"].parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(prepare_runtime(runtime["db_path"]))

    pid_file = repo_root / "deploy" / "no_docker" / "runtime_logs" / "pids" / "web.pid"
    _kill_old_server(pid_file)

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
    proc = subprocess.Popen(command, cwd=str(repo_root), env=env)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(proc.pid))
    print(f"[iris-api] Started PID {proc.pid}")
    raise SystemExit(proc.wait())


if __name__ == "__main__":
    main()

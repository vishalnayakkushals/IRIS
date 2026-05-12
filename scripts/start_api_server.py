from __future__ import annotations

import os
import signal
import sys
import asyncio
from pathlib import Path
import subprocess
import socket


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


def _is_windows_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _firewall_rule_exists_windows(port: str) -> bool:
    if sys.platform != "win32":
        return True
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow | "
                f"Get-NetFirewallPortFilter | Where-Object {{ $_.Protocol -eq 'TCP' -and $_.LocalPort -eq '{port}' }} | "
                f"Select-Object -First 1"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and bool((result.stdout or "").strip())
    except Exception:
        return False


def _warn_if_network_access_may_be_blocked(host: str, port: str) -> None:
    if host not in {"0.0.0.0", "::", "*"}:
        print(f"[iris-api] Warning: server host is {host}, so LAN devices cannot connect. Use API_HOST=0.0.0.0")
        return
    try:
        lan_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        lan_ip = ""
    if sys.platform == "win32" and not _firewall_rule_exists_windows(port):
        print("[iris-api] Warning: no Windows Firewall allow rule was found for TCP port "
              f"{port}. Local devices may fail to open http://{lan_ip or 'THIS-PC-IP'}:{port}/")
        print("[iris-api] Fix once in an elevated PowerShell:")
        print(f"  powershell -ExecutionPolicy Bypass -File .\\scripts\\enable_api_network_access.ps1 -Port {port}")
        if not _is_windows_admin():
            print("[iris-api] Current terminal is not running as Administrator, so the firewall rule cannot be created automatically.")


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
    _warn_if_network_access_may_be_blocked(host, port)

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

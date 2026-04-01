from __future__ import annotations

import argparse
import subprocess
import time
from collections.abc import Iterable
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from perf_common import append_event, new_run_id, now_epoch_ms


def _probe_url(run_id: str, url: str, timeout: float, tries: int, note: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    module = (query.get("module") or [""])[0]
    path_name = parsed.path or "/"
    if parsed.query:
        path_name = f"{path_name}?{parsed.query}"
    page_name = module or path_name

    success = False
    for attempt in range(1, max(1, tries) + 1):
        start_ms = now_epoch_ms()
        status = "success"
        status_code = None
        error_text = ""
        bytes_read = 0
        try:
            request = Request(url, headers={"User-Agent": "IRIS-CTO-PerfObserver/1.0"})
            with urlopen(request, timeout=timeout) as resp:
                body = resp.read()
                bytes_read = len(body)
                status_code = int(getattr(resp, "status", resp.getcode()))
            success = True
        except (TimeoutError, URLError, OSError) as exc:
            status = "error"
            error_text = str(exc)
        end_ms = now_epoch_ms()
        append_event(
            {
                "run_id": run_id,
                "event_type": "page_probe",
                "page_name": page_name,
                "module_name": module,
                "path_name": path_name,
                "url": url,
                "attempt": attempt,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": max(0, end_ms - start_ms),
                "status": status,
                "status_code": status_code,
                "bytes_read": bytes_read,
                "note": note,
                "error": error_text,
            }
        )
        if success:
            break
    return success


def _run_fix_command(run_id: str, command: str, note: str) -> int:
    start_ms = now_epoch_ms()
    completed = subprocess.run(command, shell=True, check=False)
    end_ms = now_epoch_ms()
    append_event(
        {
            "run_id": run_id,
            "event_type": "fix_command",
            "page_name": "",
            "module_name": "",
            "path_name": "command",
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": max(0, end_ms - start_ms),
            "status": "success" if completed.returncode == 0 else "failed",
            "status_code": completed.returncode,
            "note": note,
            "command": command,
        }
    )
    return int(completed.returncode)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CTO isolated run-level perf cycle logger.")
    parser.add_argument("--run-id", default="", help="Optional run id. If omitted, a new run id is generated.")
    parser.add_argument("--note", default="", help="Fix/build note for this run.")
    parser.add_argument("--command", default="", help="Optional shell command to execute and time.")
    parser.add_argument("--url", action="append", default=[], help="URL to probe. Repeat for multiple pages.")
    parser.add_argument("--timeout", type=float, default=20.0, help="URL timeout seconds.")
    parser.add_argument("--tries", type=int, default=1, help="Retry count per URL.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_id = str(args.run_id).strip() or new_run_id()
    note = str(args.note).strip()
    urls: Iterable[str] = [str(u).strip() for u in args.url if str(u).strip()]

    run_start_ms = now_epoch_ms()
    append_event(
        {
            "run_id": run_id,
            "event_type": "run_start",
            "page_name": "",
            "module_name": "",
            "path_name": "run",
            "start_ms": run_start_ms,
            "end_ms": run_start_ms,
            "duration_ms": 0,
            "status": "started",
            "status_code": 0,
            "note": note,
        }
    )

    rc = 0
    if str(args.command).strip():
        rc = _run_fix_command(run_id=run_id, command=str(args.command).strip(), note=note)

    probe_success = True
    for url in urls:
        ok = _probe_url(run_id=run_id, url=url, timeout=float(args.timeout), tries=int(args.tries), note=note)
        probe_success = probe_success and ok

    run_end_ms = now_epoch_ms()
    final_ok = rc == 0 and probe_success
    append_event(
        {
            "run_id": run_id,
            "event_type": "run_end",
            "page_name": "",
            "module_name": "",
            "path_name": "run",
            "start_ms": run_start_ms,
            "end_ms": run_end_ms,
            "duration_ms": max(0, run_end_ms - run_start_ms),
            "status": "success" if final_ok else "failed",
            "status_code": 0 if final_ok else 1,
            "note": note,
        }
    )

    print(f"run_id={run_id}")
    print(f"status={'success' if final_ok else 'failed'}")
    raise SystemExit(0 if final_ok else 1)


if __name__ == "__main__":
    main()

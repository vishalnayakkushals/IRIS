from __future__ import annotations

import argparse
import time
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from perf_common import append_event, new_run_id, now_epoch_ms


def _probe_once(run_id: str, url: str, timeout: float, note: str, cycle_no: int) -> None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    module = (query.get("module") or [""])[0]
    path_name = parsed.path or "/"
    if parsed.query:
        path_name = f"{path_name}?{parsed.query}"
    page_name = module or path_name

    start_ms = now_epoch_ms()
    status = "success"
    status_code = None
    bytes_read = 0
    error_text = ""
    try:
        request = Request(url, headers={"User-Agent": "IRIS-CTO-PerfObserver/1.0"})
        with urlopen(request, timeout=timeout) as resp:
            body = resp.read()
            bytes_read = len(body)
            status_code = int(getattr(resp, "status", resp.getcode()))
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
            "cycle_no": int(cycle_no),
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continuous lightweight page probe logger (isolated CTO utility).")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--note", default="watch")
    parser.add_argument("--url", action="append", default=[], help="URL to probe. Repeat for multiple.")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--cycles", type=int, default=0, help="0 means infinite.")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    urls = [str(u).strip() for u in args.url if str(u).strip()]
    if not urls:
        raise SystemExit("At least one --url is required.")

    run_id = str(args.run_id).strip() or new_run_id()
    note = str(args.note).strip()
    start_ms = now_epoch_ms()
    append_event(
        {
            "run_id": run_id,
            "event_type": "run_start",
            "page_name": "",
            "module_name": "",
            "path_name": "watch",
            "start_ms": start_ms,
            "end_ms": start_ms,
            "duration_ms": 0,
            "status": "started",
            "status_code": 0,
            "note": note,
        }
    )
    print(f"watch_run_id={run_id}")

    cycle = 0
    max_cycles = int(args.cycles)
    try:
        while True:
            cycle += 1
            for url in urls:
                _probe_once(run_id=run_id, url=url, timeout=float(args.timeout), note=note, cycle_no=cycle)
            if max_cycles > 0 and cycle >= max_cycles:
                break
            time.sleep(max(1.0, float(args.interval_seconds)))
    except KeyboardInterrupt:
        pass
    finally:
        end_ms = now_epoch_ms()
        append_event(
            {
                "run_id": run_id,
                "event_type": "run_end",
                "page_name": "",
                "module_name": "",
                "path_name": "watch",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": max(0, end_ms - start_ms),
                "status": "success",
                "status_code": 0,
                "note": note,
            }
        )
        print("watch_stopped")


if __name__ == "__main__":
    main()

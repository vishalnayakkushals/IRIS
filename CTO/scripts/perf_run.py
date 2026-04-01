from __future__ import annotations

import argparse

from perf_common import append_event, new_run_id, now_epoch_ms


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CTO run-level tracker (start/end).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--run-id", default="")
    start.add_argument("--note", default="")

    end = sub.add_parser("end")
    end.add_argument("--run-id", required=True)
    end.add_argument("--note", default="")
    end.add_argument("--status", choices=["success", "failed"], default="success")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    now_ms = now_epoch_ms()
    if args.cmd == "start":
        run_id = str(args.run_id).strip() or new_run_id()
        append_event(
            {
                "run_id": run_id,
                "event_type": "run_start",
                "page_name": "",
                "module_name": "",
                "path_name": "run",
                "start_ms": now_ms,
                "end_ms": now_ms,
                "duration_ms": 0,
                "status": "started",
                "status_code": 0,
                "note": str(args.note).strip(),
            }
        )
        print(run_id)
        return

    append_event(
        {
            "run_id": str(args.run_id).strip(),
            "event_type": "run_end",
            "page_name": "",
            "module_name": "",
            "path_name": "run",
            "start_ms": now_ms,
            "end_ms": now_ms,
            "duration_ms": 0,
            "status": str(args.status),
            "status_code": 0 if args.status == "success" else 1,
            "note": str(args.note).strip(),
        }
    )
    print(f"ended {args.run_id} ({args.status})")


if __name__ == "__main__":
    main()

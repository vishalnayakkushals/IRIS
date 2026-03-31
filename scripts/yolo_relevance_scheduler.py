from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.store_registry import get_app_settings, upsert_app_settings  # noqa: E402


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on", "y", "t"}


def _safe_int(value: object, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return int(default)


def _safe_float(value: object, default: float) -> float:
    try:
        return float(str(value or "").strip())
    except Exception:
        return float(default)


def _parse_hhmm(raw: str) -> tuple[int, int]:
    text = str(raw or "").strip()
    if len(text) != 5 or ":" not in text:
        raise ValueError("run-at must be HH:MM")
    hh, mm = text.split(":", 1)
    return int(hh), int(mm)


def _next_due(now_local: datetime, run_hour: int, run_minute: int) -> datetime:
    candidate = now_local.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
    if now_local >= candidate:
        candidate = candidate + timedelta(days=1)
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily YOLO Stage-1 relevance scheduler")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--run-once", action="store_true")
    return parser.parse_args()


def _runtime_env() -> dict[str, object]:
    return {
        "enabled": _truthy(os.getenv("YOLO_RELEVANCE_ENABLED", "1"), default=True),
        "run_at": str(os.getenv("YOLO_RELEVANCE_DAILY_RUN_AT", "15:00") or "15:00").strip(),
        "tz": str(os.getenv("YOLO_RELEVANCE_TZ", "Asia/Kolkata") or "Asia/Kolkata").strip(),
        "root": str(os.getenv("YOLO_RELEVANCE_ROOT", "/app/data/test_stores") or "/app/data/test_stores").strip(),
        "out_root": str(os.getenv("YOLO_RELEVANCE_OUT_ROOT", "/app/data/exports/current/stage1_relevance") or "/app/data/exports/current/stage1_relevance").strip(),
        "store_id": str(os.getenv("YOLO_RELEVANCE_STORE_ID", "TEST_STORE_D07") or "TEST_STORE_D07").strip(),
        "conf": _safe_float(os.getenv("YOLO_RELEVANCE_CONF", "0.18"), 0.18),
        "max_images": max(0, _safe_int(os.getenv("YOLO_RELEVANCE_MAX_IMAGES", "0"), 0)),
        "allow_fallback": _truthy(os.getenv("YOLO_RELEVANCE_ALLOW_FALLBACK", "0"), default=False),
        "gzip_exports": _truthy(os.getenv("YOLO_RELEVANCE_GZIP_EXPORTS", "1"), default=True),
        "drop_plain_csv": _truthy(os.getenv("YOLO_RELEVANCE_DROP_PLAIN_CSV", "1"), default=True),
    }


def _run_cycle(args: argparse.Namespace) -> tuple[bool, int]:
    cfg = _runtime_env()
    settings = get_app_settings(args.db)
    store_scope = str(cfg["store_id"] or "ALL").strip() or "ALL"
    key_last_day = f"cfg_stage1_last_run_date__{store_scope}"

    try:
        tz = ZoneInfo(str(cfg["tz"]))
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz=tz)
    run_hour, run_minute = _parse_hhmm(str(cfg["run_at"]))

    if not bool(cfg["enabled"]):
        next_due = _next_due(now_local, run_hour, run_minute)
        upsert_app_settings(
            args.db,
            {
                "cfg_stage1_next_run_at": next_due.astimezone(timezone.utc).isoformat(),
                "cfg_stage1_last_summary_json": json.dumps(
                    {
                        "status": "disabled",
                        "message": "YOLO_RELEVANCE_ENABLED=0",
                        "at": datetime.now(tz=timezone.utc).isoformat(),
                    },
                    separators=(",", ":"),
                ),
            },
        )
        wait_seconds = max(5, min(int(args.poll_seconds), int((next_due - now_local).total_seconds())))
        return False, wait_seconds

    due_today = now_local.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
    last_run_day = str(settings.get(key_last_day, "") or "").strip()
    today_key = now_local.date().isoformat()
    if now_local < due_today:
        wait_seconds = max(5, min(int(args.poll_seconds), int((due_today - now_local).total_seconds())))
        upsert_app_settings(args.db, {"cfg_stage1_next_run_at": due_today.astimezone(timezone.utc).isoformat()})
        return False, wait_seconds
    if last_run_day == today_key:
        next_due = due_today + timedelta(days=1)
        upsert_app_settings(args.db, {"cfg_stage1_next_run_at": next_due.astimezone(timezone.utc).isoformat()})
        wait_seconds = max(5, min(int(args.poll_seconds), int((next_due - now_local).total_seconds())))
        return False, wait_seconds

    command = [
        sys.executable,
        "scripts/yolo_relevance_scan.py",
        "--root",
        str(cfg["root"]),
        "--out-dir",
        str(cfg["out_root"]),
        "--detector",
        "yolo",
        "--conf",
        str(float(cfg["conf"])),
    ]
    if str(cfg["store_id"]).strip():
        command.extend(["--store-id", str(cfg["store_id"]).strip()])
    if int(cfg["max_images"]) > 0:
        command.extend(["--max-images", str(int(cfg["max_images"]))])
    if bool(cfg["allow_fallback"]):
        command.append("--allow-detector-fallback")
    if bool(cfg["gzip_exports"]):
        command.append("--gzip-exports")
    if bool(cfg["drop_plain_csv"]):
        command.append("--drop-plain-csv")

    started_at = datetime.now(tz=timezone.utc)
    print(
        "[stage1-scheduler] cycle-start "
        f"at={started_at.isoformat()} run_at_local={str(cfg['run_at'])} tz={str(cfg['tz'])} "
        f"store={store_scope} root={str(cfg['root'])}"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app/src"
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    finished_at = datetime.now(tz=timezone.utc)
    next_due = _next_due(datetime.now(tz=tz), run_hour, run_minute)
    summary = {
        "started_at": started_at.isoformat(),
        "ended_at": finished_at.isoformat(),
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": int(proc.returncode),
        "store_scope": store_scope,
        "stdout_tail": str(proc.stdout or "")[-3000:],
        "stderr_tail": str(proc.stderr or "")[-3000:],
        "next_run_at": next_due.astimezone(timezone.utc).isoformat(),
    }
    upsert_app_settings(
        args.db,
        {
            key_last_day: today_key,
            "cfg_stage1_last_run_at": finished_at.isoformat(),
            "cfg_stage1_next_run_at": next_due.astimezone(timezone.utc).isoformat(),
            "cfg_stage1_last_summary_json": json.dumps(summary, separators=(",", ":")),
        },
    )
    print(
        "[stage1-scheduler] cycle-end "
        f"at={finished_at.isoformat()} status={summary['status']} next={summary['next_run_at']}"
    )
    return True, max(5, int(args.poll_seconds))


def main() -> None:
    args = parse_args()
    args.db = args.db.resolve()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    print(
        "[stage1-scheduler] worker-start "
        f"db={args.db} poll_seconds={int(args.poll_seconds)} enabled={_truthy(os.getenv('YOLO_RELEVANCE_ENABLED', '1'))}"
    )
    try:
        while True:
            _ran, sleep_seconds = _run_cycle(args)
            if args.run_once:
                break
            time.sleep(max(5, int(sleep_seconds)))
    except KeyboardInterrupt:
        print("[stage1-scheduler] worker-stop requested")


if __name__ == "__main__":
    main()

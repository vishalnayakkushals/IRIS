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
        out = int(str(value or "").strip())
        return out
    except Exception:
        return int(default)


def _parse_hhmm(raw: str) -> tuple[int, int]:
    text = str(raw or "").strip()
    if len(text) != 5 or ":" not in text:
        raise ValueError("run-at must be HH:MM")
    hh, mm = text.split(":", 1)
    return int(hh), int(mm)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily GPT vision evaluation scheduler")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--run-once", action="store_true")
    return parser.parse_args()


def _runtime_env() -> dict[str, object]:
    return {
        "enabled": _truthy(os.getenv("GPT_VISION_ENABLED", "0"), default=False),
        "run_at": str(os.getenv("GPT_DAILY_RUN_AT", "02:30") or "02:30").strip(),
        "tz": str(os.getenv("GPT_TZ", "Asia/Kolkata") or "Asia/Kolkata").strip(),
        "store_id": str(os.getenv("GPT_TEST_STORE_ID", "TEST_STORE_D07") or "TEST_STORE_D07").strip(),
        "gdrive_url": str(os.getenv("GPT_TEST_GDRIVE_URL", "") or "").strip(),
        "ground_truth": str(os.getenv("GPT_TEST_GROUND_TRUTH", "/app/data/exports/gpt_eval/TEST_STORE_D07/ground_truth_template.csv") or "").strip(),
        "out_root": str(os.getenv("GPT_TEST_OUTPUT_ROOT", "/app/data/exports/gpt_eval") or "/app/data/exports/gpt_eval").strip(),
        "data_root": str(os.getenv("GPT_TEST_DATA_ROOT", "/app/data/test_stores") or "/app/data/test_stores").strip(),
        "limit": max(1, min(100, _safe_int(os.getenv("GPT_VISION_MAX_IMAGES", "100"), 100))),
        "model": str(os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini").strip(),
        "api_base": str(os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1") or "https://api.openai.com/v1").strip(),
        "save_json": _truthy(os.getenv("GPT_SAVE_JSON", "1"), default=True),
        "skip_sync": _truthy(os.getenv("GPT_SKIP_SYNC", "0"), default=False),
    }


def _next_due(now_local: datetime, run_hour: int, run_minute: int) -> datetime:
    candidate = now_local.replace(hour=run_hour, minute=run_minute, second=0, microsecond=0)
    if now_local >= candidate:
        candidate = candidate + timedelta(days=1)
    return candidate


def _run_cycle(args: argparse.Namespace) -> tuple[bool, int]:
    cfg = _runtime_env()
    settings = get_app_settings(args.db)
    enabled = bool(cfg["enabled"])
    store_id = str(cfg["store_id"])
    key_last_day = f"cfg_gpt_last_run_date__{store_id}"

    try:
        tz = ZoneInfo(str(cfg["tz"]))
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz=tz)
    run_hour, run_minute = _parse_hhmm(str(cfg["run_at"]))

    if not enabled:
        next_due = _next_due(now_local, run_hour, run_minute)
        upsert_app_settings(
            args.db,
            {
                "cfg_gpt_next_run_at": next_due.astimezone(timezone.utc).isoformat(),
                "cfg_gpt_last_summary_json": json.dumps(
                    {
                        "status": "disabled",
                        "message": "GPT_VISION_ENABLED=0",
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
        upsert_app_settings(args.db, {"cfg_gpt_next_run_at": due_today.astimezone(timezone.utc).isoformat()})
        return False, wait_seconds
    if last_run_day == today_key:
        next_due = due_today + timedelta(days=1)
        upsert_app_settings(args.db, {"cfg_gpt_next_run_at": next_due.astimezone(timezone.utc).isoformat()})
        wait_seconds = max(5, min(int(args.poll_seconds), int((next_due - now_local).total_seconds())))
        return False, wait_seconds

    gdrive_url = str(cfg["gdrive_url"] or "")
    ground_truth = str(cfg["ground_truth"] or "")
    if not gdrive_url or not ground_truth:
        upsert_app_settings(
            args.db,
            {
                "cfg_gpt_last_summary_json": json.dumps(
                    {
                        "status": "error",
                        "message": "Missing GPT_TEST_GDRIVE_URL or GPT_TEST_GROUND_TRUTH env.",
                        "at": datetime.now(tz=timezone.utc).isoformat(),
                    },
                    separators=(",", ":"),
                )
            },
        )
        return False, max(5, int(args.poll_seconds))

    command = [
        sys.executable,
        "scripts/evaluate_chatgpt_vision_batch.py",
        "--gdrive-url",
        gdrive_url,
        "--ground-truth",
        ground_truth,
        "--store-id",
        store_id,
        "--limit",
        str(int(cfg["limit"])),
        "--out-dir",
        str(cfg["out_root"]),
        "--data-root",
        str(cfg["data_root"]),
        "--model",
        str(cfg["model"]),
        "--api-base",
        str(cfg["api_base"]),
    ]
    if bool(cfg["save_json"]):
        command.append("--save-json")
    if bool(cfg["skip_sync"]):
        command.append("--skip-sync")

    started_at = datetime.now(tz=timezone.utc)
    print(
        "[gpt-scheduler] cycle-start "
        f"at={started_at.isoformat()} store={store_id} run_at_local={str(cfg['run_at'])} tz={str(cfg['tz'])} "
        f"model={str(cfg['model'])} limit={int(cfg['limit'])}"
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = "/app/src"
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    finished_at = datetime.now(tz=timezone.utc)
    next_due = _next_due(datetime.now(tz=tz), run_hour, run_minute)
    summary = {
        "started_at": started_at.isoformat(),
        "ended_at": finished_at.isoformat(),
        "store_id": store_id,
        "model": str(cfg["model"]),
        "limit": int(cfg["limit"]),
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": int(proc.returncode),
        "stdout_tail": str(proc.stdout or "")[-3000:],
        "stderr_tail": str(proc.stderr or "")[-3000:],
        "next_run_at": next_due.astimezone(timezone.utc).isoformat(),
    }
    upsert_app_settings(
        args.db,
        {
            key_last_day: today_key,
            "cfg_gpt_last_run_at": finished_at.isoformat(),
            "cfg_gpt_next_run_at": next_due.astimezone(timezone.utc).isoformat(),
            "cfg_gpt_last_summary_json": json.dumps(summary, separators=(",", ":")),
        },
    )
    print(
        "[gpt-scheduler] cycle-end "
        f"at={finished_at.isoformat()} status={summary['status']} next={summary['next_run_at']}"
    )
    return True, max(5, int(args.poll_seconds))


def main() -> None:
    args = parse_args()
    args.db = args.db.resolve()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    print(
        "[gpt-scheduler] worker-start "
        f"db={args.db} poll_seconds={int(args.poll_seconds)} enabled={_truthy(os.getenv('GPT_VISION_ENABLED', '0'))}"
    )
    try:
        while True:
            _ran, sleep_seconds = _run_cycle(args)
            if args.run_once:
                break
            time.sleep(max(5, int(sleep_seconds)))
    except KeyboardInterrupt:
        print("[gpt-scheduler] worker-stop requested")


if __name__ == "__main__":
    main()


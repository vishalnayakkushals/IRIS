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
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y", "t"}


def _safe_int(value: object, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return int(default)


def _next_local_time(now_local: datetime, hh: int, mm: int) -> datetime:
    candidate = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now_local >= candidate:
        candidate = candidate + timedelta(days=1)
    return candidate


def _parse_hhmm(text: str) -> tuple[int, int]:
    raw = str(text or "").strip()
    hh, mm = raw.split(":", 1)
    return int(hh), int(mm)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="On-fly scheduler (hourly + nightly catch-up)")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--run-once", action="store_true")
    return parser.parse_args()


def _run_command(command: list[str]) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "/app/src" if Path("/app/src").exists() else "src"
    proc = subprocess.run(command, capture_output=True, text=True, env=env)
    return int(proc.returncode), str(proc.stdout or "")[-3000:], str(proc.stderr or "")[-3000:]


def _run_cycle(args: argparse.Namespace) -> tuple[bool, int]:
    enabled = _truthy(os.getenv("ONFLY_ENABLED", "1"), default=True)
    store_id = str(os.getenv("ONFLY_STORE_ID", "TEST_STORE_D07")).strip() or "TEST_STORE_D07"
    source_url = str(os.getenv("ONFLY_SOURCE_URL", "")).strip()
    out_dir = str(os.getenv("ONFLY_OUT_DIR", "/app/data/exports/current/onfly")).strip()
    tz_name = str(os.getenv("ONFLY_TZ", "Asia/Kolkata")).strip() or "Asia/Kolkata"
    hourly_minutes = max(5, _safe_int(os.getenv("ONFLY_HOURLY_MINUTES", "60"), 60))
    nightly_at = str(os.getenv("ONFLY_NIGHTLY_RUN_AT", "03:00")).strip() or "03:00"
    max_images = max(1, min(100, _safe_int(os.getenv("ONFLY_MAX_IMAGES", "100"), 100)))
    enable_gpt = _truthy(os.getenv("GPT_VISION_ENABLED", "0"), default=False)
    detector = str(os.getenv("ONFLY_DETECTOR", "yolo")).strip() or "yolo"
    conf = str(os.getenv("ONFLY_CONF", "0.18")).strip() or "0.18"
    version = str(os.getenv("ONFLY_PIPELINE_VERSION", "onfly_v1")).strip() or "onfly_v1"
    yolo_version = str(os.getenv("ONFLY_YOLO_VERSION", "")).strip()
    gpt_version = str(os.getenv("ONFLY_GPT_VERSION", "")).strip()
    allow_fallback = _truthy(os.getenv("ONFLY_ALLOW_DETECTOR_FALLBACK", "0"), default=False)

    settings = get_app_settings(args.db)
    key_hourly = f"cfg_onfly_last_hourly__{store_id}"
    key_nightly = f"cfg_onfly_last_nightly__{store_id}"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz=tz)
    hh, mm = _parse_hhmm(nightly_at)

    if not enabled:
        next_nightly = _next_local_time(now_local, hh, mm).astimezone(timezone.utc).isoformat()
        upsert_app_settings(args.db, {"cfg_onfly_next_nightly_at": next_nightly})
        return False, max(5, int(args.poll_seconds))

    if not source_url:
        upsert_app_settings(
            args.db,
            {
                "cfg_onfly_last_summary_json": json.dumps(
                    {"status": "error", "message": "ONFLY_SOURCE_URL is empty", "at": datetime.now(tz=timezone.utc).isoformat()},
                    separators=(",", ":"),
                )
            },
        )
        return False, max(5, int(args.poll_seconds))

    last_hourly = str(settings.get(key_hourly, "") or "").strip()
    run_hourly = True
    if last_hourly:
        try:
            last_dt = datetime.fromisoformat(last_hourly)
            run_hourly = (datetime.now(tz=timezone.utc) - last_dt) >= timedelta(minutes=hourly_minutes)
        except Exception:
            run_hourly = True

    last_nightly_day = str(settings.get(key_nightly, "") or "").strip()
    due_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    run_nightly = now_local >= due_local and last_nightly_day != now_local.date().isoformat()

    mode = ""
    if run_nightly:
        mode = "nightly"
    elif run_hourly:
        mode = "hourly"
    else:
        next_due = min(
            _next_local_time(now_local, hh, mm),
            now_local + timedelta(minutes=hourly_minutes),
        )
        wait = max(5, min(int(args.poll_seconds), int((next_due - now_local).total_seconds())))
        upsert_app_settings(args.db, {"cfg_onfly_next_run_at": next_due.astimezone(timezone.utc).isoformat()})
        return False, wait

    command = [
        sys.executable,
        "scripts/run_onfly_pipeline.py",
        "--store-id",
        store_id,
        "--source-url",
        source_url,
        "--db",
        str(args.db),
        "--out-dir",
        out_dir,
        "--detector",
        detector,
        "--conf",
        conf,
        "--max-images",
        str(max_images),
        "--run-mode",
        mode,
        "--pipeline-version",
        version,
    ]
    if yolo_version:
        command.extend(["--yolo-version", yolo_version])
    if gpt_version:
        command.extend(["--gpt-version", gpt_version])
    if enable_gpt:
        command.append("--enable-gpt")
    if allow_fallback:
        command.append("--allow-detector-fallback")
    rc, out_tail, err_tail = _run_command(command)
    now_utc = datetime.now(tz=timezone.utc)
    history_raw = str(settings.get("cfg_onfly_scheduler_history_json", "[]") or "[]").strip()
    try:
        history = json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []
    history.append(
        {
            "ran_at": now_utc.isoformat(),
            "mode": mode,
            "store_id": store_id,
            "returncode": int(rc),
            "status": "ok" if rc == 0 else "error",
            "stdout_tail": out_tail[-600:],
            "stderr_tail": err_tail[-600:],
        }
    )
    history = history[-40:]
    updates = {
        key_hourly: now_utc.isoformat(),
        "cfg_onfly_last_run_at": now_utc.isoformat(),
        "cfg_onfly_last_summary_json": json.dumps(
            {"status": "ok" if rc == 0 else "error", "mode": mode, "returncode": rc, "stdout_tail": out_tail, "stderr_tail": err_tail},
            separators=(",", ":"),
        ),
        "cfg_onfly_scheduler_history_json": json.dumps(history, separators=(",", ":")),
    }
    if mode == "nightly":
        updates[key_nightly] = now_local.date().isoformat()
    next_nightly = _next_local_time(now_local, hh, mm).astimezone(timezone.utc).isoformat()
    updates["cfg_onfly_next_nightly_at"] = next_nightly
    updates["cfg_onfly_next_run_at"] = (now_utc + timedelta(minutes=hourly_minutes)).isoformat()
    upsert_app_settings(args.db, updates)
    return True, max(5, int(args.poll_seconds))


def main() -> None:
    args = parse_args()
    args.db = args.db.resolve()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    print(f"[onfly-scheduler] start db={args.db} poll={int(args.poll_seconds)}")
    try:
        while True:
            _ran, sleep_sec = _run_cycle(args)
            if args.run_once:
                break
            time.sleep(max(5, int(sleep_sec)))
    except KeyboardInterrupt:
        print("[onfly-scheduler] stop requested")


if __name__ == "__main__":
    main()

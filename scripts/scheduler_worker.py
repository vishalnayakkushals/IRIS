from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import time
import traceback

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.iris_dashboard import (  # noqa: E402
    _ensure_config_defaults,
    _parse_iso_utc,
    _run_scheduler_cycle,
    _scheduler_min_interval_minutes,
    _setting_bool,
    _setting_float,
    _setting_int,
)
from iris.store_registry import upsert_app_settings  # noqa: E402


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on", "y", "t"}


def _coerce_capture_date(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        text = f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _runtime_controls(settings: dict[str, str]) -> dict[str, object]:
    custom_payload: dict[str, object] = {}
    custom_raw = str(settings.get("pipeline_custom_settings_json", "") or "").strip()
    if custom_raw:
        try:
            parsed = json.loads(custom_raw)
            if isinstance(parsed, dict):
                custom_payload = parsed
        except Exception:
            custom_payload = {}

    conf_default = custom_payload.get("ctrl_conf_threshold", 0.18)
    try:
        conf_default = float(conf_default)
    except Exception:
        conf_default = 0.18

    detector_default = str(custom_payload.get("ctrl_detector_type", "yolo") or "yolo").strip().lower()
    if detector_default not in {"yolo", "opencv_hog", "mock"}:
        detector_default = "yolo"

    controls = {
        "conf_threshold": _setting_float(settings, "cfg_detection_conf_threshold", float(conf_default), minimum=0.01, maximum=0.95),
        "detector_type": str(settings.get("cfg_detection_detector_type", detector_default) or detector_default).strip().lower(),
        "time_bucket_minutes": _setting_int(
            settings,
            "cfg_detection_time_bucket_minutes",
            int(custom_payload.get("ctrl_time_bucket_minutes", 1) or 1),
            minimum=1,
            maximum=60,
        ),
        "bounce_threshold_sec": _setting_int(
            settings,
            "cfg_detection_bounce_threshold_sec",
            int(custom_payload.get("ctrl_bounce_threshold_sec", 120) or 120),
            minimum=10,
            maximum=3600,
        ),
        "session_gap_sec": _setting_int(
            settings,
            "cfg_detection_session_gap_sec",
            int(custom_payload.get("ctrl_session_gap_sec", 30) or 30),
            minimum=1,
            maximum=600,
        ),
        "session_timeout_sec": _setting_int(
            settings,
            "cfg_detection_session_timeout_sec",
            int(custom_payload.get("ctrl_session_timeout_sec", 180) or 180),
            minimum=30,
            maximum=7200,
        ),
        "enable_age_gender": _truthy(
            settings.get("cfg_detection_enable_age_gender", custom_payload.get("ctrl_enable_age_gender", False)),
            default=False,
        ),
        "capture_date_filter": _coerce_capture_date(settings.get("cfg_detection_capture_date", "")),
    }
    if controls["detector_type"] not in {"yolo", "opencv_hog", "mock"}:
        controls["detector_type"] = "yolo"
    return controls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IRIS background scheduler worker")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--root", type=Path, default=Path("data/stores"))
    parser.add_argument("--out", type=Path, default=Path("data/exports/current"))
    parser.add_argument("--employee-assets-root", type=Path, default=Path("data/employee_assets"))
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--run-once", action="store_true")
    return parser.parse_args()


def _run_due_cycle(args: argparse.Namespace) -> tuple[bool, int]:
    yolo_enabled = _truthy(os.getenv("YOLO_ENABLED", "1"), default=True)
    settings = _ensure_config_defaults(args.db)
    scheduler_enabled = _setting_bool(settings, "cfg_scheduler_enabled", True)
    min_interval = _scheduler_min_interval_minutes(settings)
    interval_minutes = _setting_int(
        settings,
        "cfg_scheduler_interval_minutes",
        30,
        minimum=min_interval,
        maximum=1440,
    )
    persisted_interval = _setting_int(settings, "cfg_scheduler_interval_minutes", 30, minimum=1, maximum=1440)
    if interval_minutes != persisted_interval:
        upsert_app_settings(args.db, {"cfg_scheduler_interval_minutes": str(int(interval_minutes))})
        settings = _ensure_config_defaults(args.db)

    next_run_dt = _parse_iso_utc(settings.get("cfg_scheduler_next_run_at", ""))
    now_utc = datetime.now(tz=timezone.utc)

    if not scheduler_enabled:
        if next_run_dt is not None:
            upsert_app_settings(args.db, {"cfg_scheduler_next_run_at": ""})
        return False, max(5, int(args.poll_seconds))

    if not yolo_enabled:
        next_run_after = now_utc + timedelta(minutes=int(interval_minutes))
        upsert_app_settings(args.db, {"cfg_scheduler_next_run_at": next_run_after.isoformat()})
        return False, min(max(1, int(args.poll_seconds)), max(1, int((next_run_after - now_utc).total_seconds())))

    if next_run_dt is not None and now_utc < next_run_dt:
        seconds_until_due = max(1, int((next_run_dt - now_utc).total_seconds()))
        return False, min(max(1, int(args.poll_seconds)), seconds_until_due)

    controls = _runtime_controls(settings)
    started_at = datetime.now(tz=timezone.utc)
    print(
        "[scheduler] cycle-start "
        f"at={started_at.isoformat()} interval_min={interval_minutes} detector={controls['detector_type']} "
        f"capture_date={controls['capture_date_filter'] or 'all'}"
    )

    summary: dict[str, object]
    try:
        _output, summary = _run_scheduler_cycle(
            db_path=args.db,
            root_dir=args.root,
            out_dir=args.out,
            employee_assets_root=args.employee_assets_root,
            conf_threshold=float(controls["conf_threshold"]),
            detector_type=str(controls["detector_type"]),
            time_bucket_minutes=int(controls["time_bucket_minutes"]),
            bounce_threshold_sec=int(controls["bounce_threshold_sec"]),
            session_gap_sec=int(controls["session_gap_sec"]),
            session_timeout_sec=int(controls["session_timeout_sec"]),
            capture_date_filter=controls["capture_date_filter"],
            enable_age_gender=bool(controls["enable_age_gender"]),
            write_gzip_exports=True,
            keep_plain_csv=True,
        )
    except Exception as exc:
        summary = {
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=5),
        }
        print(f"[scheduler] cycle-error {summary['error']}")

    finished_at = datetime.now(tz=timezone.utc)
    next_run_after = finished_at + timedelta(minutes=int(interval_minutes))
    upsert_app_settings(
        db_path=args.db,
        settings={
            "cfg_scheduler_last_run_at": finished_at.isoformat(),
            "cfg_scheduler_next_run_at": next_run_after.isoformat(),
            "cfg_scheduler_last_summary_json": json.dumps(summary, separators=(",", ":")),
        },
    )
    print(
        "[scheduler] cycle-end "
        f"at={finished_at.isoformat()} next={next_run_after.isoformat()} summary={summary.get('message', summary.get('status', 'ok'))}"
    )
    return True, max(1, int(args.poll_seconds))


def main() -> None:
    args = parse_args()
    args.db = args.db.resolve()
    args.root = args.root.resolve()
    args.out = args.out.resolve()
    args.employee_assets_root = args.employee_assets_root.resolve()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.root.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    args.employee_assets_root.mkdir(parents=True, exist_ok=True)

    print(
        "[scheduler] worker-start "
        f"db={args.db} root={args.root} out={args.out} poll_seconds={int(args.poll_seconds)} "
        f"yolo_enabled={_truthy(os.getenv('YOLO_ENABLED', '1'), default=True)}"
    )
    try:
        while True:
            _ran, sleep_seconds = _run_due_cycle(args)
            if args.run_once:
                break
            time.sleep(max(1, int(sleep_seconds)))
    except KeyboardInterrupt:
        print("[scheduler] worker-stop requested")


if __name__ == "__main__":
    main()

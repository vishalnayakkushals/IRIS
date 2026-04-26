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

from iris.store_registry import get_app_settings, list_stores, upsert_app_settings  # noqa: E402


ONFLY_SCHEDULER_DEFAULTS: dict[str, object] = {
    "enabled": True,
    "store_id": "BLRRRN",
    "source_url": "",
    "out_dir": "",
    "tz_name": "Asia/Kolkata",
    "hourly_minutes": 60,
    "nightly_at": "03:00",
    "max_images": 0,
    "enable_gpt": True,
    "detector": "yolo",
    "conf": "0.18",
    "pipeline_version": "onfly_v1",
    "yolo_version": "",
    "gpt_version": "",
    "allow_fallback": False,
}


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


def _load_onfly_scheduler_config(db_path: Path) -> dict[str, object]:
    settings = get_app_settings(db_path)

    def _read_str(primary_key: str, fallback_key: str | None = None, default: str = "") -> str:
        primary = str(settings.get(primary_key, "") or "").strip()
        if primary:
            return primary
        if fallback_key:
            secondary = str(settings.get(fallback_key, "") or "").strip()
            if secondary:
                return secondary
        return default

    store_id = _read_str(
        "cfg_onfly_scheduler_store_id",
        "cfg_onfly_store_id",
        str(ONFLY_SCHEDULER_DEFAULTS["store_id"]),
    )
    mapped_source_url = ""
    if store_id:
        for store in list_stores(db_path):
            if str(getattr(store, "store_id", "")).strip() == store_id:
                mapped_source_url = str(getattr(store, "drive_folder_url", "") or "").strip()
                break

    cfg: dict[str, object] = {
        "enabled": _truthy(settings.get("cfg_onfly_scheduler_enabled", "1"), default=bool(ONFLY_SCHEDULER_DEFAULTS["enabled"])),
        "store_id": store_id,
        "source_url": mapped_source_url or _read_str(
            "cfg_onfly_scheduler_source_url",
            "cfg_onfly_source_url",
            str(ONFLY_SCHEDULER_DEFAULTS["source_url"]),
        ),
        "out_dir": _read_str(
            "cfg_onfly_scheduler_out_dir",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["out_dir"]),
        ),
        "tz_name": _read_str(
            "cfg_onfly_scheduler_tz",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["tz_name"]),
        ),
        "hourly_minutes": max(
            5,
            _safe_int(
                settings.get("cfg_onfly_scheduler_hourly_minutes", ONFLY_SCHEDULER_DEFAULTS["hourly_minutes"]),
                int(ONFLY_SCHEDULER_DEFAULTS["hourly_minutes"]),
            ),
        ),
        "nightly_at": _read_str(
            "cfg_onfly_scheduler_nightly_run_at",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["nightly_at"]),
        ),
        "max_images": max(
            0,
            _safe_int(
                settings.get("cfg_onfly_scheduler_max_images", ONFLY_SCHEDULER_DEFAULTS["max_images"]),
                int(ONFLY_SCHEDULER_DEFAULTS["max_images"]),
            ),
        ),
        "enable_gpt": _truthy(
            settings.get("cfg_onfly_scheduler_enable_gpt", "1"),
            default=bool(ONFLY_SCHEDULER_DEFAULTS["enable_gpt"]),
        ),
        "detector": _read_str(
            "cfg_onfly_scheduler_detector",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["detector"]),
        ),
        "conf": _read_str(
            "cfg_onfly_scheduler_conf",
            "cfg_onfly_conf",
            str(ONFLY_SCHEDULER_DEFAULTS["conf"]),
        ),
        "pipeline_version": _read_str(
            "cfg_onfly_scheduler_pipeline_version",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["pipeline_version"]),
        ),
        "yolo_version": _read_str(
            "cfg_onfly_scheduler_yolo_version",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["yolo_version"]),
        ),
        "gpt_version": _read_str(
            "cfg_onfly_scheduler_gpt_version",
            None,
            str(ONFLY_SCHEDULER_DEFAULTS["gpt_version"]),
        ),
        "allow_fallback": _truthy(
            settings.get("cfg_onfly_scheduler_allow_fallback", "0"),
            default=bool(ONFLY_SCHEDULER_DEFAULTS["allow_fallback"]),
        ),
    }
    out_dir = str(cfg.get("out_dir", "") or "").strip()
    if not out_dir:
        cfg["out_dir"] = str((db_path.parent / "exports" / "current" / "onfly").resolve())
    return cfg


def _scheduled_store_rows(db_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for store in list_stores(db_path):
        store_id = str(getattr(store, "store_id", "") or "").strip()
        source_url = str(getattr(store, "drive_folder_url", "") or "").strip()
        if not store_id or not source_url:
            continue
        rows.append({"store_id": store_id, "source_url": source_url})
    return rows


def _build_onfly_command(
    *,
    db_path: Path,
    out_dir: str,
    mode: str,
    store_id: str,
    source_url: str,
    detector: str,
    conf: str,
    max_images: int,
    version: str,
    yolo_version: str,
    gpt_version: str,
    enable_gpt: bool,
    allow_fallback: bool,
) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_onfly_pipeline.py",
        "--store-id",
        store_id,
        "--source-url",
        source_url,
        "--db",
        str(db_path),
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
    return command


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


def _parse_run_summary(stdout_tail: str) -> dict[str, object]:
    raw = str(stdout_tail or "").strip()
    if not raw:
        return {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _run_cycle(args: argparse.Namespace) -> tuple[bool, int]:
    scheduler_cfg = _load_onfly_scheduler_config(args.db)
    enabled = bool(scheduler_cfg["enabled"])
    store_id = str(scheduler_cfg["store_id"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["store_id"])
    source_url = str(scheduler_cfg["source_url"]).strip()
    out_dir = str(scheduler_cfg["out_dir"]).strip()
    tz_name = str(scheduler_cfg["tz_name"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["tz_name"])
    hourly_minutes = int(scheduler_cfg["hourly_minutes"])
    nightly_at = str(scheduler_cfg["nightly_at"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["nightly_at"])
    max_images = int(scheduler_cfg["max_images"])
    enable_gpt = bool(scheduler_cfg["enable_gpt"])
    detector = str(scheduler_cfg["detector"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["detector"])
    conf = str(scheduler_cfg["conf"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["conf"])
    version = str(scheduler_cfg["pipeline_version"]).strip() or str(ONFLY_SCHEDULER_DEFAULTS["pipeline_version"])
    yolo_version = str(scheduler_cfg["yolo_version"]).strip()
    gpt_version = str(scheduler_cfg["gpt_version"]).strip()
    allow_fallback = bool(scheduler_cfg["allow_fallback"])

    settings = get_app_settings(args.db)
    key_hourly = f"cfg_onfly_last_hourly__{store_id}"
    key_nightly = f"cfg_onfly_last_nightly__{store_id}"
    key_nightly_global = "cfg_onfly_last_nightly_global"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz=tz)
    hh, mm = _parse_hhmm(nightly_at)

    if not enabled:
        next_nightly = _next_local_time(now_local, hh, mm).astimezone(timezone.utc).isoformat()
        upsert_app_settings(args.db, {"cfg_onfly_next_nightly_at": next_nightly, "cfg_onfly_next_run_at": ""})
        return False, max(5, int(args.poll_seconds))

    scheduled_rows = _scheduled_store_rows(args.db)
    if not source_url and not scheduled_rows:
        upsert_app_settings(
            args.db,
            {
                "cfg_onfly_last_summary_json": json.dumps(
                    {"status": "error", "message": "No mapped store source found", "at": datetime.now(tz=timezone.utc).isoformat()},
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

    last_nightly_day = str(settings.get(key_nightly_global, settings.get(key_nightly, "")) or "").strip()
    due_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    run_nightly = now_local >= due_local and last_nightly_day != now_local.date().isoformat()

    mode = ""
    if run_nightly:
        mode = "nightly"
    elif run_hourly:
        mode = "hourly"
    else:
        next_nightly_local = _next_local_time(now_local, hh, mm)
        if last_hourly:
            try:
                next_hourly_utc = datetime.fromisoformat(last_hourly) + timedelta(minutes=hourly_minutes)
            except Exception:
                next_hourly_utc = datetime.now(tz=timezone.utc) + timedelta(minutes=hourly_minutes)
        else:
            next_hourly_utc = datetime.now(tz=timezone.utc)
        next_due_utc = min(next_hourly_utc, next_nightly_local.astimezone(timezone.utc))
        wait = max(5, min(int(args.poll_seconds), max(5, int((next_due_utc - datetime.now(tz=timezone.utc)).total_seconds()))))
        upsert_app_settings(
            args.db,
            {
                "cfg_onfly_next_run_at": next_due_utc.isoformat(),
                "cfg_onfly_next_nightly_at": next_nightly_local.astimezone(timezone.utc).isoformat(),
            },
        )
        return False, wait

    now_utc = datetime.now(tz=timezone.utc)
    scheduled_targets = (
        scheduled_rows
        if mode == "nightly"
        else [{"store_id": store_id, "source_url": source_url}] if store_id and source_url else []
    )
    if not scheduled_targets:
        upsert_app_settings(
            args.db,
            {
                "cfg_onfly_last_summary_json": json.dumps(
                    {"status": "error", "message": "Selected store has no mapped source URL", "mode": mode},
                    separators=(",", ":"),
                )
            },
        )
        return False, max(5, int(args.poll_seconds))

    history_raw = str(settings.get("cfg_onfly_scheduler_history_json", "[]") or "[]").strip()
    try:
        history = json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []

    run_results: list[dict[str, object]] = []
    any_ran = False
    gpt_retry_pending = 0
    overall_rc = 0
    for target in scheduled_targets:
        target_store_id = str(target.get("store_id", "") or "").strip()
        target_source_url = str(target.get("source_url", "") or "").strip()
        if not target_store_id or not target_source_url:
            continue
        any_ran = True
        command = _build_onfly_command(
            db_path=args.db,
            out_dir=out_dir,
            mode=mode,
            store_id=target_store_id,
            source_url=target_source_url,
            detector=detector,
            conf=conf,
            max_images=max_images,
            version=version,
            yolo_version=yolo_version,
            gpt_version=gpt_version,
            enable_gpt=enable_gpt,
            allow_fallback=allow_fallback,
        )
        rc, out_tail, err_tail = _run_command(command)
        parsed_summary = _parse_run_summary(out_tail)
        target_retry_pending = int(parsed_summary.get("gpt_retry_pending", 0) or 0) if parsed_summary else 0
        gpt_retry_pending += target_retry_pending
        overall_rc = max(overall_rc, int(rc))
        history.append(
            {
                "ran_at": now_utc.isoformat(),
                "mode": mode,
                "store_id": target_store_id,
                "returncode": int(rc),
                "status": "quota_waiting" if target_retry_pending > 0 else ("ok" if rc == 0 else "error"),
                "stdout_tail": out_tail[-600:],
                "stderr_tail": err_tail[-600:],
                "gpt_retry_pending": target_retry_pending,
            }
        )
        run_results.append(
            {
                "store_id": target_store_id,
                "returncode": int(rc),
                "status": "quota_waiting" if target_retry_pending > 0 else ("ok" if rc == 0 else "error"),
                "stdout_tail": out_tail,
                "stderr_tail": err_tail,
                "gpt_retry_pending": target_retry_pending,
            }
        )

    if not any_ran:
        return False, max(5, int(args.poll_seconds))

    history = history[-40:]
    overall_status = "quota_waiting" if gpt_retry_pending > 0 else ("ok" if overall_rc == 0 else "error")
    updates = {
        key_hourly: now_utc.isoformat(),
        "cfg_onfly_last_run_at": now_utc.isoformat(),
        "cfg_onfly_last_status": overall_status,
        "cfg_onfly_last_summary_json": json.dumps(
            {
                "status": overall_status,
                "mode": mode,
                "returncode": overall_rc,
                "stores_ran": [str(r.get("store_id", "") or "").strip() for r in run_results],
                "store_results": run_results,
                "gpt_retry_pending": gpt_retry_pending,
            },
            separators=(",", ":"),
        ),
        "cfg_onfly_scheduler_history_json": json.dumps(history, separators=(",", ":")),
    }
    if mode == "nightly":
        updates[key_nightly_global] = now_local.date().isoformat()
        for target in scheduled_targets:
            target_store_id = str(target.get("store_id", "") or "").strip()
            if target_store_id:
                updates[f"cfg_onfly_last_nightly__{target_store_id}"] = now_local.date().isoformat()
    next_nightly = _next_local_time(now_local, hh, mm).astimezone(timezone.utc).isoformat()
    updates["cfg_onfly_next_nightly_at"] = next_nightly
    if gpt_retry_pending > 0:
        updates["cfg_onfly_next_run_at"] = (now_utc + timedelta(minutes=5)).isoformat()
    else:
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

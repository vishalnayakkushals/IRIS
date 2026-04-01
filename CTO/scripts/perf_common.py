from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


CTO_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = CTO_DIR / "logs"
REPORT_DIR = CTO_DIR / "reports"
MAIN_LOG_FILE = LOG_DIR / "perf_events.jsonl"


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_epoch_ms() -> int:
    return int(time.time() * 1000)


def new_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_{uuid4().hex[:6]}"


def append_event(event: dict[str, Any]) -> None:
    ensure_dirs()
    payload = dict(event)
    payload.setdefault("logged_at", now_iso_utc())
    with MAIN_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_events() -> list[dict[str, Any]]:
    if not MAIN_LOG_FILE.exists():
        return []
    rows: list[dict[str, Any]] = []
    with MAIN_LOG_FILE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def percentile(values: Iterable[float], pct: float) -> float:
    data = sorted(float(v) for v in values)
    if not data:
        return 0.0
    if pct <= 0:
        return data[0]
    if pct >= 100:
        return data[-1]
    idx = (len(data) - 1) * (pct / 100.0)
    lower = int(idx)
    upper = min(lower + 1, len(data) - 1)
    frac = idx - lower
    return data[lower] * (1.0 - frac) + data[upper] * frac

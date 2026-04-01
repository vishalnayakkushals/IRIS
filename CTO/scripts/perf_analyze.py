from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from perf_common import REPORT_DIR, load_events, percentile


def _run_sort_key(run_id: str, starts: dict[str, int]) -> tuple[int, str]:
    return (int(starts.get(run_id, 0)), run_id)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _group_probe_events(events: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, list[dict[str, Any]]]]:
    run_starts: dict[str, int] = {}
    run_probe_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        run_id = str(event.get("run_id", "")).strip()
        if not run_id:
            continue
        event_type = str(event.get("event_type", "")).strip().lower()
        if event_type == "run_start":
            run_starts[run_id] = _as_int(event.get("start_ms", 0))
        if event_type == "page_probe":
            run_probe_events[run_id].append(event)
    return run_starts, run_probe_events


def _summarize_run(run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [_safe_float(e.get("duration_ms", 0)) for e in events]
    statuses = [str(e.get("status", "")).lower() for e in events]
    return {
        "run_id": run_id,
        "probe_count": len(events),
        "success_count": sum(1 for s in statuses if s == "success"),
        "failed_count": sum(1 for s in statuses if s != "success"),
        "avg_probe_ms": round(mean(durations), 2) if durations else 0.0,
        "p95_probe_ms": round(percentile(durations, 95), 2) if durations else 0.0,
    }


def _path_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    bucket: dict[str, list[float]] = defaultdict(list)
    for e in events:
        path = str(e.get("path_name", "")).strip() or str(e.get("url", "")).strip() or "unknown"
        bucket[path].append(_safe_float(e.get("duration_ms", 0)))
    stats: dict[str, dict[str, Any]] = {}
    for path, durations in bucket.items():
        stats[path] = {
            "count": len(durations),
            "avg_ms": round(mean(durations), 2),
            "p95_ms": round(percentile(durations, 95), 2),
        }
    return stats


def _write_regression_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "path_name",
        "latest_count",
        "latest_avg_ms",
        "latest_p95_ms",
        "previous_count",
        "previous_avg_ms",
        "delta_ms",
        "delta_pct",
        "regression",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_markdown_report(
    path: Path,
    latest_summary: dict[str, Any],
    previous_summary: dict[str, Any] | None,
    slow_paths: list[dict[str, Any]],
    regression_rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# CTO Performance Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Latest run: `{latest_summary.get('run_id', '')}`")
    lines.append(f"- Probe count: {latest_summary.get('probe_count', 0)}")
    lines.append(f"- Avg probe ms: {latest_summary.get('avg_probe_ms', 0)}")
    lines.append(f"- P95 probe ms: {latest_summary.get('p95_probe_ms', 0)}")
    if previous_summary:
        lines.append(f"- Previous run: `{previous_summary.get('run_id', '')}`")
        lines.append(f"- Previous avg probe ms: {previous_summary.get('avg_probe_ms', 0)}")
    lines.append("")
    lines.append("## Slowest Paths (Latest Run)")
    if not slow_paths:
        lines.append("- No page probe rows found.")
    else:
        for row in slow_paths:
            lines.append(
                f"- `{row['path_name']}`: avg={row['latest_avg_ms']} ms, p95={row['latest_p95_ms']} ms, samples={row['latest_count']}"
            )
    lines.append("")
    lines.append("## Regressions vs Previous Run")
    regressions = [r for r in regression_rows if r.get("regression") == "yes"]
    if not regressions:
        lines.append("- No regressions detected.")
    else:
        for row in regressions[:10]:
            lines.append(
                f"- `{row['path_name']}` worsened by {row['delta_ms']} ms ({row['delta_pct']}%)"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze CTO perf logs and flag slow/regressing paths.")
    parser.add_argument("--slow-threshold-ms", type=float, default=1200.0)
    parser.add_argument("--top", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    events = load_events()
    run_starts, run_probe_events = _group_probe_events(events)
    if not run_probe_events:
        print("No page_probe events found in CTO/logs/perf_events.jsonl")
        return

    sorted_runs = sorted(run_probe_events.keys(), key=lambda rid: _run_sort_key(rid, run_starts))
    latest_run_id = sorted_runs[-1]
    previous_run_id = sorted_runs[-2] if len(sorted_runs) > 1 else None

    latest_events = run_probe_events[latest_run_id]
    latest_summary = _summarize_run(latest_run_id, latest_events)
    latest_path_stats = _path_stats(latest_events)

    previous_summary = None
    previous_path_stats: dict[str, dict[str, Any]] = {}
    if previous_run_id:
        previous_events = run_probe_events[previous_run_id]
        previous_summary = _summarize_run(previous_run_id, previous_events)
        previous_path_stats = _path_stats(previous_events)

    all_paths = sorted(set(latest_path_stats.keys()) | set(previous_path_stats.keys()))
    regression_rows: list[dict[str, Any]] = []
    for path_name in all_paths:
        latest = latest_path_stats.get(path_name, {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0})
        prev = previous_path_stats.get(path_name, {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0})
        delta_ms = round(float(latest["avg_ms"]) - float(prev["avg_ms"]), 2)
        delta_pct = round((delta_ms / float(prev["avg_ms"]) * 100.0), 2) if float(prev["avg_ms"]) > 0 else 0.0
        regression_rows.append(
            {
                "path_name": path_name,
                "latest_count": int(latest["count"]),
                "latest_avg_ms": float(latest["avg_ms"]),
                "latest_p95_ms": float(latest["p95_ms"]),
                "previous_count": int(prev["count"]),
                "previous_avg_ms": float(prev["avg_ms"]),
                "delta_ms": delta_ms,
                "delta_pct": delta_pct,
                "regression": "yes" if delta_ms > 0 else "no",
            }
        )

    slow_paths = sorted(
        [row for row in regression_rows if float(row["latest_avg_ms"]) >= float(args.slow_threshold_ms)],
        key=lambda r: float(r["latest_avg_ms"]),
        reverse=True,
    )[: max(1, int(args.top))]

    csv_path = REPORT_DIR / "perf_regression_report.csv"
    md_path = REPORT_DIR / "latest_perf_report.md"
    _write_regression_csv(csv_path, regression_rows)
    _write_markdown_report(md_path, latest_summary, previous_summary, slow_paths, regression_rows)

    print(f"Latest run: {latest_run_id}")
    print(f"Probe rows: {latest_summary['probe_count']}, avg={latest_summary['avg_probe_ms']} ms, p95={latest_summary['p95_probe_ms']} ms")
    print(f"Report: {md_path}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()

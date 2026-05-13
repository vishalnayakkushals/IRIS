from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.runtime_bootstrap import load_env_file  # noqa: E402
from iris.source_clients import GDriveClient, LocalClient, parse_date_token, parse_drive_folder_id  # noqa: E402


STAGE_NAME_MAP = {
    "LIST": "LIST",
    "SKIP_CHECK": "SKIP_CHECK",
    "DOWNLOAD": "DOWNLOAD",
    "YOLO": "YOLO",
    "GPT": "GPT",
    "REPORT_WRITER": "REPORT_WRITE",
    "REPORT_WRITE": "REPORT_WRITE",
    "DASHBOARD_INGEST": "DASHBOARD_INGEST",
}

FAILURE_STAGE_ORDER = [
    "LIST",
    "SKIP_CHECK",
    "DOWNLOAD",
    "YOLO",
    "GPT",
    "REPORT_WRITE",
    "DASHBOARD_INGEST",
]

GPT_FAILED_STATUSES = {"failed", "quota_pending_retry", "gpt_dlq"}
GPT_SUCCESS_STATUSES = {"done"}


@dataclass(frozen=True)
class StoreSource:
    store_id: str
    store_name: str
    source_uri: str
    source_provider: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export exact IRIS on-fly processing stats by store and date")
    parser.add_argument("--store-id", default="", help="Optional store filter")
    parser.add_argument("--date", default="", help="Optional date filter in dd-mm-yyyy or yyyy-mm-dd")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args()


def _display_date(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    parsed = parse_date_token(raw)
    if parsed is not None:
        return parsed.strftime("%d-%m-%Y")
    if len(raw) == 10 and raw[2] == "-" and raw[5] == "-":
        return raw
    return raw


def _iso_date(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    parsed = parse_date_token(raw)
    if parsed is not None:
        return parsed.isoformat()
    if len(raw) == 10 and raw[2] == "-" and raw[5] == "-":
        return f"{raw[6:10]}-{raw[3:5]}-{raw[0:2]}"
    return raw


def _normalized_display_filter(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        parsed = parse_date_token(text)
        return parsed.strftime("%d-%m-%Y") if parsed is not None else text
    return text


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _store_sources(store_id: str) -> list[StoreSource]:
    from iris.runtime_bootstrap import load_env_file as _load_env_file  # noqa: WPS433

    _load_env_file()
    from backend.app.db.canonical_metadata import stores  # noqa: WPS433
    from backend.app.db.session import engine_sync  # noqa: WPS433
    import sqlalchemy as sa  # noqa: WPS433

    rows: list[StoreSource] = []
    with engine_sync.begin() as conn:
        stmt = sa.select(stores.c.store_id, stores.c.store_name, stores.c.drive_folder_url).order_by(stores.c.store_id)
        if store_id:
            stmt = stmt.where(stores.c.store_id == store_id)
        for row in conn.execute(stmt).mappings().all():
            uri = str(row.get("drive_folder_url") or "").strip()
            provider = "gdrive" if parse_drive_folder_id(uri) else ("local" if uri else "")
            rows.append(
                StoreSource(
                    store_id=str(row.get("store_id") or "").strip(),
                    store_name=str(row.get("store_name") or row.get("store_id") or "").strip(),
                    source_uri=uri,
                    source_provider=provider,
                )
            )
    return rows


def _fallback_store_sources(db_path: Path, store_id: str) -> list[StoreSource]:
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = []
        where = ""
        if store_id:
            where = "WHERE store_id=?"
            params.append(store_id)
        rows = conn.execute(
            f"""
            SELECT store_id, source_uri, source_provider, MAX(last_seen_at) AS latest_seen
            FROM onfly_image_state
            {where}
            GROUP BY store_id, source_uri, source_provider
            ORDER BY store_id, latest_seen DESC
            """,
            tuple(params),
        ).fetchall()
        first_by_store: dict[str, StoreSource] = {}
        for row in rows:
            sid = str(row["store_id"] or "").strip()
            if sid and sid not in first_by_store:
                first_by_store[sid] = StoreSource(
                    store_id=sid,
                    store_name=sid,
                    source_uri=str(row["source_uri"] or "").strip(),
                    source_provider=str(row["source_provider"] or "").strip(),
                )
        return list(first_by_store.values())
    finally:
        conn.close()


def _build_client(source: StoreSource, google_api_key: str):
    if source.source_provider == "gdrive" or parse_drive_folder_id(source.source_uri):
        return GDriveClient(source.source_uri, google_api_key)
    return LocalClient(source.source_uri)


def _display_from_source_token(token: str) -> str:
    raw = str(token or "").strip()
    if not raw:
        return ""
    parsed = parse_date_token(raw)
    if parsed is not None:
        return parsed.strftime("%d-%m-%Y")
    return raw


def _source_inventory_local(client: LocalClient, *, display_filter: str) -> dict[str, int]:
    inventory: dict[str, int] = defaultdict(int)
    for path in client.root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            continue
        rel = path.relative_to(client.root)
        first_part = str(rel.parts[0]).strip() if rel.parts else ""
        display_date = _display_from_source_token(first_part) or "unknown_date"
        if display_filter and display_date != display_filter:
            continue
        inventory[display_date] += 1
    return dict(inventory)


def _source_inventory_gdrive(client: GDriveClient, *, display_filter: str) -> dict[str, int]:
    inventory: dict[str, int] = defaultdict(int)

    def _walk(folder_id: str, rel_parts: list[str]) -> None:
        subfolders, images = client._list_folder(folder_id)
        display_date = _display_from_source_token(rel_parts[0]) if rel_parts else ""
        for _ in images:
            date_key = display_date or "unknown_date"
            if display_filter and date_key != display_filter:
                continue
            inventory[date_key] += 1
        for subfolder in subfolders:
            name = str(subfolder.get("name") or "").strip()
            if not name:
                continue
            if display_filter and not rel_parts:
                subfolder_date = _display_from_source_token(name)
                if subfolder_date != display_filter:
                    continue
            _walk(str(subfolder.get("id") or "").strip(), rel_parts + [name])

    _walk(client.folder_id, [])
    return dict(inventory)


def _source_inventory(source: StoreSource, *, google_api_key: str, display_filter: str) -> dict[str, int]:
    if not source.source_uri:
        return {}
    client = _build_client(source, google_api_key)
    if isinstance(client, GDriveClient):
        return _source_inventory_gdrive(client, display_filter=display_filter)
    if isinstance(client, LocalClient):
        return _source_inventory_local(client, display_filter=display_filter)
    return {}


def _state_stats(conn: sqlite3.Connection, store_id: str, display_filter: str) -> dict[str, dict[str, int]]:
    params: list[Any] = [store_id]
    where = ["store_id=?"]
    if display_filter:
        where.append("date_display=?")
        params.append(display_filter)
    rows = conn.execute(
        f"""
        SELECT
            date_display,
            COUNT(*) AS scanned_listed,
            SUM(CASE WHEN yolo_status='done' THEN 1 ELSE 0 END) AS yolo_processed,
            SUM(CASE WHEN yolo_status='done' AND yolo_relevant=1 THEN 1 ELSE 0 END) AS yolo_relevant,
            SUM(CASE WHEN yolo_status='done' AND yolo_relevant=0 THEN 1 ELSE 0 END) AS yolo_irrelevant,
            SUM(CASE WHEN LOWER(COALESCE(gpt_status,'')) IN ('done') THEN 1 ELSE 0 END) AS gpt_successful,
            SUM(CASE WHEN LOWER(COALESCE(gpt_status,'')) IN ('failed','quota_pending_retry','gpt_dlq') THEN 1 ELSE 0 END) AS gpt_failed
        FROM onfly_image_state
        WHERE {" AND ".join(where)}
        GROUP BY date_display
        ORDER BY date_display
        """,
        tuple(params),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        key = str(row["date_display"] or "").strip() or "unknown_date"
        out[key] = {
            "scanned_listed": int(row["scanned_listed"] or 0),
            "yolo_processed": int(row["yolo_processed"] or 0),
            "yolo_relevant": int(row["yolo_relevant"] or 0),
            "yolo_irrelevant": int(row["yolo_irrelevant"] or 0),
            "gpt_successful": int(row["gpt_successful"] or 0),
            "gpt_failed": int(row["gpt_failed"] or 0),
        }
    return out


def _walkin_counts(conn: sqlite3.Connection, store_id: str, display_filter: str) -> dict[str, int]:
    params: list[Any] = [store_id]
    where = ["store_id=?"]
    if display_filter:
        where.append("business_date=?")
        params.append(_iso_date(display_filter))
    rows = conn.execute(
        f"""
        SELECT business_date, COUNT(*) AS walkin_rows
        FROM onfly_walkin_sessions
        WHERE {" AND ".join(where)}
        GROUP BY business_date
        """,
        tuple(params),
    ).fetchall()
    return {
        _display_date(str(row["business_date"] or "").strip()): int(row["walkin_rows"] or 0)
        for row in rows
    }


def _run_dates(conn: sqlite3.Connection, store_id: str) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT run_id, business_date
        FROM onfly_pipeline_runs
        WHERE store_id=?
        """,
        (store_id,),
    ).fetchall()
    return {str(row["run_id"] or ""): _display_date(str(row["business_date"] or "").strip()) for row in rows}


def _event_aggregates(conn: sqlite3.Connection, store_id: str, display_filter: str) -> dict[str, dict[str, Any]]:
    image_dates = {
        str(row["image_id"]): str(row["date_display"] or "").strip() or "unknown_date"
        for row in conn.execute("SELECT image_id, date_display FROM onfly_image_state WHERE store_id=?", (store_id,)).fetchall()
    }
    run_dates = _run_dates(conn, store_id)
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "delta_skipped_images": set(),
        "gpt_attempted_images": set(),
        "stage_failures": {stage: 0 for stage in FAILURE_STAGE_ORDER},
        "stage_failure_reasons": {stage: Counter() for stage in FAILURE_STAGE_ORDER},
    })
    rows = conn.execute(
        """
        SELECT e.run_id, e.stage, e.event_type, e.image_id, e.message, e.error_message, e.payload_json
        FROM onfly_pipeline_run_events e
        INNER JOIN onfly_pipeline_runs r ON r.run_id = e.run_id
        WHERE r.store_id=?
        ORDER BY e.created_at ASC, e.event_id ASC
        """,
        (store_id,),
    ).fetchall()
    for row in rows:
        image_id = str(row["image_id"] or "").strip()
        date_key = image_dates.get(image_id, "")
        if not date_key:
            date_key = run_dates.get(str(row["run_id"] or "").strip(), "") or "UNSCOPED"
        if display_filter and date_key != display_filter:
            continue
        event_bucket = out[date_key]
        stage = STAGE_NAME_MAP.get(str(row["stage"] or "").strip(), str(row["stage"] or "").strip())
        message = str(row["message"] or "").strip()
        error_message = str(row["error_message"] or "").strip()
        event_type = str(row["event_type"] or "").strip().lower()
        if stage == "SKIP_CHECK" and image_id and "Skipped by delta check" in message:
            event_bucket["delta_skipped_images"].add(image_id)
        if stage == "GPT" and image_id and event_type == "start":
            event_bucket["gpt_attempted_images"].add(image_id)
        if stage in FAILURE_STAGE_ORDER and event_type == "failure":
            event_bucket["stage_failures"][stage] += 1
            if error_message or message:
                event_bucket["stage_failure_reasons"][stage][error_message or message] += 1
    return out


def _report_file_counts(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    display_filter: str,
    out_dir: Path,
    candidate_dates: set[str],
) -> dict[str, dict[str, Any]]:
    params: list[Any] = [store_id]
    where = ["store_id=?"]
    if display_filter:
        where.append("business_date=?")
        params.append(_iso_date(display_filter))
    rows = conn.execute(
        f"""
        SELECT business_date, image_results_csv, walkin_sessions_csv, store_date_csv, summary_json
        FROM onfly_report_index
        WHERE {" AND ".join(where)}
        """,
        tuple(params),
    ).fetchall()
    indexed_by_date: dict[str, dict[str, str]] = {}
    for row in rows:
        date_key = _display_date(str(row["business_date"] or "").strip()) or "unknown_date"
        indexed_by_date[date_key] = {
            "image_results_csv": str(row["image_results_csv"] or "").strip(),
            "walkin_sessions_csv": str(row["walkin_sessions_csv"] or "").strip(),
            "store_date_csv": str(row["store_date_csv"] or "").strip(),
            "summary_json": str(row["summary_json"] or "").strip(),
        }

    out: dict[str, dict[str, Any]] = {}
    for date_key in sorted(set(candidate_dates) | set(indexed_by_date.keys())):
        indexed_paths = indexed_by_date.get(date_key, {})
        existing, report_visible = _existing_report_paths_for_date(
            store_id=store_id,
            date_key=date_key,
            out_dir=out_dir,
            indexed_paths=indexed_paths,
        )
        report_index_present = date_key in indexed_by_date
        out[date_key] = {
            "report_files_generated": len(existing),
            "report_file_paths": existing,
            "report_index_present": report_index_present,
            "report_visible_in_dashboard": report_visible and report_index_present,
            "report_generated_not_visible": report_visible and not report_index_present,
        }
    return out


def _mismatch_notes(row: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if row["files_exist_not_scanned"] > 0:
        notes.append(
            f"files exist but not scanned: {row['files_exist_not_scanned']}"
        )
    if row["scanned_not_yolo_processed"] > 0:
        notes.append(
            f"scanned but not YOLO processed: {row['scanned_not_yolo_processed']}"
        )
    if row["relevant_missing_gpt"] > 0:
        notes.append(
            f"relevant but GPT missing: {row['relevant_missing_gpt']}"
        )
    if row["gpt_success_missing_session_rows"] > 0:
        notes.append(
            f"GPT success but no session row: {row['gpt_success_missing_session_rows']}"
        )
    if row["report_generated_not_visible"]:
        notes.append("report generated but not visible in dashboard")
    return notes


def _jsonify_counter(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return json.dumps(dict(counter.most_common()), separators=(",", ":"))


def _csv_has_store_date_row(path: Path, *, store_id: str, date_key: str) -> bool:
    if not path.exists():
        return False
    display_date = _display_date(date_key)
    iso_date = _iso_date(date_key)
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_store = str(row.get("store_id", "") or "").strip()
                if row_store and row_store != store_id:
                    continue
                row_date = _display_date(str(row.get("Date", "") or row.get("business_date", "") or row.get("date", "") or "").strip())
                if row_date and row_date == display_date:
                    return True
                if iso_date and _iso_date(str(row.get("business_date", "") or row.get("date", "") or "").strip()) == iso_date:
                    return True
    except Exception:
        return False
    return False


def _existing_report_paths_for_date(
    *,
    store_id: str,
    date_key: str,
    out_dir: Path,
    indexed_paths: dict[str, str],
) -> tuple[list[str], bool]:
    store_root = out_dir / store_id
    canonical_image_results = store_root / "onfly_image_results.csv"
    canonical_walkin = store_root / "onfly_walkin_sessions.csv"
    canonical_store_date = out_dir / "onfly_store_date_report.csv"

    existing_paths: list[str] = []
    report_visible = False

    image_results_path = Path(indexed_paths.get("image_results_csv") or canonical_image_results)
    if _csv_has_store_date_row(image_results_path, store_id=store_id, date_key=date_key):
        existing_paths.append(str(image_results_path.resolve()))
        report_visible = True

    walkin_path = Path(indexed_paths.get("walkin_sessions_csv") or canonical_walkin)
    if _csv_has_store_date_row(walkin_path, store_id=store_id, date_key=date_key):
        existing_paths.append(str(walkin_path.resolve()))
        report_visible = True

    store_date_path = Path(indexed_paths.get("store_date_csv") or canonical_store_date)
    if _csv_has_store_date_row(store_date_path, store_id=store_id, date_key=date_key):
        existing_paths.append(str(store_date_path.resolve()))
        report_visible = True

    summary_json_path = str(indexed_paths.get("summary_json") or "").strip()
    if summary_json_path and Path(summary_json_path).exists():
        existing_paths.append(str(Path(summary_json_path).resolve()))

    return sorted(dict.fromkeys(existing_paths)), report_visible


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    load_env_file()
    db_path = args.db.resolve()
    out_dir = args.out_dir.resolve()
    output_csv = args.output_csv.resolve() if args.output_csv else (out_dir / "onfly_processing_stats.csv")
    output_json = args.output_json.resolve() if args.output_json else (out_dir / "onfly_processing_stats_summary.json")
    google_api_key = str(os.environ.get("GOOGLE_API_KEY", "")).strip()
    display_filter = _normalized_display_filter(args.date)

    store_sources = [source for source in _store_sources(args.store_id) if source.source_uri]
    if not store_sources:
        store_sources = _fallback_store_sources(db_path, args.store_id)

    conn = _sqlite_connect(db_path)
    try:
        rows: list[dict[str, Any]] = []
        for source in store_sources:
            source_inventory = _source_inventory(source, google_api_key=google_api_key, display_filter=display_filter)
            state_stats = _state_stats(conn, source.store_id, display_filter)
            walkin_counts = _walkin_counts(conn, source.store_id, display_filter)
            event_stats = _event_aggregates(conn, source.store_id, display_filter)
            candidate_dates = {
                *source_inventory.keys(),
                *state_stats.keys(),
                *walkin_counts.keys(),
                *event_stats.keys(),
            }
            report_stats = _report_file_counts(
                conn,
                store_id=source.store_id,
                display_filter=display_filter,
                out_dir=out_dir,
                candidate_dates=candidate_dates,
            )
            all_dates = sorted(candidate_dates | set(report_stats.keys()))
            for date_key in all_dates:
                state = state_stats.get(date_key, {})
                events = event_stats.get(date_key, {})
                reports = report_stats.get(date_key, {})
                delta_skipped = len(events.get("delta_skipped_images", set()))
                gpt_attempted = len(events.get("gpt_attempted_images", set()))
                source_total = int(source_inventory.get(date_key, 0))
                scanned_listed = int(state.get("scanned_listed", 0))
                yolo_processed = int(state.get("yolo_processed", 0))
                yolo_relevant = int(state.get("yolo_relevant", 0))
                gpt_successful = int(state.get("gpt_successful", 0))
                walkin_rows = int(walkin_counts.get(date_key, 0))
                files_exist_not_scanned = max(0, source_total - scanned_listed)
                scanned_not_yolo_processed = max(0, scanned_listed - yolo_processed - delta_skipped)
                relevant_missing_gpt = max(0, yolo_relevant - gpt_attempted)
                gpt_success_missing_session_rows = max(0, gpt_successful - walkin_rows)
                row = {
                    "store_id": source.store_id,
                    "store_name": source.store_name,
                    "source_provider": source.source_provider,
                    "source_uri": source.source_uri,
                    "folder_date": date_key,
                    "total_image_files_available": source_total,
                    "scanned_listed": scanned_listed,
                    "delta_skipped": int(delta_skipped),
                    "yolo_processed": yolo_processed,
                    "yolo_relevant": yolo_relevant,
                    "yolo_irrelevant": int(state.get("yolo_irrelevant", 0)),
                    "gpt_attempted": int(gpt_attempted),
                    "gpt_successful": gpt_successful,
                    "gpt_failed": int(state.get("gpt_failed", 0)),
                    "walkin_rows_generated": walkin_rows,
                    "report_files_generated": int(reports.get("report_files_generated", 0)),
                    "files_exist_not_scanned": files_exist_not_scanned,
                    "scanned_not_yolo_processed": scanned_not_yolo_processed,
                    "relevant_missing_gpt": relevant_missing_gpt,
                    "gpt_success_missing_session_rows": gpt_success_missing_session_rows,
                    "missing_unprocessed_images": max(0, source_total - yolo_processed - delta_skipped),
                    "failure_list_count": int(events.get("stage_failures", {}).get("LIST", 0)),
                    "failure_skip_check_count": int(events.get("stage_failures", {}).get("SKIP_CHECK", 0)),
                    "failure_download_count": int(events.get("stage_failures", {}).get("DOWNLOAD", 0)),
                    "failure_yolo_count": int(events.get("stage_failures", {}).get("YOLO", 0)),
                    "failure_gpt_count": int(events.get("stage_failures", {}).get("GPT", 0)),
                    "failure_report_write_count": int(events.get("stage_failures", {}).get("REPORT_WRITE", 0)),
                    "failure_dashboard_ingest_count": int(events.get("stage_failures", {}).get("DASHBOARD_INGEST", 0)),
                    "failure_list_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("LIST", Counter())),
                    "failure_skip_check_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("SKIP_CHECK", Counter())),
                    "failure_download_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("DOWNLOAD", Counter())),
                    "failure_yolo_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("YOLO", Counter())),
                    "failure_gpt_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("GPT", Counter())),
                    "failure_report_write_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("REPORT_WRITE", Counter())),
                    "failure_dashboard_ingest_reasons": _jsonify_counter(events.get("stage_failure_reasons", {}).get("DASHBOARD_INGEST", Counter())),
                    "report_index_present": bool(reports.get("report_index_present", False)),
                    "report_visible_in_dashboard": bool(reports.get("report_visible_in_dashboard", False)),
                    "report_generated_not_visible": bool(reports.get("report_generated_not_visible", False)),
                    "report_file_paths_json": json.dumps(reports.get("report_file_paths", []), separators=(",", ":")),
                }
                row["source_total_files"] = row["total_image_files_available"]
                row["mismatch_notes"] = " | ".join(_mismatch_notes(row))
                rows.append(row)
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            fieldnames = list(rows[0].keys())
            with output_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        else:
            output_csv.write_text("", encoding="utf-8")
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": {"store_id": args.store_id or "", "date": display_filter or ""},
            "row_count": len(rows),
            "stores": sorted({row["store_id"] for row in rows}),
            "output_csv": str(output_csv.resolve()),
            "output_json": str(output_json.resolve()),
            "ui_recommendation": {
                "section": "Pipeline / Operations",
                "placement": "Add a collapsible 'Processing Stats' table directly below Date-wise Scan Report on /scheduler.",
            },
            "rows": rows,
        }
        output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(str(output_csv.resolve()))
        print(str(output_json.resolve()))
        return rows
    finally:
        conn.close()


def main() -> None:
    args = parse_args()
    build_rows(args)


if __name__ == "__main__":
    main()

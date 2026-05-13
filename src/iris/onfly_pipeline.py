from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import concurrent.futures
import json
import os
import random
import sqlite3
import time
from typing import Any

import pandas as pd

from iris.iris_analysis import build_detector
from iris.store_registry import parse_drive_folder_id
from iris.gpt_batch import init_batch_tables, queue_image_for_batch, build_and_submit_batch, get_batch_queue_count
from iris.source_clients import (
    CAMERA_PATTERN,
    COMPACT_DATE,
    IMAGE_EXTS,
    ISO_DATE,
    TIME_PATTERN,
    GDriveClient,
    LocalClient,
    OnFlyConfig,
    SourceClient,
    SourceImage,
    build_source_client,
    image_meta as _image_meta,
)
from iris.pipeline_events import (
    PIPELINE_STAGES,
    append_pipeline_event as _append_pipeline_event,
    connect as _connect,
    create_pipeline_run as _create_pipeline_run,
    init_onfly_tables,
    now_iso as _now,
    queue_set as _queue_set,
    update_pipeline_run as _update_pipeline_run,
)
from iris.gpt_runtime import (
    CircuitBreaker as _CircuitBreaker,
    HeartbeatThread as _HeartbeatThread,
    TokenBucket as _TokenBucket,
    _RETAIL_WALKIN_PROMPT,
    openai_eval as _openai_eval,
)
from iris.download_manager import (
    FrameSampleAnchor,
    evaluate_frame_sampling,
    is_gpt_quota_error as _is_gpt_quota_error,
    sha256_of as _sha256_of,
    yolo_detect_direct as _yolo_detect_direct,
    yolo_detect_full_result as _yolo_detect_full_result,
)
from iris.session_reconstruction import (
    auto_discover_cameras as _auto_discover_cameras,
    load_billing_cameras as _load_billing_cameras,
    load_excluded_cameras as _load_excluded_cameras,
    load_prompt_improvement_text as _load_prompt_improvement_text,
    load_qa_correction_map as _load_qa_correction_map,
    load_store_hours as _load_store_hours,
    norm_date as _norm_date,
    persist_gpt_sessions,
    resolve_sampled_frames,
    sync_run_to_postgres as _sync_run_to_postgres,
)
from iris.report_writer import (
    write_cost_metrics,
    write_pipeline_reports,
)

__all__ = [
    "CAMERA_PATTERN",
    "COMPACT_DATE",
    "IMAGE_EXTS",
    "ISO_DATE",
    "TIME_PATTERN",
    "GDriveClient",
    "LocalClient",
    "OnFlyConfig",
    "SourceClient",
    "SourceImage",
    "build_source_client",
    "parse_drive_folder_id",
    "init_onfly_tables",
    "run_onfly_pipeline",
    "recent_onfly_runs",
    "_connect",
    "_now",
    "_RETAIL_WALKIN_PROMPT",
]

_DISCOVERY_SEED_BATCH_SIZE = 1000


def _seed_discovered_images(conn: sqlite3.Connection, cfg: OnFlyConfig, images: list[SourceImage]) -> None:
    if not images:
        return
    for start in range(0, len(images), _DISCOVERY_SEED_BATCH_SIZE):
        batch = images[start : start + _DISCOVERY_SEED_BATCH_SIZE]
        now = _now()
        conn.executemany(
            """
            INSERT OR IGNORE INTO onfly_image_state(
                store_id,image_id,source_provider,source_uri,source_item_id,source_url,image_name,relative_path,
                date_source,date_display,camera_id,timestamp_hint,discovered_at,last_seen_at,pipeline_version,yolo_version,gpt_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    cfg.store_id,
                    item.image_id,
                    item.source_provider,
                    cfg.source_uri,
                    item.source_item_id,
                    item.source_url,
                    item.image_name,
                    item.relative_path,
                    item.date_source,
                    item.date_display,
                    item.camera_id,
                    item.timestamp_hint,
                    now,
                    now,
                    cfg.pipeline_version,
                    "",
                    "",
                )
                for item in batch
            ],
        )
        conn.commit()


def _safe_relevant_date(item: SourceImage) -> str:
    text = str(item.date_display or "").strip()
    if text:
        return text.replace("/", "-").replace("\\", "-").replace(":", "-")
    text = str(item.date_source or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        yyyy, mm, dd = text.split("-")
        return f"{dd}-{mm}-{yyyy}"
    if text:
        return text.replace("/", "-").replace("\\", "-").replace(":", "-")
    return "unknown_date"


def _write_relevant_review_image(cfg: OnFlyConfig, item: SourceImage, image_bytes: bytes) -> None:
    if cfg.keep_relevant_dir is None:
        return
    date_dir = cfg.keep_relevant_dir / _safe_relevant_date(item)
    date_dir.mkdir(parents=True, exist_ok=True)
    try:
        (date_dir / item.image_name).write_bytes(image_bytes)
    except Exception:
        pass

def run_onfly_pipeline(cfg: OnFlyConfig) -> dict[str, Any]:
    init_onfly_tables(cfg.db_path)
    with sqlite3.connect(str(cfg.db_path)) as _btconn:
        init_batch_tables(_btconn)
    yolo_version = str(cfg.yolo_version or cfg.pipeline_version or "onfly_v1").strip()
    gpt_version = str(cfg.gpt_version or cfg.pipeline_version or "onfly_v1").strip()
    started_at = _now()
    run_id = str(cfg.run_id or "").strip() or f"{cfg.store_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    perf0 = time.perf_counter()
    client = build_source_client(cfg.source_uri, cfg.google_api_key)
    source_provider = client.provider
    detector = None
    detector_warning = ""
    timings = {"list_ms": 0.0, "detector_init_ms": 0.0, "download_ms": 0.0, "yolo_ms": 0.0, "gpt_ms": 0.0, "report_ms": 0.0}
    t_list = time.perf_counter()
    # Load already-processed Drive file IDs so list_images skips them during DFS
    # collection. Without this, folders with >max_images files get stuck — the DFS
    # fills its limit with already-done files and never advances to new ones.
    _seen_ids: set[str] = set()
    if hasattr(client, "folder_id"):  # GDriveClient only — LocalClient doesn't need this
        try:
            _conn_pre = _connect(cfg.db_path)
            _seen_rows = _conn_pre.execute(
                "SELECT source_item_id FROM onfly_image_state WHERE store_id=? AND source_provider='gdrive'",
                (cfg.store_id,),
            ).fetchall()
            _seen_ids = {str(r[0]) for r in _seen_rows if r[0]}
            _conn_pre.close()
        except Exception:
            pass
    images = client.list_images(cfg.max_images, seen_ids=_seen_ids)
    timings["list_ms"] = round((time.perf_counter() - t_list) * 1000.0, 2)

    # ── Load QA artefacts (Option A + Option B) ──────────────────────────────
    data_root = Path(cfg.db_path).parent  # db is in data_root
    _correction_map = _load_qa_correction_map(cfg.store_id, data_root)
    _prompt_extra = _load_prompt_improvement_text(cfg.store_id, data_root)

    # ── Load camera exclusion list from PostgreSQL ────────────────────────────
    # Cameras labelled external or skip are excluded from YOLO + GPT entirely.
    _excluded_cameras: set[str] = _load_excluded_cameras(cfg.store_id)
    # Billing cameras: full analysis, customers here count as conversions.
    _billing_cameras: set[str] = _load_billing_cameras(cfg.store_id)
    # Store hours: only process images taken during open hours (default 10–21).
    _store_open_hour, _store_close_hour = _load_store_hours(cfg.store_id)

    conn = _connect(cfg.db_path)
    try:
        stage = PIPELINE_STAGES[0]
        business_date = ""
        if images:
            source_dates = sorted({_norm_date(str(img.date_display or "").strip()) for img in images if str(img.date_display or "").strip()})
            if len(source_dates) == 1:
                business_date = source_dates[0]
            elif len(source_dates) > 1:
                business_date = "MULTI_DATE"

        # BoT-SORT tracker — only instantiated when cfg.use_tracker=True
        _tracker = None
        if cfg.use_tracker:
            from iris.bot_sort_tracker import BotSortTracker
            _tracker = BotSortTracker(
                iou_threshold=cfg.tracker_iou_threshold,
                max_age=cfg.tracker_max_age,
                min_hits=cfg.tracker_min_hits,
            )
        _create_pipeline_run(
            conn,
            run_id=run_id,
            store_id=cfg.store_id,
            business_date=business_date,
            source_type=client.provider,
            source_uri=cfg.source_uri,
            started_at=started_at,
        )
        # Start heartbeat thread — updates last_heartbeat_at every 25s so the run
        # is never mistakenly marked zombie even during slow downloads or long GPT calls.
        _heartbeat = _HeartbeatThread(cfg.db_path, run_id)
        _heartbeat.start()
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage,
            event_type="success",
            message="List stage completed",
            payload={"images_discovered": len(images)},
        )
        stage = PIPELINE_STAGES[1]
        _seed_discovered_images(conn, cfg, images)
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage,
            event_type="success",
            message="Discovered image inventory seeded into state table",
            payload={"seeded_images": len(images)},
        )
        _update_pipeline_run(conn, run_id, images_discovered=len(images), current_stage=stage)
        conn.commit()
        new_images = 0
        skipped = 0
        yolo_done = 0
        yolo_relevant = 0
        gpt_done = 0
        gpt_failed = 0
        gpt_retry_pending = 0
        gpt_cache_hits = 0  # GPT calls saved by hash-based result cache
        smart_sampled = 0
        duplicate_skips = 0
        outside_hours_skips = 0
        excluded_camera_skips = 0
        gpt_call_count = 0
        gpt_batch_images = 0
        gpt_quota_unavailable = False
        gpt_quota_error = ""
        gpt_work_list: list[tuple] = []
        bytes_cache: dict[str, bytes] = {}
        gpt_result_map: dict[str, tuple] = {}
        _seen_hashes: set[str] = set()  # Layer 2: SHA256 dedup within this run
        _sampling_anchors: dict[str, FrameSampleAnchor] = {}

        _GPT_EMPTY = {"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_failed", "walkins": []}

        def _run_gpt(work: tuple) -> tuple:  # noqa: E306
            """Submit one image to GPT with rate limiting, circuit breaker, and jittered retry.

            Industry-standard pattern:
            - Token bucket: enforces calls/sec without hammering the API.
            - Circuit breaker: after 5 consecutive 429s trips OPEN for 90s, then
              half-opens and tries again — prevents cost storms and unrecoverable loops.
            - Exponential backoff + jitter: each retry waits 2^attempt + rand(0,1)s,
              multiplied by 4 for quota errors, capped at 120s. Jitter prevents
              all concurrent workers from retrying at the exact same moment.
            - DLQ: after _GPT_MAX_ATTEMPTS the image is marked gpt_dlq (dead letter),
              surfaced separately in the dashboard from ordinary failures.
            """
            _item, _img_bytes = work
            _g0 = time.perf_counter()
            for _attempt in range(1, _GPT_MAX_ATTEMPTS + 1):
                # Circuit breaker — if tripped, fail fast rather than pile onto a rate-limit storm
                if _breaker.is_open:
                    return (
                        _item.image_id, _GPT_EMPTY.copy(),
                        "quota_pending_retry", "circuit_open — breaker tripped, skipping this cycle",
                        round((time.perf_counter() - _g0) * 1000.0, 2),
                    )
                # Rate limit — acquire a token (blocks up to 60s before giving up)
                if not _bucket.acquire(timeout=60.0):
                    return (
                        _item.image_id, _GPT_EMPTY.copy(),
                        "quota_pending_retry", "rate_limiter_timeout",
                        round((time.perf_counter() - _g0) * 1000.0, 2),
                    )
                try:
                    _is_billing = bool(_billing_cameras and _item.camera_id in _billing_cameras)
                    try:
                        _out = _openai_eval(
                            cfg,
                            _img_bytes,
                            _item.image_name,
                            prompt_extra=_prompt_extra,
                            is_billing_camera=_is_billing,
                        )
                    except TypeError as _sig_exc:
                        if "unexpected keyword argument" not in str(_sig_exc):
                            raise
                        _out = _openai_eval(cfg, _img_bytes, _item.image_name)
                    _breaker.record_success()
                    return (_item.image_id, _out, "done", "", round((time.perf_counter() - _g0) * 1000.0, 2))
                except Exception as _exc:
                    _gerr = str(_exc)
                    _is_quota = _is_gpt_quota_error(_gerr)
                    if _is_quota:
                        _breaker.record_failure()
                        return (
                            _item.image_id,
                            _GPT_EMPTY.copy(),
                            "quota_pending_retry",
                            _gerr,
                            round((time.perf_counter() - _g0) * 1000.0, 2),
                        )
                    if _attempt < _GPT_MAX_ATTEMPTS:
                        # Exponential backoff with jitter — prevents retry storms
                        _base = (2 ** _attempt) + random.uniform(0.0, 1.0)
                        _delay = min(_base, 120.0)
                        time.sleep(_delay)
                    else:
                        # Exhausted retries → dead letter queue
                        return (
                            _item.image_id, _GPT_EMPTY.copy(),
                            "gpt_dlq", f"[attempt {_attempt}/{_GPT_MAX_ATTEMPTS}] {_gerr}",
                            round((time.perf_counter() - _g0) * 1000.0, 2),
                        )
            # Should never reach here
            return (_item.image_id, _GPT_EMPTY.copy(), "failed", "run_gpt_exhausted", 0.0)

        _max_w = max(1, int(cfg.gpt_parallel_workers))
        _gpt_pool: concurrent.futures.ThreadPoolExecutor | None = (
            concurrent.futures.ThreadPoolExecutor(max_workers=_max_w) if cfg.gpt_enabled else None
        )
        _gpt_ordered: list[tuple] = []  # (item, image_bytes, future) — in YOLO submission order

        def _sync_interim_gpt_counts() -> None:
            _done = 0
            _failed = 0
            for _result in gpt_result_map.values():
                _status = _result[1]
                _done += int(_status == "done")
                _failed += int(_status != "done")
            _update_pipeline_run(conn, run_id, gpt_success_count=_done, gpt_failed_count=_failed)

        # ── Rate limiter + circuit breaker for OpenAI ───────────────────────
        # gpt_rate_limit_rps controls tokens/sec; capacity = number of parallel workers
        # so all workers can be in flight simultaneously once primed.
        _bucket = _TokenBucket(rate=cfg.gpt_rate_limit_rps, capacity=_max_w)
        _breaker = _CircuitBreaker(fail_max=5, reset_timeout=90.0)
        _GPT_MAX_ATTEMPTS = 3  # per-image retry limit before DLQ

        _append_pipeline_event(conn, run_id=run_id, stage=PIPELINE_STAGES[1], event_type="start", message="Skip check started")
        for item in images:
            # Camera exclusion: skip YOLO + GPT for cameras marked external or skip
            if _excluded_cameras and item.camera_id and item.camera_id in _excluded_cameras:
                skipped += 1
                excluded_camera_skips += 1
                conn.execute(
                    "INSERT OR IGNORE INTO onfly_image_state(store_id,image_id,source_provider,source_uri,source_item_id,"
                    "source_url,image_name,relative_path,date_source,date_display,camera_id,timestamp_hint,"
                    "discovered_at,last_seen_at,pipeline_version,yolo_version,gpt_version,"
                    "yolo_status,gpt_status) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'camera_excluded','camera_excluded')",
                    (cfg.store_id, item.image_id, item.source_provider, cfg.source_uri, item.source_item_id,
                     item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display,
                     item.camera_id, item.timestamp_hint, _now(), _now(), cfg.pipeline_version, "", ""),
                )
                conn.commit()
                continue
            # Store-hours filter: skip images taken outside open hours (no YOLO, no GPT)
            _ts = str(item.timestamp_hint or "").strip()
            if _ts:
                try:
                    # timestamp_hint format: YYYY-MM-DD HH:MM:SS
                    _img_mins = int(_ts[11:13]) * 60 + int(_ts[14:16]) if len(_ts) >= 16 else -1
                    if _img_mins >= 0 and not (_store_open_hour <= _img_mins < _store_close_hour):
                        skipped += 1
                        outside_hours_skips += 1
                        conn.execute(
                            "INSERT OR IGNORE INTO onfly_image_state(store_id,image_id,source_provider,source_uri,source_item_id,"
                            "source_url,image_name,relative_path,date_source,date_display,camera_id,timestamp_hint,"
                            "discovered_at,last_seen_at,pipeline_version,yolo_version,gpt_version,"
                            "yolo_status,gpt_status) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'outside_hours','outside_hours')",
                            (cfg.store_id, item.image_id, item.source_provider, cfg.source_uri, item.source_item_id,
                             item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display,
                             item.camera_id, item.timestamp_hint, _now(), _now(), cfg.pipeline_version, "", ""),
                        )
                        conn.commit()
                        continue
                except (ValueError, IndexError):
                    pass  # unparseable timestamp — proceed with analysis
            now = _now()
            row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            if row is None:
                conn.execute("INSERT OR IGNORE INTO onfly_image_state(store_id,image_id,source_provider,source_uri,source_item_id,source_url,image_name,relative_path,date_source,date_display,camera_id,timestamp_hint,discovered_at,last_seen_at,pipeline_version,yolo_version,gpt_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (cfg.store_id, item.image_id, item.source_provider, cfg.source_uri, item.source_item_id, item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, now, cfg.pipeline_version, "", ""))
                row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            else:
                conn.execute("UPDATE onfly_image_state SET source_url=?,image_name=?,relative_path=?,date_source=?,date_display=?,camera_id=?,timestamp_hint=?,last_seen_at=? WHERE store_id=? AND image_id=?", (item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, cfg.store_id, item.image_id))
            if row is None:
                continue
            row_yolo_version = str(row["yolo_version"] or row["pipeline_version"] or "").strip()
            row_gpt_version = str(row["gpt_version"] or row["pipeline_version"] or "").strip()
            done_yolo = str(row["yolo_status"] or "") == "done"
            done_gpt = str(row["gpt_status"] or "") == "done"
            existing_relevant = int(row["yolo_relevant"] or 0)
            yolo_needed = cfg.force_reprocess or not (done_yolo and row_yolo_version == yolo_version)
            # Decide GPT work from version/state first. Relevance is finalized only after the
            # current-run YOLO pass, otherwise stale DB state can suppress GPT incorrectly.
            gpt_work_needed = bool(
                cfg.gpt_enabled
                and (
                    cfg.force_reprocess
                    or yolo_needed
                    or not (done_gpt and row_gpt_version == gpt_version)
                )
            )
            if (not yolo_needed) and (not gpt_work_needed):
                skipped += 1
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[1],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="Skipped by delta check",
                    payload={
                        "pipeline_version": cfg.pipeline_version,
                        "yolo_version": yolo_version,
                        "gpt_version": gpt_version,
                        "done_yolo": done_yolo,
                        "done_gpt": done_gpt,
                    },
                )
                _update_pipeline_run(
                    conn,
                    run_id,
                    images_skipped=skipped,
                    images_processed=skipped + new_images,
                    current_stage=PIPELINE_STAGES[1],
                )
                conn.commit()
                continue
            new_images += 1
            stage = PIPELINE_STAGES[2]
            _update_pipeline_run(
                conn,
                run_id,
                images_skipped=skipped,
                current_stage=stage,
            )
            _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="pending")

            _append_pipeline_event(
                conn,
                run_id=run_id,
                stage=stage,
                event_type="start",
                image_id=item.image_id,
                image_name=item.image_name,
                message="Downloading image bytes",
            )
            dl0 = time.perf_counter()
            try:
                image_bytes = client.fetch_bytes(item)
            except Exception as exc:
                err = str(exc)
                conn.execute(
                    "UPDATE onfly_image_state SET yolo_status='failed_download', yolo_error=?, gpt_status='skipped_download_error', gpt_error=?, last_run_id=? WHERE store_id=? AND image_id=?",
                    (err[:1000], err[:1000], run_id, cfg.store_id, item.image_id),
                )
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="failed_download", error=err)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="failure",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="Download failed",
                    error_message=err[:1000],
                )
                conn.commit()
                continue
            timings["download_ms"] += round((time.perf_counter() - dl0) * 1000.0, 2)

            # Layer 2: SHA256 exact-duplicate check + GPT result cache
            _h = _sha256_of(image_bytes)
            _is_within_run_dup = _h in _seen_hashes
            _cached_gpt_row = None
            if not _is_within_run_dup and _h:
                # Priority 1: find a prior image with same bytes that already has GPT done → cache hit
                _cached_gpt_row = conn.execute(
                    "SELECT src.image_id AS src_image_id, src.yolo_relevant, src.person_count, src.yolo_conf, src.yolo_error,"
                    " src.gpt_version, src.gpt_customer_count, src.gpt_staff_count, src.gpt_conversions, src.gpt_bounce, src.gpt_result_json"
                    " FROM onfly_image_state src"
                    " WHERE src.store_id=? AND src.content_hash=? AND src.image_id!=?"
                    " AND src.gpt_status='done'"
                    " LIMIT 1",
                    (cfg.store_id, _h, item.image_id),
                ).fetchone()
            if _cached_gpt_row is not None:
                # Cache hit: copy YOLO + GPT results verbatim — zero GPT call
                conn.execute(
                    "UPDATE onfly_image_state SET content_hash=?, pipeline_version=?,"
                    " yolo_version=?, yolo_status='done', yolo_relevant=?, person_count=?, yolo_conf=?, yolo_error=?,"
                    " gpt_version=?, gpt_status='cached_from_hash',"
                    " gpt_customer_count=?, gpt_staff_count=?, gpt_conversions=?, gpt_bounce=?, gpt_result_json=?,"
                    " last_run_id=? WHERE store_id=? AND image_id=?",
                    (
                        _h, cfg.pipeline_version,
                        yolo_version, int(_cached_gpt_row["yolo_relevant"] or 0),
                        int(_cached_gpt_row["person_count"] or 0), float(_cached_gpt_row["yolo_conf"] or 0.0),
                        str(_cached_gpt_row["yolo_error"] or ""),
                        str(_cached_gpt_row["gpt_version"] or gpt_version),
                        int(_cached_gpt_row["gpt_customer_count"] or 0), int(_cached_gpt_row["gpt_staff_count"] or 0),
                        int(_cached_gpt_row["gpt_conversions"] or 0), int(_cached_gpt_row["gpt_bounce"] or 0),
                        str(_cached_gpt_row["gpt_result_json"] or "{}"),
                        run_id, cfg.store_id, item.image_id,
                    ),
                )
                # Bulk-copy walkin sessions from original image — single INSERT...SELECT, no re-parsing
                conn.execute(
                    "INSERT OR IGNORE INTO onfly_walkin_sessions("
                    " store_id, run_id, image_id, source_image_name, source_folder_name, camera_id,"
                    " business_date, date, event_type, event_time, walkin_id, group_id, role,"
                    " entry_time, exit_time, time_spent_mins, session_status, entry_type,"
                    " first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,"
                    " direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,"
                    " gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,"
                    " clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics"
                    ") SELECT"
                    " store_id, ?, ?, ?, source_folder_name, camera_id,"
                    " business_date, date, event_type, event_time, walkin_id, group_id, role,"
                    " entry_time, exit_time, time_spent_mins, session_status, entry_type,"
                    " first_seen_time, last_seen_time, matched_session_id, match_score, 'cached_from_hash:' || match_reason,"
                    " direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,"
                    " gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,"
                    " clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics"
                    " FROM onfly_walkin_sessions WHERE store_id=? AND image_id=?",
                    (run_id, item.image_id, item.image_name, cfg.store_id, str(_cached_gpt_row["src_image_id"])),
                )
                _seen_hashes.add(_h)
                gpt_cache_hits += 1
                skipped += 1
                new_images -= 1
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="cached_from_hash")
                _append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="progress",
                    image_id=item.image_id, image_name=item.image_name,
                    message="GPT result loaded from hash cache — zero API call",
                    payload={"src_image_id": str(_cached_gpt_row["src_image_id"]), "content_hash": _h[:16]})
                conn.commit()
                continue
            # Priority 2: same hash, prior image processed but GPT not done → plain duplicate skip
            _is_dup = _is_within_run_dup
            if not _is_dup and _h:
                _dup_exists = conn.execute(
                    "SELECT 1 FROM onfly_image_state"
                    " WHERE store_id=? AND content_hash=? AND image_id!=?"
                    " AND yolo_status NOT IN ('pending','skipped_duplicate_sha256','outside_hours','camera_excluded')"
                    " LIMIT 1",
                    (cfg.store_id, _h, item.image_id),
                ).fetchone()
                _is_dup = _dup_exists is not None
            if _is_dup:
                conn.execute(
                    "UPDATE onfly_image_state SET yolo_status='skipped_duplicate_sha256',"
                    " gpt_status='skipped_duplicate_sha256', content_hash=?, last_run_id=?"
                    " WHERE store_id=? AND image_id=?",
                    (_h, run_id, cfg.store_id, item.image_id),
                )
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="skipped_duplicate_sha256")
                _append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="progress",
                    image_id=item.image_id, image_name=item.image_name,
                    message="Skipped — exact duplicate (SHA256 match)")
                skipped += 1
                duplicate_skips += 1
                new_images -= 1
                conn.commit()
                continue
            _seen_hashes.add(_h)
            conn.execute(
                "UPDATE onfly_image_state SET content_hash=? WHERE store_id=? AND image_id=?",
                (_h, cfg.store_id, item.image_id),
            )

            bytes_cache[item.image_id] = image_bytes
            _append_pipeline_event(
                conn,
                run_id=run_id,
                stage=stage,
                event_type="success",
                image_id=item.image_id,
                image_name=item.image_name,
                message="Download completed",
                payload={"bytes": len(image_bytes)},
            )
            if detector is None:
                d0 = time.perf_counter()
                detector, detector_warning = build_detector(cfg.detector_type, cfg.conf_threshold, use_cache=False)
                timings["detector_init_ms"] = round((time.perf_counter() - d0) * 1000.0, 2)
                if cfg.detector_type in {"yolo", "onnx"} and detector_warning and "fallback active" in detector_warning.lower() and not cfg.allow_detector_fallback:
                    raise RuntimeError("YOLO unavailable and fallback detected. Fix runtime or allow fallback.")
            if yolo_needed:
                stage = PIPELINE_STAGES[3]
                _update_pipeline_run(conn, run_id, current_stage=stage)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="start",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO detection started",
                )
                y0 = time.perf_counter()
                _det = _yolo_detect_full_result(detector, image_bytes, item.image_name)
                pcount = int(_det.person_count or 0)
                max_conf = float(_det.max_person_conf or 0.0)
                yerr = str(_det.detection_error or "")
                person_boxes = list(_det.person_boxes or [])
                if _tracker is not None and not yerr and person_boxes:
                    _confs = list(_det.person_confidences) if _det.person_confidences else [max_conf] * len(person_boxes)
                    _tracker.update(person_boxes, _confs, image_id=item.image_id)
                timings["yolo_ms"] += round((time.perf_counter() - y0) * 1000.0, 2)
                relevant = int(pcount > 0 and not yerr)
                yolo_relevant += int(relevant == 1)
                yolo_done += 1
                conn.execute("UPDATE onfly_image_state SET pipeline_version=?,yolo_version=?,yolo_status='done',yolo_relevant=?,person_count=?,yolo_conf=?,yolo_error=?,last_run_id=? WHERE store_id=? AND image_id=?", (cfg.pipeline_version, yolo_version, relevant, pcount, max_conf, str(yerr)[:1000], run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="done")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="success" if not yerr else "failure",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO detection completed",
                    payload={"person_count": int(pcount), "max_confidence_score": float(max_conf), "relevant": int(relevant), "yolo_version": yolo_version},
                    error_message=str(yerr)[:1000],
                )
                _update_pipeline_run(
                    conn,
                    run_id,
                    images_relevant=yolo_relevant,
                    images_irrelevant=max(0, yolo_done - yolo_relevant),
                )
            else:
                relevant = existing_relevant
                pcount = int(row["person_count"] or 0)
                max_conf = float(row["yolo_conf"] or 0.0)
                yerr = str(row["yolo_error"] or "")
                person_boxes = []
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[3],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO skipped (version match)",
                    payload={"yolo_version": yolo_version, "stored_yolo_version": row_yolo_version, "relevant": int(relevant)},
                )
            gpt_needed = bool(cfg.gpt_enabled and relevant == 1 and gpt_work_needed)
            if gpt_needed and person_boxes:
                sample_key = f"{str(item.date_display or item.date_source or '').strip()}|{str(item.camera_id or '').strip()}"
                sampled, sample_reason, sample_signature, sample_anchor = evaluate_frame_sampling(
                    _sampling_anchors.get(sample_key),
                    item,
                    person_boxes,
                    pcount,
                )
                if sampled and _sampling_anchors.get(sample_key) is not None:
                    anchor = _sampling_anchors[sample_key]
                    conn.execute(
                        "UPDATE onfly_image_state SET gpt_version=?, gpt_status='sampled_wait_anchor', sampled_anchor_image_id=?, sampled_signature=?, sampled_skip_reason=?, last_run_id=? WHERE store_id=? AND image_id=?",
                        (gpt_version, anchor.image_id, sample_signature, sample_reason, run_id, cfg.store_id, item.image_id),
                    )
                    _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="sampled_wait_anchor")
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=PIPELINE_STAGES[4],
                        event_type="progress",
                        image_id=item.image_id,
                        image_name=item.image_name,
                        message="GPT skipped by smart frame sampling",
                        payload={"anchor_image_id": anchor.image_id, "sampling_signature": sample_signature},
                    )
                    smart_sampled += 1
                    skipped += 1
                    new_images -= 1
                    gpt_needed = False
                    conn.commit()
                    continue
                if sample_anchor is not None:
                    _sampling_anchors[sample_key] = sample_anchor

            if relevant == 1:
                _write_relevant_review_image(cfg, item, image_bytes)
            if relevant == 1 and cfg.gpt_enabled and gpt_needed:
                stage = PIPELINE_STAGES[4]
                _update_pipeline_run(conn, run_id, current_stage=stage)
                if gpt_quota_unavailable and not cfg.gpt_batch_mode:
                    conn.execute(
                        "UPDATE onfly_image_state SET gpt_version=?,gpt_status='quota_pending_retry',gpt_customer_count=0,gpt_staff_count=0,gpt_conversions=0,gpt_bounce=0,gpt_result_json='{}',gpt_error=?,last_run_id=? WHERE store_id=? AND image_id=?",
                        (gpt_version, str(gpt_quota_error or "quota unavailable")[:1000], run_id, cfg.store_id, item.image_id),
                    )
                    _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="waiting_quota", error=gpt_quota_error)
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=stage,
                        event_type="retry",
                        image_id=item.image_id,
                        image_name=item.image_name,
                        message="GPT quota already unavailable; queued for retry without new API call",
                        error_message=str(gpt_quota_error or "")[:1000],
                    )
                    gpt_retry_pending += 1
                    _update_pipeline_run(
                        conn,
                        run_id,
                        retry_status=f"GPT quota unavailable; {gpt_retry_pending} image(s) queued for retry",
                    )
                    conn.commit()
                    continue
                if cfg.gpt_batch_mode:
                    # Batch mode: queue for overnight OpenAI Batch API processing
                    gpt_batch_images += 1
                    queue_image_for_batch(
                        conn,
                        store_id=cfg.store_id,
                        image_id=item.image_id,
                        run_id=run_id,
                        image_name=item.image_name,
                        camera_id=str(item.camera_id or ""),
                        is_billing_camera=True,
                        image_bytes=image_bytes,
                        person_count=int(pcount),
                        yolo_conf=float(max_conf),
                    )
                    conn.execute(
                        "UPDATE onfly_image_state SET gpt_status='batch_queued', last_run_id=? WHERE store_id=? AND image_id=?",
                        (run_id, cfg.store_id, item.image_id),
                    )
                    _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="batch_queued")
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=stage,
                        event_type="progress",
                        image_id=item.image_id,
                        image_name=item.image_name,
                        message="GPT queued for overnight batch processing",
                    )
                else:
                    gpt_call_count += 1
                    _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="pending")
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=stage,
                        event_type="start",
                        image_id=item.image_id,
                        image_name=item.image_name,
                        message="GPT analysis queued for parallel processing",
                    )
                    gpt_work_list.append((item, image_bytes))
                    if _gpt_pool is not None:
                        _fut = _gpt_pool.submit(_run_gpt, (item, image_bytes))
                        _gpt_ordered.append((item, image_bytes, _fut))
            elif relevant == 1 and cfg.gpt_enabled and not gpt_needed:
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="skipped_version")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[4],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT skipped (version match)",
                    payload={"gpt_version": gpt_version, "stored_gpt_version": row_gpt_version},
                )
            else:
                status = "skipped_irrelevant" if relevant == 0 else "disabled"
                conn.execute("UPDATE onfly_image_state SET gpt_version=?,gpt_status=?,gpt_customer_count=0,gpt_staff_count=0,gpt_conversions=0,gpt_bounce=0,gpt_result_json='{}',gpt_error='',last_run_id=? WHERE store_id=? AND image_id=?", (gpt_version, status, run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status=status)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT skipped",
                    payload={"reason": status},
                )
                
                # Zero Waste Policy: Delete irrelevant images from local disk immediately
                if relevant == 0 and client.provider == "local":
                    try:
                        Path(item.source_url).unlink(missing_ok=True)
                    except Exception:
                        pass
            # Drain completed GPT futures so live progress reflects GPT counts during YOLO
            if _gpt_pool is not None:
                for _pi, _, _pf in _gpt_ordered:
                    if _pf.done() and _pi.image_id not in gpt_result_map:
                        try:
                            _r = _pf.result()
                            gpt_result_map[_r[0]] = _r[1:]
                            if _r[2] == "quota_pending_retry":
                                gpt_quota_unavailable = True
                                gpt_quota_error = str(_r[3] or "")
                        except Exception as _pe:
                            gpt_result_map[_pi.image_id] = (
                                {"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_failed", "walkins": []},
                                "failed", str(_pe), 0.0,
                            )
                _sync_interim_gpt_counts()
            _update_pipeline_run(
                conn,
                run_id,
                images_skipped=skipped,
                images_processed=skipped + new_images,
                images_relevant=yolo_relevant,
                images_irrelevant=max(0, yolo_done - yolo_relevant),
                gpt_success_count=gpt_done,
                gpt_failed_count=gpt_failed,
            )
            conn.commit()
        # Phase 2: wait for any GPT futures still in flight (submitted during YOLO pass above)
        if _gpt_pool is not None:
            for _pi, _, _pf in _gpt_ordered:
                if _pi.image_id not in gpt_result_map:
                    try:
                        _r = _pf.result()
                        gpt_result_map[_r[0]] = _r[1:]
                        if _r[2] == "quota_pending_retry":
                            gpt_quota_unavailable = True
                            gpt_quota_error = str(_r[3] or "")
                    except Exception as _pe:
                        gpt_result_map[_pi.image_id] = (
                            {"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_failed", "walkins": []},
                            "failed", str(_pe), 0.0,
                        )
            _gpt_pool.shutdown(wait=True)
            _sync_interim_gpt_counts()
            conn.commit()
        # Phase 3: sequential session writes — preserves event-time ordering for Re-ID state machine.
        if gpt_work_list:
            stage = PIPELINE_STAGES[4]
            for _item, _img_bytes in gpt_work_list:
                _gpt_dict, gstatus, gerr, _elapsed_ms = gpt_result_map.get(
                    _item.image_id,
                    ({"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_missing", "walkins": []}, "failed", "no_result", 0.0),
                )
                timings["gpt_ms"] += _elapsed_ms
                gpt_done += int(gstatus == "done")
                gpt_failed += int(gstatus in {"failed", "gpt_dlq"})
                gpt_retry_pending += int(gstatus == "quota_pending_retry")
                # Free image bytes immediately after GPT result is consumed — prevents
                # bytes_cache from growing to GBs during large runs.
                bytes_cache.pop(_item.image_id, None)
                walkins = _gpt_dict.pop("walkins", [])
                gpt_summary = json.dumps(_gpt_dict, separators=(',', ':'))
                conn.execute(
                    "UPDATE onfly_image_state SET gpt_version=?,gpt_status=?,gpt_customer_count=?,gpt_staff_count=?,gpt_conversions=?,gpt_bounce=?,gpt_result_json=?,gpt_error=?,last_run_id=? WHERE store_id=? AND image_id=?",
                    (gpt_version, gstatus, int(_gpt_dict.get("customer_count", 0)), int(_gpt_dict.get("staff_count", 0)), int(_gpt_dict.get("conversions", 0)), int(_gpt_dict.get("bounce", 0)), gpt_summary, str(gerr)[:1000], run_id, cfg.store_id, _item.image_id),
                )
                persist_gpt_sessions(
                    conn,
                    store_id=cfg.store_id,
                    run_id=run_id,
                    item=_item,
                    walkins=walkins,
                )
                queue_status = "waiting_quota" if gstatus == "quota_pending_retry" else gstatus
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=_item.image_id, stage="chatgpt", status=queue_status, error=gerr)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="success" if gstatus == "done" else ("retry" if gstatus == "quota_pending_retry" else "failure"),
                    image_id=_item.image_id,
                    image_name=_item.image_name,
                    message=(
                        "GPT analysis completed"
                        if gstatus == "done"
                        else ("GPT quota unavailable; queued for retry" if gstatus == "quota_pending_retry" else "GPT analysis failed")
                    ),
                    payload={
                        "walkins": len(walkins),
                        "customer_count": int(_gpt_dict.get("customer_count", 0)),
                        "staff_count": int(_gpt_dict.get("staff_count", 0)),
                        "gpt_status": gstatus,
                    },
                    error_message=str(gerr)[:1000],
                )
                retry_status = (
                    f"GPT quota unavailable; {gpt_retry_pending} image(s) queued for retry"
                    if gpt_retry_pending > 0
                    else ""
                )
                _update_pipeline_run(
                    conn,
                    run_id,
                    gpt_success_count=gpt_done,
                    gpt_failed_count=gpt_failed,
                    retry_status=retry_status,
                )
                conn.commit()

        if smart_sampled:
            _resolved_sampled = resolve_sampled_frames(conn, store_id=cfg.store_id, run_id=run_id)
            if _resolved_sampled:
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[4],
                    event_type="success",
                    message="Smart-sampled frames resolved from anchor GPT results",
                    payload={"resolved_frames": int(_resolved_sampled)},
                )
                conn.commit()

        # End-of-day closeout: deterministically close remaining open sessions.
        conn.execute(
            """
            UPDATE onfly_walkin_sessions
            SET session_status='CLOSED_EOD',
                exit_time=CASE
                    WHEN COALESCE(NULLIF(last_seen_time,''), '') <> '' THEN last_seen_time
                    WHEN COALESCE(NULLIF(event_time,''), '') <> '' THEN event_time
                    ELSE '23:59:59'
                END
            WHERE store_id=? AND run_id=? AND session_status IN ('OPEN','INFERRED_INSIDE_OPEN')
            """,
            (cfg.store_id, run_id),
        )

        # Batch mode: submit queued images to OpenAI Batch API
        gpt_batch_db_id: str | None = None
        gpt_batch_queued_count = 0
        if cfg.gpt_batch_mode:
            gpt_batch_queued_count = get_batch_queue_count(conn, cfg.store_id, run_id)
            if gpt_batch_queued_count > 0:
                try:
                    _batch_prompt = _RETAIL_WALKIN_PROMPT + (
                        f"\n\nSTORE-SPECIFIC RULES:\n{_prompt_extra}" if _prompt_extra else ""
                    )
                    gpt_batch_db_id = build_and_submit_batch(
                        cfg.store_id,
                        run_id,
                        cfg.openai_api_key,
                        cfg.openai_model,
                        conn,
                        _batch_prompt,
                        openai_api_base=cfg.openai_api_base,
                    )
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=PIPELINE_STAGES[4],
                        event_type="success",
                        message=f"OpenAI batch submitted: {gpt_batch_queued_count} images → batch_id={gpt_batch_db_id}",
                        payload={"batch_db_id": gpt_batch_db_id, "queued_count": gpt_batch_queued_count},
                    )
                except Exception as _be:
                    _append_pipeline_event(
                        conn,
                        run_id=run_id,
                        stage=PIPELINE_STAGES[4],
                        event_type="failure",
                        message=f"Batch submission failed: {_be}",
                    )
            conn.commit()

        summary = write_pipeline_reports(
            conn,
            cfg=cfg,
            run_id=run_id,
            source_provider=source_provider,
            images=images,
            timings=timings,
            perf0=perf0,
            started_at=started_at,
            yolo_version=yolo_version,
            gpt_version=gpt_version,
            detector_warning=detector_warning,
            skipped=skipped,
            new_images=new_images,
            yolo_done=yolo_done,
            yolo_relevant=yolo_relevant,
            gpt_done=gpt_done,
            gpt_failed=gpt_failed,
            gpt_cache_hits=gpt_cache_hits,
            smart_sampled=smart_sampled,
            gpt_retry_pending=gpt_retry_pending,
            gpt_batch_db_id=gpt_batch_db_id,
            gpt_batch_queued_count=gpt_batch_queued_count,
            correction_map=_correction_map,
        )
        image_results_path = Path(summary["outputs"]["image_results_csv"])
        report_actual_path = Path(summary["outputs"]["store_report_csv"])
        walkin_sessions_path = Path(summary["outputs"]["walkin_sessions_csv"]) if summary["outputs"].get("walkin_sessions_csv") else (cfg.out_dir / cfg.store_id / "onfly_walkin_sessions.csv")
        ended_at = summary["ended_at"]
        total_ms = float(summary["timings_ms"]["total_ms"])
        retry_status = summary.get("retry_status", "")
        summary_status = summary.get("status", "success")
        store_out = cfg.out_dir / cfg.store_id
        summary_path = cfg.out_dir / f"onfly_run_summary_{run_id}.json"

        # BoT-SORT tracker finalization — produces track_sessions CSV alongside run outputs
        if _tracker is not None:
            try:
                from iris.session_state_machine import classify_sessions, sessions_summary as _sess_summary
                _all_tracks = _tracker.finalize()
                _track_sessions = classify_sessions(_all_tracks, run_id, cfg.store_id, business_date)
                if _track_sessions:
                    _track_rows = [
                        {
                            "session_id": s.session_id,
                            "run_id": s.run_id,
                            "store_id": s.store_id,
                            "business_date": s.business_date,
                            "track_id_local": s.track_id_local,
                            "track_global_id": s.track_global_id,
                            "status": s.status,
                            "entry_frame_idx": s.entry_frame_idx,
                            "exit_frame_idx": s.exit_frame_idx,
                            "entry_image_id": s.entry_image_id,
                            "exit_image_id": s.exit_image_id,
                            "dwell_frames": s.dwell_frames,
                            "confidence": round(s.confidence, 4),
                            "avg_bbox_x1": round(s.avg_bbox[0], 4),
                            "avg_bbox_y1": round(s.avg_bbox[1], 4),
                            "avg_bbox_x2": round(s.avg_bbox[2], 4),
                            "avg_bbox_y2": round(s.avg_bbox[3], 4),
                        }
                        for s in _track_sessions
                    ]
                    _track_csv = store_out / f"onfly_track_sessions_{run_id}.csv"
                    pd.DataFrame(_track_rows).to_csv(_track_csv, index=False)
                    summary["tracker"] = _sess_summary(_track_sessions)
                    summary["outputs"]["track_sessions_csv"] = str(_track_csv.resolve())
            except Exception as _te:
                summary["tracker_error"] = str(_te)[:500]
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["outputs"]["run_summary_json"] = str(summary_path.resolve())
        # ── Sync this run's sessions + discover cameras in PostgreSQL ──────────
        try:
            _sync_run_to_postgres(conn, run_id, cfg.store_id)
        except Exception as _pg_exc:
            import logging
            logging.getLogger(__name__).warning("Post-run PG sync failed (non-fatal): %s", _pg_exc)
        try:
            _auto_discover_cameras(conn, cfg.store_id)
        except Exception as _cam_exc:
            import logging
            logging.getLogger(__name__).warning("Camera auto-discover failed (non-fatal): %s", _cam_exc)
        metric_day = business_date if business_date and business_date != "MULTI_DATE" else started_at[:10]
        est_cost_inr = round((gpt_call_count * 0.06) + (gpt_batch_images * 0.045), 2)
        write_cost_metrics(
            conn,
            metric_day=metric_day,
            store_id=cfg.store_id,
            run_id=run_id,
            counters={
                "images_listed": len(images),
                "yolo_relevant": yolo_relevant,
                "gpt_calls": gpt_call_count,
                "hash_cache_hits": gpt_cache_hits,
                "sampled_skips": smart_sampled,
                "duplicate_skips": duplicate_skips,
                "outside_hours_skips": outside_hours_skips,
                "excluded_camera_skips": excluded_camera_skips,
                "quota_failures": gpt_retry_pending,
                "gpt_batch_images": gpt_batch_images,
                "gpt_realtime_images": gpt_call_count,
                "est_cost_inr": est_cost_inr,
            },
        )
        conn.commit()
        return summary
    except Exception as exc:
        err = str(exc)
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage if "stage" in locals() else "UNKNOWN",
            event_type="failure",
            message="Pipeline execution failed",
            error_message=err[:1000],
        )
        _update_pipeline_run(conn, run_id, status="failed", error_message=err[:1000], error_trace=err[:4000], ended_at=_now())
        conn.commit()
        raise
    finally:
        # Stop heartbeat — must happen before conn.close() so the final status write wins
        try:
            _heartbeat.stop()
        except Exception:
            pass
        # If run is still 'running' here, a BaseException (SIGTERM/KeyboardInterrupt) bypassed
        # the except block above. Mark it abandoned so it doesn't appear stuck forever.
        try:
            row = conn.execute(
                "SELECT status FROM onfly_pipeline_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row and row[0] == "running":
                _now_ts = _now()
                conn.execute(
                    "UPDATE onfly_pipeline_runs SET status='abandoned', "
                    "error_message='Pipeline process was interrupted (server restart or SIGTERM)', "
                    "ended_at=?, updated_at=? WHERE run_id=?",
                    (_now_ts, _now_ts, run_id),
                )
                conn.commit()
        except Exception:
            pass
        conn.close()


def recent_onfly_runs(db_path: Path, store_id: str, limit: int = 20) -> pd.DataFrame:
    init_onfly_tables(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT run_id,store_id,run_mode,source_provider,started_at,ended_at,total_listed,new_images,skipped_cached,yolo_done,yolo_relevant,gpt_done,total_ms,list_ms,download_ms,yolo_ms,gpt_ms,report_ms,status FROM onfly_run_metrics WHERE store_id=? ORDER BY started_at DESC LIMIT ?", (store_id, int(limit))).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()

from __future__ import annotations

from pathlib import Path
import json
import pandas as pd
import sqlite3
from typing import Any

from .pipeline_events import append_pipeline_event, ms_to_hms, now_iso, update_pipeline_run, PIPELINE_STAGES


def apply_customer_group_correction(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "group_id" not in df.columns:
        return df
    out = df.copy()
    for col in ["role", "group_id", "walkin_id", "source_image_name", "store_id", "run_id"]:
        if col not in out.columns:
            out[col] = ""
    out["role_norm"] = out["role"].astype(str).str.strip().str.upper()
    out["group_id"] = out["group_id"].astype(str).str.strip()
    out["walkin_id"] = out["walkin_id"].astype(str).str.strip()
    out["source_image_name"] = out["source_image_name"].astype(str).str.strip()
    stats = (
        out.assign(is_customer=out["role_norm"].eq("CUSTOMER"), is_staff=out["role_norm"].eq("STAFF"))
        .groupby(["store_id", "run_id", "source_image_name", "group_id"], dropna=False, as_index=False)
        .agg(customer_rows=("is_customer", "sum"), staff_rows=("is_staff", "sum"))
    )
    stats["preserve_group"] = (
        (stats["group_id"].astype(str).str.strip() != "")
        & (stats["customer_rows"] >= 2)
        & (stats["customer_rows"] <= 4)
        & (stats["staff_rows"] == 0)
    )
    key_cols = ["store_id", "run_id", "source_image_name", "group_id"]
    out = out.merge(stats[key_cols + ["preserve_group"]], on=key_cols, how="left")
    out["preserve_group"] = out["preserve_group"].fillna(False)

    def _session_group(row: pd.Series) -> str:
        walkin = str(row.get("walkin_id", "") or "").strip()
        if walkin:
            return walkin
        image_id = str(row.get("image_id", "") or "").strip()
        row_id = str(row.get("id", "") or "").strip()
        return f"{image_id or 'session'}_{row_id or '0'}"

    customer_mask = out["role_norm"].eq("CUSTOMER")
    split_mask = customer_mask & ((out["group_id"] == "") | (~out["preserve_group"]))
    if split_mask.any():
        out.loc[split_mask, "group_id"] = out.loc[split_mask].apply(_session_group, axis=1)
    non_customer_mask = ~customer_mask
    if non_customer_mask.any():
        out.loc[non_customer_mask, "group_id"] = out.loc[non_customer_mask].apply(
            lambda row: f"NON_CUSTOMER_{str(row.get('id', '') or '').strip() or str(row.get('walkin_id', '') or '').strip() or '0'}",
            axis=1,
        )
    return out.drop(columns=["role_norm", "preserve_group"])


def safe_write_csv(target: Path, df: pd.DataFrame, run_id: str, write_warnings: list[str]) -> Path:
    target = Path(target)
    try:
        df.to_csv(target, index=False)
        return target
    except PermissionError:
        fallback = target.with_name(f"{target.stem}_{run_id}{target.suffix}")
        df.to_csv(fallback, index=False)
        write_warnings.append(f"Locked canonical file '{target.name}', wrote fallback '{fallback.name}' instead.")
        return fallback


def _folder_from_rel(relative_path: Any) -> str:
    text = str(relative_path or "").strip().replace("\\", "/")
    if not text:
        return ""
    first = text.split("/", 1)[0].strip()
    if len(first) == 10 and first[4] == "-" and first[7] == "-":
        yyyy, mm, dd = first.split("-")
        return f"{dd}-{mm}-{yyyy}"
    return first


def _sanitize_manifest_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown_date"
    return text.replace("/", "-").replace("\\", "-").replace(":", "-")


def write_relevant_review_manifests(
    frame_df: pd.DataFrame,
    *,
    store_out: Path,
    run_id: str,
    write_warnings: list[str],
) -> dict[str, str]:
    if frame_df.empty or "relevant" not in frame_df.columns:
        return {}
    relevant_df = frame_df[frame_df["relevant"].fillna(0).astype(int) == 1].copy()
    if relevant_df.empty:
        return {}
    manifest_cols = [
        col for col in [
            "store_id",
            "Date",
            "folder_name",
            "image_id",
            "image_name",
            "camera_id",
            "timestamp_hint",
            "source_url",
            "relative_path",
            "person_count",
            "customer_count",
            "staff_count",
            "gpt_status",
        ]
        if col in relevant_df.columns
    ]
    relevant_df = relevant_df[manifest_cols]
    manifest_root = store_out / "yolo_review_manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}
    combined_path = safe_write_csv(manifest_root / "all_relevant_images.csv", relevant_df, run_id, write_warnings)
    outputs["all"] = str(combined_path.resolve())
    for date_value, date_df in relevant_df.groupby("Date", dropna=False):
        date_dir = manifest_root / _sanitize_manifest_date(date_value)
        date_dir.mkdir(parents=True, exist_ok=True)
        date_path = safe_write_csv(date_dir / "relevant_images.csv", date_df, run_id, write_warnings)
        outputs[str(date_value or "")] = str(date_path.resolve())
    return outputs


def write_pipeline_reports(
    conn: sqlite3.Connection,
    *,
    cfg: Any,
    run_id: str,
    source_provider: str,
    images: list[Any],
    timings: dict[str, float],
    perf0: float,
    started_at: str,
    yolo_version: str,
    gpt_version: str,
    detector_warning: str,
    skipped: int,
    new_images: int,
    yolo_done: int,
    yolo_relevant: int,
    gpt_done: int,
    gpt_failed: int,
    gpt_cache_hits: int,
    smart_sampled: int,
    gpt_retry_pending: int,
    gpt_batch_db_id: str | None,
    gpt_batch_queued_count: int,
    correction_map: dict[tuple[str, str], str],
) -> dict[str, Any]:
    import time
    t_rep = time.perf_counter()
    stage = PIPELINE_STAGES[5]
    update_pipeline_run(conn, run_id, current_stage=stage)
    append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="start", message="Writing report artifacts")
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    store_out = cfg.out_dir / cfg.store_id
    store_out.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? ORDER BY date_display,image_name", (cfg.store_id,)).fetchall()
    frame_df = pd.DataFrame([dict(row) for row in rows])
    listed_image_ids = {img.image_id for img in images}
    if not frame_df.empty and listed_image_ids:
        frame_df = frame_df[frame_df["image_id"].astype(str).isin(listed_image_ids)].copy()
    if frame_df.empty:
        frame_df = pd.DataFrame(columns=["store_id", "date_display", "image_name", "source_url", "camera_id", "timestamp_hint", "yolo_relevant", "person_count", "gpt_customer_count", "gpt_staff_count", "gpt_conversions", "gpt_bounce"])
    frame_df = frame_df.rename(columns={"date_display": "Date", "yolo_relevant": "relevant", "gpt_customer_count": "customer_count", "gpt_staff_count": "staff_count", "gpt_conversions": "conversions", "gpt_bounce": "bounce"})
    if "relative_path" in frame_df.columns:
        frame_df["folder_name"] = frame_df["relative_path"].map(_folder_from_rel)
    else:
        frame_df["folder_name"] = frame_df.get("Date", "")
    if "date_source" in frame_df.columns:
        frame_df = frame_df.drop(columns=["date_source"])
    preferred = ["store_id", "image_id", "relative_path", "folder_name", "Date", "image_name", "camera_id", "timestamp_hint"]
    ordered = [c for c in preferred if c in frame_df.columns] + [c for c in frame_df.columns if c not in preferred]
    frame_df = frame_df[ordered]
    write_warnings: list[str] = []
    image_results_path = safe_write_csv(store_out / "onfly_image_results.csv", frame_df, run_id, write_warnings)
    relevant_manifest_outputs = write_relevant_review_manifests(
        frame_df,
        store_out=store_out,
        run_id=run_id,
        write_warnings=write_warnings,
    )
    agg_df = frame_df.groupby(["store_id", "Date"], as_index=False).agg(
        total_images=("image_id", "count"),
        relevant_images=("relevant", "sum"),
        customer_count=("customer_count", "sum"),
        conversions=("conversions", "sum"),
        bounce=("bounce", "sum"),
    ) if not frame_df.empty else pd.DataFrame(columns=["store_id", "Date", "total_images", "relevant_images", "customer_count", "conversions", "bounce"])
    report_csv = cfg.out_dir / "onfly_store_date_report.csv"
    report_actual_path = report_csv
    if report_csv.exists():
        prev = pd.read_csv(report_csv)
        dates = set(agg_df["Date"].astype(str).tolist())
        mask = ~((prev.get("store_id", "") == cfg.store_id) & (prev.get("Date", "").astype(str).isin(dates)))
        merged = pd.concat([prev[mask], agg_df], ignore_index=True)
        report_actual_path = safe_write_csv(report_csv, merged, run_id, write_warnings)
    else:
        report_actual_path = safe_write_csv(report_csv, agg_df, run_id, write_warnings)

    from .session_reconstruction import apply_qa_corrections_to_run
    apply_qa_corrections_to_run(conn, cfg.store_id, run_id, correction_map)
    walkin_rows = conn.execute(
        """
        SELECT w.id, w.store_id, w.run_id, w.image_id, w.source_folder_name AS folder_name,
               w.source_image_name AS image_name, w.camera_id AS camera_id, w.business_date AS business_date,
               w.date, w.event_type, w.event_time, w.walkin_id, w.group_id, w.role, w.entry_time, w.exit_time,
               w.time_spent_mins, w.session_status, w.entry_type, w.first_seen_time, w.last_seen_time,
               w.matched_session_id, w.match_score, w.match_reason, w.direction_confidence, w.match_fingerprint,
               w.debug_parsed_time, w.debug_gpt_event_type, w.gender, w.age_band, w.attire_visual_marker,
               w.primary_clothing, w.jewellery_load, w.bag_type, w.clothing_style_archetype, w.engagement_type,
               w.engagement_depth, w.purchase_signal_bag, w.included_in_analytics, w.created_at
        FROM onfly_walkin_sessions w WHERE w.store_id=? AND w.run_id=? ORDER BY w.date, w.walkin_id, w.id
        """,
        (cfg.store_id, run_id),
    ).fetchall()
    if walkin_rows:
        walkin_df = apply_customer_group_correction(pd.DataFrame([dict(row) for row in walkin_rows]))
        audit_only_cols = ["matched_session_id", "match_score", "match_reason", "direction_confidence", "match_fingerprint", "debug_parsed_time", "created_at"]
        business_df = walkin_df.drop(columns=[c for c in ["debug_gpt_event_type", *audit_only_cols] if c in walkin_df.columns])
        walkin_sessions_path = safe_write_csv(store_out / "onfly_walkin_sessions.csv", business_df, run_id, write_warnings)
        safe_write_csv(store_out / "onfly_walkin_sessions_audit.csv", walkin_df, run_id, write_warnings)
    else:
        walkin_sessions_path = store_out / "onfly_walkin_sessions.csv"
    timings["report_ms"] = round((time.perf_counter() - t_rep) * 1000.0, 2)
    append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="success", message="Report writer completed", payload={"image_results_csv": str(image_results_path.resolve()), "store_date_csv": str(report_actual_path.resolve()), "walkin_rows": int(len(walkin_rows)), "warnings": write_warnings})
    total_ms = round((time.perf_counter() - perf0) * 1000.0, 2)
    ended_at = now_iso()
    retry_status = f"GPT quota unavailable; {gpt_retry_pending} image(s) queued for retry" if gpt_retry_pending > 0 else ""
    summary_status = "partial" if (gpt_retry_pending > 0 or gpt_failed > 0) else "success"
    summary = {
        "run_id": run_id,
        "store_id": cfg.store_id,
        "source_uri": cfg.source_uri,
        "source_provider": source_provider,
        "run_mode": cfg.run_mode,
        "pipeline_version": cfg.pipeline_version,
        "yolo_version": yolo_version,
        "gpt_version": gpt_version,
        "started_at": started_at,
        "ended_at": ended_at,
        "total_listed": len(images),
        "new_images": new_images,
        "skipped_cached": skipped,
        "yolo_done": yolo_done,
        "yolo_relevant": yolo_relevant,
        "gpt_done": gpt_done,
        "gpt_failed": gpt_failed,
        "gpt_cache_hits": gpt_cache_hits,
        "smart_sampled": smart_sampled,
        "gpt_retry_pending": gpt_retry_pending,
        "gpt_batch_mode": cfg.gpt_batch_mode,
        "gpt_batch_queued": gpt_batch_queued_count,
        "gpt_batch_db_id": gpt_batch_db_id,
        "status": summary_status,
        "retry_status": retry_status,
        "timings_ms": {**timings, "total_ms": total_ms},
        "detector_warning": detector_warning,
        "write_warnings": write_warnings,
        "outputs": {
            "image_results_csv": str(image_results_path.resolve()),
            "store_report_csv": str(report_actual_path.resolve()),
            "walkin_sessions_csv": str(walkin_sessions_path.resolve()) if walkin_rows else "",
            "yolo_review_manifests": relevant_manifest_outputs,
        },
    }
    summary_path = cfg.out_dir / f"onfly_run_summary_{run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["outputs"]["run_summary_json"] = str(summary_path.resolve())
    timings_df = pd.DataFrame([
        {
            "run_id": run_id,
            "store_id": cfg.store_id,
            "pipeline_version": cfg.pipeline_version,
            "yolo_version": yolo_version,
            "gpt_version": gpt_version,
            "started_at": started_at,
            "ended_at": ended_at,
            "list_ms": float(timings["list_ms"]),
            "download_ms": float(timings["download_ms"]),
            "yolo_ms": float(timings["yolo_ms"]),
            "gpt_ms": float(timings["gpt_ms"]),
            "report_ms": float(timings["report_ms"]),
            "total_ms": float(total_ms),
            "list_hms": ms_to_hms(float(timings["list_ms"])),
            "download_hms": ms_to_hms(float(timings["download_ms"])),
            "yolo_hms": ms_to_hms(float(timings["yolo_ms"])),
            "gpt_hms": ms_to_hms(float(timings["gpt_ms"])),
            "report_hms": ms_to_hms(float(timings["report_ms"])),
            "total_hms": ms_to_hms(float(total_ms)),
        }
    ])
    timings_path = store_out / "onfly_process_timings.csv"
    if timings_path.exists():
        try:
            prev_timings = pd.read_csv(timings_path)
            timings_df = pd.concat([prev_timings, timings_df], ignore_index=True)
        except Exception:
            pass
    safe_write_csv(timings_path, timings_df, run_id, write_warnings)
    summary["outputs"]["process_timings_csv"] = str(timings_path.resolve())
    stage = PIPELINE_STAGES[6]
    update_pipeline_run(conn, run_id, current_stage=stage)
    append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="start", message="Updating dashboard ingestion index")
    for report_row in agg_df.to_dict(orient="records"):
        report_date = str(report_row.get("Date", "")).strip()
        if not report_date:
            continue
        conn.execute(
            """
            INSERT INTO onfly_report_index(store_id,business_date,run_id,image_results_csv,walkin_sessions_csv,store_date_csv,summary_json,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(store_id,business_date) DO UPDATE SET
                run_id=excluded.run_id,
                image_results_csv=excluded.image_results_csv,
                walkin_sessions_csv=excluded.walkin_sessions_csv,
                store_date_csv=excluded.store_date_csv,
                summary_json=excluded.summary_json,
                updated_at=excluded.updated_at
            """,
            (
                cfg.store_id,
                report_date,
                run_id,
                str(image_results_path.resolve()),
                str(walkin_sessions_path.resolve()) if walkin_rows else "",
                str(report_actual_path.resolve()),
                str(summary_path.resolve()),
                now_iso(),
            ),
        )
    append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="success", message="Dashboard ingestion index updated")
    update_pipeline_run(
        conn,
        run_id,
        status=summary_status,
        current_stage=stage,
        ended_at=ended_at,
        images_discovered=len(images),
        images_skipped=skipped,
        images_processed=skipped + new_images,
        images_relevant=yolo_relevant,
        images_irrelevant=max(0, yolo_done - yolo_relevant),
        gpt_success_count=gpt_done,
        gpt_failed_count=gpt_failed,
        gpt_cache_hits=gpt_cache_hits,
        report_image_results_csv=str(image_results_path.resolve()),
        report_walkin_sessions_csv=str(walkin_sessions_path.resolve()) if walkin_rows else "",
        report_store_date_csv=str(report_actual_path.resolve()),
        retry_status=retry_status,
    )
    conn.execute(
        "INSERT OR REPLACE INTO onfly_run_metrics(run_id,store_id,run_mode,source_provider,started_at,ended_at,total_listed,new_images,skipped_cached,yolo_done,yolo_relevant,gpt_done,total_ms,list_ms,download_ms,yolo_ms,gpt_ms,report_ms,status,summary_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, cfg.store_id, cfg.run_mode, source_provider, started_at, ended_at, len(images), new_images, skipped, yolo_done, yolo_relevant, gpt_done, total_ms, timings["list_ms"], timings["download_ms"], timings["yolo_ms"], timings["gpt_ms"], timings["report_ms"], "ok", json.dumps(summary, separators=(",", ":"))),
    )
    conn.commit()
    return summary


def write_cost_metrics(
    conn: sqlite3.Connection,
    *,
    metric_day: str,
    store_id: str,
    run_id: str,
    counters: dict[str, float | int],
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO onfly_cost_metrics(
            metric_day, store_id, run_id, images_listed, yolo_relevant, gpt_calls,
            hash_cache_hits, sampled_skips, duplicate_skips, outside_hours_skips,
            excluded_camera_skips, quota_failures, gpt_batch_images, gpt_realtime_images,
            est_cost_inr, created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            metric_day,
            store_id,
            run_id,
            int(counters.get("images_listed", 0) or 0),
            int(counters.get("yolo_relevant", 0) or 0),
            int(counters.get("gpt_calls", 0) or 0),
            int(counters.get("hash_cache_hits", 0) or 0),
            int(counters.get("sampled_skips", 0) or 0),
            int(counters.get("duplicate_skips", 0) or 0),
            int(counters.get("outside_hours_skips", 0) or 0),
            int(counters.get("excluded_camera_skips", 0) or 0),
            int(counters.get("quota_failures", 0) or 0),
            int(counters.get("gpt_batch_images", 0) or 0),
            int(counters.get("gpt_realtime_images", 0) or 0),
            float(counters.get("est_cost_inr", 0.0) or 0.0),
            now_iso(),
        ),
    )

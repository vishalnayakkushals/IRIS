from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .gpt_runtime import parse_filename_time
from .source_clients import SourceImage

_ROLE_MAP: dict[str, str] = {
    "customer": "Customer",
    "staff": "Staff",
    "uncertain": "Uncertain",
    "unknown": "Uncertain",
    "passerby": "Passerby",
    "banner": "Banner",
    "poster": "Banner",
    "poster non human": "Banner",
    "poster_non_human": "Banner",
    "poster or non-human": "Banner",
    "inside active": "Customer",
}

_PG_WALKIN_COLS = [
    "store_id", "run_id", "image_id", "source_image_name", "source_folder_name", "camera_id", "business_date", "date",
    "event_type", "event_time", "walkin_id", "group_id", "role", "entry_time", "exit_time", "time_spent_mins", "session_status",
    "entry_type", "first_seen_time", "last_seen_time", "matched_session_id", "match_score", "match_reason", "direction_confidence",
    "match_fingerprint", "debug_parsed_time", "debug_gpt_event_type", "gender", "age_band", "attire_visual_marker", "primary_clothing",
    "jewellery_load", "bag_type", "clothing_style_archetype", "engagement_type", "engagement_depth", "purchase_signal_bag", "included_in_analytics",
]


def norm_role(role: str) -> str:
    text = str(role or "").strip()
    return _ROLE_MAP.get(text.lower(), text.title() if text else "Uncertain")


def norm_yn(val: str) -> str:
    return "Yes" if str(val or "").strip().lower() == "yes" else "No"


def norm_date(date_str: str) -> str:
    text = str(date_str or '').strip()
    if len(text) == 10 and text[2] == '-' and text[5] == '-':
        return f"{text[6:10]}-{text[3:5]}-{text[0:2]}"
    return text


def canonical_event_type(row: dict[str, str]) -> str:
    raw = str(row.get("Event Type", "") or "").strip().upper()
    role = str(row.get("Role", "") or "").strip().lower()
    entry_type = str(row.get("Entry Type", "") or "").strip().lower()
    engage = str(row.get("Engagement Type", "") or "").strip().lower()
    if raw in {"ENTRY", "EXIT", "INSIDE_ACTIVE", "INSIDE_PURCHASING", "PASSERBY_OUTSIDE", "STAFF", "POSTER_NON_HUMAN", "UNCLEAR"}:
        return raw
    if role == "staff":
        return "STAFF"
    if "assisted entry" in entry_type or "walk-in" in entry_type:
        return "ENTRY"
    if "billing" in engage:
        return "INSIDE_PURCHASING"
    if engage in {"browsing", "waiting", "assisted"}:
        return "INSIDE_ACTIVE"
    if role == "customer":
        return "INSIDE_ACTIVE"
    return "UNCLEAR"


def event_fingerprint(row: dict[str, str], camera_id: str) -> str:
    keys = [
        camera_id,
        str(row.get("Role", "") or "").strip().lower(),
        str(row.get("Gender", "") or "").strip().lower(),
        str(row.get("Age Band", "") or "").strip().lower(),
        str(row.get("Primary Clothing", "") or "").strip().lower(),
        str(row.get("Bag Type", "") or "").strip().lower(),
        str(row.get("Jewellery Load", "") or "").strip().lower(),
        str(row.get("Primary Clothing Style Archetype", "") or "").strip().lower(),
        str(row.get("Attire / Visual Marker", "") or "").strip().lower()[:80],
    ]
    return "|".join(keys)


def load_qa_correction_map(store_id: str, data_root: Path) -> dict[tuple[str, str], str]:
    path = data_root / "models" / f"qa_corrections_{store_id}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        out: dict[tuple[str, str], str] = {}
        for correction in data.get("corrections", []):
            fn = str(correction.get("filename") or "").strip().lower()
            tid = str(correction.get("track_id") or "").strip().lower()
            label = str(correction.get("corrected_label") or "").strip().lower()
            if fn and label:
                out[(fn, tid)] = label
        return out
    except Exception:
        return {}


def apply_qa_corrections_to_run(conn: sqlite3.Connection, store_id: str, run_id: str, correction_map: dict[tuple[str, str], str]) -> int:
    if not correction_map:
        return 0
    rows = conn.execute("SELECT id, source_image_name, walkin_id, role FROM onfly_walkin_sessions WHERE store_id=? AND run_id=?", (store_id, run_id)).fetchall()
    count = 0
    for row in rows:
        img_key = str(row["source_image_name"] or "").strip().lower()
        wid_key = str(row["walkin_id"] or "").strip().lower()
        corrected = correction_map.get((img_key, wid_key)) or correction_map.get((img_key, "frame"))
        if corrected and corrected != str(row["role"] or "").strip().lower():
            new_role = corrected.capitalize()
            new_analytics = "Yes" if corrected == "customer" else "No"
            conn.execute("UPDATE onfly_walkin_sessions SET role=?, included_in_analytics=? WHERE id=?", (new_role, new_analytics, row["id"]))
            count += 1
    if count:
        conn.commit()
    return count


def load_prompt_improvement_text(store_id: str, data_root: Path) -> str:
    path = data_root / "models" / f"prompt_improvements_{store_id}.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text())
        return str(data.get("active_text") or "").strip()
    except Exception:
        return ""


def load_excluded_cameras(store_id: str) -> set[str]:
    try:
        from backend.app.db.session import engine_sync
        from sqlalchemy import text as sa_text
        with engine_sync.connect() as pg:
            rows = pg.execute(sa_text("SELECT camera_id FROM camera_configs WHERE store_id=:sid AND camera_type IN ('external','skip','backroom')"), {"sid": store_id}).fetchall()
        return {str(r[0]) for r in rows if r[0]}
    except Exception:
        return set()


def load_store_hours(store_id: str) -> tuple[int, int]:
    try:
        from backend.app.db.session import engine_sync
        from sqlalchemy import text as sa_text
        with engine_sync.connect() as pg:
            row = pg.execute(sa_text("SELECT open_hour, open_minute, close_hour, close_minute FROM stores WHERE store_id=:sid"), {"sid": store_id}).fetchone()
        if row:
            return int(row[0] or 10) * 60 + int(row[1] or 30), int(row[2] or 21) * 60 + int(row[3] or 30)
    except Exception:
        pass
    return (630, 1290)


def load_billing_cameras(store_id: str) -> set[str]:
    try:
        from backend.app.db.session import engine_sync
        from sqlalchemy import text as sa_text
        with engine_sync.connect() as pg:
            rows = pg.execute(sa_text("SELECT camera_id FROM camera_configs WHERE store_id=:sid AND camera_type = 'billing'"), {"sid": store_id}).fetchall()
        return {str(r[0]) for r in rows if r[0]}
    except Exception:
        return set()


def auto_discover_cameras(sqlite_conn: sqlite3.Connection, store_id: str) -> None:
    try:
        rows = sqlite_conn.execute(
            """
            SELECT camera_id, MIN(image_id) AS sample_image_id
            FROM onfly_image_state
            WHERE store_id=? AND camera_id IS NOT NULL AND camera_id != ''
            GROUP BY camera_id
            """,
            (store_id,),
        ).fetchall()
        if not rows:
            return
        from backend.app.db.session import engine_sync
        from sqlalchemy import text as sa_text
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc)
        with engine_sync.begin() as pg:
            for cam_id, sample_image_id in rows:
                existing = pg.execute(sa_text("SELECT 1 FROM camera_configs WHERE store_id=:sid AND camera_id=:cid"), {"sid": store_id, "cid": cam_id}).first()
                if not existing:
                    pg.execute(
                        sa_text(
                            "INSERT INTO camera_configs (store_id, camera_id, camera_role, floor_name, location_name, entry_line_x, entry_direction, camera_type, sample_image_id, updated_at) VALUES (:sid, :cid, 'INSIDE', '', '', 0.5, 'OUTSIDE_TO_INSIDE', 'unlabeled', :sample, :now)"
                        ),
                        {"sid": store_id, "cid": cam_id, "sample": sample_image_id or "", "now": now},
                    )
    except Exception:
        pass


def sync_run_to_postgres(sqlite_conn: sqlite3.Connection, run_id: str, store_id: str) -> None:
    cols_sql = ", ".join(_PG_WALKIN_COLS)
    rows = sqlite_conn.execute(f"SELECT {cols_sql} FROM onfly_walkin_sessions WHERE run_id=? AND store_id=?", (run_id, store_id)).fetchall()
    if not rows:
        return
    from backend.app.db.session import engine_sync
    from sqlalchemy import text as sa_text
    placeholders = ", ".join([f":{c}" for c in _PG_WALKIN_COLS])
    insert_sql = sa_text(f"INSERT INTO onfly_walkin_sessions ({cols_sql}) VALUES ({placeholders})")
    batch = [dict(zip(_PG_WALKIN_COLS, row)) for row in rows]
    with engine_sync.begin() as pg_conn:
        pg_conn.execute(sa_text("DELETE FROM onfly_walkin_sessions WHERE run_id=:run_id AND store_id=:store_id"), {"run_id": run_id, "store_id": store_id})
        pg_conn.execute(insert_sql, batch)


def _tsec(value: str) -> int:
    try:
        hh, mm, ss = [int(x) for x in str(value or "").split(":")]
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return -1


def _find_best_open_session(conn: sqlite3.Connection, store_id: str, business_date: str, item: SourceImage, event_time: str, row: dict[str, str]) -> tuple[int | None, float, str]:
    candidates = conn.execute(
        """
        SELECT id, camera_id, gender, age_band, primary_clothing, bag_type,
               clothing_style_archetype, jewellery_load, attire_visual_marker, last_seen_time
        FROM onfly_walkin_sessions
        WHERE store_id=? AND business_date=? AND role='Customer'
          AND session_status IN ('OPEN','INFERRED_INSIDE_OPEN')
        ORDER BY id DESC
        """,
        (store_id, business_date),
    ).fetchall()
    best_id: int | None = None
    best_score = -1.0
    best_reason = "no_open_session"
    now_sec = _tsec(event_time)
    for cand in candidates:
        score = 0.0
        reasons: list[str] = []
        if str(cand["camera_id"] or "") == str(item.camera_id or ""):
            score += 2.0
            reasons.append("camera")
        for key in ["gender", "age_band", "primary_clothing", "bag_type", "clothing_style_archetype", "jewellery_load"]:
            rv = str(row.get({
                "gender": "Gender",
                "age_band": "Age Band",
                "primary_clothing": "Primary Clothing",
                "bag_type": "Bag Type",
                "clothing_style_archetype": "Primary Clothing Style Archetype",
                "jewellery_load": "Jewellery Load",
            }[key], "") or "").strip().lower()
            cv = str(cand[key] or "").strip().lower()
            if rv and cv and rv == cv:
                score += 1.0
                reasons.append(key)
        last_sec = _tsec(str(cand["last_seen_time"] or ""))
        if now_sec >= 0 and last_sec >= 0:
            gap = abs(now_sec - last_sec)
            if gap <= 120:
                score += 2.0
                reasons.append("time<=120s")
            elif gap <= 300:
                score += 1.0
                reasons.append("time<=300s")
        if score > best_score:
            best_score = score
            best_id = int(cand["id"])
            best_reason = ",".join(reasons) if reasons else "weak_match"
    return best_id, float(best_score if best_score > 0 else 0.0), best_reason


def persist_gpt_sessions(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    run_id: str,
    item: SourceImage,
    walkins: list[dict[str, str]],
) -> None:
    event_time = parse_filename_time(item.image_name) or str(item.timestamp_hint or "").split(" ")[-1].strip()
    business_date = str(item.date_display or "").strip()
    for walkin in walkins:
        role = norm_role(walkin.get("Role", "") or "")
        event_type = canonical_event_type(walkin)
        direction_conf = str(walkin.get("Direction Confidence", "") or "").strip() or "NA"
        match_fingerprint = str(walkin.get("Match Fingerprint", "") or "").strip() or event_fingerprint(walkin, item.camera_id)
        raw_included = str(walkin.get("Included in Analytics", "") or "").strip()
        included = norm_yn(raw_included) if raw_included else ("Yes" if role == "Customer" else "No")
        gpt_event = str(walkin.get("Event Type", "") or "").strip()

        if event_type in {"PASSERBY_OUTSIDE", "POSTER_NON_HUMAN", "STAFF", "UNCLEAR"}:
            conn.execute(
                """INSERT INTO onfly_walkin_sessions(
                       store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                       event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                       session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                       direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                       gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                       clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                    event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), role, "", "", "",
                    "CLOSED", walkin.get("Entry Type", ""), event_time, event_time, "", 0.0, "non_customer_event",
                    direction_conf, match_fingerprint, event_time, gpt_event,
                    walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                    walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                    walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), "No",
                ),
            )
            continue

        match_id, match_score, match_reason = _find_best_open_session(conn, store_id, business_date, item, event_time, walkin)
        strong_entry_match = match_id is not None and match_score >= 6.0
        strong_match = match_id is not None and match_score >= 4.0

        if event_type == "ENTRY":
            if strong_entry_match:
                conn.execute("UPDATE onfly_walkin_sessions SET last_seen_time=?, match_score=?, match_reason=? WHERE id=?", (event_time, match_score, f"entry_attach:{match_reason}", int(match_id)))
            else:
                conn.execute(
                    """INSERT INTO onfly_walkin_sessions(
                           store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                           event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                           session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                           direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                           gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                           clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                        event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", event_time, "NA", "NA",
                        "OPEN", "ENTRY", event_time, event_time, "", 0.0, "new_entry",
                        direction_conf, match_fingerprint, event_time, gpt_event,
                        walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                        walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                        walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                    ),
                )
            continue

        if event_type in {"INSIDE_ACTIVE", "INSIDE_PURCHASING"}:
            if strong_match:
                conn.execute("UPDATE onfly_walkin_sessions SET last_seen_time=?, match_score=?, match_reason=? WHERE id=?", (event_time, match_score, f"inside_update:{match_reason}", int(match_id)))
            else:
                conn.execute(
                    """INSERT INTO onfly_walkin_sessions(
                           store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                           event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                           session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                           direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                           gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                           clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                        event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", event_time, "NA", "NA",
                        "INFERRED_INSIDE_OPEN", "INFERRED_INSIDE", event_time, event_time, "", 0.0, "inferred_inside",
                        direction_conf, match_fingerprint, event_time, gpt_event,
                        walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                        walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                        walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                    ),
                )
            continue

        if event_type == "EXIT":
            if strong_match:
                conn.execute("UPDATE onfly_walkin_sessions SET exit_time=?, last_seen_time=?, session_status='CLOSED', match_score=?, match_reason=? WHERE id=?", (event_time, event_time, match_score, f"exit_match:{match_reason}", int(match_id)))
            else:
                conn.execute(
                    """INSERT INTO onfly_walkin_sessions(
                           store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                           event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                           session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                           direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                           gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                           clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                       ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                        event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", "NA", event_time, "NA",
                        "UNMATCHED_EXIT", "NA", event_time, event_time, "", 0.0, "no_open_match",
                        direction_conf, match_fingerprint, event_time, gpt_event,
                        walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                        walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                        walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                    ),
                )
            continue

        conn.execute(
            """INSERT INTO onfly_walkin_sessions(
                   store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                   event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                   session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                   direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                   gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                   clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), role, event_time, "NA", "NA",
                "OPEN", walkin.get("Entry Type", ""), event_time, event_time, "", 0.0, "fallback",
                direction_conf, match_fingerprint, event_time, gpt_event,
                walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
            ),
        )


def clone_walkin_sessions_from_source(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    run_id: str,
    target_image_id: str,
    target_image_name: str,
    source_image_id: str,
    source_folder_name: str,
    reason_prefix: str,
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO onfly_walkin_sessions(
               store_id, run_id, image_id, source_image_name, source_folder_name, camera_id,
               business_date, date, event_type, event_time, walkin_id, group_id, role,
               entry_time, exit_time, time_spent_mins, session_status, entry_type,
               first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
               direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
               gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
               clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
           ) SELECT
               store_id, ?, ?, ?, ?, camera_id,
               business_date, date, event_type, event_time, walkin_id, group_id, role,
               entry_time, exit_time, time_spent_mins, session_status, entry_type,
               first_seen_time, last_seen_time, matched_session_id, match_score, ? || match_reason,
               direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
               gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
               clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
             FROM onfly_walkin_sessions WHERE store_id=? AND image_id=?""",
        (run_id, target_image_id, target_image_name, source_folder_name, reason_prefix, store_id, source_image_id),
    )


def resolve_sampled_frames(conn: sqlite3.Connection, *, store_id: str, run_id: str) -> int:
    rows = conn.execute(
        "SELECT image_id, image_name, date_display, sampled_anchor_image_id FROM onfly_image_state WHERE store_id=? AND last_run_id=? AND gpt_status='sampled_wait_anchor' AND sampled_anchor_image_id != ''",
        (store_id, run_id),
    ).fetchall()
    resolved = 0
    for row in rows:
        anchor = conn.execute(
            "SELECT yolo_relevant, person_count, yolo_conf, yolo_error, gpt_version, gpt_customer_count, gpt_staff_count, gpt_conversions, gpt_bounce, gpt_result_json, gpt_status FROM onfly_image_state WHERE store_id=? AND image_id=?",
            (store_id, str(row["sampled_anchor_image_id"])),
        ).fetchone()
        if not anchor or str(anchor["gpt_status"] or "") not in {"done", "cached_from_hash", "sampled_from_anchor"}:
            continue
        conn.execute(
            "UPDATE onfly_image_state SET gpt_version=?, gpt_status='sampled_from_anchor', gpt_customer_count=?, gpt_staff_count=?, gpt_conversions=?, gpt_bounce=?, gpt_result_json=?, gpt_error='', last_run_id=? WHERE store_id=? AND image_id=?",
            (
                str(anchor["gpt_version"] or ""),
                int(anchor["gpt_customer_count"] or 0),
                int(anchor["gpt_staff_count"] or 0),
                int(anchor["gpt_conversions"] or 0),
                int(anchor["gpt_bounce"] or 0),
                str(anchor["gpt_result_json"] or "{}"),
                run_id,
                store_id,
                str(row["image_id"]),
            ),
        )
        clone_walkin_sessions_from_source(
            conn,
            store_id=store_id,
            run_id=run_id,
            target_image_id=str(row["image_id"]),
            target_image_name=str(row["image_name"] or ""),
            source_image_id=str(row["sampled_anchor_image_id"]),
            source_folder_name=str(row["date_display"] or ""),
            reason_prefix="sampled_from_anchor:",
        )
        resolved += 1
    return resolved

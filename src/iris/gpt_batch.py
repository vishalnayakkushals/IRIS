"""OpenAI Batch API integration for IRIS — 50% cost saving on GPT calls.

Flow:
  1. During pipeline run (batch mode on):
       queue_image_for_batch() stores image bytes + metadata in SQLite.
       Pipeline marks images as gpt_status='batch_queued'.

  2. End of run: build_and_submit_batch()
       Creates a JSONL file of all queued images, uploads to OpenAI /v1/files,
       then creates a batch via /v1/batches. Returns batch_db_id.
       The laptop can now close — batch runs on OpenAI's servers overnight.

  3. Next morning (6 AM via Task Scheduler or manual): check_and_apply_batch()
       Polls /v1/batches/{id}. When status=completed, downloads output file,
       parses walkin rows, writes to onfly_image_state + onfly_walkin_sessions.
       Syncs to PostgreSQL so dashboard reflects latest data.

Cost: 50% of real-time GPT price. Results within 24h (typically 2–6h overnight).
"""
from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ── Walkin schema constants (mirror of onfly_pipeline.py) ────────────────────

_WALKIN_COLUMNS = [
    "Date", "Walk-in ID", "Group ID", "Role", "Entry Time", "Exit Time",
    "Time Spent (mins)", "Session Status", "Entry Type", "Gender", "Age Band",
    "Attire / Visual Marker", "Primary Clothing", "Jewellery Load", "Bag Type",
    "Primary Clothing Style Archetype", "Engagement Type", "Engagement Depth",
    "Purchase Signal (Bag)", "Conversion Signal", "Included in Analytics",
    "Event Type", "Direction Confidence", "Match Fingerprint",
]

_ROLE_MAP: dict[str, str] = {
    "customer": "Customer", "staff": "Staff", "uncertain": "Uncertain",
    "unknown": "Uncertain", "passerby": "Passerby",
    "inside active": "Customer",
}

_BATCH_CUSTOM_ID_PREFIX = "irisq_"


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _norm_role(role: str) -> str:
    r = str(role or "").strip()
    return _ROLE_MAP.get(r.lower(), r.title() if r else "Uncertain")


def _norm_yn(val: str) -> str:
    return "Yes" if str(val or "").strip().lower() == "yes" else "No"


def _norm_date(date_str: str) -> str:
    d = str(date_str or "").strip()
    if len(d) == 10 and d[2] == "-" and d[5] == "-":
        return f"{d[6:10]}-{d[3:5]}-{d[0:2]}"
    return d


def _apply_staff_rule(walkins: list[dict[str, str]]) -> list[dict[str, str]]:
    for row in walkins:
        role = str(row.get("Role", "") or "").lower()
        text = " ".join([
            str(row.get("Attire / Visual Marker", "") or "").lower(),
            str(row.get("Primary Clothing", "") or "").lower(),
            str(row.get("Primary Clothing Style Archetype", "") or "").lower(),
        ])
        has_pant = any(t in text for t in ("pant", "pants", "trouser", "trousers"))
        has_staff = ((("white" in text or "red" in text) and "black" in text) and has_pant)
        if has_staff and role in {"customer", "uncertain", ""}:
            row["Role"] = "Staff"
            row["Included in Analytics"] = "No"
    return walkins


def _walkin_schema_for_batch() -> dict:
    row_props = {col: {"type": "string"} for col in _WALKIN_COLUMNS}
    return {
        "name": "retail_onfly_walkin_table",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"rows": {
                "type": "array",
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": row_props, "required": list(row_props.keys()),
                },
            }},
            "required": ["rows"],
        },
    }


# ── Table init ────────────────────────────────────────────────────────────────

def init_batch_tables(conn: sqlite3.Connection) -> None:
    """Create batch-related SQLite tables. Safe to call multiple times."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onfly_gpt_batch_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT NOT NULL,
            image_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            image_name TEXT NOT NULL DEFAULT '',
            camera_id TEXT NOT NULL DEFAULT '',
            is_billing_camera INTEGER NOT NULL DEFAULT 0,
            image_b64 TEXT NOT NULL DEFAULT '',
            image_ext TEXT NOT NULL DEFAULT 'jpeg',
            person_count INTEGER NOT NULL DEFAULT 0,
            yolo_conf REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            batch_db_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(store_id, image_id, run_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS onfly_gpt_batches (
            batch_db_id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            openai_batch_id TEXT NOT NULL DEFAULT '',
            openai_file_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            image_count INTEGER NOT NULL DEFAULT 0,
            output_file_id TEXT NOT NULL DEFAULT '',
            results_applied INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '',
            submitted_at TEXT NOT NULL DEFAULT '',
            completed_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_batch_queue_store_status ON onfly_gpt_batch_queue(store_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_batches_store_status ON onfly_gpt_batches(store_id, status)")
    conn.commit()


# ── Queue ─────────────────────────────────────────────────────────────────────

def queue_image_for_batch(
    conn: sqlite3.Connection,
    *,
    store_id: str,
    image_id: str,
    run_id: str,
    image_name: str,
    camera_id: str,
    is_billing_camera: bool,
    image_bytes: bytes,
    person_count: int = 0,
    yolo_conf: float = 0.0,
) -> None:
    """Add a YOLO-relevant image to the overnight batch queue."""
    ext = Path(image_name).suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    now = _now()
    conn.execute(
        """
        INSERT INTO onfly_gpt_batch_queue(
            store_id, image_id, run_id, image_name, camera_id, is_billing_camera,
            image_b64, image_ext, person_count, yolo_conf, status, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)
        ON CONFLICT(store_id, image_id, run_id) DO UPDATE SET
            status='pending', image_b64=excluded.image_b64,
            person_count=excluded.person_count, updated_at=excluded.updated_at
        """,
        (store_id, image_id, run_id, image_name, camera_id, int(is_billing_camera),
         b64, ext, person_count, yolo_conf, now, now),
    )


# ── Submit ────────────────────────────────────────────────────────────────────

def build_and_submit_batch(
    store_id: str,
    run_id: str,
    openai_api_key: str,
    openai_model: str,
    conn: sqlite3.Connection,
    prompt_text: str,
    *,
    openai_api_base: str = "https://api.openai.com/v1",
) -> str | None:
    """
    Collect all pending queue entries for store+run, build a JSONL batch file,
    upload to OpenAI, and create a batch job.
    Returns batch_db_id on success, None if no images queued.
    The batch runs on OpenAI servers — laptop can close after this returns.
    """
    rows = conn.execute(
        "SELECT id, image_id, image_name, camera_id, is_billing_camera, image_b64, image_ext "
        "FROM onfly_gpt_batch_queue "
        "WHERE store_id=? AND run_id=? AND status='pending'",
        (store_id, run_id),
    ).fetchall()
    if not rows:
        return None

    batch_db_id = f"batch_{store_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    now = _now()
    schema_def = _walkin_schema_for_batch()

    billing_ctx = (
        "\n\nCAMERA CONTEXT — BILLING/CHECKOUT: This image is captured by a camera positioned at a "
        "billing counter or checkout area. Any Customer visible here is at the payment point. "
        "Apply Conversion Signal = Yes for all Customers in this image. Set Engagement Type = Billing."
    )

    lines: list[str] = []
    for row in rows:
        queue_id, image_id, image_name, camera_id, is_billing, b64, ext = row
        full_prompt = prompt_text + (billing_ctx if is_billing else "")
        data_uri = f"data:image/{ext};base64,{b64}"

        body = {
            "model": openai_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": full_prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_def["name"],
                    "strict": schema_def["strict"],
                    "schema": schema_def["schema"],
                },
            },
            "max_tokens": 2000,
        }
        lines.append(json.dumps({
            "custom_id": f"{_BATCH_CUSTOM_ID_PREFIX}{queue_id}",
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }, separators=(",", ":")))

    jsonl_bytes = "\n".join(lines).encode("utf-8")
    headers = {"Authorization": f"Bearer {openai_api_key}"}
    base = openai_api_base.rstrip("/")

    # Upload JSONL file to OpenAI
    file_resp = requests.post(
        f"{base}/files",
        headers=headers,
        files={"file": (f"{batch_db_id}.jsonl", jsonl_bytes, "application/jsonl")},
        data={"purpose": "batch"},
        timeout=180,
    )
    file_resp.raise_for_status()
    file_id = file_resp.json()["id"]

    # Create the batch job (24-hour completion window)
    batch_resp = requests.post(
        f"{base}/batches",
        headers={**headers, "Content-Type": "application/json"},
        json={"input_file_id": file_id, "endpoint": "/v1/chat/completions", "completion_window": "24h"},
        timeout=60,
    )
    batch_resp.raise_for_status()
    openai_batch_id = batch_resp.json()["id"]

    # Record batch in SQLite
    conn.execute(
        """
        INSERT INTO onfly_gpt_batches(
            batch_db_id, store_id, run_id, openai_batch_id, openai_file_id,
            status, image_count, submitted_at, created_at, updated_at
        ) VALUES (?,?,?,?,?,'submitted',?,?,?,?)
        """,
        (batch_db_id, store_id, run_id, openai_batch_id, file_id, len(rows), now, now, now),
    )

    # Mark queue entries submitted
    queue_ids = [str(r[0]) for r in rows]
    conn.execute(
        f"UPDATE onfly_gpt_batch_queue SET status='submitted', batch_db_id=?, updated_at=? "
        f"WHERE id IN ({','.join('?' * len(queue_ids))})",
        [batch_db_id, now] + queue_ids,
    )
    conn.commit()
    return batch_db_id


# ── Poll + retrieve ───────────────────────────────────────────────────────────

def check_batch_status(
    batch_db_id: str,
    openai_api_key: str,
    conn: sqlite3.Connection,
    *,
    openai_api_base: str = "https://api.openai.com/v1",
) -> dict[str, Any]:
    """Check OpenAI status and update our DB. Returns status dict."""
    row = conn.execute(
        "SELECT openai_batch_id, status, output_file_id FROM onfly_gpt_batches WHERE batch_db_id=?",
        (batch_db_id,),
    ).fetchone()
    if row is None:
        return {"status": "not_found", "batch_db_id": batch_db_id}

    openai_batch_id, our_status, existing_output_file = row
    if our_status in ("completed", "failed", "cancelled"):
        return {"status": our_status, "batch_db_id": batch_db_id, "output_file_id": existing_output_file}

    headers = {"Authorization": f"Bearer {openai_api_key}"}
    try:
        resp = requests.get(
            f"{openai_api_base.rstrip('/')}/batches/{openai_batch_id}",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return {"status": "check_failed", "error": str(exc), "batch_db_id": batch_db_id}

    openai_status = data.get("status", "")
    output_file_id = data.get("output_file_id") or ""
    now = _now()

    status_map = {
        "validating": "submitted", "in_progress": "in_progress",
        "finalizing": "in_progress", "completed": "completed",
        "failed": "failed", "expired": "failed",
        "cancelled": "cancelled", "cancelling": "cancelled",
    }
    new_status = status_map.get(openai_status, "submitted")

    conn.execute(
        "UPDATE onfly_gpt_batches SET status=?, output_file_id=?, "
        "completed_at=?, updated_at=? WHERE batch_db_id=?",
        (new_status, output_file_id,
         now if new_status in ("completed", "failed") else "", now, batch_db_id),
    )
    conn.commit()

    return {
        "status": new_status,
        "openai_status": openai_status,
        "batch_db_id": batch_db_id,
        "openai_batch_id": openai_batch_id,
        "output_file_id": output_file_id,
        "request_counts": data.get("request_counts", {}),
    }


def apply_batch_results(
    batch_db_id: str,
    openai_api_key: str,
    conn: sqlite3.Connection,
    *,
    openai_api_base: str = "https://api.openai.com/v1",
) -> dict[str, int]:
    """
    Download output file for a completed batch and apply results to SQLite.
    Writes walkin sessions and syncs to PostgreSQL.
    Returns {"applied": N, "failed": M}.
    """
    row = conn.execute(
        "SELECT store_id, run_id, output_file_id, results_applied "
        "FROM onfly_gpt_batches WHERE batch_db_id=?",
        (batch_db_id,),
    ).fetchone()
    if row is None:
        return {"error": 1, "reason": "batch_not_found"}
    store_id, run_id, output_file_id, results_applied = row
    if results_applied:
        return {"already_applied": 1, "batch_db_id": batch_db_id}
    if not output_file_id:
        return {"error": 1, "reason": "no_output_file"}

    headers = {"Authorization": f"Bearer {openai_api_key}"}
    try:
        resp = requests.get(
            f"{openai_api_base.rstrip('/')}/files/{output_file_id}/content",
            headers=headers, timeout=300, stream=True,
        )
        resp.raise_for_status()
        raw_lines = resp.text.strip().split("\n")
    except Exception as exc:
        return {"error": 1, "reason": str(exc)}

    gpt_version = "batch_v1"
    applied = 0
    failed = 0
    now = _now()

    for line in raw_lines:
        if not line.strip():
            continue
        try:
            result = json.loads(line)
        except Exception:
            failed += 1
            continue

        custom_id = result.get("custom_id", "")
        if not custom_id.startswith(_BATCH_CUSTOM_ID_PREFIX):
            failed += 1
            continue
        try:
            queue_id = int(custom_id[len(_BATCH_CUSTOM_ID_PREFIX):])
        except ValueError:
            failed += 1
            continue

        q_row = conn.execute(
            "SELECT image_id, image_name, camera_id, is_billing_camera, person_count, yolo_conf "
            "FROM onfly_gpt_batch_queue WHERE id=?",
            (queue_id,),
        ).fetchone()
        if q_row is None:
            failed += 1
            continue

        image_id, image_name, camera_id, is_billing, person_count, yolo_conf = q_row

        # Check for error response
        error = result.get("error")
        response = result.get("response", {})
        status_code = int(response.get("status_code", 200))

        if error or status_code >= 400:
            err_msg = str(error or f"HTTP {status_code}")[:500]
            conn.execute(
                "UPDATE onfly_image_state SET gpt_status='failed', gpt_error=?, gpt_version=?, last_run_id=? "
                "WHERE store_id=? AND image_id=?",
                (err_msg, gpt_version, run_id, store_id, image_id),
            )
            conn.execute("UPDATE onfly_gpt_batch_queue SET status='failed', updated_at=? WHERE id=?", (now, queue_id))
            failed += 1
            conn.commit()
            continue

        # Parse walkins from Chat Completions response
        try:
            choices = response.get("body", {}).get("choices", [])
            content_text = choices[0]["message"]["content"]
            parsed = json.loads(content_text)
            raw_walkins = parsed.get("rows", [])
        except Exception as exc:
            conn.execute(
                "UPDATE onfly_image_state SET gpt_status='failed', gpt_error=?, gpt_version=?, last_run_id=? "
                "WHERE store_id=? AND image_id=?",
                (str(exc)[:500], gpt_version, run_id, store_id, image_id),
            )
            failed += 1
            conn.commit()
            continue

        walkins: list[dict[str, str]] = []
        for rw in raw_walkins:
            if isinstance(rw, dict):
                walkins.append({col: str(rw.get(col, "NA") or "NA").strip() for col in _WALKIN_COLUMNS})
        walkins = _apply_staff_rule(walkins)

        customer_count = sum(1 for w in walkins if w.get("Included in Analytics", "").lower() == "yes")
        staff_count = sum(1 for w in walkins if w.get("Role", "").lower() == "staff")
        conversions = sum(
            1 for w in walkins
            if w.get("Conversion Signal", "").lower() == "yes"
            or w.get("Purchase Signal (Bag)", "").lower() == "yes"
        )
        gpt_dict = {"customer_count": customer_count, "staff_count": staff_count,
                    "conversions": conversions, "bounce": 0,
                    "notes": f"{len(walkins)} persons (batch)"}

        # Update image state → gpt_status='done' (same as real-time path)
        conn.execute(
            "UPDATE onfly_image_state SET gpt_version=?, gpt_status='done', "
            "gpt_customer_count=?, gpt_staff_count=?, gpt_conversions=?, gpt_bounce=0, "
            "gpt_result_json=?, gpt_error='', last_run_id=? "
            "WHERE store_id=? AND image_id=?",
            (gpt_version, customer_count, staff_count, conversions,
             json.dumps(gpt_dict, separators=(",", ":")),
             run_id, store_id, image_id),
        )

        # Get image metadata for session writing
        img_row = conn.execute(
            "SELECT date_display, date_source FROM onfly_image_state WHERE store_id=? AND image_id=?",
            (store_id, image_id),
        ).fetchone()
        business_date = ""
        if img_row:
            raw_date = str(img_row[0] or img_row[1] or "").strip()
            business_date = _norm_date(raw_date) if raw_date else ""

        # Parse event_time from filename pattern HH-MM-SS_
        import re as _re
        _m = _re.match(r"^(\d{2})-(\d{2})-(\d{2})_", image_name)
        event_time = f"{_m.group(1)}:{_m.group(2)}:{_m.group(3)}" if _m else ""

        for walkin in walkins:
            role = _norm_role(walkin.get("Role", ""))
            entry_t = str(walkin.get("Entry Time") or "").strip() or event_time
            exit_t = str(walkin.get("Exit Time") or "").strip()
            event_type_raw = str(walkin.get("Event Type") or "").strip().upper()
            # Determine event_type from Role
            if role.lower() == "staff":
                canonical_event = "STAFF"
            elif entry_t:
                canonical_event = "ENTRY"
            else:
                canonical_event = event_type_raw or "UNCLEAR"

            conn.execute(
                """
                INSERT OR IGNORE INTO onfly_walkin_sessions(
                    store_id, run_id, image_id, source_image_name, source_folder_name, camera_id,
                    business_date, date, event_type, event_time, walkin_id, group_id, role,
                    entry_time, exit_time, time_spent_mins, session_status, entry_type,
                    first_seen_time, last_seen_time, match_reason,
                    direction_confidence, match_fingerprint, debug_gpt_event_type,
                    gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                    clothing_style_archetype, engagement_type, engagement_depth,
                    purchase_signal_bag, included_in_analytics
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    store_id, run_id, image_id, image_name, "", camera_id,
                    business_date, business_date,
                    canonical_event, event_time,
                    str(walkin.get("Walk-in ID") or ""), str(walkin.get("Group ID") or ""),
                    role, entry_t, exit_t,
                    str(walkin.get("Time Spent (mins)") or "NA"),
                    str(walkin.get("Session Status") or "OPEN"),
                    str(walkin.get("Entry Type") or ""),
                    entry_t, exit_t or "",
                    "batch_applied",
                    str(walkin.get("Direction Confidence") or ""),
                    str(walkin.get("Match Fingerprint") or ""),
                    event_type_raw,
                    str(walkin.get("Gender") or ""),
                    str(walkin.get("Age Band") or ""),
                    str(walkin.get("Attire / Visual Marker") or "")[:500],
                    str(walkin.get("Primary Clothing") or ""),
                    str(walkin.get("Jewellery Load") or ""),
                    str(walkin.get("Bag Type") or ""),
                    str(walkin.get("Primary Clothing Style Archetype") or ""),
                    str(walkin.get("Engagement Type") or ""),
                    str(walkin.get("Engagement Depth") or ""),
                    _norm_yn(str(walkin.get("Purchase Signal (Bag)") or "No")),
                    _norm_yn(str(walkin.get("Included in Analytics") or "No")),
                ),
            )

        conn.execute("UPDATE onfly_gpt_batch_queue SET status='done', updated_at=? WHERE id=?", (now, queue_id))
        applied += 1
        conn.commit()

    # Mark batch results applied
    conn.execute(
        "UPDATE onfly_gpt_batches SET results_applied=1, updated_at=? WHERE batch_db_id=?",
        (now, batch_db_id),
    )
    conn.commit()

    # Sync to PostgreSQL
    try:
        from iris.onfly_pipeline import _sync_run_to_postgres
        _sync_run_to_postgres(conn, run_id, store_id)
    except Exception:
        pass

    return {"applied": applied, "failed": failed, "batch_db_id": batch_db_id}


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_pending_batches(conn: sqlite3.Connection, store_id: str | None = None) -> list[dict[str, Any]]:
    """List all non-completed batches for a store (or all stores)."""
    if store_id:
        rows = conn.execute(
            "SELECT batch_db_id, store_id, run_id, openai_batch_id, status, image_count, "
            "results_applied, submitted_at, completed_at, error "
            "FROM onfly_gpt_batches WHERE store_id=? "
            "ORDER BY created_at DESC LIMIT 50",
            (store_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT batch_db_id, store_id, run_id, openai_batch_id, status, image_count, "
            "results_applied, submitted_at, completed_at, error "
            "FROM onfly_gpt_batches ORDER BY created_at DESC LIMIT 100",
        ).fetchall()
    cols = ["batch_db_id", "store_id", "run_id", "openai_batch_id", "status",
            "image_count", "results_applied", "submitted_at", "completed_at", "error"]
    return [dict(zip(cols, r)) for r in rows]


def get_batch_queue_count(conn: sqlite3.Connection, store_id: str, run_id: str) -> int:
    """How many images are queued for batch in this run."""
    row = conn.execute(
        "SELECT COUNT(*) FROM onfly_gpt_batch_queue WHERE store_id=? AND run_id=? AND status='pending'",
        (store_id, run_id),
    ).fetchone()
    return int(row[0] if row else 0)

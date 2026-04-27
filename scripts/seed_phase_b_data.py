"""
Phase B data seeder.
Populates onfly_walkin_sessions and pipeline_run_log from real YOLO image state
so the React dashboard has live data without requiring a completed GPT pipeline run.

Run once from repo root:
    python scripts/seed_phase_b_data.py

Safe to re-run — clears only rows inserted by this script (source='seeded').
"""
from __future__ import annotations

import random
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DB = REPO / "data" / "store_registry.db"

random.seed(42)

# ── Realistic persona pool ────────────────────────────────────────────────────
GENDERS      = ["Female", "Male", "Female", "Male", "Female"]           # slight female skew
AGE_BANDS    = ["18-25", "26-35", "36-45", "46-55", "26-35", "18-25"]
STYLES       = ["Traditional", "Contemporary", "Fusion", "Ethnic", "Contemporary"]
ATTIRES      = ["Saree", "Salwar Kameez", "Casual Western", "Formal", "Kurti"]
JEWELLERY    = ["Heavy", "Moderate", "Light", "Minimal", "Moderate"]
BAGS         = ["Handbag", "None", "Tote", "Clutch", "None"]
ENGAGEMENT   = ["Browsing", "Comparing", "Active Touch", "Enquiring", "Browsing"]
DEPTH        = ["Surface", "Moderate", "Deep", "Surface", "Moderate"]
PURCHASE_SIG = ["No Bag", "Bag Sighted", "No Bag", "No Bag", "Bag Sighted"]
STATUSES     = ["closed", "closed", "closed", "partial", "closed"]


def pick(*pool: list) -> str:
    return random.choice(pool[0])


def rand_time(base_hour: int = 11, span: int = 8) -> str:
    h = base_hour + random.randint(0, span)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    return f"{h:02d}:{m:02d}:{s:02d}"


def make_walkin(store_id: str, date: str, idx: int, role: str, run_id: str) -> dict:
    entry = rand_time(10, 9)
    dwell = round(random.uniform(3, 45) if role == "CUSTOMER" else random.uniform(4 * 60, 9 * 60) / 60, 1)
    h, m, s = map(int, entry.split(":"))
    exit_dt = datetime(2000, 1, 1, h, m, s) + timedelta(minutes=dwell)
    exit_t = exit_dt.strftime("%H:%M:%S")

    if role == "CUSTOMER":
        entry_type = "BILLING" if random.random() < 0.42 else "BROWSE"
        gender = pick(GENDERS)
        age_band = pick(AGE_BANDS)
        style = pick(STYLES)
        attire = pick(ATTIRES)
        jwl = pick(JEWELLERY)
        bag_type = pick(BAGS)
        engagement = pick(ENGAGEMENT)
        depth = pick(DEPTH)
        purchase_sig = "Bag Sighted" if entry_type == "BILLING" else pick(PURCHASE_SIG)
    else:
        entry_type = "STAFF_ENTRY"
        gender = pick(["Female", "Male"])
        age_band = "26-35"
        style = "Uniform"
        attire = "Store Uniform"
        jwl = "Minimal"
        bag_type = "None"
        engagement = "Service"
        depth = "N/A"
        purchase_sig = "N/A"

    return {
        "store_id": store_id,
        "run_id": run_id,
        "image_id": f"{store_id}_{date}_{idx:04d}",
        "date": date,
        "walkin_id": f"W-{store_id[:3]}-{date.replace('-','')}-{idx:04d}",
        "group_id": f"G-{idx // 3:04d}",
        "role": role,
        "entry_time": entry,
        "exit_time": exit_t,
        "time_spent_mins": str(dwell),
        "session_status": pick(STATUSES),
        "entry_type": entry_type,
        "gender": gender,
        "age_band": age_band,
        "attire_visual_marker": attire,
        "primary_clothing": attire,
        "jewellery_load": jwl,
        "bag_type": bag_type,
        "clothing_style_archetype": style,
        "engagement_type": engagement,
        "engagement_depth": depth,
        "purchase_signal_bag": purchase_sig,
        "included_in_analytics": "yes" if role == "CUSTOMER" else "no",
        "source_image_name": f"img_{idx:04d}.jpg",
        "source_folder_name": date,
        "camera_id": f"D{random.randint(1,20):02d}",
        "business_date": date,
        "event_type": "ENTRY",
        "event_time": entry,
        "first_seen_time": entry,
        "last_seen_time": exit_t,
        "matched_session_id": "",
        "match_score": 0.0,
        "match_reason": "seeded",
        "direction_confidence": "HIGH",
        "match_fingerprint": str(uuid.uuid4())[:8],
        "debug_parsed_time": entry,
        "debug_gpt_event_type": role,
        "created_at": f"{date}T{entry}+00:00",
    }


def seed_walkins(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM onfly_walkin_sessions WHERE match_reason='seeded'")

    # Get real YOLO data grouped by store + date
    rows = conn.execute("""
        SELECT store_id, date_source, date_display,
               SUM(CAST(person_count AS INTEGER)) as total_persons
        FROM onfly_image_state
        WHERE yolo_status='done' AND yolo_relevant=1
              AND date_source != ''
        GROUP BY store_id, date_source
        HAVING total_persons > 0
        ORDER BY store_id, date_source
    """).fetchall()

    inserted = 0
    for row in rows:
        store_id = row["store_id"]
        date = row["date_source"]
        n_persons = min(int(row["total_persons"]), 60)  # cap per date to keep seed fast

        # Derive a run_id from the pipeline runs table
        run = conn.execute(
            "SELECT run_id FROM onfly_pipeline_runs WHERE store_id=? AND business_date LIKE ? LIMIT 1",
            (store_id, f"%{date}%")
        ).fetchone()
        run_id = run["run_id"] if run else f"{store_id}_{date.replace('-','')}_seeded"

        # ~72% customers, ~28% staff
        n_staff = max(1, round(n_persons * 0.28))
        n_customers = n_persons - n_staff

        sessions = []
        for i in range(n_customers):
            sessions.append(make_walkin(store_id, date, inserted + i, "CUSTOMER", run_id))
        for i in range(n_staff):
            sessions.append(make_walkin(store_id, date, inserted + n_customers + i, "STAFF", run_id))

        random.shuffle(sessions)
        for s in sessions:
            cols = ", ".join(s.keys())
            placeholders = ", ".join("?" for _ in s)
            conn.execute(
                f"INSERT OR IGNORE INTO onfly_walkin_sessions ({cols}) VALUES ({placeholders})",
                list(s.values())
            )
        inserted += len(sessions)

    conn.commit()
    return inserted


def seed_pipeline_log(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM pipeline_run_log WHERE triggered_by='seeded'")

    runs = conn.execute("""
        SELECT run_id, store_id, status, current_stage,
               images_relevant, gpt_success_count, started_at, ended_at,
               error_message, retry_status
        FROM onfly_pipeline_runs
        ORDER BY started_at DESC
        LIMIT 30
    """).fetchall()

    inserted = 0
    for r in runs:
        status_map = {"partial": "done", "running": "done", "done": "done", "failed": "failed"}
        status = status_map.get(r["status"], "done")

        relevant = int(r["images_relevant"] or 0)
        gpt_done = int(r["gpt_success_count"] or 0)
        remarks = f"{relevant} relevant images, {gpt_done} GPT processed"
        if r["retry_status"]:
            remarks += f" | {r['retry_status']}"

        conn.execute("""
            INSERT OR IGNORE INTO pipeline_run_log
              (run_id, job_key, job_name, store_id, status, remarks,
               triggered_by, started_at, completed_at, result_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            r["run_id"],
            "yolo_scan",
            "Run YOLO Relevance Scan",
            r["store_id"],
            status,
            remarks,
            "seeded",
            r["started_at"] or "",
            r["ended_at"] or "",
            "{}",
            r["started_at"] or "",
        ))
        inserted += 1

    conn.commit()
    return inserted


def main() -> None:
    conn = sqlite3.connect(str(DB), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")

    print(f"DB: {DB}")
    n_walkins = seed_walkins(conn)
    print(f"Seeded {n_walkins} walkin sessions into onfly_walkin_sessions")

    n_runs = seed_pipeline_log(conn)
    print(f"Seeded {n_runs} runs into pipeline_run_log")

    # Verify
    c_w = conn.execute("SELECT COUNT(*) FROM onfly_walkin_sessions").fetchone()[0]
    c_r = conn.execute("SELECT COUNT(*) FROM pipeline_run_log").fetchone()[0]
    print(f"Verification: walkin_sessions={c_w}, pipeline_run_log={c_r}")
    conn.close()


if __name__ == "__main__":
    main()

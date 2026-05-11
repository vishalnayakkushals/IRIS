"""
Test GPT Result Caching by Image Hash
Runs two checks:
  1. Real-data scan: how many duplicate hashes already exist in iris.db
  2. Functional test: inserts test rows into a temp DB and verifies the cache path works end-to-end
"""
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

# ── Check 1: Real data scan ───────────────────────────────────────────────────
DB = Path("data/store_registry.db")
if not DB.exists():
    print("SKIP real-data scan: data/iris.db not found")
else:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    dups = conn.execute("""
        SELECT content_hash, COUNT(*) AS cnt,
               SUM(CASE WHEN gpt_status='done' THEN 1 ELSE 0 END) AS done_count,
               SUM(CASE WHEN gpt_status='cached_from_hash' THEN 1 ELSE 0 END) AS cached_count,
               GROUP_CONCAT(gpt_status, ', ') AS statuses
        FROM onfly_image_state
        WHERE content_hash IS NOT NULL AND content_hash != ''
        GROUP BY content_hash
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 30
    """).fetchall()

    total_done    = conn.execute("SELECT COUNT(*) FROM onfly_image_state WHERE gpt_status='done'").fetchone()[0]
    total_cached  = conn.execute("SELECT COUNT(*) FROM onfly_image_state WHERE gpt_status='cached_from_hash'").fetchone()[0]
    total_all     = conn.execute("SELECT COUNT(*) FROM onfly_image_state").fetchone()[0]

    # Pairs that WOULD have been cache hits (one done, one not done)
    would_cache = conn.execute("""
        SELECT COUNT(*) FROM onfly_image_state a
        WHERE a.content_hash != ''
          AND a.gpt_status != 'done'
          AND EXISTS (
              SELECT 1 FROM onfly_image_state b
              WHERE b.store_id = a.store_id
                AND b.content_hash = a.content_hash
                AND b.image_id != a.image_id
                AND b.gpt_status = 'done'
          )
    """).fetchone()[0]

    conn.close()

    print("=" * 60)
    print("REAL DATA SCAN — data/iris.db")
    print("=" * 60)
    print(f"  Total images:              {total_all}")
    print(f"  GPT done:                  {total_done}")
    print(f"  Already cached_from_hash:  {total_cached}")
    print(f"  Duplicate hash groups:     {len(dups)}")
    print(f"  Would-be cache hits*:      {would_cache}  (* images that have a done twin)")
    if total_done > 0:
        pct = round(would_cache / total_done * 100, 1)
        print(f"  Effective cache rate:      {pct}% of GPT calls saveable")
    if dups:
        print()
        print("  Top duplicate groups:")
        for r in dups[:10]:
            print(f"    hash={r['content_hash'][:14]}... count={r['cnt']}  done={r['done_count']}  statuses=[{r['statuses']}]")
    print()

# ── Check 2: Functional test in temp DB ──────────────────────────────────────
print("=" * 60)
print("FUNCTIONAL TEST — temp DB")
print("=" * 60)

# Bootstrap the pipeline's init_onfly_tables in the temp DB
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from iris.onfly_pipeline import init_onfly_tables

with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "test.db"
    init_onfly_tables(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    STORE = "TEST_STORE"
    HASH  = hashlib.sha256(b"fake image bytes for test").hexdigest()
    NOW   = "2026-05-11T10:00:00"

    # Insert a "fully processed" original image
    conn.execute("""
        INSERT INTO onfly_image_state(
            store_id, image_id, source_provider, source_uri, source_item_id,
            source_url, image_name, relative_path, date_source, date_display,
            camera_id, timestamp_hint, discovered_at, last_seen_at,
            pipeline_version, yolo_version, gpt_version,
            content_hash, yolo_status, yolo_relevant, person_count, yolo_conf, yolo_error,
            gpt_status, gpt_customer_count, gpt_staff_count, gpt_conversions, gpt_bounce,
            gpt_result_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        STORE, "ORIG_IMAGE_001", "gdrive", "gdrive://folder", "drive_file_id_001",
        "https://drive.google.com/orig", "IMG_D01-10-00-00.jpg", "2026/05/11",
        "2026-05-11", "2026-05-11", "D01", "2026-05-11 10:00:00",
        NOW, NOW, "v1", "yolo_v1", "gpt_v1",
        HASH, "done", 1, 3, 0.87, "",
        "done", 2, 1, 1, 0,
        '{"customer_count":2,"staff_count":1,"conversions":1,"bounce":0,"notes":"test"}'
    ))

    # Insert walkin sessions for the original image
    for i in range(3):
        conn.execute("""
            INSERT INTO onfly_walkin_sessions(
                store_id, run_id, image_id, source_image_name, source_folder_name, camera_id,
                business_date, date, event_type, event_time, walkin_id, group_id, role,
                entry_time, exit_time, time_spent_mins, session_status, entry_type,
                first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            STORE, "RUN_001", "ORIG_IMAGE_001", "IMG_D01-10-00-00.jpg", "2026-05-11", "D01",
            "2026-05-11", "2026-05-11", "ENTRY", "10:00:00",
            f"W{i+1:02d}", "G01", "Customer" if i < 2 else "Staff",
            "10:00:00", "NA", "NA", "OPEN", "ENTRY",
            "10:00:00", "10:00:00", "", 0.0, "new_entry",
            "High", f"FP{i+1}", "10:00:00", "ENTRY",
            "Female", "25 - 34", "Blue saree", "Saree", "Minimal", "None",
            "Ethnic", "Browsing", "Medium", "No", "Yes" if i < 2 else "No",
        ))
    conn.commit()

    # Now simulate: new image arrives with SAME hash but DIFFERENT image_id
    NEW_IMAGE_ID = "DUPLICATE_IMAGE_002"
    conn.execute("""
        INSERT INTO onfly_image_state(
            store_id, image_id, source_provider, source_uri, source_item_id,
            source_url, image_name, relative_path, date_source, date_display,
            camera_id, timestamp_hint, discovered_at, last_seen_at, pipeline_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        STORE, NEW_IMAGE_ID, "gdrive", "gdrive://folder", "drive_file_id_002",
        "https://drive.google.com/dup", "IMG_D01-10-00-00_copy.jpg", "2026/05/11",
        "2026-05-11", "2026-05-11", "D01", "2026-05-11 10:00:00",
        NOW, NOW, "v1",
    ))
    conn.commit()

    # Run the exact cache-lookup query from the pipeline
    cached_row = conn.execute("""
        SELECT src.image_id AS src_image_id, src.yolo_relevant, src.person_count, src.yolo_conf, src.yolo_error,
               src.gpt_version, src.gpt_customer_count, src.gpt_staff_count, src.gpt_conversions, src.gpt_bounce, src.gpt_result_json
        FROM onfly_image_state src
        WHERE src.store_id=? AND src.content_hash=? AND src.image_id!=?
          AND src.gpt_status='done'
        LIMIT 1
    """, (STORE, HASH, NEW_IMAGE_ID)).fetchone()

    if cached_row is None:
        print("  FAIL: cache lookup returned None — hash not found")
        sys.exit(1)

    print(f"  Cache lookup:              PASS (found src={cached_row['src_image_id']})")
    print(f"  GPT customers in cache:    {cached_row['gpt_customer_count']}")
    print(f"  YOLO person count:         {cached_row['person_count']}")

    # Apply the UPDATE (same as pipeline)
    RUN_ID = "TEST_RUN_002"
    conn.execute("""
        UPDATE onfly_image_state SET content_hash=?, pipeline_version=?,
          yolo_version=?, yolo_status='done', yolo_relevant=?, person_count=?, yolo_conf=?, yolo_error=?,
          gpt_version=?, gpt_status='cached_from_hash',
          gpt_customer_count=?, gpt_staff_count=?, gpt_conversions=?, gpt_bounce=?, gpt_result_json=?,
          last_run_id=? WHERE store_id=? AND image_id=?
    """, (
        HASH, "v1",
        "yolo_v1", int(cached_row["yolo_relevant"] or 0),
        int(cached_row["person_count"] or 0), float(cached_row["yolo_conf"] or 0.0),
        str(cached_row["yolo_error"] or ""),
        str(cached_row["gpt_version"] or "gpt_v1"),
        int(cached_row["gpt_customer_count"] or 0), int(cached_row["gpt_staff_count"] or 0),
        int(cached_row["gpt_conversions"] or 0), int(cached_row["gpt_bounce"] or 0),
        str(cached_row["gpt_result_json"] or "{}"),
        RUN_ID, STORE, NEW_IMAGE_ID,
    ))

    # Apply the walkin copy INSERT...SELECT (same as pipeline)
    conn.execute("""
        INSERT OR IGNORE INTO onfly_walkin_sessions(
          store_id, run_id, image_id, source_image_name, source_folder_name, camera_id,
          business_date, date, event_type, event_time, walkin_id, group_id, role,
          entry_time, exit_time, time_spent_mins, session_status, entry_type,
          first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
          direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
          gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
          clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
        ) SELECT
          store_id, ?, ?, ?, source_folder_name, camera_id,
          business_date, date, event_type, event_time, walkin_id, group_id, role,
          entry_time, exit_time, time_spent_mins, session_status, entry_type,
          first_seen_time, last_seen_time, matched_session_id, match_score, 'cached_from_hash:' || match_reason,
          direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
          gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
          clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
        FROM onfly_walkin_sessions WHERE store_id=? AND image_id=?
    """, (RUN_ID, NEW_IMAGE_ID, "IMG_D01-10-00-00_copy.jpg", STORE, str(cached_row["src_image_id"])))
    conn.commit()

    # Verify results
    result = conn.execute(
        "SELECT gpt_status, gpt_customer_count, gpt_staff_count, content_hash FROM onfly_image_state WHERE image_id=?",
        (NEW_IMAGE_ID,)
    ).fetchone()

    copied_sessions = conn.execute(
        "SELECT COUNT(*) FROM onfly_walkin_sessions WHERE image_id=? AND match_reason LIKE 'cached_from_hash:%'",
        (NEW_IMAGE_ID,)
    ).fetchone()[0]

    orig_sessions = conn.execute(
        "SELECT COUNT(*) FROM onfly_walkin_sessions WHERE image_id=?",
        ("ORIG_IMAGE_001",)
    ).fetchone()[0]

    print()
    print("  After cache apply:")
    print(f"    gpt_status:              {result['gpt_status']}")
    print(f"    gpt_customer_count:      {result['gpt_customer_count']}")
    print(f"    gpt_staff_count:         {result['gpt_staff_count']}")
    print(f"    content_hash matches:    {result['content_hash'] == HASH}")
    print(f"    Original walkin rows:    {orig_sessions}")
    print(f"    Copied walkin rows:      {copied_sessions}")

    ok = (
        result["gpt_status"] == "cached_from_hash"
        and result["gpt_customer_count"] == 2
        and result["gpt_staff_count"] == 1
        and result["content_hash"] == HASH
        and copied_sessions == orig_sessions
    )
    print()
    print(f"  OVERALL: {'PASS' if ok else 'FAIL'}")
    conn.close()

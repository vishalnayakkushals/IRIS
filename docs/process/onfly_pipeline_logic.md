# On-Fly Pipeline Logic (Source of Truth)

This document is the canonical logic reference for IRIS on-fly processing.
Update this file whenever on-fly behavior changes.

## Pipeline Stages

### Step 1 - `LIST`
- Input source can be:
  - Google Drive URL
  - Google Drive folder id
  - Local path
- The scanner discovers `.jpg`, `.jpeg`, `.png`.
- Derives metadata:
  - `folder_name` (date bucket source)
  - `camera_id` (from filename, e.g. `D07`)
  - `timestamp_hint` (from filename, e.g. `12-17-32`)

### Step 2 - `SKIP_CHECK` (Delta / Idempotent)
- Uses `onfly_image_state` in `store_registry.db`.
- Version-aware skip:
  - YOLO uses `yolo_version`
  - GPT uses `gpt_version`
  - fallback compatibility uses `pipeline_version` for legacy rows
- If YOLO version is unchanged and YOLO already done, YOLO is skipped.
- If GPT version changed (and image is relevant), only GPT re-runs.
- Only new or version-changed images continue.

### Step 3 - `DOWNLOAD` (Memory Only)
- Fetches bytes from source.
- Keeps bytes in memory cache.
- No permanent image write at this stage.
- SHA-256 is computed for exact duplicate reuse.

### Step 4 - `YOLO`
- Runs person detection.
- Outputs:
  - `person_count`
  - `yolo_conf`
  - `yolo_error` (if any)
  - person boxes used by downstream smart sampling
- Relevance rule:
  - `person_count > 0` => relevant
- Persists in `onfly_image_state`:
  - `yolo_status`
  - `yolo_relevant`

### Step 5 - `SMART_FRAME_SAMPLING`
- Runs only after YOLO on relevant frames.
- Consecutive frames from the same camera/date are compared using YOLO person-box signature and timing proximity.
- The first anchor frame goes to GPT.
- Similar follow-up frames are marked:
  - `gpt_status='sampled_wait_anchor'`
  - `sampled_anchor_image_id`
  - `sampled_signature`
  - `sampled_skip_reason`
- After the anchor GPT result is known, sampled frames inherit the resolved session output.

### Step 6 - `GPT`
- Runs only for relevant anchor frames (when GPT enabled).
- Input image is base64 in memory (not persisted as raw image blobs).
- GPT decides semantics:
  - role/event understanding (`ENTRY`, `EXIT`, `INSIDE_ACTIVE`, etc.)
  - customer/staff/banner/pedestrian context
- **Time source-of-truth is filename timestamp parsing**:
  - `entry_time` / `exit_time` are assigned from parsed image time, not GPT free-text clock.
- If GPT quota is unavailable:
  - YOLO must continue
  - GPT work moves to retry state instead of repeatedly burning API calls.

### Step 7 - `REPORT_WRITER`
- Writes canonical store files:
  - `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv`
  - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv`
  - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions_audit.csv`
- Writes shared summary:
  - `data/exports/current/onfly/onfly_store_date_report.csv`
- Writes per-run summary:
  - `data/exports/current/onfly/onfly_run_summary_<run_id>.json`
  - `data/exports/current/onfly/<STORE_ID>/onfly_process_timings.csv`
- Writes cost proof rows into:
  - `onfly_cost_metrics`

### Step 8 - `DASHBOARD_INGEST`
- Updates on-fly report index tables for UI/report discovery.
- Pipeline journey is recorded in:
  - `onfly_pipeline_runs`
  - `onfly_pipeline_run_events`

## Session Logic (Current)

- GPT classifies event semantics.
- Session state transitions:
  - `ENTRY` -> `OPEN`
  - `INSIDE_ACTIVE` / `INSIDE_PURCHASING` -> update open session or create `INFERRED_INSIDE_OPEN`
  - `EXIT` -> close best matching open session (`CLOSED`) else `UNMATCHED_EXIT`
- End-of-day closeout:
  - remaining open sessions -> `CLOSED_EOD`

## Staff Override Rule (Current)

- Red shirt + black pant/trouser store-staff pattern is forced to staff in post-processing.
- White shirt + black pant/trouser manager pattern is forced to staff in post-processing.

## Runtime Model (Current)

IRIS now uses:
- FastAPI web process
- dedicated core scheduler worker
- dedicated on-fly scheduler worker
- dedicated store auto-sync worker

The web server does not own long-running scheduler loops.

## Update Discipline

Whenever pipeline logic changes, update:
1. `docs/process/onfly_pipeline_logic.md` (this file)
2. `CHANGE_LEDGER.md` (touched files + behavior summary)
3. `docs/AI_HANDOVER_STORAGE.md` if runtime/cost behavior changes

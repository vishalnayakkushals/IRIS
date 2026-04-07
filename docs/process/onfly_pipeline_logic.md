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

### Step 4 - `YOLO`
- Runs person detection.
- Outputs:
  - `person_count`
  - `yolo_conf`
  - `yolo_error` (if any)
- Relevance rule:
  - `person_count > 0` => relevant
- Persists in `onfly_image_state`:
  - `yolo_status`
  - `yolo_relevant`

### Step 5 - `GPT`
- Runs only for relevant images (when GPT enabled).
- Input image is base64 in memory (not persisted as image blobs).
- GPT decides semantics:
  - role/event understanding (`ENTRY`, `EXIT`, `INSIDE_ACTIVE`, etc.)
  - customer/staff/banner/pedestrian context
- **Time source-of-truth is filename timestamp parsing**:
  - `entry_time` / `exit_time` are assigned from parsed image time, not GPT free-text clock.

### Step 6 - `REPORT_WRITER`
- Writes canonical store files:
  - `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv`
  - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv`
- Writes shared summary:
  - `data/exports/current/onfly/onfly_store_date_report.csv`
- `data/exports/current/onfly/onfly_run_summary_<run_id>.json`
- `data/exports/current/onfly/<STORE_ID>/onfly_process_timings.csv` (per-run timing dataset)

### Step 7 - `DASHBOARD_INGEST`
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

## Output Notes

- `onfly_image_results.csv` = one row per image (YOLO + GPT aggregates)
- `onfly_walkin_sessions.csv` = one row per person/session event
- `onfly_walkin_sessions_audit.csv` = full person/session event with debug/audit columns
- `onfly_store_date_report.csv` = store/date totals

## Update Discipline

Whenever pipeline logic changes, update:
1. `docs/process/onfly_pipeline_logic.md` (this file)
2. `CHANGE_LEDGER.md` (touched files + behavior summary)

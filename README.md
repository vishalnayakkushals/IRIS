# IRIS

IRIS is an anonymous retail intelligence platform for low-frame-rate camera snapshots with privacy-first defaults.

## MVP Context

- Scale target: 6 stores, 2 cameras per store.
- Ingest: timestamped snapshots (1 image/sec/camera).
- Privacy: no face recognition, no identity persistence.
- Analytics targets: footfall, dwell, bounce, hotspots, loss-of-sale alerts.

Reference assets:
- `docs/mvp-blueprint.md`
- `contracts/openapi.yaml`
- `contracts/schemas/store-config.schema.json`
- `contracts/schemas/event-envelope.schema.json`
- `docs/process/system-foundations.md`
- `docs/planning/project-delivery-plan.md`
- `docs/actionable-review-checklist.md`
- `docs/planning/execution-status.md`
- `docs/operations/cloud-deployment.md`
- `docs/operations/deployment-runbook.md`
- `docs/operations/github-walkthrough-for-beginners.md`
- `docs/templates/brd-template.md`
- `docs/business/iris-brd.md`
- `docs/business/management-process-diagram.md`
- `docs/templates/prd-template.md`
- `docs/developer/developer-doc.md`
- `docs/developer/data-flow-architecture.md`
- `docs/prd/iris-platform-prd-v1.md`

## Implemented App (Current)

This repository now includes a working store-level analysis app with:
- Person-detection-based customer insights.
- Camera hotspot ranking per store.
- Data quality reporting.
- CSV exports for all stores and per store.
- Store/email mapping for access control.
- Employee image registry per store.
- Google Drive folder link and sync per store.

## Project Structure

```text
IRIS/
  contracts/
  docs/
  ideas/
  release-notes/
  tests/
  data/
    stores/                 # one folder per store with snapshots
    exports/current/        # latest analysis CSV output
    exports/day1/           # day-1 run snapshots (optional)
    employee_assets/        # uploaded employee images
    store_registry.db       # sqlite store/email/drive mapping
  scripts/
    analyze_stores.py
    snapshot_summary.py
    run_async_worker.py
    build_training_dataset.py
    daily_retrain.py
  src/
    iris/
      iris_dashboard.py
      iris_analysis.py
      store_registry.py
  requirements.txt
  environment.yml
```

## Folder Contract

Expected store layout:

```text
data/stores/
  store_001/
    HH-MM-SS_DXX-N.jpg
  store_002/
    HH-MM-SS_DXX-N.jpg
```

Example filename: `09-57-27_D02-1.jpg`

Compatibility mode:
- If there are no store subfolders and images are directly in root, root is treated as one store.

## Setup

```powershell
python -m pip install -r requirements.txt
```

Create local environment file (do not commit secrets):

```powershell
Copy-Item .env.example .env
```

SOP checklist status for this repo:
- `docs/process/b2b_projects_sop_status.md`

## Optional CTO Performance Observer (Isolated)

- Path: `CTO/`
- Main log: `CTO/logs/perf_events.jsonl`
- Analyzer output:
  - `CTO/reports/latest_perf_report.md`
  - `CTO/reports/perf_regression_report.csv`

Run one cycle with probes:

```powershell
python CTO/scripts/perf_cycle.py --note "post-fix check" --url "http://localhost:8765/?module=Reports" --url "http://localhost:8765/?module=Access&section=Config"
python CTO/scripts/perf_analyze.py
```

Optional continuous watch (Ctrl+C to stop):

```powershell
python CTO/scripts/perf_watch.py --note "browse-watch" --interval-seconds 30 --url "http://localhost:8765/?module=Reports"
```

## Run Batch Analysis

```powershell
python scripts/analyze_stores.py --conf 0.25 --detector yolo --time-bucket 1 --gzip-exports
```

Fast first-pass (first 20 images per store, blank/unreadable frames ignored):

```powershell
python scripts/analyze_stores.py --detector mock --max-images-per-store 20
```

CSV outputs:
- `data/exports/current/all_stores_summary.csv`
- `data/exports/current/store_<store_id>_image_insights.csv`
- `data/exports/current/store_<store_id>_camera_hotspots.csv`

## Run Dashboard

```powershell
streamlit run src/run_dashboard.py --server.port 8765
```

Dashboard tabs:
- `Overview`
- `Store Detail`
- `Quality`
- `Store Admin`

Frame Review terminology (UI labels):
- `PEDESTRIANS` (display name for legacy `OUTSIDE_PASSER`)
- `BANNER` (display name for legacy `POSTER_BANNER`)

## Store Admin Capabilities

From `Store Admin`:
- Add/update stores: `store_id`, `store_name`, `email`, `drive_folder_url`
- Maintain one email -> one store mapping
- Upload employee images per store
- Sync snapshots from linked Google Drive folders

Google Drive sync modes:
- If `GOOGLE_API_KEY` is set, app uses Google Drive API recursive sync (recommended for large folders).
- If not set, app falls back to `gdown` folder sync (can be limited for very large folders).

Sidebar:
- `Access Email (optional)` filters dashboard view to mapped store
- `Auto-sync linked drives before analysis` syncs data points before run

## Automated Daily Drive Sync (6 AM)

Use the new scheduler for fully automated extraction that is independent of your local terminal session.

Behavior:
- First run: full backfill of all images in the mapped Drive folder.
- Next runs: delta sync mode (latest date-folder only when date folders exist).
- Only missing files are downloaded (existing local files are reused).
- Deleted Drive files are marked inactive in sync index (optionally can be physically removed).
- Multi-queue parallel downloader is used for faster extraction.

Run once:

```powershell
python scripts/drive_delta_sync_scheduler.py --store-id BLRJAY --run-once --workers 8
```

Run daily at 6 AM (Asia/Kolkata):

```powershell
python scripts/drive_delta_sync_scheduler.py --store-id BLRJAY --run-at 06:00 --tz Asia/Kolkata --workers 8
```

Docker service (always-on scheduler):
- `deploy/docker-compose.yml` now includes `iris-sync`.
- Configure env vars:
  - `GOOGLE_API_KEY`
  - `IRIS_SYNC_STORE_ID` (default `BLRJAY`)
  - `IRIS_SYNC_RUN_AT` (default `06:00`)
  - `IRIS_SYNC_TZ` (default `Asia/Kolkata`)
  - `IRIS_SYNC_WORKERS` (default `6`)

Throughput benchmark helper:

```powershell
python scripts/benchmark_drive_sync.py --drive-folder-url "https://drive.google.com/drive/folders/<folder_id>" --sample-size 300 --workers 8
```

## Test-Folder GPT Post-Relevance Flow (YOLO -> GPT)

Use this when you want GPT-only intelligence after YOLO relevance filtering for `TEST_STORE_D07`:

1. Stage-1 YOLO relevant-image scan (no BLRJAY full GPT rollup):
```powershell
run_iris.bat stage1-scan-now
```

2. GPT post-relevance validation run (default top 30 relevant images):
```powershell
run_iris.bat gpt-test-validation-now
```

Outputs:
- `data/exports/current/gpt_validation/TEST_STORE_D07/gpt_validation_results.csv`
- `data/exports/current/gpt_validation/TEST_STORE_D07/gpt_validation_frame_summary.csv`
- `data/exports/current/gpt_validation/TEST_STORE_D07/gpt_store_date_summary.csv`
- `data/exports/current/gpt_validation/TEST_STORE_D07/yolo_vs_gpt_accuracy.csv`
- `data/exports/current/gpt_validation/TEST_STORE_D07/gpt_vs_reviewer_accuracy.csv`
- `data/exports/current/gpt_validation/TEST_STORE_D07/annotated/`

Dashboard:
- `Reports > Report Module > GPT Validation Results (Test Folder)`
- `Reports > Report Module > GPT Store-Date Summary (Test Folder)`
- `Reports > Report Module > YOLO vs GPT Accuracy (Test Folder)`
- `Reports > Report Module > GPT vs Reviewer Accuracy (Test Folder)`

## Detector Notes

- Default detector: YOLOv8n via `ultralytics` (CPU mode), stored at `data/models/yolov8n.pt`.
- If detector is unavailable, pipeline continues and records `detection_error`.
- Use `--detector mock` for deterministic local testing.
- Docker default (`IRIS_ENABLE_YOLO=0`) is lightweight and does not install YOLO deps.
- Enable YOLO in Docker by setting `IRIS_ENABLE_YOLO=1` before build.

What these mean:
- **YOLO**: real object detector model (higher accuracy, more compute).
- **MOCK**: deterministic simulated detector for testing and low-resource fallback (fast, not real-world accurate).

## Hotstar-like speed roadmap implemented (practical MVP steps)

### Step 1: Queue + async worker
- Added event queue abstraction (`src/iris/event_queue.py`).
- Added async worker runner (`scripts/run_async_worker.py`) that consumes frame events and runs analysis/export.
- Added event producer (`scripts/enqueue_store_frames.py`) to queue first N valid frames per store.

### Step 2: Training dataset + daily retrain
- Added dataset writer (`scripts/build_training_dataset.py`) from exports.
- Added daily retrain/calibration job (`scripts/daily_retrain.py`) that writes model metrics + artifact.

### Step 3: Model registry + rollback
- Added model registry table and helpers in store registry DB.
- Added auto rollback rule using error-rate threshold.

## Daily walk-in + conversion report

- Store detail now includes a daily report with:
  - unique individuals,
  - unique groups,
  - actual customers (= unique individuals + unique groups),
  - actual conversions,
  - conversion rate.
- Conversion is currently based on BILLING camera-role evidence ("red box" equivalent in MVP config).


## Server Deployment Readiness (Low-Space Mode)

Implemented optimizations for server-grade, low-storage runtime:
- Employee uploads are normalized/compressed to optimized JPEG.
- Drive-synced store images are auto-optimized in-place after sync.
- Analysis exports can be written as `.csv.gz` to reduce disk usage.
- Dashboard supports compressed export toggles (`Write compressed CSV`, `Keep plain CSV`).

Recommended production defaults:
- Enable compressed exports.
- Disable plain CSV once downstream consumers read `.csv.gz`.
- Keep detector as `mock` for low-CPU fallback environments.

CLI for compressed-only exports:

```powershell
python scripts/analyze_stores.py --root data/stores --out data/exports/current --detector yolo --gzip-exports --drop-plain-csv
```

## Stack Direction (React + NodeJS + SQL)

Your target stack is correct for production hardening:
- **Frontend**: React (dashboard UI)
- **Backend**: NodeJS (API/auth/jobs/webhooks)
- **DB**: SQL (PostgreSQL recommended)

What to change next (without breaking current app):
1. Keep current Python analysis engine as a worker service.
2. Introduce NodeJS API as orchestration layer (store mapping, auth, job triggers).
3. Move registry from SQLite to PostgreSQL for multi-instance concurrency.
4. Keep React UI as the long-term replacement for Streamlit while preserving current analytics contracts.


Set API key for reliable full-folder sync (server env):

```bash
export GOOGLE_API_KEY="<your_key>"
```


## Run in Docker

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

Open: `http://localhost:8765`

To enable YOLO dependencies in Docker:

```bash
export IRIS_ENABLE_YOLO=1
docker compose -f deploy/docker-compose.yml up --build -d
```


## Why `requirements.txt` and `environment.yml` are in root

These two files are intentionally kept at the project root (standard practice):

- `requirements.txt`: pip install source for local/dev/CI/container builds.
- `environment.yml`: Conda environment definition for teams using Conda.

Many tools (Docker, CI runners, IDEs, pip/conda commands) expect these files at root by default.
Keeping them in a nested folder usually adds unnecessary path complexity.

### If Docker build says `requirements.txt` not found
Use the latest `deploy/docker-compose.yml` from repo. It must contain:

- `build.context: ..`
- `build.dockerfile: deploy/Dockerfile`

Then rerun:

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```


### Why Docker downloads dependencies again and again
This usually happens because:

- You run `docker compose ... build --no-cache` (forces full reinstall every time).
- `requirements.txt` changed (invalidates dependency layer).
- First install includes very large ML wheels (`ultralytics` -> `torch`), so initial build is big.

Use normal incremental builds after first success:

```bash
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

Use `--no-cache` only for hard reset/debug builds.

### If `docker compose build` + `up -d` does not pick your latest code
Use a hard refresh once:

```bash
git pull origin main
docker compose -f deploy/docker-compose.yml down
docker image rm deploy-iris:latest || true
docker compose -f deploy/docker-compose.yml up --build --force-recreate -d
docker compose -f deploy/docker-compose.yml logs -f iris
```

If logs still show:

```text
from .iris_analysis import ...
```

your container is running an older image (before the import fix). Pull latest `main` and rebuild with `--force-recreate`.

## One-Command Local Refresh Automation (PowerShell)

Run this helper to automate pull + refresh + readiness checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/refresh_and_check.ps1 -Mode rebuild
```

Fast mode (no rebuild):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/refresh_and_check.ps1 -Mode restart
```

Windows shortcut wrapper (`.bat`):

```bat
run_iris.bat
```

Optional modes:

```bat
run_iris.bat restart
run_iris.bat rebuild
run_iris.bat restart --skip-pull
```


## On-The-Fly Vision Pipeline (Lightweight)

IRIS now supports a lightweight URL-first pipeline for evaluation and staged production rollout:

1. `LIST`: source ingestion from URL/path (`Google Drive` today, `S3` adapter path reserved)
2. `SKIP_CHECK`: idempotent/delta check in SQLite (`onfly_image_state`)
3. `DOWNLOAD`: in-memory image fetch
4. `YOLO`: person relevance filter
5. `GPT`: semantic analysis only for relevant images (optional toggle)
6. `REPORT_WRITER`: canonical CSV/JSON artifacts
7. `DASHBOARD_INGEST`: report index updates for UI visibility

Important:
- GPT decides semantic event type/role, while timestamp assignment is canonicalized from filename parsing for session times.
- Detailed and always-current logic lives in:
  - `docs/process/onfly_pipeline_logic.md`

Key artifacts:
- `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv`
- `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv`
- `data/exports/current/onfly/onfly_store_date_report.csv`
- `data/exports/current/onfly/onfly_run_summary_<run_id>.json`

Quick run (container):
- `run_iris.bat onfly-run-now`
- `run_iris.bat onfly-benchmark`
- `run_iris.bat onfly-scheduler-start`

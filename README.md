# IRIS

IRIS is an anonymous retail intelligence platform for low-frame-rate camera snapshots with privacy-first defaults.

## MVP Context

- Scale target: 6 stores, 2 cameras per store.
- Ingest: timestamped snapshots (1 image/sec/camera).
- Privacy: no face recognition, no identity persistence.
- Analytics targets: footfall, dwell, bounce, hotspots, loss-of-sale alerts.

Reference assets:
- `docs/mvp-blueprint.md`
- `api/openapi.yaml`
- `schemas/store-config.schema.json`
- `schemas/event-envelope.schema.json`
- `docs/process/system-foundations.md`
- `docs/planning/project-delivery-plan.md`
- `docs/actionable-review-checklist.md`
- `docs/planning/execution-status.md`
- `docs/operations/cloud-deployment.md`
- `docs/operations/github-walkthrough-for-beginners.md`
- `docs/templates/brd-template.md`
- `docs/business/iris-brd.md`
- `docs/templates/prd-template.md`
- `docs/developer/developer-doc.md`
- `cto_bot.py`

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
  api/
  docs/
  ideas/
  release-notes/
  schemas/
  tests/
  data/
    stores/                 # one folder per store with snapshots
    exports/current/        # latest analysis CSV output
    exports/day1/           # day-1 run snapshots (optional)
    employee_assets/        # uploaded employee images
    store_registry.db       # sqlite store/email/drive mapping
  analyze_stores.py
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

## Run Batch Analysis

```powershell
python analyze_stores.py --conf 0.25 --detector yolo --time-bucket 1 --gzip-exports
```

CSV outputs:
- `data/exports/current/all_stores_summary.csv`
- `data/exports/current/store_<store_id>_image_insights.csv`
- `data/exports/current/store_<store_id>_camera_hotspots.csv`

## Run Dashboard

```powershell
streamlit run iris_dashboard.py --server.port 8765
```

Dashboard tabs:
- `Overview`
- `Store Detail`
- `Quality`
- `Store Admin`

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

## Detector Notes

- Default detector: YOLOv8n via `ultralytics` (CPU mode), stored at `data/models/yolov8n.pt`.
- If detector is unavailable, pipeline continues and records `detection_error`.
- Use `--detector mock` for deterministic local testing.


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
python analyze_stores.py --root data/stores --out data/exports/current --detector yolo --gzip-exports --drop-plain-csv
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


## Run CTO bot health orchestrator

```bash
python cto_bot.py --log-dir data/ops_logs
```

This runs QA/CTO/DevOps checks, records role-based logs, and exits non-zero on failures.

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
python analyze_stores.py --conf 0.25 --detector yolo --time-bucket 1
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

Sidebar:
- `Access Email (optional)` filters dashboard view to mapped store
- `Auto-sync linked drives before analysis` syncs data points before run

## Detector Notes

- Default detector: YOLOv8n via `ultralytics` (CPU mode), stored at `data/models/yolov8n.pt`.
- If detector is unavailable, pipeline continues and records `detection_error`.
- Use `--detector mock` for deterministic local testing.

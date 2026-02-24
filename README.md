# IRIS Store-Level Customer Analysis

This app analyzes retail snapshot images, where each folder represents one store.
It produces:
- Customer insights (person detection)
- Camera-level hotspot ranking
- Data quality diagnostics
- CSV exports for downstream use
- Store/email mapping and access filtering
- Employee image registry per store
- Google Drive link per store with on-demand sync

## Folder Contract

Expected store layout:

```text
<root>/
  store_001/
    HH-MM-SS_DXX-N.jpg
  store_002/
    HH-MM-SS_DXX-N.jpg
```

Example filename: `09-57-27_D02-1.jpg`

Compatibility mode:
- If no store subfolders exist and images are directly inside `<root>`, the root is treated as one store.

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Run Batch Analysis + CSV Export

```powershell
python analyze_stores.py --root . --out exports --conf 0.25 --detector yolo --time-bucket 1
```

Key output files:
- `exports/all_stores_summary.csv`
- `exports/store_<store_id>_image_insights.csv`
- `exports/store_<store_id>_camera_hotspots.csv`

## Run Dashboard

```powershell
streamlit run iris_dashboard.py --server.port 8765
```

Dashboard sections:
- Overview (all stores leaderboard + KPIs)
- Store Detail (hotspots, trend, gallery)
- Quality (invalid files, parsing/detection issues)
- Store Admin (store/email mapping, drive link, employee uploads)

## Store Admin Capabilities

From dashboard `Store Admin` tab:
- Add/Update stores (`store_id`, `store_name`, `email`, `drive_folder_url`)
- Keep email-to-store mapping (one email maps to one store)
- Upload employee images per store
- Sync snapshots from each linked Google Drive folder

Sidebar controls:
- `Access Email (optional)`: restricts dashboard view to mapped store
- `Auto-sync linked drives before analysis`: pulls data points before running analysis

## Detector Notes

- Default detector: YOLOv8n (`ultralytics`, CPU mode).
- If YOLO is unavailable, the app records `detection_error` and continues without crashing.
- Use `--detector mock` for deterministic local testing without model runtime.

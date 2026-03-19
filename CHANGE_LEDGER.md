# IRIS Change Ledger

## Purpose
This is the mandatory handover file for humans and AI agents.
It records what changed, where it changed, and why.

## Update Rules (Mandatory)
1. Update this file in every change set before pushing to `main`.
2. Add one new entry in `Change Entries` for each commit/PR batch.
3. If a new module/file is added, update `Module Registry`.
4. Always list exact changed paths (relative paths).
5. Keep summaries short, factual, and implementation-focused.

## Module Registry
| Module/File | Responsibility |
|---|---|
| `src/iris/iris_dashboard.py` | Streamlit UI, navigation, auth flow, operations/access pages, configuration UI. |
| `src/iris/iris_analysis.py` | Store image analysis pipeline, detector abstraction, metrics, exports, tracking logic. |
| `src/iris/store_registry.py` | Store/user/role DB logic, source sync adapters (Drive/S3/local), audit state. |
| `src/iris/drive_delta_sync.py` | Scheduled Google Drive delta-sync engine: first full pull, latest-folder delta pulls, multi-queue downloads, and deletion tombstones. |
| `src/iris/event_queue.py` | Local event queue abstraction for async processing. |
| `src/run_dashboard.py` | Streamlit entrypoint for package-safe execution in Docker/local. |
| `scripts/drive_delta_sync_scheduler.py` | Daily 6 AM scheduler wrapper for autonomous sync execution. |
| `scripts/benchmark_drive_sync.py` | Throughput benchmark utility to estimate first-day and daily sync times. |
| `tests/test_iris_analysis.py` | Analysis pipeline and detector tests. |
| `tests/test_store_registry.py` | Registry, sync, access-control, and persistence tests. |
| `tests/test_drive_delta_sync.py` | Delta-sync planner/scope/deletion behavior tests. |

## Change Entry Template
Use this template for each new change:

```md
### YYYY-MM-DD | Commit <sha>
- Summary:
  - <one-line behavior summary>
- Changed Paths:
  - `<path1>`
  - `<path2>`
- New Modules Introduced:
  - `<path>` (or `None`)
- Infra/Config Impact:
  - <env var / dependency / docker impact or `None`>
```

## Change Entries

### 2026-03-12 | Commit ff4d140
- Summary:
  - Fixed top branding header so uploaded organization logo and app name reliably render.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-12 | Commit bc76693
- Summary:
  - Added optional legacy TensorFlow Faster-RCNN detector backend (`tf_frcnn`) for person counting.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_iris_analysis.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional TensorFlow runtime and model path (`TF_FRCNN_MODEL_PATH`) required only when selecting `tf_frcnn`.

### 2026-03-12 | Commit de4f171
- Summary:
  - Added provider-ready source sync (Google Drive/S3/local) and synced-store filtering.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_store_registry.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional `boto3` needed only for S3 sync mode.

### 2026-03-12 | Commit 5dd19ff
- Summary:
  - Improved staff/customer classification using employee-image color profiling.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-12 | Commit 9a27459
- Summary:
  - Added QA proof links/overlays, feedback workflow, and customer journey verification pages.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-12 | Commit eb95afc
- Summary:
  - Fixed store drill-down proof validation by adding clickable image hyperlinks and robust path resolution for Docker/local path differences.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit 66ab8ab
- Summary:
  - Added BLRJAY pilot-day execution support: store-day customer session IDs, floor/location hotspots, date-scoped exports, and dashboard/CLI controls for March 12, 2025 validation.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `src/iris/store_registry.py`
  - `scripts/analyze_stores.py`
  - `tests/test_iris_analysis.py`
  - `tests/test_store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `GOOGLE_API_KEY` required for reliable large Google Drive sync.
  - DeepFace is optional; age/gender fields remain empty when unavailable.

### 2026-03-13 | Commit ef6f0bb
- Summary:
  - Fixed date-filter export edge case by enforcing missing frame columns (`customer_ids/group_ids`) before store-day artifact export.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit 8185165
- Summary:
  - Simplified store mapping UX and added Store Camera Mapping with location master + auto camera ID discovery from image filenames.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit 68ecab8
- Summary:
  - Fixed top-row branding render to reliably show uploaded logo and app name using native Streamlit components in both login and app header.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit d8d0474
- Summary:
  - Fixed Users directory crash when `accessible_stores` is absent by guarding DataFrame column handling before `fillna`.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit 6bfe17b
- Summary:
  - Removed `Trade/Display License Workflow` and `Alert Routing` modules from navigation and page routing; added legacy redirects to `Organisation`.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit fe59bc9
- Summary:
  - Added Google-Photos-style employee onboarding: per-image preview + name labeling during upload, plus optional labeling from selected store snapshots.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-13 | Commit fe12326
- Summary:
  - Renamed unclear report pages: `Quality` -> `Data Health` and `QA Timeline` -> `Frame Review`, including headers and legacy URL alias support.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit 00fe5d8
- Summary:
  - Added in-app frame hyperlinks and hover image previews in Frame Review, with internal links that preserve auth token and reduce repeated login prompts.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit 6ca9066
- Summary:
  - Fixed `/nan` filename-link bug in frame proof table and added simple business KPI summary cards (entries, closed exits, conversion, gender split, age-group split) for store drill-down.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit pending
- Summary:
  - Removed standalone filename hyperlink block, switched proof/gallery links to in-app validation links, and added customer-face validation grid with 80-person quick view.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit 996925f
- Summary:
  - Fixed false person counts by adding static banner/poster suppression in analysis; kept staff separate from customers after suppression; switched dashboard default detector to `yolo` (mock remains test-only).
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - For accurate production counts, use YOLO runtime (`IRIS_ENABLE_YOLO=1` in Docker build).

### 2026-03-16 | Commit pending
- Summary:
  - Fixed YOLO Docker runtime import failure by adding required OpenCV system libraries (`libxcb`, `libgl`, related X/GLib libs) to the image build.
- Changed Paths:
  - `deploy/Dockerfile`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Docker image now installs extra OS packages needed for YOLO/OpenCV runtime.

### 2026-03-16 | Commit 968c2c7
- Summary:
  - Prevented accidental `mock` detector usage in production UI; detector list now defaults to real detectors (`yolo`, `tf_frcnn`) and auto-switches legacy `mock` session state back to `yolo` unless explicitly enabled by `IRIS_ALLOW_MOCK_DETECTOR=1`.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional env flag `IRIS_ALLOW_MOCK_DETECTOR=1` required to show `mock` detector in UI.

### 2026-03-16 | Commit b690c2c
- Summary:
  - Fixed Visual Verification broken links (`/nan`) by sanitizing invalid URLs and routing verification links to in-app authenticated frame pages; added hover preview links in Customer Journey Visual Verification.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit 9fde8e3
- Summary:
  - Simplified QA review workflow: clearer correction form, searchable feedback queue with status KPIs, frame-open links, reviewer workbench with image preview, and one-click Approve/Reject/Set Pending actions.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-16 | Commit f561268
- Summary:
  - Added auto-learning banner false-positive suppression: when QA correction marks `no_person`, the app stores camera/box perceptual-hash signatures and auto-reruns analysis; future runs suppress matching detections automatically.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_store_registry.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Database adds `qa_false_positive_signatures` table for learned suppression memory.

### 2026-03-16 | Commit pending
- Summary:
  - Tuned detection accuracy defaults: upgraded YOLO model default (`yolov8m`), relaxed red-shirt staff threshold, made static false-positive suppression stricter, and lowered default detection confidence to `0.18` across analysis/CLI/dashboard defaults.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `scripts/analyze_stores.py`
  - `scripts/run_async_worker.py`
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Default YOLO model is heavier (`yolov8m`) and may require more CPU/GPU and RAM than `yolov8n`.

### 2026-03-18 | Work In Progress
- Summary:
  - Raised person-detection config defaults (`YOLO_MODEL_PATH`, 0.20 confidence), added per-detection confidence tracking, HSV-based redshirt detection, and stricter static/banner suppression helpers plus new `person_confidences` hygiene in exports/tests.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `tests/test_iris_analysis.py`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional `YOLO_MODEL_PATH` env lets you steer between `yolov8s.pt` and larger weights; nothing else changed.

### 2026-03-18 | Commit pending
- Summary:
  - Merged both local working change sets into canonical branch: added optional detection-cache/parallel analysis scaffolding, `person_confidences` propagation, HSV red-shirt fallback updates, and dependency additions (`pydantic`, `pyarrow`), then fixed merge regressions (`CameraConfig` reconstruction and static-banner suppression behavior) to keep tests passing.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/store_registry.py`
  - `requirements.txt`
  - `deploy/requirements.docker.txt`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Adds Python deps `pydantic>=2.0,<3.0` and `pyarrow>=15.0,<16.0`.

### 2026-03-18 | Commit pending
- Summary:
  - Switched repository workflow source-of-truth path to `Desktop\\Github\\IRIS` in agent instructions so local working convention matches requested deployment flow.
- Changed Paths:
  - `AGENTS.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | Commit pending
- Summary:
  - Fixed Docker runtime crash (`ModuleNotFoundError: cv2`) by adding OpenCV headless dependency to app and Docker requirement sets.
- Changed Paths:
  - `requirements.txt`
  - `deploy/requirements.docker.txt`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Adds `opencv-python-headless>=4.10,<5.0` to runtime dependencies.

### 2026-03-18 | Commit pending
- Summary:
  - Added optional filename-prefix filtering in analysis pipeline and CLI so targeted windows (for example `11-35`, `12-15`, `12-17`) can be analyzed without processing the full store set.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `scripts/analyze_stores.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | Commit pending
- Summary:
  - Implemented Drive delta-sync foundation: added `store_source_file_index` table and sync logic that compares indexed/local files against Drive listing, downloads only missing files, and never erases existing local snapshots.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `tests/test_store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - SQLite schema adds `store_source_file_index` and index `idx_source_file_index_store_provider_present`.

### 2026-03-18 | Commit pending
- Summary:
  - Fixed broken hover verification links by sanitizing `nan` values and resolving preview images from local `path/relative_path/source_folder` fallback logic in customer journey views.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | Commit pending
- Summary:
  - Fixed Google Drive API sync reliability on restricted networks by adding download fallback (`drive.google.com/uc`) when `alt=media` is blocked, and skipping already-present files to speed repeated syncs.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Added autonomous daily Drive sync design: first full pull, then latest-date delta sync with multi-queue downloads, deletion tombstones, scheduler runner (6 AM), dockerized sync worker service, and benchmark tooling.
- Changed Paths:
  - `src/iris/drive_delta_sync.py`
  - `src/iris/store_registry.py`
  - `scripts/drive_delta_sync_scheduler.py`
  - `scripts/benchmark_drive_sync.py`
  - `deploy/docker-compose.yml`
  - `README.md`
  - `tests/test_drive_delta_sync.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `src/iris/drive_delta_sync.py`
  - `scripts/drive_delta_sync_scheduler.py`
  - `scripts/benchmark_drive_sync.py`
  - `tests/test_drive_delta_sync.py`
- Infra/Config Impact:
  - New optional docker service `iris-sync` and env vars `IRIS_SYNC_STORE_ID`, `IRIS_SYNC_RUN_AT`, `IRIS_SYNC_TZ`, `IRIS_SYNC_WORKERS` (requires `GOOGLE_API_KEY`).

### 2026-03-19 | Commit pending
- Summary:
  - Implemented strict gate session engine support for entry/exit tracking (D07 fallback), prevented non-gate ID creation in strict mode, added session validity/staff flags, and switched business KPIs to valid CLOSED sessions when strict contract is active.
  - Added centroid-side crossing fallback when track IDs are unstable, plus regression tests for strict mode and session-based KPIs.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed blank/zero-data dashboard regression caused by stale exports by adding empty-export detection and one-time auto-recovery analysis when source images exist; added explicit no-source message when root path has no images.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Added explicit dashboard notice when `Images Per Store` sampling is enabled to prevent confusion when totals appear capped (e.g., 200 images instead of full folder volume).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed stale in-session dashboard data by auto-reloading exports when `all_stores_summary` on disk is newer than cached session output (supports terminal-triggered analysis runs without manual cache reset).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed detection-cache poisoning across detector changes by adding detector signature (backend/model/conf/device) into cache key; prevents old `Detector unavailable` results from being reused after YOLO is enabled.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

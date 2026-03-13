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
| `src/iris/event_queue.py` | Local event queue abstraction for async processing. |
| `src/run_dashboard.py` | Streamlit entrypoint for package-safe execution in Docker/local. |
| `tests/test_iris_analysis.py` | Analysis pipeline and detector tests. |
| `tests/test_store_registry.py` | Registry, sync, access-control, and persistence tests. |

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

### 2026-03-13 | Commit pending
- Summary:
  - Fixed date-filter export edge case by enforcing missing frame columns (`customer_ids/group_ids`) before store-day artifact export.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

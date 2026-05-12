# IRIS Developer Guide

**Last updated:** 2026-05-12

## What to know first

IRIS is now a React + FastAPI application with dedicated background workers.

Do not assume:
- Streamlit is still the primary UI (false; legacy assumption to avoid)
- the web process owns scheduler loops
- a single mega-file is still the intended extension point

## Current Runtime Shape

| Component | Entry point |
| --- | --- |
| Web/API | `scripts/start_api_server.py` |
| Core scheduler worker | `scripts/start_scheduler_worker_service.py` |
| On-fly scheduler worker | `scripts/start_onfly_scheduler_service.py` |
| Store auto-sync worker | `scripts/start_store_auto_sync_service.py` |

## Main code areas

### Backend API
- `backend/app/main.py`
- `backend/app/api/`
- `backend/app/db/`
- `backend/app/workers/`

### Pipeline core
- `src/iris/onfly_pipeline.py`
- `src/iris/source_clients.py`
- `src/iris/download_manager.py`
- `src/iris/gpt_runtime.py`
- `src/iris/session_reconstruction.py`
- `src/iris/report_writer.py`
- `src/iris/pipeline_events.py`

### Frontend
- `frontend/src/pages/`
- `frontend/src/features/reports/`
- `frontend/src/features/scheduler/`
- `frontend/src/features/frame-review/`

## Rules for safe changes

1. Update `CHANGE_LEDGER.md` in every change set.
2. Keep source-of-truth docs aligned:
   - `README.md`
   - `docs/deployment/cost-optimization-plan.md`
   - `docs/process/onfly_pipeline_logic.md`
   - `deploy/cloud/README.md`
3. Avoid adding new mega-files.
4. Prefer helper modules/hooks/components over page growth.
5. Preserve the 3 PM GPT-saving schedule behavior unless explicitly asked.

## Testing baseline

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
$env:PYTHONPATH='src'
python -m pytest tests/test_onfly_pipeline.py tests/test_onfly_scheduler.py tests/test_routes_onfly.py tests/test_store_registry.py tests/test_runtime_bootstrap.py -q
cd frontend
npm run build
```


# IRIS Agent Workflow

## Source of Truth

- Primary repository path: `C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS`
- GitHub repository: `https://github.com/vishalnayakkushals/IRIS`
- Default branch: `main`

## Mandatory Change Tracking

- Every code change must update `CHANGE_LEDGER.md` before push.
- If a new module/file is introduced, add it to the `Module Registry` section in `CHANGE_LEDGER.md`.
- The ledger entry must list exact touched paths and a short behavior summary.

## Required Working Style

- Apply code changes locally in the canonical path.
- Validate with runnable commands (especially Docker for deployment issues).
- Commit only intended files with clear commit messages.
- Push each completed change set to `origin/main` so local and GitHub remain aligned.

## New Phase 1 Modules (React + FastAPI + Celery)

| Module/File | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app factory: CORS, API routers, static React file serving on port 8766. |
| `backend/app/config.py` | Pydantic-settings: DB_PATH, REDIS_URL, JWT_SECRET, STORE_ID, API keys loaded from env. |
| `backend/app/auth/jwt_handler.py` | create_token() / verify_token() using python-jose. |
| `backend/app/auth/dependencies.py` | FastAPI Depends: get_current_user() → extracts email from Bearer JWT. |
| `backend/app/api/routes_auth.py` | POST /api/auth/login, GET /api/auth/me — uses existing authenticate_user() from store_registry. |
| `backend/app/api/routes_jobs.py` | GET /api/jobs, POST /api/jobs/{key}/trigger, POST /api/jobs/trigger-all. |
| `backend/app/api/routes_runs.py` | GET /api/runs — recent pipeline run history from pipeline_run_log table. |
| `backend/app/db/pipeline_log.py` | CRUD for pipeline_run_log: insert_run_log, update_run_log_status, get_latest_per_job, get_recent_runs. |
| `backend/app/celery_app/worker.py` | Celery app factory + beat schedule (hourly YOLO, midnight full pipeline). |
| `backend/app/celery_app/tasks/drive_sync.py` | drive_sync_task: wraps sync_store_gdrive_delta(), chains to yolo_scan if chain=True. |
| `backend/app/celery_app/tasks/yolo_scan.py` | yolo_scan_task: wraps run_stage1_scan(), chains to gpt_analysis if relevant_count > 0. |
| `backend/app/celery_app/tasks/gpt_analysis.py` | gpt_analysis_task: wraps run_onfly_pipeline(gpt_enabled=True), rate_limit=10/m. |
| `backend/app/celery_app/tasks/report.py` | report_task: wraps run_stage1_report() to generate final store report CSV. |
| `backend/Dockerfile` | Multi-stage: Node 20 builds React → Python 3.11-slim runs FastAPI with static React embedded. |
| `frontend/src/pages/Login.tsx` | JWT login form → stores token in localStorage. |
| `frontend/src/pages/SchedulerDashboard.tsx` | Main scheduler dashboard: Manual Sync tab + Run History tab, polls /api/jobs every 5s. |
| `frontend/src/components/JobTable.tsx` | Pipeline jobs table with status badges and trigger buttons. |
| `frontend/src/components/StatusBadge.tsx` | Color-coded status: running=orange, queued=pink, done=green, failed=red, idle=gray. |
| `frontend/src/api/client.ts` | Axios instance with Bearer token interceptor and 401 auto-logout. |

## Standard Local Deploy Commands

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
git pull origin main
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

## Docker Build Mode

- Default: lightweight build (`IRIS_ENABLE_YOLO=0`) for faster startup.
- Full YOLO build when needed:

```powershell
$env:IRIS_ENABLE_YOLO="1"
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

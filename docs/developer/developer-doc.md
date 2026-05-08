# IRIS Developer Documentation

**Last updated:** 2026-04-30
**Stack:** Python 3.11 + FastAPI + React 18 + TypeScript + SQLite/PostgreSQL

---

## 1. Repository Structure

```text
IRIS/
├── backend/                        # FastAPI REST API + AI pipeline
│   ├── app/
│   │   ├── main.py                 # App entry point, all routers registered here
│   │   ├── config.py               # Pydantic-settings: DB, Redis, JWT, API keys
│   │   ├── limiter.py              # slowapi rate-limiter instance
│   │   ├── api/                    # Route handlers (one file per domain)
│   │   │   ├── routes_auth.py      # POST /api/auth/login, GET /api/auth/me
│   │   │   ├── routes_admin.py     # Store/user/role/camera/employee CRUD
│   │   │   ├── routes_dashboard.py # Analytics: overview, trend, leaderboard, delta
│   │   │   ├── routes_detail.py    # Store list and per-store detail
│   │   │   ├── routes_health.py    # GET /api/health
│   │   │   ├── routes_jobs.py      # Celery job trigger + status
│   │   │   ├── routes_onfly.py     # On-fly pipeline sync + live progress
│   │   │   ├── routes_qa.py        # Frame review feedback + image serving
│   │   │   ├── routes_reports.py   # Walk-in reports, validation map, CSV downloads
│   │   │   └── routes_runs.py      # Pipeline run history
│   │   ├── auth/
│   │   │   ├── jwt_handler.py      # create_token(), verify_token()
│   │   │   └── dependencies.py     # get_current_user() FastAPI dependency
│   │   ├── db/
│   │   │   ├── canonical_metadata.py  # All SQLAlchemy table definitions (single source of truth)
│   │   │   ├── pipeline_log.py     # CRUD helpers for pipeline_run_log
│   │   │   ├── platform_data.py    # Auth queries + analytics queries
│   │   │   └── session.py          # Async + sync SQLAlchemy engine/sessionmaker
│   │   ├── models/                 # Pydantic request/response schemas
│   │   ├── celery_app/             # Celery worker + beat schedule + task modules
│   │   └── static/                 # React production build (served at /)
│   └── requirements.txt
│
├── frontend/                       # React 18 + TypeScript + Vite
│   ├── src/
│   │   ├── api/client.ts           # All API calls (axios, JWT interceptors)
│   │   ├── pages/                  # 20 page components (see Section 4)
│   │   └── components/             # Shared UI components
│   ├── vite.config.ts              # Dev proxy → localhost:8767
│   └── package.json
│
├── src/iris/                       # Core Python AI/pipeline library
│   ├── onfly_pipeline.py           # Main pipeline: Drive → YOLO → GPT → sessions
│   ├── iris_analysis.py            # Batch analysis engine
│   ├── iris_dashboard.py           # Legacy Streamlit dashboard (being phased out)
│   ├── drive_delta_sync.py         # Google Drive incremental sync
│   ├── store_registry.py           # SQLite store/user/config registry
│   ├── bot_sort_tracker.py         # BoT-SORT multi-camera person tracker
│   ├── session_state_machine.py    # Walk-in session reconstruction
│   ├── entrance_pipeline.py        # Entrance detection pipeline
│   ├── event_queue.py              # Async event queue
│   ├── runtime_bootstrap.py        # Application bootstrap
│   └── secret_store.py             # API key / credential storage
│
├── scripts/                        # CLI utilities and one-shot runners
├── data/
│   ├── store_registry.db           # SQLite runtime DB (primary)
│   ├── stores/                     # Camera snapshots per store
│   ├── exports/current/            # Pipeline CSV outputs
│   └── employee_assets/            # Uploaded staff photos
├── deploy/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/
├── requirements.txt                # Legacy Streamlit + analysis deps
├── CHANGE_LEDGER.md                # Mandatory — updated on every commit
└── run_iris.bat                    # Windows shortcut for common commands
```

---

## 2. Local Setup

### 2.1 Backend (FastAPI)

```powershell
# Install backend dependencies
pip install -r backend/requirements.txt

# Copy and configure environment
Copy-Item .env.example .env
# Edit .env — set OPENAI_API_KEY, GOOGLE_API_KEY, JWT_SECRET

# Start API server (development)
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8767 --reload

# Or via NSSM Windows service (auto-restarts on crash/sleep)
# Service name: IRIS-API, runs on port 8767
```

Required environment variables:

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
| `JWT_SECRET` | Yes | `change_me_in_env` | Must change before production |
| `OPENAI_API_KEY` | Yes (for GPT pipeline) | `""` | GPT-4.1-mini vision analysis |
| `GOOGLE_API_KEY` | Yes (for Drive sync) | `""` | Google Drive API |
| `POSTGRES_URL` | No | local postgres URL | Falls back to SQLite if not reachable |
| `CORS_ORIGINS` | No | `localhost:3000,8767` | Comma-separated allowed origins |

### 2.2 Frontend (React + Vite)

```powershell
cd frontend
npm install

# Development (proxies /api to localhost:8767)
npm run dev          # runs on localhost:3000

# Production build → copy to backend static
npm run build
Copy-Item -Recurse -Force dist\* ..\backend\app\static\
```

### 2.3 Legacy Streamlit Dashboard (port 8765)

```powershell
pip install -r requirements.txt
streamlit run src/run_dashboard.py --server.port 8765
```

> **Note:** Streamlit is being phased out. All new features go into the React + FastAPI stack. Do not add features to `iris_dashboard.py`.

### 2.4 Docker (all-in-one)

```bash
docker compose -f deploy/docker-compose.yml up --build -d
# API + React: http://localhost:8767
# Legacy Streamlit: http://localhost:8765
```

---

## 3. Backend Modules — What Each File Does

### 3.1 API Routes

| File | Prefix | Key Endpoints |
| --- | --- | --- |
| `routes_auth.py` | `/api/auth` | `POST /login` (rate-limited 10/min), `GET /me` |
| `routes_admin.py` | `/api` | Store CRUD, user/role management, employee photos, camera zones, store master CSV upload, activity logs |
| `routes_dashboard.py` | `/api/dashboard` | `GET /analytics`, `GET /trend`, `GET /leaderboard`, `GET /delta` — all read from SQLite |
| `routes_detail.py` | `/api/detail` | Store list, per-store walk-in sessions and metrics |
| `routes_health.py` | `/api` | `GET /health` → `{"status":"ok"}` |
| `routes_jobs.py` | `/api/jobs` | List jobs, `POST /{key}/trigger`, `POST /trigger-all` (Celery) |
| `routes_onfly.py` | `/api/onfly` | `POST /sync/{store_id}` (triggers pipeline in background thread), `GET /status/{store_id}`, `GET /stores`, `GET /progress/{store_id}` (SSE live progress) |
| `routes_qa.py` | `/api/qa` | Frame review: list/create/update/delete feedback, `GET /image` serves frame thumbnails via Drive proxy, `POST /retrain/{store_id}` |
| `routes_reports.py` | `/api/reports` | Walk-in detail (`/walkins`), day summary (`/summary`), image scans (`/image-scans`), validation map (`/validation/walkin-image-map`), all with `/download/*` CSV variants |
| `routes_runs.py` | `/api/runs` | `GET /runs` (recent pipeline runs), `GET /runs/{run_id}` |

### 3.2 Database Layer (`backend/app/db/`)

**`canonical_metadata.py`** — single source of truth for all table schemas (SQLAlchemy Table objects). Do not define tables anywhere else.

Key tables:

| Table | Purpose |
| --- | --- |
| `stores` | Store registry (store_id, name, drive URL, sync config) |
| `users` | User accounts (email, password_hash, store_id, is_admin) |
| `roles` / `role_permissions` / `user_roles` | RBAC system |
| `onfly_image_state` | Per-image processing state: `image_name`, `camera_id`, `date_source`, `yolo_relevant`, `gpt_status`, `gpt_customer_count`, `source_url` (Drive link) |
| `onfly_walkin_sessions` | Walk-in sessions: `walkin_id`, `group_id`, `entry_time`, `exit_time`, `camera_id`, `role`, `gender`, `age_band`, `purchase_signal_bag`, `source_image_name`, `run_id` |
| `pipeline_run_log` | All pipeline job executions: `job_key`, `status`, `remarks`, `started_at`, `completed_at` |
| `qa_feedback` | Frame review decisions: `predicted_label`, `corrected_label`, `review_status`, `comment` |
| `report_store_day_summary` | Daily rollup: walkins, conversions, dwell, conversion rate |
| `model_versions` | ML model version registry with accuracy metrics |

**`platform_data.py`** — query helpers used by route handlers:
- `authenticate_platform_user()` — validates email/password (supports bcrypt and pbkdf2_sha256)
- `get_overview_metrics()` — platform-wide KPIs
- `get_store_metrics()` — per-store footfall, dwell, bounce
- `get_traffic_series()` — time-series for trend charts
- `get_pipeline_runs()` / `get_walkin_sessions()` — data for reports

**`session.py`** — two engines:
- `AsyncSessionLocal` — used in FastAPI async route handlers (asyncpg driver)
- Sync engine — used in background threads and Celery tasks (psycopg2 driver)

### 3.3 Core Pipeline (`src/iris/`)

**`onfly_pipeline.py`** — the main AI pipeline. Called from `routes_onfly.py`:
1. Lists images from Google Drive folder (delta sync — skips already-processed images)
2. Downloads in-memory, runs YOLO (`yolov8n.pt`, confidence threshold 0.18)
3. For YOLO-relevant images only: calls GPT-4.1-mini vision API
4. Writes results to `onfly_image_state` (SQLite)
5. Reconstructs walk-in sessions → writes to `onfly_walkin_sessions`
6. Updates `pipeline_run_log`

**`drive_delta_sync.py`** — Google Drive sync:
- Uses `GOOGLE_API_KEY` for Drive API calls
- `DATE_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")` — only syncs date-named subfolders
- Delta mode: only downloads files not already in `onfly_image_state`

**`bot_sort_tracker.py`** — multi-camera person tracker. Assigns persistent track IDs across frames. Used for session reconstruction in `session_state_machine.py`.

**`store_registry.py`** — legacy SQLite store/user/camera config registry. Still used by Streamlit. New features should use `canonical_metadata.py` + `platform_data.py` instead.

---

## 4. Frontend Pages

| Page | Route | Purpose |
| --- | --- | --- |
| `Login.tsx` | `/login` | JWT login form |
| `Overview.tsx` | `/` | KPI cards, trend chart, gender/age donut, store leaderboard |
| `SchedulerDashboard.tsx` | `/scheduler` | Pipeline job status table, manual trigger, Celery run history, per-store auto-sync status |
| `ReportsPage.tsx` | `/reports` | Walk-in detail, day summary, image scans, validation map — all with pagination and CSV download |
| `FrameReview.tsx` | `/frame-review` | Paginated (24/page) frame thumbnail review with confirm/reject/label controls |
| `StoreDetail.tsx` | `/store/:id` | Per-store walk-in sessions and camera metrics |
| `StoreMaster.tsx` | `/store-master` | Store master data upload (CSV) and per-row validation |
| `StoreMapping.tsx` | `/store-mapping` | Store-to-location mapping configuration |
| `StoreAccess.tsx` | `/store-access` | User-to-store access control |
| `UsersPage.tsx` | `/users` | User CRUD + role assignment |
| `RolePermissions.tsx` | `/roles` | Role and permission matrix |
| `EmployeeManagement.tsx` | `/employees` | Staff photo upload and management |
| `CameraZones.tsx` | `/cameras` | Camera zone configuration |
| `CustomerJourneys.tsx` | `/journeys` | Customer path analytics |
| `ActivityLogs.tsx` | `/activity` | User action audit log |
| `ModelAccuracy.tsx` | `/model-accuracy` | YOLO/GPT model version history and accuracy metrics |
| `ModelFeedback.tsx` | `/model-feedback` | Submit model correction feedback |
| `QualityFeedback.tsx` | `/quality` | QA quality review interface |
| `RunDetail.tsx` | `/runs/:id` | Single pipeline run details and event log |
| `Organisation.tsx` | `/organisation` | Organisation-level settings |

### Key Frontend Patterns

**API calls** — all in `frontend/src/api/client.ts`. Always add new endpoints here, never inline in components.

**Auth** — JWT stored in `localStorage`. Axios interceptor attaches `Authorization: Bearer <token>` to every request. 401 response → redirect to `/login`.

**Build and deploy:**
```powershell
cd frontend && npm run build
Remove-Item -Recurse -Force ..\backend\app\static\assets\*
Copy-Item -Recurse -Force dist\* ..\backend\app\static\
# Then restart uvicorn / NSSM service
```

---

## 5. Data Paths and Key Files

| Path | Contents |
| --- | --- |
| `data/store_registry.db` | Primary runtime SQLite database |
| `data/stores/<store_id>/<YYYY-MM-DD>/` | Camera snapshots (filename: `HH-MM-SS_D<cam>-N.jpg`) |
| `data/exports/current/` | Pipeline CSV output files |
| `data/exports/current/onfly/<store_id>/` | On-fly pipeline per-store outputs |
| `data/employee_assets/<store_id>/` | Uploaded staff photos |
| `data/models/yolov8n.pt` | YOLOv8n model weights (downloaded on first run) |
| `backend/app/static/` | React production build — served at `/` |
| `.env` | Local secrets (never commit) |

---

## 6. Running Tests

```bash
# Backend unit tests
PYTHONPATH=src pytest -q

# Type checking (frontend)
cd frontend && npx tsc --noEmit
```

CI runs on every push via `.github/workflows/python-package-conda.yml`:
- `flake8` lint (critical errors only)
- `pytest` with `PYTHONPATH=src`

---

## 7. Key Development Rules

1. **Update `CHANGE_LEDGER.md` on every commit.** List exact changed paths and a one-line summary. This is mandatory — not optional.

2. **New API endpoints go in `backend/app/api/`** — one file per domain. Register the router in `backend/app/main.py`.

3. **New database tables go in `backend/app/db/canonical_metadata.py` only.** Do not define tables in route files or ad hoc.

4. **New frontend API calls go in `frontend/src/api/client.ts` only.** Do not use `fetch()` or `axios` inline in components.

5. **Do not add features to Streamlit (`iris_dashboard.py`).** Streamlit is being phased out. All new UI work goes into the React + FastAPI stack.

6. **Image matching in validation report uses camera-first logic.** When resolving which Drive image corresponds to a walk-in session, the matching order is: (1) direct image name match, (2) same-camera time-window overlap, (3) cross-camera fallback (marked `⚠ Cross-camera` in UI). Do not bypass this order.

7. **Frontend build output must be copied to `backend/app/static/` after every build.** The FastAPI server serves the React SPA from there.

8. **Never commit `.env`, API keys, or `data/store_registry.db`.** These are in `.gitignore`.

---

## 8. Common Tasks

### Restart the API server after code changes

```powershell
# From admin PowerShell (NSSM service)
Restart-Service IRIS-API

# Or kill uvicorn (NSSM auto-restarts in 10s)
Stop-Process -Id <PID> -Force   # find PID: netstat -ano | findstr ":8767"
```

### Trigger a pipeline run manually

```powershell
# Via UI: Scheduler page → "Sync Now" button
# Via API:
curl -X POST http://localhost:8767/api/onfly/sync/<store_id> -H "Authorization: Bearer <token>"
```

### Run on-fly pipeline directly from CLI

```powershell
python scripts/run_onfly_pipeline.py --store-id BLRJAY
```

### Rebuild frontend and deploy

Always clean the old assets before copying. Vite hashes file names on every build — without the clean step, old bundles accumulate and get committed to git bloating the repo.

```powershell
cd frontend
npm run build
# REQUIRED: wipe old hashed bundles before copying new ones
Remove-Item -Recurse -Force ..\backend\app\static\assets\*
Copy-Item -Recurse -Force dist\* ..\backend\app\static\
# Restart the server (NSSM service or kill uvicorn PID)
```

**Never use `Copy-Item` without the `Remove-Item` first.** Skipping it leaves the old `*-<hash>.js` files in git alongside the new ones. After the copy, verify only 5 files exist in `backend/app/static/assets/` (the 4 JS bundles + 1 CSS file).

### Check which ports are running

```powershell
netstat -ano | findstr "LISTENING" | findstr ":87"
# Port 8767 = NSSM service (correct)
# Port 8765 = Legacy Streamlit
# Other ports = leftover dev processes, stop them
```

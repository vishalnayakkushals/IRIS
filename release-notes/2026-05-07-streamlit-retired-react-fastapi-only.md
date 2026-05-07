# Release Notes — 2026-05-07

## Feature Name
Streamlit Fully Retired — React + FastAPI Is Now the Only UI

---

## What Changed

### Streamlit Removed
The original Streamlit dashboard (`src/iris/iris_dashboard.py`, 8,410 lines) and all supporting files have been permanently deleted. The React + FastAPI application is now the sole UI and API for IRIS.

**Files deleted:**

| File | What it was |
| --- | --- |
| `src/iris/iris_dashboard.py` | The original 8,410-line Streamlit dashboard |
| `src/run_dashboard.py` | Streamlit entrypoint wrapper |
| `scripts/start_web_app.py` | Streamlit local launcher (port 8765) |
| `deploy/Dockerfile` | Legacy Streamlit-only Docker image build |
| `deploy/requirements.docker.txt` | Streamlit-only Python dependency list |
| `fix_login.py` | One-time password reset script left in root |
| `patch.py` | One-time drive_delta_sync patch script left in root |

**Dependencies removed from `requirements.txt`:**
- `streamlit>=1.40,<2.0`
- `plotly>=5.24,<6.0` (Streamlit chart library — not used in pipeline or API)
- `pyarrow>=15.0,<16.0` (Streamlit dataframe serialiser — not used elsewhere)

**`deploy/docker-compose.yml`:** The `iris` service (Streamlit on port 8765) has been removed. Docker Compose now starts only the production services: `iris-api`, `iris-celery-worker`, `iris-celery-beat`, and `redis`.

---

### README Rewritten
The `README.md` was entirely about Streamlit. It has been rewritten from scratch to document the current stack:
- How to run locally (`python scripts/start_api_server.py`)
- How to run with Docker
- Project structure (React + FastAPI layout)
- Environment variables
- All 9 key dashboard pages with routes
- Pipeline flow diagram
- API docs link (`/docs`, `/redoc`)

---

### AGENTS.md Updated
- All deleted Streamlit files added to the Deleted/Removed Modules table with deletion dates.
- Docker Build Mode section (referenced old Streamlit Dockerfile args) replaced with clean no-Docker and Docker start commands.

---

### React Build — Clean Compile
`npm run build` completed with zero TypeScript errors and zero warnings across all 3,884 modules and 20 pages. Fresh build copied to `backend/app/static/`.

---

## Impact

- `pip install -r requirements.txt` is now ~200 MB lighter (no Streamlit + Torch transitive deps from plotly).
- Docker image build is faster and smaller (no Streamlit layer).
- Port 8765 is no longer in use. The only port is **8767** (no-Docker) / **8766** (Docker).
- New team members reading the README get an accurate picture of the current stack from day one.

---

## What the React Dashboard Covers (Full Feature Parity)

| Streamlit Page | React Replacement |
| --- | --- |
| Overview / KPI cards | `/` — Overview with Tremor KPI cards, trend charts, leaderboard |
| Store Detail | `/detail` — Per-store walk-in analytics, date filter |
| Reports | `/reports` — Walk-in sessions, image scan log, CSV downloads |
| Frame Review / QA | `/frame-review` — Paginated frame QA with approve/reject |
| Store Admin | `/admin/stores` — Full store CRUD, Drive sync toggle |
| User Management | `/admin/users` — User CRUD, password reset, role assignment |
| Store Access | `/admin/store-access` — Dual-panel listbox store access management |
| Role & Permissions | `/admin/roles` — Role CRUD, bulk permission checkboxes |
| Employee Management | `/admin/employees` — Employee image upload per store |
| Camera Zones | `/admin/cameras` — Camera zone configuration |
| Store Master | `/admin/store-master` — CSV upload, state/zone/city metadata |
| Activity Logs | `/admin/activity` — Audit trail of all admin actions |
| Scheduler | `/scheduler` — Pipeline run status, manual trigger, live progress |
| Model Accuracy | `/model-accuracy` — YOLO vs GPT accuracy metrics |
| Model Feedback | `/model-feedback` — QA feedback management |

---

## Validation

- `npm run build` → zero errors, 3,884 modules, 20 pages.
- `GET http://localhost:8767/api/health` → `{"status":"ok","service":"iris-api"}`.
- Login, dashboard, reports, frame review, scheduler — all confirmed working.

---

## Rollback Plan

There is no rollback path for Streamlit. The files have been deleted and pushed to `main`. If Streamlit were needed again (it should not be), it would require restoring from git history:

```powershell
git show HEAD~1:src/iris/iris_dashboard.py > src/iris/iris_dashboard.py
```

This is not expected or recommended.

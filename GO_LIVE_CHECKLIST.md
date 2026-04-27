# IRIS Go-Live Checklist — Cross-AI Handoff

Last updated: 2026-04-27
Active phase: Phase 1 complete, Phase 2 in progress

---

## Port Map

| Port | Service | Status |
|------|---------|--------|
| 8765 | Streamlit (existing) | Live, untouched |
| 8766 | FastAPI + React (new) | Live, no-docker |

---

## Phase 1 — FastAPI + React Stack Live (DONE)

- [x] `backend/requirements.txt` — fastapi, uvicorn, pydantic-settings, python-jose, passlib, sqlalchemy, asyncpg, celery, redis, httpx installed
- [x] `scripts/start_api_server.py` — no-docker launcher, PYTHONPATH wired, port 8766
- [x] FastAPI server running on port 8766 (health: `GET /api/health` → `{"status":"ok"}`)
- [x] Login working: custom pbkdf2_sha256 hash (IRIS format, not passlib) verified in `platform_data.py`
- [x] `GET /api/auth/login` + `GET /api/auth/me` — JWT auth working
- [x] `GET /api/dashboard/overview` — real SQLite metrics (falls back from Postgres)
- [x] `GET /api/detail/stores` — real store list from SQLite store_registry
- [x] `GET /api/detail/{store_id}/metrics` — footfall/bounce/dwell per store
- [x] `GET /api/detail/walkins` — all walkin sessions (empty until GPT pipeline runs)
- [x] `GET /api/detail/{store_id}/walkins` — walkins filtered by store
- [x] React frontend built and deployed to `backend/app/static/`
- [x] `StoreDetail.tsx` — dynamic store selector + 13-column walkin sessions table
- [x] `Overview.tsx` — real metrics from `/api/dashboard/overview`
- [x] `CHANGE_LEDGER.md` updated

---

## Phase 2 — Wire Real Pipeline Data (IN PROGRESS)

- [ ] Run GPT pipeline for at least one store — populates `onfly_walkin_sessions` table
- [ ] Verify walk-in sessions appear in React StoreDetail table
- [ ] `SchedulerDashboard.tsx` — wire `GET /api/jobs` to real pipeline_run_log status
- [ ] Add time-series chart data endpoint: `GET /api/dashboard/traffic?store_id=X&days=7`
- [ ] Add `Overview.tsx` traffic chart (currently shows placeholder)
- [ ] Change default password from `ChangeMe123!` before cloud go-live

---

## Phase 3 — Cloud Deployment (NOT STARTED)

- [ ] Set up Linux VM or cloud instance
- [ ] Install Python 3.11+, create venv, install requirements
- [ ] Copy `deploy/no_docker/.env.example` → `/opt/iris/shared/iris.env`, fill secrets
- [ ] Set `IRIS_ENV_FILE=/opt/iris/shared/iris.env`
- [ ] Install systemd services: `deploy/no_docker/linux/iris-web.service`, `iris-api.service`
- [ ] Expose port 8766 behind reverse proxy (nginx)
- [ ] Set real `JWT_SECRET` (not default `change_me_in_env`)
- [ ] Set real `OPENAI_API_KEY`, `GOOGLE_API_KEY`
- [ ] Verify login + scheduler dashboard on cloud URL

---

## Key Files Changed in Phase 1

| File | What Changed |
|------|-------------|
| `backend/app/db/platform_data.py` | Fixed PIL crash in auth; added custom pbkdf2 verify; added `get_walkin_sessions()` |
| `backend/app/api/routes_detail.py` | Added `/walkins` and `/{store_id}/walkins` endpoints |
| `frontend/src/api/client.ts` | Added `listStores`, `fetchStoreMetrics`, `fetchWalkins`, `WalkinSession` type |
| `frontend/src/pages/StoreDetail.tsx` | Dynamic store selector + full sessions table |
| `scripts/start_api_server.py` | No-docker FastAPI launcher |
| `backend/app/static/` | React build (rebuilt after StoreDetail changes) |

---

## How to Start the API Server (No Docker)

```bash
# From repo root:
python scripts/start_api_server.py

# Or directly:
PYTHONPATH="$(pwd):$(pwd)/src" python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8766
```

## How to Rebuild React After Frontend Changes

```bash
cd frontend
npm run build
cp -r dist/. ../backend/app/static/
# Restart uvicorn (or it will pick up static changes automatically)
```

---

## Known Issues / Blockers

1. **Walk-in sessions table is empty** — No GPT pipeline run has completed yet against the live SQLite DB. Run the onfly pipeline with `--enable-gpt` to populate `onfly_walkin_sessions`.
2. **Password must be changed** — Default password `ChangeMe123!` is in the DB. Run `scripts/add_user.py` with a new password before cloud go-live.
3. **Postgres not running** — All reads fall back to SQLite. This is fine for no-docker local. For cloud, Postgres optional but recommended.
4. **JWT_SECRET is default** — `backend/app/config.py` defaults to `change_me_in_env`. Set `JWT_SECRET` env var in production.

---

## For the Next AI Agent

Pick up from: **Phase 2, item 1** — run GPT pipeline and verify walkin sessions appear in React.

The React UI is at `http://localhost:8766/`. Login with:
- Email: `vishal.nayak@kushals.com`
- Password: `ChangeMe123!`

After login, go to "Store Detail" page and select a store — the walk-in sessions table will populate once the pipeline runs.

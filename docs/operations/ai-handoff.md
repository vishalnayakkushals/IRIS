# AI Engine Context Handoff

**Purpose:** Provide this file to any new AI agent (Gemini, Codex, Claude, Cursor) to instantly resume the modernization of the IRIS App without hallucinating or losing context.

## 1. Project Goal
Modernize the IRIS retail intelligence platform (originally a Streamlit MVP with SQLite) into a **React (Shadcn/Tremor) + FastAPI + PostgreSQL** stack designed for deployment on AWS EC2.

## 2. Completed Phases 
*The exact detailed file modifications are strictly logged in `CHANGE_LEDGER.md`.*
* **Phase 1 (Infrastructure & Router Scaffold):** Bootstrapped the frontend React + Vite + Tailwind 4 architecture. Added Shadcn App shells, Tremor KPIs, and configured Vite proxies to the new FastAPI `routes_dashboard.py`.
* **Phase 2 (UI Migrations):** The legacy Streamlit dashboards are purely React pages now.
  * `/overview` mapped to `frontend/src/pages/Overview.tsx`
  * `/scheduler` mapped to `frontend/src/pages/SchedulerDashboard.tsx`
  * `/detail` mapped to `frontend/src/pages/StoreDetail.tsx`
  * `/quality` mapped to `frontend/src/pages/QualityFeedback.tsx`
  * `/admin` mapped to `frontend/src/pages/StoreAdmin.tsx`

## 3. Strict Development Rules for AI Agents
1. **Source of Truth:** ALWAYS read `CHANGE_LEDGER.md` before writing code to understand what the last agent did. ALWAYS update `CHANGE_LEDGER.md` when you finish a block of work.
2. **Commit Often:** Run `git add . && git commit -m "..." && git push origin main` after logical checkpoints. This repository acts as a local AWS staging environment.
3. **No New Root Folders:** Keep UI in `frontend/src/pages` and API in `backend/app/api`.
4. **Environment:** No `.env.local` files for storing production secrets; assume the AWS EC2 environment handles injecting secrets via OS-level `Systemd` or `nssm`.

## 4. Next Immediate Tasks (Resume Here!)
If you are a new AI Agent taking over, start with **Phase 3: Database Switch**.
- [ ] Read `backend/app/config.py` and `backend/app/db/session.py`.
- [ ] Using the Alembic configuration we initialized, run the first schema upgrade to transition the SQLite tables (`pipeline_run_log`, `store_registry`) into the native PostgreSQL schema.
- [ ] Connect the empty React Data Tables (like those inside `QualityFeedback.tsx` or `StoreDetail.tsx`) to pull actual database rows via FastAPI JSON endpoints.
- [ ] Run the `scripts/mock_ingest.py` Load Validator to guarantee the Celery queues do not deadlock the new Postgres driver under a 150-store load.

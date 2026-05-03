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

### 2026-05-03 - Remove Default Store Field From Users Form

- Changed paths:
  - `frontend/src/pages/UsersPage.tsx`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Default Store field removed from Users form**: The store-assignment dropdown (`StoreSearchSelect`) was removed from both the Add User and Edit User forms. Store access is now managed exclusively via the Store Access page (dual listbox). Removed `StoreSearchSelect` component, `stores` state, `adminListStores()` call, and the `stores` prop from `UserForm`. The `store_id` value is preserved in the database for existing users and still sent to the API on update; it is simply no longer editable from this page.

### 2026-05-03 - Store Access Dual Listbox, YOLO+GPT Parallel, Login Forgot Password, User Password Change

- Changed paths:
  - `frontend/src/pages/StoreAccess.tsx` (complete rewrite)
  - `frontend/src/pages/Login.tsx`
  - `frontend/src/pages/UsersPage.tsx`
  - `src/iris/onfly_pipeline.py`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Store Access dual listbox**: Replaced the old grid toggle UI with a professional dual-panel listbox. Left panel = Available stores, right panel = Granted Access. Panels have search, "Select all/Deselect all", click-to-highlight, double-click-to-move instantly. Arrow buttons move selected or all filtered. State/Zone cascading filter dropdowns. "Grant All Stores" toggle button. Store metadata (city/state/zone) merged from `adminListStoreMaster()` for filtering.
  - **YOLO+GPT parallel execution**: Moved `_gpt_pool` creation before the YOLO loop so GPT futures are submitted immediately for each relevant image as YOLO processes it. Live progress now reflects GPT completions during the YOLO scan (drain loop checks `_pf.done()` per iteration). Phase 2 waits for any remaining in-flight futures. Thread-safe: SQLite writes remain on main thread only; `_run_gpt` calls only OpenAI HTTP (no DB).
  - **Login forgot password**: Added "Forgot password?" link below Sign In button. Expands an amber info box: "Contact your IRIS administrator to reset your password from the Users page."
  - **User password change in edit form**: Edit form (non-new user) now shows optional "Change Password" field with show/hide toggle. If filled, `adminResetPassword` is called after update. New password is displayed prominently in a green banner toast (10-second display with manual dismiss) so admin can share it with the user.

### 2026-05-03 - Delete CTO Bot, Admin UX Overhaul, QA Accuracy Optimisation

- Changed paths:
  - `CTO/` (deleted — all files)
  - `tools/cto_bot/` (deleted — all files)
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_qa.py`
  - `backend/app/api/routes_reports.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/EmployeeManagement.tsx`
  - `frontend/src/pages/ModelFeedback.tsx`
  - `frontend/src/pages/RolePermissions.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreAccess.tsx`
- Summary:
  - **Deleted CTO bot entirely**: `CTO/` (perf_cycle, perf_analyze, perf_watch, perf_run, perf_common + batch scripts) and `tools/cto_bot/` (cto_bot.py, workflow template). Confirmed zero imports or references across all .py/.ts/.tsx/.json/.yml project files. CTO bot was a standalone HTTP response-time observer for Streamlit on port 8765 — no production dependency.
  - **Admin pages use global store**: CameraZones, EmployeeManagement, and ModelFeedback now use `useStore()` context (TopNav global selector) instead of their own `adminListStores()` + `<StoreSelect>` per-page. Store selection is now single-point from the top navigation.
  - **CameraZones "All Stores" guard**: Renders a "select a specific store" prompt instead of an empty table when no store is active.
  - **EmployeeManagement "All Stores" view**: When global store is empty, calls new `GET /admin/employees` endpoint (no filter) and shows all employees across all stores with a store-ID badge on each card. Upload button is hidden in All Stores mode.
  - **New backend endpoint**: `GET /admin/employees` returns all employees across all stores ordered by store then name.
  - **Store Access bulk toggle**: Added "Select All" and "Clear All" buttons to the store-access grid so admins can grant a user access to all stores in one click.
  - **Roles & Permissions bulk checkboxes**: `PermissionMatrix` header now has a master checkbox per column (Read / Write) that selects or clears all rows. Supports indeterminate state when some but not all rows are checked.
  - **Scheduler GPT default ON**: `gptEnabled` state in SchedulerDashboard now defaults to `true`. Previously defaulted to `false`, silently disabling GPT on every manual sync unless the user remembered to tick the box.
  - **Scheduler always tracks global store**: Removed the `if (globalStoreId)` guard on the sync effect — now switches to "All Stores" (empty) correctly when the TopNav selector is cleared.
  - **QA accuracy endpoint optimised**: `GET /qa/accuracy/:store_id` replaced Python-side row-by-row counting with a single SQL `COUNT + SUM(CASE ...)` aggregate query — eliminates loading every feedback row into memory for stats computation.
  - **ModelFeedback redundant call removed**: `reportsModelAccuracy()` was called twice (on mount and after retrain); now called only on mount and after retrain separately.
  - **Reports date-mismatch fix** (routes_reports.py): `_image_only_dates()` helper appends placeholder rows for dates with images but no GPT sessions into both Footfall Detail and Validation downloads. `walkins-qa` endpoint now LEFT JOINs `onfly_image_state` by `(store, date, camera_id)` to return real `gdrive:` image IDs for QA Review thumbnails.

### 2026-05-01 - UX: Blank-first load, single filter, CSV dedup, run history controls
- Changed paths:
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreMaster.tsx`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - Overview and Reports pages now start blank — no data fetched until user explicitly selects a store. An empty-state card prompts selection.
  - SchedulerDashboard no longer auto-selects the first store on load; starts blank.
  - StoreMaster column filters (City/State/Zone/Cluster Manager/Area Manager) now work one-at-a-time — selecting a value in one dropdown clears all others.
  - CSV import in StoreMaster now detects duplicate store_id rows before upload: shows which IDs duplicated, removes them from preview, and asks user to re-confirm before proceeding.
  - Execution History section in Scheduler: added row-limit dropdown (10/20/50/100) and Download CSV button that exports the visible run records.

### 2026-05-01 - Frontend Performance Optimizations
- Changed paths:
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/package.json` (added `@tanstack/react-virtual`)
  - `frontend/package-lock.json`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - Removed `showAnimation` from all 4 Tremor chart instances in Overview.tsx (LineChart, DonutChart, BarChart ×2). Chart entry animations were causing CPU spikes on every page load.
  - Added `useMemo` to all inline chart data transforms in Overview.tsx (`trendData`, `genderData`, `ageData`) and to computed KPI values in ReportsPage.tsx (`storeMap`, `totalWalkins`, `totalConversions`, `avgRate`).
  - Replaced flat DOM rendering in `ValidationTable` with TanStack Virtual (`@tanstack/react-virtual`). Table now renders only the ~15 rows visible in the 600px scroll window regardless of total row count (up to 5000). ValidationTable bypasses the `visibleRows` slice cap and receives all rows directly.
  - Static bundle rebuilt and copied to `backend/app/static/`.

### 2026-04-30 - Fix CI, Clean BLRJAY Data, Stop Redundant Processes
- Changed paths:
  - `.github/workflows/python-package-conda.yml`
- Summary:
  - Fixed CI failure: added `pip install -r backend/requirements.txt` so FastAPI/SQLAlchemy deps are present when pytest imports backend route modules. Added `--exclude` for node_modules and static assets in flake8. Added `--ignore` for frontend and static dirs in pytest.
  - Cleaned all BLRJAY (BLR - Jayanagar) pipeline data from SQLite: 299 walk-in sessions, 7422 image states, 15 pipeline runs, 19917 task queue entries, 101548 source file index rows, 8 run logs, 6 run metrics, 4 report index rows, 1 sync state row. Drive folder URL cleared from stores table.
  - Stopped redundant uvicorn processes on ports 8768 (PID 20492) and 8769 (PID 17944). Only port 8767 (NSSM service) remains.

### 2026-04-30 - Fix Validation Camera Matching, Update Developer Docs, Deployment Prep
- Changed paths:
  - `backend/app/api/routes_reports.py`
  - `frontend/src/pages/ReportsPage.tsx`
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_dashboard.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/routes_qa.py`
  - `backend/app/config.py`
  - `backend/app/main.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/index.css`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreDetail.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/CustomerJourneys.tsx`
  - `frontend/src/pages/EmployeeManagement.tsx`
  - `frontend/src/pages/ModelFeedback.tsx`
  - `src/iris/onfly_pipeline.py`
  - `docs/developer/developer-doc.md`
  - `docs/developer/data-flow-architecture.md`
  - `docs/deployment/deployment-readiness-report-2026-04-30.md` (new)
  - `docs/deployment/deployment-email-drafts-2026-04-30.md` (new)
  - `scripts/install_service.ps1` (new)
  - `scripts/iris_server.bat` (new)
  - `tests/test_routes_onfly.py` (new)
  - `backend/app/static/` (rebuilt frontend bundle)
- Summary:
  - Fixed validation report returning images from wrong cameras: `_resolve_session_images()` now uses camera-first priority (same-camera time-window → cross-camera fallback) so a session on D13 only matches D13 images. Added "Camera Match" column (green=Exact, red=Cross-camera) to validation table in `ReportsPage.tsx`.
  - Improved `_load_image_contexts()` date matching to handle DD-MM-YYYY display format.
  - Added CORS `expose_headers: Content-Disposition` to fix CSV downloads. Added DOM attachment fix for download anchor click.
  - Fully rewrote `docs/developer/developer-doc.md` and `docs/developer/data-flow-architecture.md` — both were referencing Streamlit-only architecture with no mention of FastAPI, React, Celery, or the on-fly pipeline.
  - Added deployment readiness report and email drafts under `docs/deployment/`.
  - Added NSSM Windows service installer script and iris_server.bat helper.

### 2026-04-30 - Stable Reports And Smoother Scheduler UX
- Changed paths:
  - `frontend/src/index.css`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/ActivityLogs-BC5gurHU.js`
  - `backend/app/static/assets/CameraZones-ZLIf7Z8q.js`
  - `backend/app/static/assets/charts-Cok2OCqZ.js`
  - `backend/app/static/assets/CustomerJourneys-C8St7UGW.js`
  - `backend/app/static/assets/EmployeeManagement-Wo1zhi17.js`
  - `backend/app/static/assets/FrameReview-BQsK46zh.js`
  - `backend/app/static/assets/index-6FNKlkDq.css`
  - `backend/app/static/assets/index-D6u4CCYI.js`
  - `backend/app/static/assets/Login-DUVoiNOO.js`
  - `backend/app/static/assets/ModelAccuracy-BcHbcbR_.js`
  - `backend/app/static/assets/ModelFeedback-DdvlkNSw.js`
  - `backend/app/static/assets/Organisation-26qK7Vp0.js`
  - `backend/app/static/assets/Overview-BsseP1Pl.js`
  - `backend/app/static/assets/QualityFeedback-CaMBElGn.js`
  - `backend/app/static/assets/ReportsPage-B2svDvfo.js`
  - `backend/app/static/assets/RolePermissions-CBW_gax0.js`
  - `backend/app/static/assets/RunDetail-B5xm6s0E.js`
  - `backend/app/static/assets/SchedulerDashboard-CT8z9QKO.js`
  - `backend/app/static/assets/StoreAccess-D0RP0ejg.js`
  - `backend/app/static/assets/StoreDetail-BGuYDM2g.js`
  - `backend/app/static/assets/StoreMapping-DzxMdyPz.js`
  - `backend/app/static/assets/StoreMaster-BtxT335H.js`
  - `backend/app/static/assets/StoreSelect-BRGRKxB9.js`
  - `backend/app/static/assets/ui-CBosKoRr.js`
  - `backend/app/static/assets/UsersPage-MMvC_tKu.js`
  - `backend/app/static/assets/vendor-lQptqJEI.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Removed auto-refresh churn from the Report page so tables stay stable for review/download, then replaced the old tab layout with dropdown-based report stack + report view selectors and a shared `10 / 100 / 500` visible-row control while keeping downloads full-size.
  - Smoothed the Scheduler / Pipeline page by making date-wise report polling silent during background refresh, slowing store-status refresh cadence, and adding an auto-sync filter so the long automation table defaults to enabled stores only.
  - Added global Recharts tooltip styling so engagement hover content stays readable instead of rendering black-on-black.

### 2026-04-30 - Dynamic Scheduler Progress And Manual Child-Folder Sync
- Changed paths:
  - `backend/app/config.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/ActivityLogs-Bqzo8vwJ.js`
  - `backend/app/static/assets/CameraZones-CZD-ICns.js`
  - `backend/app/static/assets/charts-Dcp-uvrr.js`
  - `backend/app/static/assets/CustomerJourneys-Ca9vRkKt.js`
  - `backend/app/static/assets/EmployeeManagement-1tJ7BrS5.js`
  - `backend/app/static/assets/FrameReview-BNVt3LTu.js`
  - `backend/app/static/assets/index-BPTDWKPW.js`
  - `backend/app/static/assets/index-DYrNM1ER.css`
  - `backend/app/static/assets/Login-CaNjuLd3.js`
  - `backend/app/static/assets/ModelAccuracy-nwTITG7i.js`
  - `backend/app/static/assets/ModelFeedback-DJGYYEFp.js`
  - `backend/app/static/assets/Organisation-CnBdH0MA.js`
  - `backend/app/static/assets/Overview-BwBU8YUX.js`
  - `backend/app/static/assets/QualityFeedback-DLDcAytE.js`
  - `backend/app/static/assets/ReportsPage-B4v4wOiN.js`
  - `backend/app/static/assets/RolePermissions-DceR9C-W.js`
  - `backend/app/static/assets/RunDetail-Ihv4TGUi.js`
  - `backend/app/static/assets/SchedulerDashboard-gQN0QB6B.js`
  - `backend/app/static/assets/StoreAccess-DN0SeUMz.js`
  - `backend/app/static/assets/StoreDetail-DcxZNGdf.js`
  - `backend/app/static/assets/StoreMapping-CWqOB_vN.js`
  - `backend/app/static/assets/StoreMaster-D2TWPZoh.js`
  - `backend/app/static/assets/StoreSelect-BnbDSAKm.js`
  - `backend/app/static/assets/ui-tzRwGSCQ.js`
  - `backend/app/static/assets/UsersPage-Ds_QVIF9.js`
  - `backend/app/static/assets/vendor-lQptqJEI.js`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `src/iris/onfly_pipeline.py`
  - `tests/test_routes_onfly.py`
  - `CHANGE_LEDGER.md`
- Summary:
  - Fixed the Scheduler / Pipeline page so a new run no longer looks stuck on an older 100/100 snapshot: the API now keeps track of the active run id, tolerates the short pre-listing grace window, and stops stale in-memory “running” flags from blocking fresh manual syncs.
  - Added manual sync controls for optional child-folder URL / raw Drive folder ID override, force rerun / overwrite, and a 10,000-image manual cap (with `0 = full folder`) so date-folder backfills can be kicked off from the UI without changing the mapped parent source.
  - Wired the React scheduler page to poll live progress and date-report data continuously, refreshed the store/status panel during active syncs, and rebuilt the FastAPI static bundle so the browser shows dynamic run state, override source selection, and the new force-rerun workflow.

### 2026-04-29 - Scheduler Progress Reads Runtime DB Correctly
- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/routes_reports.py`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `CHANGE_LEDGER.md`
- Summary:
  - Fixed the Scheduler / Pipeline refresh issue by making the live progress and date-wise sync report read from the on-fly runtime SQLite DB, which is the current source-of-truth that `run_onfly_pipeline()` updates in real time.
  - Fixed the deeper skip-path bug where cached images advanced no UI counters because `images_processed` and commits were not being flushed for skipped items, which made refresh look frozen during delta-heavy runs.
  - Report routes now expose live interim data from the runtime DB, and the Reports page auto-refreshes every 5 seconds for the selected store while a sync is active so management views update mid-run instead of only after final ingest.

### 2026-04-30 - Report Downloads And Thumbnail Frame Review In FastAPI UI
- Changed paths:
  - `backend/app/api/routes_qa.py`
  - `backend/app/api/routes_reports.py`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/ActivityLogs-DQBYVgt0.js`
  - `backend/app/static/assets/CameraZones-B51WuR4F.js`
  - `backend/app/static/assets/charts-Dcp-uvrr.js`
  - `backend/app/static/assets/CustomerJourneys-moeUhXsT.js`
  - `backend/app/static/assets/EmployeeManagement-DAk1AkUB.js`
  - `backend/app/static/assets/FrameReview-C5Q4vIjr.js`
  - `backend/app/static/assets/index-BDlGdo1q.js`
  - `backend/app/static/assets/index-LKUrHcsu.css`
  - `backend/app/static/assets/Login-CVnBTPEy.js`
  - `backend/app/static/assets/ModelAccuracy-XLp2Fbqv.js`
  - `backend/app/static/assets/ModelFeedback-NzRVD6IP.js`
  - `backend/app/static/assets/Organisation-DCfRJyof.js`
  - `backend/app/static/assets/Overview-BrUyGZiP.js`
  - `backend/app/static/assets/QualityFeedback-BJjhtgcI.js`
  - `backend/app/static/assets/ReportsPage-D2R4LIwN.js`
  - `backend/app/static/assets/RolePermissions-B4BhAjDZ.js`
  - `backend/app/static/assets/RunDetail-Cey3lSK7.js`
  - `backend/app/static/assets/SchedulerDashboard-C5_0ED9E.js`
  - `backend/app/static/assets/StoreAccess-DNtiMq-W.js`
  - `backend/app/static/assets/StoreDetail-Bnk9mDU4.js`
  - `backend/app/static/assets/StoreMapping-CaH7G_iG.js`
  - `backend/app/static/assets/StoreMaster-DjEIBoQb.js`
  - `backend/app/static/assets/StoreSelect-BnbDSAKm.js`
  - `backend/app/static/assets/ui-tzRwGSCQ.js`
  - `backend/app/static/assets/UsersPage-86JkHl-W.js`
  - `backend/app/static/assets/vendor-lQptqJEI.js`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added server-backed CSV download routes for summary, walk-in, and image-scan reports so the Report page can download the current filtered dataset directly from the backend instead of relying only on browser-side table exports.
  - Restored a usable frame-review workflow in the new FastAPI UI by building a live review queue from `onfly_image_state`, serving real image thumbnails from local or Google Drive sources, and letting reviewers confirm customer/staff/banner/pedestrian labels directly from the thumbnail cards.
  - Reconnected review saves to the existing QA feedback store so confirmed labels continue feeding the correction-memory / retrain flow rather than becoming a UI-only annotation step.

### 2026-04-29 - Admin Store Master Actions And Searchable Store Filters
- Changed paths:
  - `backend/app/api/routes_admin.py`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/ActivityLogs-94r3kSSM.js`
  - `backend/app/static/assets/CameraZones-BXPRVAU2.js`
  - `backend/app/static/assets/charts-Dcp-uvrr.js`
  - `backend/app/static/assets/CustomerJourneys-B4rkHjw1.js`
  - `backend/app/static/assets/EmployeeManagement-BopT_GXq.js`
  - `backend/app/static/assets/FrameReview-Cn3_-a_M.js`
  - `backend/app/static/assets/index-BJZZrzy9.js`
  - `backend/app/static/assets/index-BeiV91CK.css`
  - `backend/app/static/assets/Login-BhGw1qrS.js`
  - `backend/app/static/assets/ModelAccuracy-fumYdAqt.js`
  - `backend/app/static/assets/ModelFeedback-Bc0_GVUh.js`
  - `backend/app/static/assets/Organisation-BMuxv1HM.js`
  - `backend/app/static/assets/Overview-BgsNOslf.js`
  - `backend/app/static/assets/QualityFeedback-wNGidDyV.js`
  - `backend/app/static/assets/ReportsPage-CSzrUJ1Y.js`
  - `backend/app/static/assets/RolePermissions-UtwgVcDR.js`
  - `backend/app/static/assets/RunDetail-BSbOSAWK.js`
  - `backend/app/static/assets/SchedulerDashboard-BIE4dtma.js`
  - `backend/app/static/assets/StoreAccess-CS0J0Uir.js`
  - `backend/app/static/assets/StoreDetail-D1ypSlP9.js`
  - `backend/app/static/assets/StoreMapping-jE9hHdOK.js`
  - `backend/app/static/assets/StoreMaster-Cx8iTrbh.js`
  - `backend/app/static/assets/StoreSelect-BxIiw7TL.js`
  - `backend/app/static/assets/ui-CL4sq9tf.js`
  - `backend/app/static/assets/UsersPage-BfncX1a0.js`
  - `backend/app/static/assets/vendor-lQptqJEI.js`
  - `frontend/src/api/client.ts`
  - `frontend/src/components/StoreSelect.tsx`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/CustomerJourneys.tsx`
  - `frontend/src/pages/EmployeeManagement.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/ModelFeedback.tsx`
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreDetail.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `frontend/src/pages/StoreMaster.tsx`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added an admin-safe delete route for Store Master rows and upgraded the Store Master list endpoint to join `stores` so store name is visible alongside master metadata.
  - Built a reusable searchable store picker with a solid white dropdown, store-name-plus-ID labeling, and clear/reset support, then wired it into overview, store detail, reports, scheduler, QA, camera, employee, and journey pages.
  - Finished the Store Master admin page with search, categorical filters, manual add/edit form, and delete actions so store rows can be managed without CSV-only workflows.

### 2026-04-29 - Startup Fix For Localhost Postgres Alias
- Changed paths:
  - `start_iris.ps1`
  - `CHANGE_LEDGER.md`
- Summary:
  - Fixed the `start_iris.bat` startup blocker where `.env.local` using `POSTGRES_URL=...@localhost/iris_db` was being rejected even though it points to the same local Postgres instance as `127.0.0.1`.
  - The launcher now normalizes the localhost alias to the canonical `127.0.0.1` runtime value and also normalizes `POSTGRES_SYNC_URL` if present.
  - This keeps the approved local runtime strict while avoiding false startup failures on equivalent local Postgres hostnames.

### 2026-04-29 - Production Hardening And Demo Readiness For 8767
- Changed paths:
  - `frontend/src/App.tsx`
  - `frontend/src/pages/Organisation.tsx`
  - `frontend/src/pages/StoreAccess.tsx`
  - `frontend/src/pages/RolePermissions.tsx`
  - `frontend/src/pages/StoreMaster.tsx`
  - `frontend/vite.config.ts`
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_runs.py`
  - `backend/app/db/pipeline_log.py`
  - `scripts/start_api_server.py`
  - `scripts/prepare_production_db.py`
  - `start_iris.ps1`
  - `deploy/cloud/README.md`
  - `deploy/cloud/iris-api.service`
  - `deploy/cloud/iris-web.service`
  - `deploy/cloud/iris-celery-worker.service`
  - `deploy/cloud/nginx.conf`
  - `deploy/cloud/setup_ubuntu.sh`
  - `deploy/cloud/.env.production.example`
  - `deploy/cloud/postgres_init.sql`
  - `deploy/no_docker/README.md`
  - `deploy/no_docker/.env.example`
  - `docs/operations/deployment-runbook.md`
  - `docs/operations/platform_data_cutover_inventory.md`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/ActivityLogs-BInep-HX.js`
  - `backend/app/static/assets/CameraZones-BHf3kiXl.js`
  - `backend/app/static/assets/charts-CbBUp6H1.js`
  - `backend/app/static/assets/CustomerJourneys-B59PNl53.js`
  - `backend/app/static/assets/EmployeeManagement-CI6ClsUV.js`
  - `backend/app/static/assets/FrameReview-DK3x01Oy.js`
  - `backend/app/static/assets/index-BndMtQ5X.js`
  - `backend/app/static/assets/index-CM59RqJG.css`
  - `backend/app/static/assets/Login-BSGiCzWu.js`
  - `backend/app/static/assets/ModelAccuracy-CX4-bh90.js`
  - `backend/app/static/assets/ModelFeedback-CT5zEsGp.js`
  - `backend/app/static/assets/Organisation-DSi28KoC.js`
  - `backend/app/static/assets/Overview-DAlodMlV.js`
  - `backend/app/static/assets/QualityFeedback-CaKaFlMg.js`
  - `backend/app/static/assets/ReportsPage-BfvlFl7U.js`
  - `backend/app/static/assets/RolePermissions-N41hJeO4.js`
  - `backend/app/static/assets/RunDetail-DpPTHYU1.js`
  - `backend/app/static/assets/SchedulerDashboard-PnLIB7ZA.js`
  - `backend/app/static/assets/StoreAccess-Dvm3q9UY.js`
  - `backend/app/static/assets/StoreDetail-8NL5fH3S.js`
  - `backend/app/static/assets/StoreMapping-CTK6aTSK.js`
  - `backend/app/static/assets/StoreMaster-CJ6irXP5.js`
  - `backend/app/static/assets/ui-_P2Jp0dg.js`
  - `backend/app/static/assets/UsersPage-DtFQk7-t.js`
  - `backend/app/static/assets/vendor-CKiCRchC.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Hardened the single supported `8767` runtime by removing stale `8766` defaults from the API launcher, making the standard `start_iris.bat` path call the supported API server script without hot reload, and tightening run-detail lookup to query exact run IDs.
  - Made the React app more production-shaped by route-splitting the app, adding manual chunk output, and fixing the washed-out admin save buttons so management-facing forms remain clearly usable in the demo.
  - Upgraded Store Master import to be business-friendly: CSV/TSV parsing now recognises messy headers, infers store matches from store name / short code / gofrugal name / outlet ID, and can create missing store shells automatically instead of blocking the operator.
  - Rewrote deployment-facing docs and cloud artifacts around one supported production story: FastAPI + React on `8767`, PostgreSQL only, and schema bootstrap through `scripts/prepare_production_db.py` instead of Alembic.

### 2026-04-28 - Startup Hardening For Port 8767
- Changed paths:
  - `start_iris.ps1`
  - `backend/app/config.py`
  - `CHANGE_LEDGER.md`
- Summary:
  - Hardened the local `8767` startup path to use only the approved interpreter path resolved by the launcher for the single supported startup flow `start_iris.bat` → `start_iris.ps1`.
  - Added fail-fast validation in `start_iris.ps1` so startup stops if `.env.local` is missing, if `POSTGRES_URL` is missing or incorrect, if `JWT_SECRET` is missing, or if `API_PORT` is changed away from `8767`.
  - Removed stale test-store defaults from `backend/app/config.py` by clearing the default `store_id` and aligning the fallback Postgres URI with the approved local configuration.

### 2026-04-28 - Store Master CSV And TSV Upload
- Changed paths:
  - `frontend/src/pages/StoreMaster.tsx`
  - `start_iris.ps1`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/index-B4q25CrQ.css`
  - `backend/app/static/assets/index-BYE_eSKJ.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added real file upload support for Store Master imports so the page now accepts `.csv`, `.tsv`, and pasted data with preview before import.
  - Normalized common header variants to the canonical field names expected by the backend and filtered out blank rows safely.
  - Tightened the local launcher further so the single supported runtime path stays reproducible through `start_iris.bat`.

### 2026-04-28 - FastAPI React Management Demo Polish
- Changed paths:
  - `frontend/src/components/layout/Sidebar.tsx`
  - `frontend/src/components/layout/TopNav.tsx`
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/StoreDetail.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `docs/operations/platform_data_cutover_inventory.md`
  - `deploy/no_docker/README.md`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/index-D9HitNxc.css`
  - `backend/app/static/assets/index-CUBkFJ5t.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Reframed the FastAPI + React app for management demo use: dynamic branding from Organisation settings, clearer store names, report tables that keep headers even when empty, and a guided data-sync console that removes fake legacy queue behaviour.
  - Updated the main handoff-facing docs to align with the single supported FastAPI + React app on `http://localhost:8767`.

## Module Registry
| Module/File | Responsibility |
|---|---|
| `frontend/src/components/StoreSelect.tsx` | Shared searchable store picker with clean dropdown styling, store-name-plus-ID rendering, and resettable store filtering across admin/report pages. |
| `src/iris/iris_dashboard.py` | Streamlit UI, navigation, auth flow, operations/access pages, configuration UI. |
| `src/iris/iris_analysis.py` | Store image analysis pipeline, detector abstraction, metrics, exports, tracking logic. |
| `src/iris/store_registry.py` | Store/user/role DB logic, source sync adapters (Drive/S3/local), audit state. |
| `src/iris/drive_delta_sync.py` | Scheduled Google Drive delta-sync engine: first full pull, latest-folder delta pulls, multi-queue downloads, and deletion tombstones. |
| `src/iris/secret_store.py` | Encrypted local secret storage for API keys (Fernet-based key save/load/delete). |
| `src/iris/event_queue.py` | Local event queue abstraction for async processing. |
| `src/iris/entrance_pipeline.py` | Deterministic entrance-camera classifier (zone logic, poster/staff/passers filtering, per-track audit JSON). |
| `src/run_dashboard.py` | Streamlit entrypoint for package-safe execution in Docker/local. |
| `scripts/drive_delta_sync_scheduler.py` | Daily 6 AM scheduler wrapper for autonomous sync execution. |
| `scripts/daily_feedback_reprocess.py` | Daily feedback-aware retrain/reprocess runner with end-of-day summary JSON export. |
| `scripts/evaluate_chatgpt_vision_batch.py` | Batch ChatGPT vision evaluator: GDrive sync, structured JSON inference, business-rule filtering, and accuracy/mismatch/confusion exports vs ground truth. |
| `scripts/gpt_eval_scheduler.py` | Dedicated daily GPT-eval scheduler for TEST_STORE-style capped runs, isolated from YOLO scheduler cycles. |
| `scripts/yolo_relevance_scan.py` | Stage-1 local relevance filter: counts images, runs YOLO person detection, and exports relevant/irrelevant lists for downstream GPT scan. |
| `scripts/gpt_post_relevance_test.py` | Test-folder GPT post-relevance pipeline: per-entity GPT labels, YOLO-vs-GPT audit, reviewer override application, and annotated review artifacts. |
| `scripts/yolo_relevance_scheduler.py` | Daily Stage-1 scheduler wrapper that runs YOLO relevance scan at configured local time and stores cycle status in app settings. |
| `scripts/stage1_store_report.py` | Stage-1 reporting utility: aggregates store/date raw vs relevant image counts from relevance output and upserts dashboard-ready flat report. |
| `scripts/refresh_and_check.ps1` | One-command local automation: pull/build(or restart)/recreate/wait/log-scan with fast failure for troubleshooting. |
| `scripts/scheduler_worker.py` | Dedicated background scheduler worker: executes sync/feedback/retrain/predict cycles and updates scheduler runtime state in app settings. |
| `run_iris.bat` | Windows launcher wrapper for one-command IRIS refresh in restart/rebuild mode. |
| `run-iris-validation.ps1` | Local Windows secure launcher: reads API keys from local key files, sets runtime env vars, runs GPT test validation, and clears secrets from session env on exit. |
| `run-iris-normal.ps1` | Local Windows secure launcher: reads API keys from local key files, sets runtime env vars, runs normal `run_iris.bat` flow (with optional args), and clears secrets from session env on exit. |
| `scripts/store_google_api_key.py` | One-time utility to encrypt and persist Google API key in local data/secrets path. |
| `scripts/benchmark_drive_sync.py` | Throughput benchmark utility to estimate first-day and daily sync times. |
| `.dockerignore` | Excludes heavy runtime data/cache from Docker build context to reduce build time and storage usage. |
| `.env.example` | Local-safe environment template for required scheduler/runtime keys. |
| `.github/pull_request_template.md` | Mandatory PR review template aligned with SOP fields (what/why/how-to-test/UI+DB impact). |
| `SECURITY_CLEANUP_CHECKLIST.md` | Sign-off checklist to remove temporary keys/tokens and development artifacts. |
| `docs/process/b2b_projects_sop_status.md` | SOP compliance matrix for IRIS with Done/Now/Future status and action items. |
| `tests/test_iris_analysis.py` | Analysis pipeline and detector tests. |
| `tests/test_store_registry.py` | Registry, sync, access-control, and persistence tests. |
| `tests/test_drive_delta_sync.py` | Delta-sync planner/scope/deletion behavior tests. |
| `tests/test_onfly_pipeline.py` | On-fly pipeline regression tests for YOLO/GPT gating, state transitions, and export behavior. |
| `tests/test_onfly_scheduler.py` | DB-backed on-fly scheduler regression tests for browser-managed schedule loading. |
| `tests/test_routes_onfly.py` | API regression tests for manual source normalization and live-progress run-id selection on the FastAPI scheduler endpoints. |
| `release-notes/2026-04-01-onfly-pipeline.md` | Release-note summary for the on-fly pipeline rollout and deprecation note for bulk upload nav. |
| `scripts/benchmark_onfly_pipeline.py` | Before/after timing benchmark utility (3-run profile) for slowness diagnosis and optimization tracking. |
| `scripts/onfly_scheduler.py` | Hourly + nightly catch-up scheduler for on-the-fly runtime with app-setting status persistence. |
| `scripts/start_web_app.py` | No-Docker Streamlit launcher that loads managed env/config and exposes IRIS as a browser-accessible web app. |
| `scripts/start_scheduler_worker_service.py` | No-Docker launcher for the core background scheduler worker using managed runtime paths. |
| `scripts/start_onfly_scheduler_service.py` | No-Docker launcher for the DB-backed on-fly scheduler worker using managed runtime paths. |
| `scripts/local_runtime_manager.py` | No-PowerShell local runtime manager: writes env from local key files, starts/stops no-Docker web+schedulers, opens browser, and reports health/status. |
| `scripts/run_onfly_pipeline.py` | CLI wrapper for on-the-fly runtime execution (manual/hourly/nightly modes). |
| `scripts/scan_b2b_template.py` | External B2B template + SOP scanner that generates IRIS-ready incorporation reports (JSON + Markdown). |
| `scripts/setup_local_env.ps1` | Local-only secure env bootstrapper: reads API keys from key files and writes `.env.local` for Docker/run commands. |
| `scripts/optimize_docker_runtime.ps1` | Lightweight runtime switcher: stops optional high-memory services and keeps only core on-fly services running. |
| `src/iris/onfly_pipeline.py` | Lightweight URL-first runtime: source listing, YOLO relevance, optional GPT pass, idempotent state, and store/date exports. |
| `src/iris/runtime_bootstrap.py` | Shared no-Docker runtime bootstrap: env-file loading and persistent path resolution for web/scheduler startup. |
| `docs/process/onfly_pipeline_logic.md` | Canonical human-readable on-fly logic reference (stage flow, timestamp rules, session behavior, and output artifacts). |
| `docs/process/onfly_independent_app_checklist.md` | Readiness checklist for moving on-fly workflow to an independent app mode (no manual shell dependency). |
| `deploy/no_docker/README.md` | No-Docker deployment guide covering web app, schedulers, persistent layout, and VM service topology. |
| `deploy/no_docker/.env.example` | No-Docker environment template for persistent paths, browser port, and server-side secrets. |
| `deploy/no_docker/linux/iris-web.service` | Linux `systemd` template for the IRIS web app service. |
| `deploy/no_docker/linux/iris-scheduler.service` | Linux `systemd` template for the IRIS core scheduler worker. |
| `deploy/no_docker/linux/iris-onfly-scheduler.service` | Linux `systemd` template for the IRIS on-fly scheduler worker. |
| `deploy/no_docker/windows/install_nssm_services.ps1` | Windows NSSM installer for IRIS no-Docker services. |
| `deploy/no_docker/windows/README.md` | Windows no-Docker service setup notes for IRIS. |
| `iris_local_start.bat` | One-click local IRIS starter: prepares env, launches web+schedulers, and opens browser without PowerShell. |
| `iris_local_stop.bat` | One-click local IRIS stopper for the no-Docker web+scheduler runtime. |
| `iris_local_status.bat` | Quick local IRIS status/health launcher for no-Docker runtime. |
| `iris_local_open.bat` | Opens the local IRIS web URL in the default browser. |
| `tests/test_runtime_bootstrap.py` | Regression tests for no-Docker env-file loading and persistent runtime path resolution. |
| `tests/test_local_runtime_manager.py` | Regression tests for the no-PowerShell local runtime manager env/key helpers. |
| `CTO/scripts/perf_common.py` | Shared isolated CTO log utilities (single JSONL sink, path setup, run id, percentile). |
| `CTO/scripts/perf_cycle.py` | Single-command CTO run tracker: optional fix-command timing + page probe timing + run lifecycle events. |
| `CTO/scripts/perf_run.py` | Manual run lifecycle logger (start/end) for custom workflows. |
| `CTO/scripts/perf_analyze.py` | CTO analyzer for slow paths/regressions and latest markdown/csv report generation. |
| `CTO/scripts/perf_watch.py` | Continuous interval-based page probe logger for browsing-speed trend capture. |
| `CTO/run_cto_cycle.bat` | Windows wrapper to run a CTO perf cycle quickly with default dashboard URLs. |
| `CTO/run_cto_watch.bat` | Windows wrapper for continuous CTO browse-speed watch mode. |
| `CTO/README.md` | Usage and isolation guarantees for the CTO observer layer. |
| `backend/app/db/canonical_metadata.py` | Canonical Postgres target schema metadata for platform-state cutover away from SQLite and CSV-backed source-of-truth. |
| `backend/app/db/platform_data.py` | Pure-async Postgres-only data layer: auth, stores, walkin sessions, overview metrics, traffic series, pipeline runs (Phase D). |
| `backend/app/db/pipeline_log.py` | Pure-async Postgres-only pipeline run log CRUD (insert, update status, get latest per job, recent runs). |
| `backend/app/db/session.py` | SQLAlchemy async engine with production pool settings (pool_size=20, max_overflow=20, pool_pre_ping, READ COMMITTED). |
| `backend/migrations/versions/001_initial_schema_with_indexes.py` | Alembic migration: full production schema for 150-store scale with partitioned tables and production indexes. |
| `scripts/migrate_sqlite_to_postgres.py` | One-time SQLite → Postgres migration with datetime parsing, bool casting, and savepoint-per-row error isolation. |
| `scripts/prepare_production_db.py` | Production-safe Postgres schema bootstrapper that creates canonical tables and the optional track-session table without relying on Alembic. |
| `deploy/cloud/` | Ubuntu cloud deployment artifacts: setup script, postgres init, nginx config, systemd services, env template, README. |
| `docs/operations/platform_data_cutover_inventory.md` | Inventory of live SQLite tables and CSV artifacts plus the recommended single-platform cutover path to FastAPI/React. |

---

## AI HANDOFF GUIDE — Read This First Before Touching The Project

> This section is permanent. Every AI assistant or developer working on this project MUST read it before making changes.

### The App You Are Working On

IRIS is a retail store analytics platform.
- **Backend**: FastAPI (Python), Postgres 17, no Celery, no Docker for local dev
- **Frontend**: React + Vite + TypeScript + Tailwind, built to `backend/app/static/`
- **Live URL**: `http://localhost:8767` — this is the ONLY port. React + API both served here.

### How To Start The Server (After Every Windows Restart)

The server is **not a Windows service**. It does not auto-start. After every reboot:

```
Double-click:  C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS\start_iris.bat
```

`start_iris.bat` is the official local launcher. It calls `start_iris.ps1` internally. Use the `.bat` file for normal local startup.

Only if you are debugging startup itself, you may call the PowerShell script directly:
```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
powershell -ExecutionPolicy Bypass -File start_iris.ps1
```

This kills any old process on port 8767, loads `.env.local`, sets `PYTHONPATH`, and starts the supported API server script.

For the supported API runtime, `start_iris.ps1` now calls:
```powershell
python scripts/start_api_server.py
```
with `API_RELOAD=0`, so the default local run behaves like the real app instead of a hot-reload-only dev session.

### Port Rules — Non-Negotiable

| Port | What | Status |
|------|------|--------|
| **8767** | FastAPI + React (current, working) | USE THIS |
| ~~8766~~ | Old port, zombie process cleared after reboot | DO NOT USE |
| 8765 | Old Streamlit prototype | DEPRECATED, ignore |

**Do not change any port number to 8766.** The entire codebase has been migrated to 8767. Any code or config that still says 8766 is a bug — fix it to 8767.

### Python Environment — Single Local Python Only

**Do NOT use Docker, venv, conda, or any virtual environment.**

All packages are installed in the single local Python used by `start_iris.bat`.
Approved interpreter path:
`C:\Users\Kushals.DESKTOP-D51MT8S\AppData\Local\Programs\Python\Python312\python.exe`

To install missing packages:
```powershell
& "C:\Users\Kushals.DESKTOP-D51MT8S\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r backend/requirements.txt
```

To verify which Python is being used:
```powershell
where python
```

The launcher does not trust `where python`. It starts the approved interpreter path directly.

If you create a venv or use Docker, the server will fail to import packages the user already has installed.

### Postgres — Local Only, No Docker

Postgres 17 runs as a **Windows service** (auto-starts on boot). No Docker needed.

```
Host:     127.0.0.1
Port:     5432
Database: iris_db
User:     iris_user
Password: iris_password
```

Connection string (required in `.env.local`):
```
POSTGRES_URL=postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db
```

Local alias also accepted by the launcher and normalized automatically:
```
POSTGRES_URL=postgresql+asyncpg://iris_user:iris_password@localhost/iris_db
```

If `.env.local` is missing, if `POSTGRES_URL` is wrong, if `JWT_SECRET` is blank, or if `API_PORT` is changed away from `8767`, `start_iris.bat` will stop instead of starting a wrong app.

To verify Postgres is running (PowerShell):
```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" status -D "C:\Program Files\PostgreSQL\17\data"
```

To start it if not running:
```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\17\data"
```

### Alembic Migration State — CRITICAL

Alembic migrations `001` and `002` have been applied. The schema is at `head`.

**However, 8 columns were added DIRECTLY via `ALTER TABLE` outside of Alembic migrations.** These are in the live database but NOT in any migration file. Alembic does not know about them.

**DO NOT run `alembic upgrade head` or `alembic revision --autogenerate` — it will try to undo these manual changes.**

The manually added columns are:

| Table | Column | Type | Added |
|-------|--------|------|-------|
| `stores` | `sync_enabled` | BOOLEAN DEFAULT FALSE | 2026-04-28 |
| `stores` | `sync_interval_hours` | INTEGER DEFAULT 1 | 2026-04-28 |
| `model_versions` | `rollback_target_model_id` | VARCHAR(128) DEFAULT '' | 2026-04-28 |
| `qa_feedback` | `track_id` | VARCHAR(128) DEFAULT '' | 2026-04-28 |
| `qa_feedback` | `model_version` | VARCHAR(128) DEFAULT '' | 2026-04-28 |
| `qa_feedback` | `drive_link` | TEXT DEFAULT '' | 2026-04-28 |
| `qa_feedback` | `needs_review` | BOOLEAN DEFAULT FALSE | 2026-04-28 |
| `qa_feedback` | `annotated_image_path` | TEXT DEFAULT '' | 2026-04-28 |

These columns ARE reflected in `backend/app/db/canonical_metadata.py` (the SQLAlchemy ORM table definitions). The gap is only in Alembic migration files.

If you need to add more columns: use `ALTER TABLE` directly via `psql`, then add the column to `canonical_metadata.py`. Do NOT use `alembic revision`.

For fresh or production-style schema setup, use:
```powershell
python scripts/prepare_production_db.py
```

That script creates the canonical schema directly from `backend/app/db/canonical_metadata.py` and also ensures the optional `onfly_track_sessions` table exists.

### Login Credentials (Local Dev)

```
URL:      http://localhost:8767
Email:    vishal.nayak@kushals.com
Password: ChangeMe123!
```

Password is stored as `pbkdf2_sha256` hash. If login fails with 401, the hash may need regenerating — see `scripts/add_user.py`.

### .env.local — Required File (Not In Git)

All secrets live in `.env.local` in the project root. This file is gitignored. Required keys:

```
POSTGRES_URL=postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db
JWT_SECRET=<your-secret>
GOOGLE_API_KEY=<optional>
OPENAI_API_KEY=<optional>
```

The `start_iris.ps1` / `start_iris.bat` loader reads this file automatically.

### React Build — How To Deploy Frontend Changes

After ANY change to `frontend/src/**`:
```powershell
cd frontend
npm run build
Remove-Item ..\backend\app\static\assets\* -Force
Copy-Item dist\index.html ..\backend\app\static\index.html -Force
Copy-Item dist\assets\* ..\backend\app\static\assets\ -Force
```

The built files in `backend/app/static/` ARE committed to git. The `frontend/dist/` folder is gitignored.

### Key Files Quick Reference

| File | What It Does |
|------|-------------|
| `start_iris.bat` | Double-click to start server — the ONLY way to start locally |
| `start_iris.ps1` | Called by start_iris.bat — kills old process, loads .env.local, starts uvicorn |
| `.env.local` | All secrets — NOT in git, must exist on each machine |
| `backend/app/main.py` | FastAPI app entry point, registers all routers, starts auto-sync scheduler |
| `backend/app/config.py` | All settings via env vars — reads from .env.local |
| `backend/app/db/canonical_metadata.py` | SQLAlchemy table definitions — source of truth for DB schema |
| `scripts/prepare_production_db.py` | Supported schema/bootstrap entry point for production-style Postgres setup |
| `backend/app/api/routes_onfly.py` | Pipeline execution + background auto-sync loop |
| `backend/app/api/routes_admin.py` | Admin CRUD, organisation settings, and Store Master CSV/TSV upload handling |
| `frontend/src/api/client.ts` | All API calls from React — add new endpoints here |
| `frontend/src/pages/SchedulerDashboard.tsx` | Web-controlled IRIS data sync console for manual runs, automation visibility, and execution history |
| `frontend/src/pages/ReportsPage.tsx` | Management-facing reports view with summary, footfall detail, and image scanning outputs |

### FastAPI + React Demo Rules

- The management demo app is the FastAPI + React app on `http://localhost:8767`
- Organisation settings are expected to drive branding in the sidebar/top bar
- Scheduler page must stay web-controlled; do not reintroduce fake Celery-only trigger buttons into the main demo path
- Report tables should keep visible headers even when there is no data
- Store Master uploads should use the backend upload endpoint for real CSV/TSV parsing, with paste import only as fallback
- Store Master import is expected to recognise messy files and map rows by store name, short code, gofrugal name, or outlet ID before creating a safe missing-store shell if needed

### 2026-04-28 - Store Master Upload Fix
- Changed paths:
  - `backend/app/api/routes_admin.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/StoreMaster.tsx`
  - `backend/app/static/index.html`
  - `backend/app/static/assets/index-B1FLDFk4.css`
  - `backend/app/static/assets/index-DFhYybkl.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Replaced the fragile browser-only Store Master import path with a real backend CSV/TSV upload endpoint at `/api/admin/store-master/upload`.
  - Kept pasted table import as fallback, but file uploads now parse on the server for better compatibility with quoted CSV/TSV data and clearer validation errors.
  - Added a user-facing validation message when uploaded rows reference store IDs that are not yet present in Store Mapping.

### What NOT To Do

- Do NOT run `alembic upgrade head` or `alembic revision --autogenerate`
- Do NOT use Docker for local development
- Do NOT create a Python venv
- Do NOT change port 8767 to 8766 or any other number
- Do NOT run `npm install` — packages are already installed
- Do NOT push `.env.local` to git

---

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

### 2026-04-28 | Port consolidation + AI handoff guide + auto-sync toggle + config cleanup
- Summary:
  - Removed all references to port 8766. The only port is now 8767 everywhere.
  - Fixed `backend/app/config.py` CORS origins (was still listing 8766 — now 8767).
  - Fixed comment typo in `start_iris.ps1` ("Clearing port 8766" → 8767).
  - Added comprehensive **AI Handoff Guide** to top of CHANGE_LEDGER covering: startup procedure, port rules, Python environment, Postgres credentials, Alembic migration state (critical — 8 columns added outside migrations), login credentials, .env.local requirements, React build process, and a DO NOT DO list.
  - Added auto-sync feature: `PUT /api/admin/stores/{store_id}/sync` toggle endpoint; background asyncio loop in main.py startup (60-second tick, triggers pipeline for stores where sync_enabled=True and interval has elapsed); `sync_enabled`/`sync_interval_hours` columns added to ORM metadata; StoreMapping UI gets toggle switch column.
  - Committed `start_iris.bat` (double-click launcher) and `start_iris.ps1` (ExecutionPolicy Bypass, .env.local loader, uvicorn on 8767).
- Changed Paths:
  - `backend/app/config.py`
  - `start_iris.ps1`
  - `start_iris.bat`
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/main.py`
  - `backend/app/db/canonical_metadata.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/StoreMapping.tsx`
  - `backend/app/static/` (React build output)
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `start_iris.bat`
  - `start_iris.ps1`
- Infra/Config Impact:
  - **Port is 8767. Do not use 8766.** Postgres PG17 runs as Windows service (auto-starts on boot). Server does NOT auto-start — run `start_iris.bat` after every reboot.
  - New endpoint: `PUT /api/admin/stores/{store_id}/sync` with body `{"sync_enabled": bool, "sync_interval_hours": int}`.
  - Two new columns live in Postgres but are NOT in any Alembic migration file: `stores.sync_enabled` and `stores.sync_interval_hours` — added via direct ALTER TABLE on 2026-04-28.
  - **DO NOT run `alembic upgrade head`** — it will conflict with the 8 manually added columns. See AI Handoff Guide above for full list.

### 2026-04-28 | Phase G+H: Full admin/reports UI — 11 React pages + backend CRUD routes
- Summary:
  - Built `routes_admin.py`: full CRUD for stores, users, roles+permissions, app settings, employees (photo upload), camera configs, location master, user store access, activity log, store master — all using SQLAlchemy async.
  - Built `routes_reports.py`: walkin sessions, store day summary, image scan results, model accuracy, stores-with-data, pipeline quality endpoints.
  - Registered both routers in `main.py` under `/api/admin` and `/api/reports`.
  - Added all new API calls to `frontend/src/api/client.ts` (admin and reports exports).
  - Built 11 new React pages: `ReportsPage`, `CustomerJourneys`, `StoreMapping`, `CameraZones`, `EmployeeManagement`, `Organisation`, `UsersPage`, `RolePermissions`, `StoreAccess`, `ModelAccuracy`, `ActivityLogs`, `StoreMaster`.
  - Rewrote `Sidebar.tsx`: collapsible Admin section with 10 sub-pages, new top-level Reports and Customer Journeys links.
  - Rewrote `App.tsx`: 18 routes total including all admin sub-paths; old `/admin` redirects to `/admin/stores`.
  - Built React and deployed to `backend/app/static/`.
- Changed Paths:
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_reports.py`
  - `backend/app/main.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/App.tsx`
  - `frontend/src/components/layout/Sidebar.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/CustomerJourneys.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/EmployeeManagement.tsx`
  - `frontend/src/pages/Organisation.tsx`
  - `frontend/src/pages/UsersPage.tsx`
  - `frontend/src/pages/RolePermissions.tsx`
  - `frontend/src/pages/StoreAccess.tsx`
  - `frontend/src/pages/ModelAccuracy.tsx`
  - `frontend/src/pages/ActivityLogs.tsx`
  - `frontend/src/pages/StoreMaster.tsx`
  - `backend/app/static/` (React build output)
- New Modules Introduced:
  - `backend/app/api/routes_admin.py`
  - `backend/app/api/routes_reports.py`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/CustomerJourneys.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/EmployeeManagement.tsx`
  - `frontend/src/pages/Organisation.tsx`
  - `frontend/src/pages/UsersPage.tsx`
  - `frontend/src/pages/RolePermissions.tsx`
  - `frontend/src/pages/StoreAccess.tsx`
  - `frontend/src/pages/ModelAccuracy.tsx`
  - `frontend/src/pages/ActivityLogs.tsx`
  - `frontend/src/pages/StoreMaster.tsx`
- Infra/Config Impact:
  - No new env vars. No new DB tables. All endpoints use existing Postgres schema from `canonical_metadata.py`.
  - Employee photo upload writes to `data/employee_assets/{store_id}/` on the server filesystem.

### 2026-04-28 | Streamlit retirement: deprecation banner + React as primary UI in deployment docs
- Summary:
  - Added persistent info banner in `iris_dashboard.py` main() that directs all users to `http://localhost:8766` (React + FastAPI), explains Streamlit is in maintenance mode, and will be retired when full React parity is achieved.
  - Rewrote `deploy/no_docker/README.md` Runtime shape section to put React + FastAPI (port 8766) as the primary entry point, Streamlit (port 8765) as legacy admin fallback.
  - Updated VM go-live checklist to list port 8766 as the main exposed port, port 8765 as internal admin only, and include Postgres + `alembic upgrade head` steps.
  - Streamlit code and `start_web_app.py` are intentionally preserved — React does not yet have full feature parity (store config, employee management, image viewer with annotations, model feedback). Full removal is Phase 3.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `deploy/no_docker/README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Operators should update reverse proxies to route primary traffic to port 8766.
  - Streamlit remains available at port 8765 for admin operations not yet in React.

### 2026-04-28 | Phase F: React UI completions — RunDetail, QA Review, run history links
- Summary:
  - Added `RunDetail.tsx` page (`/runs/:runId`): stage timeline with status dots, meta grid (store, trigger, start/end, duration, remarks), linked from run history table in SchedulerDashboard.
  - Rewrote `QualityFeedback.tsx` from placeholder to real QA review table: loads last 100 walk-in sessions, per-row approve/reject buttons, summary cards, filter by review state.
  - Fixed `routes_runs.py`: was calling old SQLite `get_recent_runs(db_path, limit)` signature — switched to async Postgres version. Added `GET /api/runs/{run_id}` endpoint.
  - Added clickable job-name links in SchedulerDashboard Run History tab that navigate to `/runs/:runId`.
  - Built and deployed React to `backend/app/static/`.
- Changed Paths:
  - `frontend/src/pages/RunDetail.tsx`
  - `frontend/src/pages/QualityFeedback.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `backend/app/api/routes_runs.py`
  - `backend/app/static/` (rebuilt React dist)
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `frontend/src/pages/RunDetail.tsx`
- Infra/Config Impact:
  - New API route `GET /api/runs/{run_id}` — requires Postgres to be running.

### 2026-04-28 | Phase E: BoT-SORT tracker + session state machine
- Summary:
  - Added `src/iris/bot_sort_tracker.py`: pure-Python IoU-based multi-object tracker (BoT-SORT-compatible API). No external dependencies. Greedy IoU matching, configurable max_age/min_hits, static-object suppression via bbox-stability check.
  - Added `src/iris/session_state_machine.py`: converts tracker output to classified sessions — `active_customer`, `outside_passer`, `static_object`. Produces `sessions_summary()` dict compatible with pipeline summary format.
  - Added Alembic migration `002_track_sessions.py`: `onfly_track_sessions` table with session_id, run_id, store_id, track lifecycle columns, and 3 indexes for store+date queries.
  - Added `upsert_track_sessions()` to `backend/app/db/pipeline_log.py` for async Postgres bulk upsert.
  - Extended `OnFlyConfig` with `use_tracker`, `tracker_iou_threshold`, `tracker_max_age`, `tracker_min_hits` — all optional, default off (zero impact on existing runs).
  - Integrated tracker into `run_onfly_pipeline()`: when `use_tracker=True`, calls `_yolo_detect_full_result()` to get bboxes, feeds them to the tracker per frame, finalizes sessions at run end, writes `onfly_track_sessions_{run_id}.csv` to pipeline output directory.
  - Existing pipeline behavior completely unchanged when `use_tracker=False` (default).
- Changed Paths:
  - `src/iris/bot_sort_tracker.py`
  - `src/iris/session_state_machine.py`
  - `src/iris/onfly_pipeline.py`
  - `backend/migrations/versions/002_track_sessions.py`
  - `backend/app/db/pipeline_log.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `src/iris/bot_sort_tracker.py`
  - `src/iris/session_state_machine.py`
  - `backend/migrations/versions/002_track_sessions.py`
- Infra/Config Impact:
  - Run `alembic upgrade head` in `backend/` to create `onfly_track_sessions` table (migration 002).
  - New `OnFlyConfig` fields are opt-in; no env var changes required.
  - Enable with `OnFlyConfig(use_tracker=True, ...)` in Celery task or CLI call.

### 2026-04-28 | Phase D security hardening: rate limiting, security headers, CORS via settings, JWT startup warning
- Summary:
  - Added `slowapi` rate limiter to `POST /api/auth/login` — 10 requests/minute per IP; 429 on breach.
  - Added security headers middleware to all responses: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`.
  - Moved CORS origins out of hardcoded list into `Settings.cors_origins` (comma-separated, configurable via env var `CORS_ORIGINS`).
  - Added startup warning log when `JWT_SECRET` is using the insecure default value.
  - Locked down CORS `allow_methods` and `allow_headers` to specific values instead of `*`.
  - Extracted `limiter` into `backend/app/limiter.py` to avoid circular import between `main.py` and routes.
- Changed Paths:
  - `backend/app/main.py`
  - `backend/app/limiter.py`
  - `backend/app/api/routes_auth.py`
  - `backend/app/config.py`
  - `backend/requirements.txt`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `backend/app/limiter.py`
- Infra/Config Impact:
  - `slowapi>=0.1.9` added to `backend/requirements.txt` — run `pip install -r backend/requirements.txt`.
  - New env var `CORS_ORIGINS` (comma-separated) — defaults to localhost:3000 + localhost:8766. Set to production domain for cloud deploy.
  - Login endpoint rate-limited to 10/minute per IP.

### 2026-04-28 | Batch cleanup: fix all "Commit pending" labels, add gitignore rules, commit cloud + migration artifacts
- Summary:
  - Replaced all 80 "Commit pending" labels in CHANGE_LEDGER with "committed" since the backing commits already existed in git history.
  - Added `frontend/node_modules/`, `frontend/dist/`, `deploy/no_docker/runtime_logs/`, and `.claude/settings.local.json` to `.gitignore` to stop them appearing as untracked.
  - Committed `backend/migrations/versions/001_initial_schema_with_indexes.py` (Alembic full production schema) and `deploy/cloud/` (Ubuntu deployment artifacts) that were untracked since Phase D.
  - Committed `scripts/add_user.py` utility and `frontend/package.json` package update.
  - Minor Sidebar.tsx cleanup (removed unused import line).
- Changed Paths:
  - `CHANGE_LEDGER.md`
  - `.gitignore`
  - `backend/migrations/versions/001_initial_schema_with_indexes.py`
  - `deploy/cloud/` (setup_ubuntu.sh, postgres_init.sql, nginx.conf, iris-api.service, iris-celery-worker.service, iris-web.service, README.md)
  - `scripts/add_user.py`
  - `frontend/package.json`
  - `frontend/src/components/layout/Sidebar.tsx`
- New Modules Introduced:
  - `backend/migrations/versions/001_initial_schema_with_indexes.py`
  - `deploy/cloud/setup_ubuntu.sh`
  - `deploy/cloud/postgres_init.sql`
  - `deploy/cloud/nginx.conf`
  - `deploy/cloud/iris-api.service`
  - `deploy/cloud/iris-celery-worker.service`
  - `deploy/cloud/iris-web.service`
  - `scripts/add_user.py`
- Infra/Config Impact:
  - `deploy/cloud/setup_ubuntu.sh` is the one-command Ubuntu setup script for cloud go-live.
  - `backend/migrations/versions/001_initial_schema_with_indexes.py`: run `alembic upgrade head` once to create all 29 Postgres tables.

### 2026-04-28 | Phase C + D complete: cloud deployment artifacts and Postgres-only FastAPI layer
- Summary:
  - Phase D: Eliminated SQLite from FastAPI entirely — rewrote `platform_data.py` and `pipeline_log.py` as pure-async Postgres using SQLAlchemy asyncpg. All 8 API endpoints backed by Postgres only.
  - Added Alembic migration `001_initial_schema_with_indexes.py` with full production schema: 29 tables, partitioned `onfly_walkin_sessions` and `onfly_pipeline_run_events`, 10 critical indexes — ready for 150-store scale.
  - Added `scripts/migrate_sqlite_to_postgres.py` for one-time SQLite → Postgres migration with savepoint-per-row error isolation, datetime parsing, and bool casting.
  - Fixed `JobStatus` Pydantic model for Postgres `datetime` return type using `field_serializer`.
  - Phase C: Created `deploy/cloud/` Ubuntu deployment package — `setup_ubuntu.sh`, `postgres_init.sql`, `nginx.conf`, three `systemd` service files, `.env.production.example`, and `README.md`.
  - 3× full test pass: login, all 8 API endpoints, wrong-password rejection — Postgres only, no SQLite fallback.
- Changed Paths:
  - `backend/app/db/platform_data.py`
  - `backend/app/db/pipeline_log.py`
  - `backend/app/db/session.py`
  - `backend/app/api/routes_auth.py`
  - `backend/app/api/routes_dashboard.py`
  - `backend/app/api/routes_detail.py`
  - `backend/app/api/routes_jobs.py`
  - `backend/app/models/jobs.py`
  - `backend/alembic.ini`
  - `backend/migrations/versions/001_initial_schema_with_indexes.py`
  - `scripts/migrate_sqlite_to_postgres.py`
  - `deploy/cloud/`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/migrate_sqlite_to_postgres.py`
  - `deploy/cloud/`
- Infra/Config Impact:
  - Postgres required: `postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db`.
  - Run `alembic upgrade head` in `backend/` to create all tables.
  - Run `python scripts/migrate_sqlite_to_postgres.py` once to migrate existing data.
  - Env vars: `POSTGRES_URL`, `JWT_SECRET` (required in `.env.local` for local dev).
  - Local Postgres (Win): `& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\17\data"`.

### 2026-04-27 | Phase B Complete — Real data wired into all React pages

- Summary:
  - Built `scripts/seed_phase_b_data.py` that seeds `onfly_walkin_sessions` (213 sessions across BLRJAY/BLRRRN from real YOLO image data) and `pipeline_run_log` (15 real run records from `onfly_pipeline_runs`) — enables React UI to show live data without requiring completed GPT runs.
  - Added `get_traffic_series()` and `get_pipeline_runs()` to `platform_data.py`.
  - Added `GET /api/dashboard/traffic` (daily walk-in counts by store, 30-day window) and `GET /api/dashboard/pipeline-runs` endpoints to `routes_dashboard.py`.
  - Rewrote `Overview.tsx` with real traffic bar chart (Tremor BarChart, Customers/Staff/Conversions per date), store filter dropdown, and real metric cards.
  - Updated `client.ts` with `fetchTraffic`, `fetchDashboardRuns`, `TrafficPoint` type.
  - Rebuilt React and deployed to `backend/app/static/`.
  - 3× full test pass: all 10 API endpoints, auth boundary, wrong-password rejection, all 6 stores' metrics.
- Changed Paths:
  - `backend/app/db/platform_data.py`
  - `backend/app/api/routes_dashboard.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/Overview.tsx`
  - `backend/app/static/` (rebuilt React dist)
  - `scripts/seed_phase_b_data.py`
  - `GO_LIVE_CHECKLIST.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/seed_phase_b_data.py`
- Infra/Config Impact:
  - Run `python scripts/seed_phase_b_data.py` once on a fresh DB to populate demo data.
  - Safe to re-run — deletes only seeded rows (match_reason='seeded'), not GPT-generated rows.

### 2026-04-27 | Phase 1 Go-Live — FastAPI + React no-docker

- Summary:
  - Fixed login crash caused by store_registry.py importing PIL at module level — rewrote platform_data.py auth to use passlib-free custom pbkdf2 verify directly against SQLite, no store_registry import.
  - Added `get_walkin_sessions()` to platform_data.py and `GET /api/detail/walkins`, `GET /api/detail/{store_id}/walkins` routes to routes_detail.py.
  - Rewrote `StoreDetail.tsx` with dynamic store selector dropdown (from /api/detail/stores), real walk-in sessions table with 13 key columns, and role/entry-type color badges.
  - Added `listStores`, `fetchStoreMetrics`, `fetchWalkins` and typed `WalkinSession` interface to client.ts.
  - Created `scripts/start_api_server.py` no-docker FastAPI launcher (mirrors start_web_app.py pattern, sets PYTHONPATH, runs uvicorn on port 8766).
  - React build updated and deployed to `backend/app/static/` — port 8766 serves both React SPA and REST API.
  - Login confirmed working with IRIS custom pbkdf2_sha256 hash format (pbkdf2_sha256$salt$hex_digest).
- Changed Paths:
  - `backend/app/db/platform_data.py`
  - `backend/app/api/routes_detail.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/StoreDetail.tsx`
  - `backend/app/static/` (rebuilt React dist)
  - `scripts/start_api_server.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/start_api_server.py`
- Infra/Config Impact:
  - FastAPI server runs no-docker via `python scripts/start_api_server.py` on port 8766.
  - Default user password is `ChangeMe123!` — must be changed before cloud go-live.
  - No Docker, no Postgres required — SQLite fallback is fully functional.

### 2026-04-27 | committed
- Summary:
  - Added a FastAPI platform-data bridge that prefers Postgres-backed auth, store registry, and on-fly session reads while falling back to the current SQLite runtime when Postgres is unavailable or not backfilled.
  - Updated backend auth, overview, and store-detail routes to use the bridge instead of hardcoded local CSV parsing for their primary data access path.
  - Extended pipeline run log access to dual-write and prefer Postgres reads while preserving SQLite writes/reads for backward compatibility during cutover.
- Changed Paths:
  - `backend/app/db/platform_data.py`
  - `backend/app/db/pipeline_log.py`
  - `backend/app/api/routes_auth.py`
  - `backend/app/api/routes_dashboard.py`
  - `backend/app/api/routes_detail.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `backend/app/db/platform_data.py`
- Infra/Config Impact:
  - FastAPI runtime now attempts Postgres access through SQLAlchemy/asyncpg first for selected domains, but automatically falls back to SQLite when Postgres is unavailable or not yet populated.

### 2026-04-27 | committed
- Summary:
  - Reworked `Manual data sync of IRIS` into a simpler one-section-at-a-time dashboard with clear views for status, run now, run list, run detail, stage timeline, and scheduler history.
  - Added real local scheduler-service state visibility so the page now distinguishes a saved schedule from an actually running on-fly scheduler service.
  - Made main report summaries fall back to on-fly partial/YOLO-stage outputs so management-facing reports still show scan totals and relevance counts even when GPT output is incomplete.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-26 | committed
- Summary:
  - Mapped the live SQLite runtime tables and CSV artifacts still used by production-style paths and documented which ones must migrate vs remain export-only.
  - Defined the canonical Postgres target schema in SQLAlchemy metadata without touching the core analytics brain modules.
  - Wired Alembic to the canonical metadata and aligned backend dependency declarations for the next migration phase.
- Changed Paths:
  - `backend/app/db/canonical_metadata.py`
  - `backend/migrations/env.py`
  - `backend/requirements.txt`
  - `docs/operations/platform_data_cutover_inventory.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `backend/app/db/canonical_metadata.py`
  - `docs/operations/platform_data_cutover_inventory.md`
- Infra/Config Impact:
  - Declares `sqlalchemy`, `alembic`, and `asyncpg` in backend requirements and sets Alembic `target_metadata` to the canonical Postgres schema definition for future migrations.

### 2026-04-26 | committed
- Summary:
  - Stabilized the React/FastAPI auth flow by validating protected-page tokens through `/api/auth/me` instead of trusting any `localStorage` token string.
  - Added login-route session reuse so already-authenticated users are redirected into the app instead of seeing the login form again.
  - Fixed FastAPI React static hosting to return the SPA entry page for deep links like `/overview` and `/scheduler` while preserving `/api/*` routes.
- Changed Paths:
  - `frontend/src/App.tsx`
  - `backend/app/main.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-26 | committed
- Summary:
  - Fixed React/FastAPI login to use the real IRIS `data/store_registry.db` during local runs instead of an empty `C:\app\data\store_registry.db`, which was causing valid credentials to fail.
  - Kept Docker compatibility by resolving the default `/app/data` setting back to the repo `data/` folder automatically from backend code.
  - Fixed `/api/auth/me` so it returns the saved user profile by email instead of incorrectly trying to re-authenticate with an empty password.
- Changed Paths:
  - `backend/app/config.py`
  - `backend/app/api/routes_auth.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - No new env vars. Local backend auth now resolves the default data path to the repository `data/` folder automatically, while container `/app/data` behavior remains aligned.

### 2026-04-26 | committed
- Summary:
  - Renamed GPT/YOLO report labels to business-friendly names and grouped Report Module into `Main Reports`, `Operations Reports`, and `Model Related Reports`.
  - Kept management-facing footfall summaries in the main group while moving validation and accuracy diagnostics out of the primary review flow.
  - Restarted the local web runtime and verified the grouped report UI is live in the browser app.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-26 | committed
- Summary:
  - Scaffolding Phase 1 UI Migration using Vite, React, Shadcn, Tremor, and Lucide.
  - Added basic AppLayout, TopNav, and Sidebar shells in the frontend workspace.
  - Migrated SchedulerDashboard.tsx to use Tremor components.
  - Initialized Alembic for backend migrations and set up asynchronous Postgres connection logic in `config.py` and `db/session.py`.
  - Defined explicit AWS EC2 CI/CD deployment instructions in README and Implementation Plans.
  - Added test utilities `mock_ingest.py` and `security_audit.py`.
- Changed Paths:
  - `frontend/src/App.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `backend/app/config.py`
  - `backend/app/db/session.py`
  - `scripts/mock_ingest.py`
  - `scripts/security_audit.py`
  - `README.md`
  - `artifacts/implementation_plan.md`
- New Modules Introduced:
  - `frontend/src/components/layout/AppLayout.tsx`
  - `frontend/src/components/layout/TopNav.tsx`
  - `frontend/src/components/layout/Sidebar.tsx`
  - `backend/migrations/`
- Infra/Config Impact:
  - Defined Postgres URI `postgresql+asyncpg://iris_user:password@localhost/iris_db` for phase cutoff routing.

### 2026-04-26 | committed
- Summary:
  - Made Report Module show empty tables with column headers for every report type instead of blank panels when a store/date has no rows yet.
  - Fixed on-fly report file loading on Windows by resolving stored `/app/data/...` runtime paths back to the local workspace before reading report CSVs.
  - Verified the local web runtime after restart so the empty-table behavior is live on the browser app.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-26 | committed
- Summary:
  - Renamed business report labels to clearer store-facing names, removed the `Data Health` report option from Report Module, and kept empty GPT/QA reports visible with their column headers.
  - Preserved YOLO-stage visibility for stores with partial on-fly output by loading storewise scan results even when downstream GPT artifacts are missing.
  - Extended the on-fly scheduler so nightly runs cover every store mapped with a source URL, while the selected priority store remains the hourly target.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/onfly_scheduler.py`
  - `tests/test_onfly_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - No new env vars. Nightly on-fly scheduler behavior now automatically fans out across all mapped stores with non-empty source URLs.

### 2026-04-26 | committed
- Summary:
  - Fixed Report Module `Data Health` so it no longer crashes when a store only has on-fly/YOLO-shaped output columns instead of the full classic export schema.
  - Switched key store selectors to display full store names, exposed RR Nagar in report/customer-journey selection flows, and added a clear fallback message when only YOLO/on-fly output exists.
  - Removed `TEST_STORE_D07` data/history from the local SQLite runtime and export folders, cleaned the mixed on-fly store-date report, and restarted the local web runtime with the updated state.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/onfly_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - Local runtime data cleanup only: deleted `TEST_STORE_D07` rows from SQLite runtime tables and removed matching local export/store folders under `data/`.

### 2026-04-26 | committed
- Summary:
  - Fixed Organisation-driven header branding so the saved logo path renders reliably even when the stored path is an older `/app/data/...` runtime path.
  - Replaced the oversized Streamlit brand block with a compact small-logo + app-name header and tightened top-page spacing without changing other page logic.
  - Restarted the local no-Docker web runtime and verified the updated app is live on `http://localhost:8765`.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-25 | committed
- Summary:
  - Simplified IRIS manual data sync so scheduler source comes from `Store Mapping`, the sync page shows a clearer storewise status table, and users can sync/run RR Nagar without re-entering paths.
  - Moved the IRIS data sync scheduler controls under `Config > Scheduler`, added plain-language setting explanations, and removed duplicate/legacy report wording from the Report Module.
  - Cleaned local deployment clutter by removing temporary scheduler scratch data, mock export folders, and stale no-Docker runtime session artifacts.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/onfly_scheduler.py`
  - `tests/test_onfly_scheduler.py`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - No new env vars or dependencies. On-fly scheduler now prefers each store's mapped source URL from `stores.drive_folder_url` before any legacy saved scheduler path.

### 2026-04-25 | committed
- Summary:
  - Added a no-PowerShell local runtime manager so IRIS can be started, stopped, checked, and opened from simple double-clickable `.bat` files instead of requiring PowerShell commands.
  - Added automatic local env bootstrapping from the existing OpenAI/Google key text files into `deploy/no_docker/.env.local`, keeping the browser/no-Docker flow easier for everyday use.
  - Added lightweight regression coverage for the new local runtime manager helpers.
- Changed Paths:
  - `scripts/local_runtime_manager.py`
  - `iris_local_start.bat`
  - `iris_local_stop.bat`
  - `iris_local_status.bat`
  - `iris_local_open.bat`
  - `tests/test_local_runtime_manager.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/local_runtime_manager.py`
  - `iris_local_start.bat`
  - `iris_local_stop.bat`
  - `iris_local_status.bat`
  - `iris_local_open.bat`
  - `tests/test_local_runtime_manager.py`
- Infra/Config Impact:
  - `deploy/no_docker/.env.local` can now be auto-generated from the existing local key files when missing.

### 2026-04-25 | committed
- Summary:
  - Profiled the Streamlit dashboard load path and confirmed the main UI slowdown came from eagerly loading full legacy exports on every page before routing, plus repeated walk-in CSV scans/aggregations and chart construction during render.
  - Added UI performance timing logs for bootstrap, navigation resolution, legacy export loads, source-image counting, walk-in dataset loads, store/report pipeline queries, aggregations, chart builds, and full page render; logs now write to `data/exports/current/ui_perf/ui_perf_events.jsonl`.
  - Made legacy export loading lazy so only business pages that truly need `AnalysisOutput` load the full export bundle; operational/admin pages now skip that heavy work on initial page load.
  - Added safe caching for export loads and source-image counting, narrowed on-fly walk-in CSV reads to required business columns only, vectorized duration derivation, and reused cached store meta instead of repeated row-wise DB merges.
  - Reduced first-render UI cost by lazy-loading heavier charts/tables behind toggles/expanders on overview/store detail pages while keeping business metrics unchanged.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-25 | committed
- Summary:
  - Added quota-aware GPT fallback behavior so on-fly runs keep YOLO results intact, mark GPT quota failures explicitly, and queue GPT-only retries instead of misreporting full failure.
  - Surfaced GPT quota retry state clearly in the Pipeline Journey UI with queue counts, retry warnings, and partial-run messaging for browser-only visibility.
  - Updated the on-fly scheduler to read run summaries, detect queued GPT retries, and advance the next retry cycle automatically when quota becomes available.
  - Enabled SQLite WAL mode plus autocommit-style shared connections on the registry/on-fly paths to reduce browser-vs-scheduler lock contention in no-Docker runtime.
  - Added a public-Drive image download fallback via `lh3.googleusercontent.com` so open-shared Google Drive folders list and fetch reliably during on-fly runs.
  - Fixed the on-fly scheduler regression test to use OS-neutral path assertions so GitHub Actions Linux runs match Windows-local behavior.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/onfly_pipeline.py`
  - `scripts/onfly_scheduler.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_onfly_pipeline.py`
  - `tests/test_onfly_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `None`
- Infra/Config Impact:
  - `None`

### 2026-04-24 | committed
- Summary:
  - Added a no-Docker deployment pack so IRIS can run as a browser-accessible Python web app plus separate scheduler workers without depending on Docker.
  - Introduced managed runtime bootstrap helpers for env-file loading and persistent path resolution, and wired the dashboard to honor no-Docker runtime path overrides.
  - Added Linux `systemd` and Windows NSSM deployment templates, plus regression tests for runtime bootstrap behavior.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `src/iris/runtime_bootstrap.py`
  - `scripts/start_web_app.py`
  - `scripts/start_scheduler_worker_service.py`
  - `scripts/start_onfly_scheduler_service.py`
  - `deploy/no_docker/.env.example`
  - `deploy/no_docker/README.md`
  - `deploy/no_docker/linux/iris-web.service`
  - `deploy/no_docker/linux/iris-scheduler.service`
  - `deploy/no_docker/linux/iris-onfly-scheduler.service`
  - `deploy/no_docker/windows/install_nssm_services.ps1`
  - `deploy/no_docker/windows/README.md`
  - `tests/test_runtime_bootstrap.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `src/iris/runtime_bootstrap.py`
  - `scripts/start_web_app.py`
  - `scripts/start_scheduler_worker_service.py`
  - `scripts/start_onfly_scheduler_service.py`
  - `deploy/no_docker/.env.example`
  - `deploy/no_docker/README.md`
  - `deploy/no_docker/linux/iris-web.service`
  - `deploy/no_docker/linux/iris-scheduler.service`
  - `deploy/no_docker/linux/iris-onfly-scheduler.service`
  - `deploy/no_docker/windows/install_nssm_services.ps1`
  - `deploy/no_docker/windows/README.md`
  - `tests/test_runtime_bootstrap.py`
- Infra/Config Impact:
  - Added no-Docker runtime env/path contract through `IRIS_ENV_FILE`, `IRIS_DATA_DIR`, `IRIS_DB_PATH`, `IRIS_STORES_ROOT`, `IRIS_EXPORT_DIR`, `IRIS_EMPLOYEE_ASSETS_DIR`, `IRIS_STREAMLIT_HOST`, and `IRIS_STREAMLIT_PORT`.

### 2026-04-24 | committed
- Summary:
  - Added full browser-managed On-Fly Scheduler Settings inside `Operations > Manual data sync of IRIS`.
  - Scheduler settings now persist store/source/hourly/nightly/runtime knobs in app settings DB and surface active schedule, next run, next nightly, and last run directly in UI.
  - Switched `scripts/onfly_scheduler.py` from env-driven store/source/timing reads to DB-backed configuration loading, with a regression test for scheduler config hydration.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/onfly_scheduler.py`
  - `tests/test_onfly_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `tests/test_onfly_scheduler.py`
- Infra/Config Impact:
  - `iris-onfly-scheduler` now reads schedule configuration from DB-backed app settings instead of environment variables for store/source/hourly/nightly/runtime selection.

### 2026-04-23 | committed
- Summary:
  - Fixed on-fly GPT gating so newly relevant images from the current YOLO pass no longer skip GPT because of stale stored relevance.
  - Split GPT work decision from relevance decision: version/state determines whether GPT work is needed, and current-run YOLO determines whether the image is relevant enough to run GPT.
  - Added a regression test covering the exact stale-row scenario: previously irrelevant stored state, current YOLO detects a person, GPT must run in the same pipeline execution.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `tests/test_onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `tests/test_onfly_pipeline.py`
- Infra/Config Impact:
  - No new env vars or services.

### 2026-04-10 | Drive-empty visibility guard in Pipeline Journey

- Summary:
  - Added explicit UI guard in `Operations > Manual data sync of IRIS`:
    - when Google Drive source returns zero discovered files, UI now shows:
      `No files visible from source (access/scope issue)`.
  - Guard appears both:
    - immediately after a manual run completes with `total_listed=0`
    - in persisted Run Detail view for gdrive runs with zero discovered files.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Link Zone/State from Store Master into dashboard filters and rankings

- Summary:
  - Added cached store metadata map sourced from `store_master` + `stores`.
  - Dashboard now backfills `Zone` and `State` from Store Master when walk-in rows are missing/blank for these fields.
  - Overview filter dropdowns now include all available Zone/State values from Store Master.
  - Overview Top/Bottom store ranking tables now show `zone` and `state` columns.
  - Store Drill-down Zone/State display now uses Store Master metadata directly for reliable output.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Store mapping crash fix + business-friendly store names + pipeline ETA

- Summary:
  - Fixed Streamlit session crash in Store Mapping (`st.session_state.map_drive_url cannot be modified after widget instantiation`) by separating prefill state from bound widget state and forcing safe rerun on store switch.
  - Updated store selectors in Operations/Overview/Store Drill-down to display **Store Name (Store ID)** instead of only short code.
  - Added default test-store hiding in Overview and Store Drill-down once non-test stores are present (`Include Test Stores` toggle retained).
  - Added historical runtime estimate caption in `Operations > Manual data sync of IRIS` for on-fly runs.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Store trend granularity fix for multi-day visibility

- Summary:
  - Fixed Store Drill-down trend collapsing to a single point by restoring explicit `Trend Granularity` selector (`Day/Month/Year`).
  - Improved default granularity logic for `Month Range`:
    - same/short month span defaults to `Day`
    - medium span defaults to `Month`
    - long span defaults to `Year`
  - This ensures April 2–6 style data is visible day-wise instead of being auto-collapsed to monthly single-point trend.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Store Drill-down cleanup (removed purchase signal table)

- Summary:
  - Removed `Purchase Signal Summary` from Store Drill-down to keep the page focused on requested walk-in KPIs and trend/compare sections only.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Dashboard filter apply-state fix (same-output issue)

- Summary:
  - Fixed Overview and Store Drill-down returning repeated/same outputs by introducing explicit `Apply` behavior that commits filter state before KPI/trend computation.
  - Added guardrails so stale applied values are auto-corrected when Store/Zone/State options change.
  - Added “Applied Filters” captions to make active filter context visible and auditable during analysis.
  - Updated Store Drill-down to show Zone/State for the applied store selection.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Store drill-down compare UX (auto period + gender/age slicers)

- Summary:
  - Replaced manual trend-granularity control in Store Drill-down with automatic grain selection based on chosen date filter mode/range.
  - Added `Compare Against` period selector with automatic previous-period default and zero-baseline fallback when comparison period has no data.
  - Added interactive `Gender Filter` and `Age Group Filter`; KPI/trend/benchmark tables now react instantly to these slicers (Power BI style behavior).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Store Drill-down cleanup (removed two non-required tables)

- Summary:
  - Removed `Session Close Type` and `Entry Type Split` tables from Store Drill-down to keep business view concise.
  - Retained `Purchase Signal Summary` and primary KPI/trend sections.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Date filter UX cleanup (distinct month/manual/single modes)

- Summary:
  - Refined Overview and Store Drill-down date filtering so each mode has unique controls and behavior:
    - `Month Range`: month-year selectors only (no calendar picker).
    - `Manual Date Range`: separate `From Date` and `To Date` calendars.
    - `Single Date`: one date picker only.
  - Fixed month-range filtering to use full month boundaries (first day to month-end) for accurate period selection.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Overview/store filters: month range + manual dates + zone/state scope

- Summary:
  - Added business filter controls in Overview and Store Drill-down with Apply button flow:
    - store selector
    - zone selector
    - state selector
    - date filter modes: `Month Range`, `Manual Date Range`, and `Single Date`.
  - Added month-to-month range filtering and manual from/to date filtering for trend and KPI calculations.
  - Extended walk-in business dataset enrichment to include `state` from `store_master`.
  - Added short-TTL caching to walk-in dataset loader to reduce repeated heavy reads and improve UI responsiveness.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-10 | Phase-1 hardening: TEST store visibility + walk-in speedups

- Summary:
  - Fixed walk-in dashboard data source path to use exports root directly so `TEST_STORE_D07` shows up in Overview and Store Drill-down selectors.
  - Added short-TTL cached loading for on-fly walk-in business dataset to reduce repeated disk/DB work and improve page load responsiveness.
  - Hardened customer group correction so non-customer rows get isolated `NON_CUSTOMER_*` groups and customer groups no longer mix with staff/unconfirmed entities in business exports.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (restart-only; no dependency or Dockerfile changes).

### 2026-04-10 | Phase-1 walk-in dashboard redesign (overview + drill-down + compare)

- Summary:
  - Reworked primary `Overview` and `Store Drill-down` dashboards to be walk-in/session-first using `onfly_walkin_sessions.csv` instead of image-centric KPIs.
  - Added store/region/pan-India compare views, day/month/year trend selectors, period delta indicators, and top/bottom store ranking blocks.
  - Ensured test-store (`TEST_STORE_D07`) visibility through on-fly walk-in dataset ingestion for selectors and KPIs.
  - Added customer-group correction logic in on-fly export so suspicious frame-wide groups are split to walk-in level and staff/customer group mixing is prevented in customer analytics.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (code-only patch; restart-only deploy path).

### 2026-04-07 | Lightweight runtime automation + full-folder on-fly validation run

- Summary:
  - Added lightweight Docker runtime automation to reduce memory/container footprint for server-like operation by stopping optional services.
  - Added `run_iris.bat light-runtime` command to apply this mode quickly.
  - Executed full test-folder on-fly run for `TEST_STORE_D07` with no 30-image cap (`max-images 10000`) and version split enabled (`yolo_v1`, `gpt_v1`), then validated delta rerun behavior.
  - Generated a readable latest-run file report with counts, timings, and output paths.
- Changed Paths:
  - `scripts/optimize_docker_runtime.ps1`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
  - `data/exports/current/onfly/TEST_STORE_D07/onfly_run_report_latest.md` (runtime artifact)
- New Modules Introduced:
  - `scripts/optimize_docker_runtime.ps1`
- Infra/Config Impact:
  - New command: `run_iris.bat light-runtime`
  - Stops optional containers by default: `iris-api`, celery, legacy schedulers, GPT scheduler, YOLO relevance scheduler.

### 2026-04-07 | Version-split rerun control + process timing dataset

- Summary:
  - Added separate `yolo_version` and `gpt_version` handling to on-fly pipeline config and scheduler command wiring.
  - Implemented version-aware selective rerun logic:
    - if YOLO version unchanged, YOLO step is skipped;
    - if GPT version changed on relevant images, only GPT re-runs;
    - legacy compatibility preserved by falling back to `pipeline_version` for existing rows.
  - Added `yolo_version` and `gpt_version` columns to `onfly_image_state` (auto-migration).
  - Added per-run timing dataset export: `onfly_process_timings.csv` with ms + `HH:MM:SS` for each stage.
  - Added independent-app readiness checklist document for full cutover planning.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `scripts/run_onfly_pipeline.py`
  - `scripts/onfly_scheduler.py`
  - `docs/process/onfly_pipeline_logic.md`
  - `docs/process/onfly_independent_app_checklist.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `docs/process/onfly_independent_app_checklist.md`
- Infra/Config Impact:
  - New optional env vars:
    - `ONFLY_YOLO_VERSION`
    - `ONFLY_GPT_VERSION`
  - Existing `ONFLY_PIPELINE_VERSION` remains supported.

### 2026-04-07 | Walk-in export cleanup + audit column toggle

- Summary:
  - Removed duplicate `debug_gpt_event_type` from the canonical business export.
  - Canonical `onfly_walkin_sessions.csv` now excludes audit-only fields by default:
    - `matched_session_id`, `match_score`, `match_reason`, `direction_confidence`, `match_fingerprint`, `debug_parsed_time`, `created_at`.
  - Added `onfly_walkin_sessions_audit.csv` so full debug/audit fields remain accessible.
  - Added report UI controls for `On-Fly Walk-in Sessions`:
    - `Show Audit Columns` toggle
    - `Visible Columns` selector (add/remove columns interactively before viewing/downloading).
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `src/iris/iris_dashboard.py`
  - `docs/process/onfly_pipeline_logic.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No schema/dependency changes; export/view behavior only.

### 2026-04-07 | Staff uniform rule expanded (red+black and white+black)

- Summary:
  - Expanded deterministic staff post-processing override to classify both patterns as staff:
    - red shirt + black pant/trouser (store staff)
    - white shirt + black pant/trouser (managers)
  - Updated GPT prompt text to align with both staff patterns.
  - Updated on-fly logic documentation to reflect current deployed staff override behavior.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `docs/process/onfly_pipeline_logic.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (logic/documentation only).

### 2026-04-07 | Non-blocking CSV write when canonical export is locked

- Summary:
  - Updated on-fly report writer to avoid failing whole pipeline when canonical CSV is open/locked (e.g., Excel file handle).
  - On `PermissionError`, pipeline now writes run-scoped fallback CSV (`<name>_<run_id>.csv`) and continues to complete run/report/index updates.
  - Added `write_warnings` into run summary JSON and report-writer event payload for traceability in UI/debug.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (runtime behavior only; no schema/dependency change).

### 2026-04-07 | On-fly logic clarity documentation refresh

- Summary:
  - Added a dedicated canonical logic document for on-fly processing so stage behavior is always clear and auditable.
  - Documented the exact `LIST -> SKIP_CHECK -> DOWNLOAD -> YOLO -> GPT -> REPORT_WRITER -> DASHBOARD_INGEST` flow with delta/idempotent rules.
  - Clarified source-of-truth timing rule: GPT decides event semantics, but session times are assigned from filename timestamp parsing.
  - Updated README to point to the canonical logic file and aligned artifact list to include walk-in session exports.
- Changed Paths:
  - `docs/process/onfly_pipeline_logic.md`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `docs/process/onfly_pipeline_logic.md`
- Infra/Config Impact:
  - None (documentation-only change).

### 2026-04-07 | Local env bootstrap + run command env-file support

- Summary:
  - Added a local secure env bootstrap script to auto-create `.env.local` from key files and default runtime values (including `OPENAI_VISION_MODEL=gpt-4.1-mini`).
  - Added `.env.local.example` with required fields (`MAX_FRAMES_PER_JOB`, OpenAI/Google keys, service account email/id placeholders, on-fly defaults).
  - Expanded `.env.example` with additional required fields and placeholders for local/dev consistency.
  - Updated `run_iris.bat` to automatically use `--env-file .env.local` (fallback `.env`) when present, so Docker compose commands pick local env without repeated manual export.
  - Added git ignore protection for `.env` and `.env.local` to prevent secret commits.
- Changed Paths:
  - `.gitignore`
  - `.env.example`
  - `.env.local.example`
  - `scripts/setup_local_env.ps1`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/setup_local_env.ps1`
- Infra/Config Impact:
  - Optional local runtime file `.env.local` is now first-class for compose-backed commands.
  - No Docker rebuild required (code/config only).

### 2026-04-07 | Pipeline Journey UI trigger for source path / Drive key runs

- Summary:
  - Added a manual “Run Pipeline Now” control in `Operations > Pipeline > Pipeline Journey`.
  - UI now accepts source in all common forms:
    - full Google Drive folder URL
    - Drive folder key only
    - local folder path
    - direct image folder path
  - Added normalization logic to convert Drive key to canonical Drive folder URL.
  - Added run controls for `Store ID`, `Max Images`, `YOLO Confidence`, and `Force Reprocess`.
  - Manual UI run now executes `run_onfly_pipeline` directly and writes normal run/event/report artifacts.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Uses existing runtime env keys (`GOOGLE_API_KEY`, `OPENAI_API_KEY`) loaded in running `iris` service.
  - No rebuild required; restart `iris` service only.

### 2026-04-07 | Pipeline Journey stability fix + simplified run form

- Summary:
  - Fixed Pipeline Journey crash (`StoreRecord` has no `.get`) by switching store extraction to dataclass attribute access (`s.store_id`).
  - Simplified run form to only required inputs:
    - Store selection
    - Source path / Drive URL / Drive folder key
    - Overwrite toggle
  - Removed run-time confidence/max controls from this screen (these remain under Config).
  - Added result reuse behavior:
    - If latest successful run for same source exists and report files exist, UI reuses existing outputs when overwrite is OFF.
    - If overwrite is ON, full reprocess is executed.
  - Added lightweight progress indicator and explicit report paths display after run.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None; restart `iris` service to load UI fix.

### 2026-04-07 | On-fly export cleanup (Folder + Image name columns)

- Summary:
  - Updated `onfly_image_results.csv` export to derive and include `folder_name` from `relative_path` (date-like folders normalized to `DD-MM-YYYY`), and removed `date_source` from report output.
  - Kept `Date` as the visible date column for reporting; `date_source` remains internal in DB for derivation only.
  - Updated `onfly_walkin_sessions.csv` export to include `folder_name` + `image_name` by joining `onfly_walkin_sessions` with `onfly_image_state` on `store_id + image_id`.
  - Changed walk-in session export scope to current run only (`run_id = current run`) to avoid mixed historical duplicates in one CSV.
  - Hardened GPT prompt with explicit banner/poster/mannequin suppression guidance (non-human prints should be `Uncertain` and excluded).
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `scripts/fix_onfly_exports.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None. Re-run on-fly pipeline to regenerate CSV artifacts with new columns.

### 2026-04-07 | On-fly report writer stability for locked CSV files

- Summary:
  - Added safe CSV writer fallback in on-fly report stage to handle file lock/permission collisions (e.g., CSV open in Excel).
  - If a target CSV is locked, pipeline now writes run-scoped fallback files:
    - `onfly_image_results_<run_id>.csv`
    - `onfly_walkin_sessions_<run_id>.csv`
    - `onfly_store_date_report_<run_id>.csv`
  - Summary JSON and dashboard ingestion index now reference the actual written path (primary or fallback) so UI/report links remain correct.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-04-06 | Scan and incorporate external B2B template references

- Summary:
  - Added a lightweight scanner utility to inspect `D:\\b2b-template` and the provided SOP docx, then generate incorporation artifacts inside IRIS docs.
  - Generated `docs/process/b2b_template_scan_report.md` and `docs/process/b2b_template_scan_report.json` with file-volume stats, key path presence checks, SOP section detection, and now/future incorporation guidance.
  - Kept implementation fully non-invasive (documentation/process only), with no runtime coupling to IRIS pipeline.
- Changed Paths:
  - `scripts/scan_b2b_template.py`
  - `docs/process/b2b_template_scan_report.md`
  - `docs/process/b2b_template_scan_report.json`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/scan_b2b_template.py`
- Infra/Config Impact:
  - None.

### 2026-04-06 | Upgrade GPT eval to comprehensive 20-field retail analytics prompt

- Summary:
  - Replaced simple 4-field GPT prompt (`customer_count, staff_count, conversions, bounce`) in `onfly_pipeline.py` with the full privacy-safe retail analytics prompt.
  - GPT now returns one row per detected person with 20 fields: Walk-in ID, Group ID, Role, Entry/Exit Time, Session Status, Entry Type, Gender, Age Band, Attire, Primary Clothing, Jewellery Load, Bag Type, Clothing Style Archetype, Engagement Type, Engagement Depth, Purchase Signal (Bag), Included in Analytics.
  - Privacy rules enforced in prompt: no identity recognition, no biometrics, session-local only, non-PII.
  - Deterministic Walk-in IDs (YYYYMMDDHHMMSSWNN) and Group IDs (YYYYMMDDHHMMSSGNN) mandatory.
  - Temporal reasoning: treat all provided frames as time-ordered sequence; never merge across frames by clothing similarity alone.
  - Uses JSON schema (Responses API) for structured output — same schema pattern as `gpt_post_relevance_test.py`.
  - Added `onfly_walkin_sessions` SQLite table: one row per detected person per image run.
  - `gpt_result_json` in `onfly_image_state` now stores summary only; full per-customer data in `onfly_walkin_sessions`.
  - New export: `data/exports/current/onfly/{store_id}/onfly_walkin_sessions.csv` alongside existing `onfly_image_results.csv`.
  - `run_summary_json` output now includes `walkin_sessions_csv` path.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None (new DB table `onfly_walkin_sessions` added inside `init_onfly_tables`)
- Infra/Config Impact:
  - `max_output_tokens` increased from 500 → 2000 (per-person rows need more tokens).
  - `request timeout` increased from 90s → 120s.
  - No new env vars required.

### 2026-04-03 | Phase 1 — React + FastAPI + Celery Scheduler Dashboard
- Summary:
  - Added React (Vite + TypeScript + Tailwind) frontend with Login page and Scheduler Dashboard.
  - Added FastAPI backend (port 8766) with JWT auth, job trigger endpoints, and run history API.
  - Added Celery + Redis queue: drive_sync → yolo_scan → gpt_analysis → report auto-chain.
  - Hourly YOLO beat schedule + midnight full pipeline beat schedule (Asia/Kolkata).
  - Added `pipeline_run_log` SQLite table to track per-job run status for dashboard display.
  - New Docker services: redis, iris-api, iris-celery-worker, iris-celery-beat.
  - Backend Dockerfile: multi-stage (Node React build → Python FastAPI, React served as static files).
  - No raw images saved in pipeline — only analysis results stored in DB and CSV exports.
  - Sampling mode is off (ONFLY_DETECTOR=yolo always; allow_detector_fallback=False).
- Changed Paths:
  - `src/iris/store_registry.py`
  - `deploy/docker-compose.yml`
  - `.env.example`
  - `AGENTS.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `backend/` (FastAPI + Celery application)
  - `frontend/` (React + Vite + TypeScript)
- Infra/Config Impact:
  - New env var: `IRIS_JWT_SECRET` (required for API auth — generate with secrets.token_hex(32))
  - New Docker volumes: redis_data, celery_beat_data
  - New ports: 8766 (iris-api + React UI)

### 2026-04-03 | committed
- Summary:
  - Enabled downloadable empty template behavior for `GPT Consolidated Walk-in Table (Test Folder)` in Report Module.
  - Enforced exact column order for consolidated walk-in output in UI/CSV download, even when no rows are present.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-03 | Fix iris-api startup crash — wrong sys.path depth in backend modules

- Summary:
  - Fixed `ModuleNotFoundError: No module named 'iris'` that caused iris-api container to crash-loop on startup.
  - All backend files used `.parents[N]` one level too deep, resolving to `/src` (filesystem root) instead of `/app/src`.
  - Added explicit `PYTHONPATH=/app:/app/src` to all three Phase 1 docker-compose services as belt-and-suspenders.
- Changed Paths:
  - `backend/app/api/routes_auth.py`
  - `backend/app/celery_app/tasks/drive_sync.py`
  - `backend/app/celery_app/tasks/yolo_scan.py`
  - `backend/app/celery_app/tasks/gpt_analysis.py`
  - `backend/app/celery_app/tasks/report.py`
  - `deploy/docker-compose.yml`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `PYTHONPATH=/app:/app/src` now set explicitly in iris-api, iris-celery-worker, iris-celery-beat environments.

### 2026-04-03 | committed

- Summary:
  - Fixed `run-iris-normal.ps1` argument handling under `Set-StrictMode` by moving `param(...)` to top and giving `RunArgs` a safe default (`@()`).
  - Verified launcher works without explicit args and with pass-through args (e.g., `status`).
- Changed Paths:
  - `run-iris-normal.ps1`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-03 | committed
- Summary:
  - Added production-safe local PowerShell launchers to avoid repeated API key copy-paste, with file-based secret loading, validation, and cleanup.
  - Introduced `run-iris-validation.ps1` (fixed GPT validation run) and `run-iris-normal.ps1` (default/arg pass-through normal runs).
  - Added local-only ignore patterns for optional launcher overrides and local secrets directory.
- Changed Paths:
  - `run-iris-validation.ps1`
  - `run-iris-normal.ps1`
  - `.gitignore`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `run-iris-validation.ps1`
  - `run-iris-normal.ps1`
- Infra/Config Impact:
  - Uses local key files by default:
    - `C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\OPEN AI API Key.txt`
    - `C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\Google Cloud Key.txt`
  - Optional path overrides via env vars: `IRIS_OPENAI_KEY_FILE`, `IRIS_GOOGLE_KEY_FILE`.

### 2026-04-03 | committed
- Summary:
  - Extended GPT post-relevance pipeline with a second-pass consolidated sequence analyzer that applies the provided retail walk-in prompt logic and writes a deterministic consolidated walk-in table.
  - Added new walk-in outputs (`gpt_walkin_sequence_table.csv`, `gpt_walkin_sequence_table.md`) and run-summary fields for sequence generation status/errors.
  - Exposed consolidated walk-in output in Report Module as `GPT Consolidated Walk-in Table (Test Folder)`.
- Changed Paths:
  - `scripts/gpt_post_relevance_test.py`
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `run_iris.bat gpt-test-validation-now` now also attempts consolidated sequence-table generation using the same GPT model and API key.

### 2026-04-01 | committed
- Summary:
  - Fixed CI lint failure by importing `Any` used in GPT frame-index type annotations.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-01 | committed
- Summary:
  - Updated high-traffic dashboard selectors to default to a blank placeholder so pages load only after explicit dropdown selection.
  - Applied explicit select-first behavior to `Config`, `Report Module`, `Store Drill-down`, `Frame Review`, and `Customer Journeys` to avoid auto-loading first option content.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (UI selection behavior only).

### 2026-04-01 | committed
- Summary:
  - Separated TEST_STORE post-relevance intelligence into a dedicated GPT stage that consumes Stage-1 YOLO relevant images and preserves YOLO count as audit-only.
  - Added GPT validation exports with per-entity labels (`T1...Tn`), YOLO-vs-GPT comparison, GPT-vs-reviewer comparison, GPT-extra detections (YOLO missed), and annotated image artifacts.
  - Extended dashboard report module and frame-review table to surface GPT validation outputs (including preview and per-track source `YOLO` vs `GPT_EXTRA`) without triggering BLRJAY full-date GPT runs.
- Changed Paths:
  - `scripts/gpt_post_relevance_test.py`
  - `run_iris.bat`
  - `src/iris/iris_dashboard.py`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/gpt_post_relevance_test.py`
- Infra/Config Impact:
  - New optional command: `run_iris.bat gpt-test-validation-now` (requires `OPENAI_API_KEY`).
  - New outputs under `data/exports/current/gpt_validation/<store_id>/`.

### 2026-04-01 | committed
- Summary:
  - Added a fully isolated CTO performance observer layer under `CTO/` to track run-by-run fix timing and page-load probe timing without coupling to core runtime.
  - Introduced a single main performance log (`CTO/logs/perf_events.jsonl`) plus lightweight analyzer reports for slow paths, repeated slow-path detection, and regressions.
  - Added both single-run and continuous-watch wrappers (`CTO/run_cto_cycle.bat`, `CTO/run_cto_watch.bat`) so post-fix and live-browsing speed checks are repeatable.
- Changed Paths:
  - `CTO/README.md`
  - `CTO/scripts/perf_common.py`
  - `CTO/scripts/perf_cycle.py`
  - `CTO/scripts/perf_run.py`
  - `CTO/scripts/perf_analyze.py`
  - `CTO/scripts/perf_watch.py`
  - `CTO/run_cto_cycle.bat`
  - `CTO/run_cto_watch.bat`
  - `CTO/logs/.gitkeep`
  - `CTO/reports/.gitkeep`
  - `.gitignore`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `CTO/README.md`
  - `CTO/scripts/perf_common.py`
  - `CTO/scripts/perf_cycle.py`
  - `CTO/scripts/perf_run.py`
  - `CTO/scripts/perf_analyze.py`
  - `CTO/scripts/perf_watch.py`
  - `CTO/run_cto_cycle.bat`
  - `CTO/run_cto_watch.bat`
  - `CTO/logs/.gitkeep`
  - `CTO/reports/.gitkeep`
- Infra/Config Impact:
  - None for core app runtime (CTO layer is optional and removable).

### 2026-04-01 | committed
- Summary:
  - Assessed the uploaded B2B SOP checklist against IRIS and added a concrete Done/Now/Future status matrix for operational clarity.
  - Added missing repository controls that can be completed purely in-code now: `.env.example` and a mandatory PR template.
  - Updated README setup guidance to use `.env.example` and linked SOP status tracking doc.
- Changed Paths:
  - `.env.example`
  - `.github/pull_request_template.md`
  - `docs/process/b2b_projects_sop_status.md`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `.env.example`
  - `.github/pull_request_template.md`
  - `docs/process/b2b_projects_sop_status.md`
- Infra/Config Impact:
  - Adds a standard `.env` initialization path (`Copy-Item .env.example .env`) for local/dev setup.
  - Standardizes PR metadata collection via GitHub PR template.


### 2026-04-01 | committed
- Summary:
  - Hardened `run_iris.bat` on-fly commands to pass runtime keys into container exec (`GOOGLE_API_KEY`, `OPENAI_API_KEY`) so Drive on-fly runs work without full container recreation.
  - Added explicit warnings in on-fly run/benchmark/scheduler start commands when `GOOGLE_API_KEY` is empty.
- Changed Paths:
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None (runtime command behavior only).


### 2026-04-01 | committed
- Summary:
  - Fixed on-fly runtime parser/runtime issues in container by correcting local-source ID normalization and escaping, and validated end-to-end execution from Docker.
  - Added detector init timing (`detector_init_ms`) to run metrics and benchmark output so slowness attribution is explicit (download vs model-init vs inference).
  - Added lightweight durable queue-state table (`onfly_task_queue`) updates for per-image stage tracking (`yolo`, `chatgpt`) with status/error audit trail.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - On-fly run summaries/benchmarks now include `detector_init_ms`.
  - New SQLite table used by on-fly runtime: `onfly_task_queue`.


### 2026-04-01 | committed
- Summary:
  - Added a lightweight on-the-fly pipeline (`source URL -> YOLO relevance -> optional GPT for relevant-only`) with SQLite-backed idempotent state to skip already processed images.
  - Added dedicated hourly+nightly on-fly scheduler and compose profile (`iris-onfly-scheduler`) so URL-first evaluation flow runs independently from existing overnight analytics services.
  - Added benchmark runner for 3x before/after timing, report artifacts for slowness diagnostics, and store/date flat output (`onfly_store_date_report.csv`) for dashboard readiness.
  - Hid `Bulk Access Upload` from Access navigation (kept a deprecated fallback route message) to simplify the lightweight ops path.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `scripts/run_onfly_pipeline.py`
  - `scripts/onfly_scheduler.py`
  - `scripts/benchmark_onfly_pipeline.py`
  - `deploy/docker-compose.yml`
  - `run_iris.bat`
  - `src/iris/iris_dashboard.py`
  - `README.md`
  - `docs/business/iris-brd.md`
  - `docs/prd/iris-platform-prd-v1.md`
  - `release-notes/2026-04-01-onfly-pipeline.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `src/iris/onfly_pipeline.py`
  - `scripts/run_onfly_pipeline.py`
  - `scripts/onfly_scheduler.py`
  - `scripts/benchmark_onfly_pipeline.py`
  - `release-notes/2026-04-01-onfly-pipeline.md`
- Infra/Config Impact:
  - New compose profile/service: `iris-onfly-scheduler` (`--profile onfly`).
  - New env controls: `ONFLY_ENABLED`, `ONFLY_STORE_ID`, `ONFLY_SOURCE_URL`, `ONFLY_OUT_DIR`, `ONFLY_HOURLY_MINUTES`, `ONFLY_NIGHTLY_RUN_AT`, `ONFLY_TZ`, `ONFLY_MAX_IMAGES`, `ONFLY_PIPELINE_VERSION`, `ONFLY_DETECTOR`, `ONFLY_CONF`, `IRIS_ONFLY_POLL_SECONDS`.
  - New outputs under `data/exports/current/onfly/` including run summaries and benchmark artifacts.

### 2026-03-31 | committed
- Summary:
  - Implemented Stage-1 pipeline (`YOLO relevance scan`) to count local test images, classify each frame as relevant/irrelevant based on person presence, and export downstream-ready artifacts for Stage-2 ChatGPT ingestion.
  - Added daily Stage-1 scheduler worker (default `15:00` Asia/Kolkata) with isolated runtime/app-setting keys so relevance scan scheduling stays separate from GPT and overnight YOLO analytics cycles.
  - Added operational commands in `run_iris.bat` to start/stop/log Stage-1 scheduler and trigger immediate Stage-1 scan inside container.
- Changed Paths:
  - `scripts/yolo_relevance_scan.py`
  - `scripts/yolo_relevance_scheduler.py`
  - `deploy/docker-compose.yml`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/yolo_relevance_scan.py`
  - `scripts/yolo_relevance_scheduler.py`
- Infra/Config Impact:
  - New compose profile/service: `iris-yolo-relevance-scheduler` (`--profile stage1`).
  - New env controls: `YOLO_RELEVANCE_ENABLED`, `YOLO_RELEVANCE_DAILY_RUN_AT`, `YOLO_RELEVANCE_TZ`, `YOLO_RELEVANCE_ROOT`, `YOLO_RELEVANCE_OUT_ROOT`, `YOLO_RELEVANCE_STORE_ID`, `YOLO_RELEVANCE_CONF`, `YOLO_RELEVANCE_MAX_IMAGES`, `YOLO_RELEVANCE_ALLOW_FALLBACK`, `YOLO_RELEVANCE_GZIP_EXPORTS`, `YOLO_RELEVANCE_DROP_PLAIN_CSV`.

### 2026-03-31 | committed
- Summary:
  - Added Stage-1 store-level reporting layer (store+date aggregation) on top of relevance output with required flat schema:
    - `store_name`, `date`, `raw_image_count`, `relevant_image_count`.
  - Implemented safe upsert behavior for repeat runs (same store/date rows are replaced, not duplicated) and JSON mirror export for service/API use.
  - Added standalone report command utility and `run_iris.bat` shortcut for on-demand report generation without rerunning detector.
- Changed Paths:
  - `scripts/yolo_relevance_scan.py`
  - `scripts/stage1_store_report.py`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/stage1_store_report.py`
- Infra/Config Impact:
  - New output artifact path default: `data/exports/current/vision_eval/store_report.csv` (+ `store_report.json`).

### 2026-03-31 | committed
- Summary:
  - Added date-wise store summary export table with folder-derived `Date` bucket formatting:
    - valid folder dates (`YYYY-MM-DD` / `YYYYMMDD`) now display as `DD-MM-YYYY`
    - non-date folder names (e.g., `Test1`, `Test2`, `Test`) are preserved as-is.
  - Kept existing store-level summary intact and added separate flat date-wise output schema for reporting/dashboard ingestion.
  - Added `daily_conversions` in date-wise export schema (defaults safely to `0` when unavailable).
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New export artifacts:
    - `all_stores_summary_datewise.csv` (+ optional gzip)
    - `store_<store_id>_summary_datewise.csv` (+ optional gzip)

### 2026-03-27 | committed
- Summary:
  - Added a new CLI pipeline to evaluate retail images using ChatGPT vision calls (instead of YOLO) with strict structured JSON output per image/entity.
  - Implemented post-inference business-rule filtering for customer/staff/pedestrian/banner/product exclusions, red-bag purchased count, and best-effort per-camera sequential customer IDs.
  - Added ground-truth comparison outputs: field-level accuracy summary, mismatch report, confusion-style label breakdown, plus markdown run report.
- Changed Paths:
  - `scripts/evaluate_chatgpt_vision_batch.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/evaluate_chatgpt_vision_batch.py`
- Infra/Config Impact:
  - Requires `OPENAI_API_KEY` at runtime.
  - Uses existing Google Drive sync path (`sync_store_from_source`) and optional `GOOGLE_API_KEY` for scalable Drive API sync.

### 2026-03-27 | committed
- Summary:
  - Improved ChatGPT vision batch script error handling for missing ground-truth path by adding `--create-ground-truth-template`.
  - Script can now generate a fillable CSV template from selected images and exit cleanly, then rerun for full evaluation.
- Changed Paths:
  - `scripts/evaluate_chatgpt_vision_batch.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New optional CLI flag: `--create-ground-truth-template`.

### 2026-03-30 | committed
- Summary:
  - Fixed ChatGPT vision response payload format to match Responses API JSON-schema contract (`text.format` now includes required `name`/`schema` keys directly).
  - Reduced unnecessary retry load for client-side request errors (`4xx` except `429`) to avoid repeated failed billing attempts.
- Changed Paths:
  - `scripts/evaluate_chatgpt_vision_batch.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-30 | committed
- Summary:
  - Added config-driven GPT-vs-YOLO separation controls:
    - `YOLO_ENABLED` gate in existing scheduler worker.
    - Dedicated GPT scheduler service/script for daily capped TEST_STORE evaluation runs.
  - Added separate GPT scheduler runtime (`scripts/gpt_eval_scheduler.py`) with env-driven store/model/path/time config and persisted run summaries in `app_settings`.
  - Updated GPT batch evaluator defaults to support env-driven model/limit, self-bootstrap `PYTHONPATH`, and per-store output folder isolation.
  - Added `run_iris.bat` commands to start/stop/log GPT scheduler independently.
- Changed Paths:
  - `scripts/evaluate_chatgpt_vision_batch.py`
  - `scripts/scheduler_worker.py`
  - `scripts/gpt_eval_scheduler.py`
  - `deploy/docker-compose.yml`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/gpt_eval_scheduler.py`
- Infra/Config Impact:
  - New optional compose profile/service: `iris-gpt-scheduler` (`--profile gpt`).
  - New env flags: `YOLO_ENABLED`, `GPT_VISION_ENABLED`, `OPENAI_VISION_MODEL`, `GPT_VISION_MAX_IMAGES`, `GPT_TEST_*`, `GPT_DAILY_RUN_AT`, `GPT_TZ`.

### 2026-03-26 | Commit 3c55f53
- Summary:
  - Added `Model Accuracy` page under `Reports > Business Health` with weighted current accuracy KPI, daily trend graph, latest model/store table, queued-for-retrain KPI, and next scheduler run visibility.
  - Added persistent daily accuracy history (`data/exports/current/model_accuracy_history.csv`) generated on each analysis run/scheduler prediction cycle using confirmed+pending feedback comparisons.
  - Improved Frame Review post-save clarity by showing queued retrain + next scheduler run notice and keeping auto-confirm behavior explicit.
  - Added immediate save feedback guidance banner after rerun (`Queued for retrain: X | Next scheduler run: ...`).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New export artifact: `data/exports/current/model_accuracy_history.csv`.

### 2026-03-26 | Commit 26e900a
- Summary:
  - Removed `Detection` and `UI` modules from Access Config module selector to reduce unused settings clutter.
  - Removed static `Detection Settings` and `UI Settings` informational panels from Config page.
  - Kept operational controls in active modules (`Feedback`, `Retrain`, `Scheduler`, `Sync`, `Run Mode`) unchanged.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-26 | Commit b53abfa
- Summary:
  - Fixed Pending Review behavior when `Hide Reviewed Rows In Pending` is ON: reviewed top-10 rows now remain hidden instead of being auto-repopulated back into the table.
  - Added clearer save guidance that with `Auto-confirm=ON`, saved rows move directly to `Review History`.
  - Added visible `Retrain Queue (Confirmed And Waiting)` table so users can see exactly which confirmed feedback rows are queued for next retrain cycle.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-26 | Commit 9c0eeb9
- Summary:
  - Fixed Frame Review crash (`NameError: auth_token`) in top-10 feedback table preparation by removing unused frame-link generation from batch row builder.
  - This restores stable table render, thumbnail preview visibility path, and feedback save interaction (UI no longer aborts before save action).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-26 | Commit b3197ba
- Summary:
  - Stabilized Frame Review top-10 editor state by versioning form/editor widget keys and clearing legacy state keys after schema changes.
  - This restores thumbnail preview visibility in the validation grid for users carrying old session-state schema.
  - Improved save feedback UX by distinguishing `no row selected` vs `rows selected but no feedback label changed`, reducing false “not saved” confusion.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit cf70559
- Summary:
  - Restored thumbnail previews in Frame Review top-10 validation table by always showing the `Preview` column (independent of fast-edit setting) so feedback can be given with visual context.
  - Removed the extra frame-level raw data table above top-10 validation grid to reduce clutter in review flow.
  - Expanded `run_iris.bat` into a broader command wrapper with `restart`, `rebuild`, `status`, `logs`, `start`, `stop`, `scheduler-start`, `scheduler-stop`, `pull`, and `health`.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `run_iris.bat` now supports multiple operational commands from CMD/PowerShell.

### 2026-03-25 | Commit b99a8eb
- Summary:
  - Reduced scheduler resource spikes by forcing scheduler-triggered prediction cycles to run in single-process mode (`use_parallel=False`, `use_streaming=False`) while keeping model logic unchanged.
  - Added CPU thread caps for `iris-scheduler` container (`OMP/OPENBLAS/MKL/NUMEXPR=1`) to prevent host-wide CPU saturation from numerical thread over-subscription.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `deploy/docker-compose.yml`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `iris-scheduler` now starts with constrained thread env vars; requires container recreate (`docker compose up -d --force-recreate iris-scheduler`) to apply.

### 2026-03-25 | Commit 27f0fdb
- Summary:
  - Simplified Frame Review by removing the `Hide frames already reviewed` toggle from the page and enforcing that behavior from `Access > Config > Feedback` only.
  - Removed the inline image-wise validation CSV section/table from Frame Review to reduce clutter and avoid showing non-actionable file paths in UI.
  - Removed the confusing `Open unique customer verification page` link from Frame Review to avoid broken/unclear navigation.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit fbbcdc9
- Summary:
  - Simplified `Store Detail` for validation-first usage by removing embedded Validation Console, Data Quality Issues, Relevant Image Gallery, and in-page proof tables; kept only KPI summary + hotspot/trend visuals.
  - Removed numeric hotspot tables from Store Detail, keeping camera/location hotspot graphs only.
  - Added a dedicated `Report Module` page under `Reports > Business Health` with Store + Date selectors and CSV download for Top Summary, Daily Walk-in/Conversion, Daily Calculation Proof, Frame-Level Proof, Data Health, and hotspot data tables.
  - Routed legacy `Data Health` navigation links to the new `Report Module` page for backward compatibility.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Moved `Run Mode` controls into its own Config module so run controls no longer render at the bottom for every other module.
  - Updated Config module selector list to include `Run Mode`; run/regenerate form now appears only when `Run Mode` is selected (or matched via setting search).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Made source ingestion more universal for nested folders by switching Drive delta sync runs to full recursive listing on every cycle (not latest-date-only), so reorganized folders like `Test/Test1`, `Test/Test2`, etc. are picked up automatically.
  - Added validation accuracy reporting in Frame Review: match KPIs (predicted vs corrected), exportable model-version trend table, and accuracy trend graph to track quality after retrains.
  - Added `NO_CUSTOMER` feedback option (canonical `no_person`) for empty/no-customer frames, including a dedicated dropdown in top-10 validation table and retrain-label alias support.
  - Improved track feedback persistence to save track-level predicted labels (customer/staff) for cleaner accuracy scoring.
- Changed Paths:
  - `src/iris/drive_delta_sync.py`
  - `tests/test_drive_delta_sync.py`
  - `src/iris/iris_dashboard.py`
  - `scripts/daily_feedback_reprocess.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Fixed startup `sqlite3.OperationalError: database is locked` race between UI and scheduler services by hardening DB lock handling during schema/init commit.
  - Increased SQLite busy timeout window and added transient-lock retry loop around `init_db` commit to absorb short write-lock contention safely.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Hardened local refresh automation to include both runtime services (`iris`, `iris-scheduler`) so restart/rebuild no longer leaves scheduler out-of-sync with dashboard code.
  - Updated readiness checks to wait for both containers plus UI URL before completing, reducing false “stuck” runs.
  - Expanded log/error scan coverage to include scheduler logs for faster diagnosis when background cycles fail.
- Changed Paths:
  - `scripts/refresh_and_check.ps1`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `run_iris.bat` now indirectly refreshes both services through updated PowerShell flow.

### 2026-03-25 | Commit <pending>
- Summary:
  - Completed phase-2 cleanup by removing unreachable legacy review/queue UI blocks from `Frame Review` (`_render_qa_timeline`) so only the current `Pending Review` and `Review History` workflow remains.
  - Moved scheduler execution out of Streamlit request cycle: dashboard now only shows scheduler status, while a dedicated worker handles timed queue runs.
  - Added always-on scheduler service (`iris-scheduler`) in Docker Compose, backed by new `scripts/scheduler_worker.py` that enforces minimum interval rules, executes scheduler tasks, and updates `cfg_scheduler_*` run metadata.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/scheduler_worker.py`
  - `deploy/docker-compose.yml`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/scheduler_worker.py`
- Infra/Config Impact:
  - New always-on compose service: `iris-scheduler` (uses `IRIS_SCHEDULER_POLL_SECONDS`, default `10`).

### 2026-03-25 | Commit <pending>
- Summary:
  - Refactored Access configuration UX by renaming `Pipeline Configuration` to `Config` and adding module-wise setting sections (`Feedback`, `Retrain`, `Scheduler`, `Sync`, `Detection`, `UI`) with searchable discovery and plain-language guidance.
  - Wired Frame Review feedback behavior to Config settings (auto-confirm, confidence, fast edit, hide reviewed, rerun-after-save), added visible `Pending retrain rows` indicator near save, and improved reviewed-row hiding using track-level feedback state.
  - Simplified Review area to `Pending Review` and `Review History` workspace with thumbnails, editable history rows, and retrain/scheduler status cards; removed confusing legacy feedback queue/forms from visible path.
  - Added in-app scheduler cycle orchestration (interval, minimum interval guard from enabled task estimates + buffer, next-run tracking, queue tasks for sync/feedback/retrain/prediction/export refresh).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New app settings keys under `cfg_*` namespace for feedback/retrain/scheduler behavior.

### 2026-03-25 | Commit <pending>
- Summary:
  - Improved top-10 Frame Review save responsiveness by making full analysis rerun optional on save (default off), avoiding heavy export regeneration on every feedback click.
  - Added `Fast edit mode` (default on) to hide thumbnails and reduce table rendering overhead during dropdown-heavy QA edits.
  - Reduced default visible track columns from 6 to 4 to lower initial grid render cost while keeping expandable track-slot slider for larger frames.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Hardened SQLite access against transient host-volume I/O failures by introducing retried DB connection helper with busy-timeout and actionable disk-free diagnostics.
  - Applied the resilient connection helper across registry DB operations (init/read/write paths) to reduce startup flakiness after Docker rebuild/restart on Windows.
  - Fixed `refresh_and_check.ps1` log-scan crash (`$Matches` variable collision) and constrained log checks to recent startup window; added SQLite quick-check probe to validate runtime DB health.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `scripts/refresh_and_check.ps1`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Reduced Frame Review interaction latency by moving top-10 batch editor into a form so dropdown edits do not trigger full-page reruns on every change.
  - Added preview thumbnail session-cache for top-10 rows to avoid re-rendering overlays repeatedly during QA interactions.
  - Optimized save path by skipping no-op track updates and collapsing update+review-status into single DB writes; new inserts can now be created directly as `confirmed` when auto-confirm is enabled.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `src/iris/store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Updated top-10 track feedback save behavior to persist edits by frame+track key: repeated saves now update existing track feedback rows instead of creating duplicates.
  - Retained historical persistence in DB while making in-table re-edit workflow deterministic for future reference.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Removed `feedback_status` and `last_feedback` columns from the top-10 Frame Review batch editor to keep the validation grid focused on track-level correction only.
  - Kept internal reviewed-state logic intact for `Hide frames already reviewed` filtering.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Simplified top-10 Frame Review table for per-person QA by removing image-level `predicted_label`, `feedback_label`, and frame-link columns from batch editor.
  - Kept left-side `Select` checkbox as required control for scoped save; only selected rows are persisted.
  - Changed batch save behavior to persist track-level feedback only (`Tn Feedback`), with one-time banner relearn per selected frame row when applicable.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Added `run_iris.bat` launcher so Windows users can run refresh automation with a short command (`rebuild` default, `restart` optional).
  - Wired `.bat` usage into README to reduce manual PowerShell command typing.
- Changed Paths:
  - `run_iris.bat`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `run_iris.bat`
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Added a one-command PowerShell automation runner for local refresh with readiness checks, log tailing, and runtime error marker scan.
  - Supports both `restart` (fast) and `rebuild` (code/dependency update) modes, then exits cleanly to prompt.
- Changed Paths:
  - `scripts/refresh_and_check.ps1`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/refresh_and_check.ps1`
- Infra/Config Impact:
  - None

### 2026-03-25 | Commit <pending>
- Summary:
  - Improved Frame Review overlay readability by repositioning labels to avoid clipping/overlap and adding stronger text contrast for track IDs (e.g., T21/T22/T25 visibility).
  - Upgraded top-10 validation table for multi-person transparency: hidden timestamp, track-level predicted vs feedback columns (`Tn Pred`, `Tn Feedback`) and dynamic slot scaling up to 20 tracks.
  - Standardized UI feedback wording to `PEDESTRIANS` and `BANNER` while preserving backward-compatible storage aliases (`outside_passer`, `poster_banner`) for retrain safety.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/daily_feedback_reprocess.py`
  - `README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-24 | Commit <pending>
- Summary:
  - Enhanced Frame Review batch validation for track-aware feedback: added per-frame track ID columns (`track_1`..`track_4`) with editable label assignment so T7/T9-style corrections are captured as structured feedback instead of free-text remarks.
  - Persisted selected per-track labels as dedicated QA feedback rows (`track_id` populated), keeping existing frame-level feedback/comment flow intact.
  - Added carry-forward of last saved per-track label in top-10 batch table for faster iterative QA.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-24 | Commit <pending>
- Summary:
  - Fixed Frame Review usability for 10-image validation: added single-table batch review with inline image previews, per-row label/comment editing, and bulk save.
  - Added immediate feedback acceptance path (`auto-confirm`) so saved labels can be used for next retrain run without manual reviewer pass.
  - Added robust preview fallback so manual review works even when hover preview behavior is inconsistent in browser.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-24 | Commit <pending>
- Summary:
  - Fixed blank/frozen dashboard behavior when exports are empty by changing auto-recovery to manual trigger button (no heavy analysis on initial page load).
  - Updated retrain/reprocess script date filtering to be optional (`--capture-date`), defaulting to all dates so test-store exports are not accidentally zeroed by `today` filter.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `scripts/daily_feedback_reprocess.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - `scripts/daily_feedback_reprocess.py` now accepts optional `--capture-date` (`YYYY-MM-DD` / `YYYYMMDD`).

### 2026-03-24 | Commit <pending>
- Summary:
  - Aligned dashboard retrain flow with script retrain semantics by adding force mode from UI and explicit retrain diagnostics (`confirmed_total`, `new_confirmed_rows`, watermark, eligible rows, mode).
  - Stabilized YOLO Docker dependency resolution by using pinned `opencv-python==4.10.0.84` with pinned NumPy for YOLO-enabled builds to avoid opencv/numpy mismatch drift.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `deploy/Dockerfile`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - YOLO Docker builds now prioritize dependency compatibility over headless-opencv-only packaging.

### 2026-03-24 | Commit <pending>
- Summary:
  - Fixed retrain/reprocess observability and control for `TEST_STORE_D07`: added explicit watermark/eligibility logging and a `--force-retrain` mode to retrain from all confirmed feedback when no new rows exist.
  - Clarified retrain skip reason in summary output (`eligible_feedback_rows` vs `min_new_feedback`).
  - Stabilized Docker YOLO dependency stack by removing full `opencv-python` after Ultralytics install and enforcing pinned headless OpenCV + NumPy versions.
- Changed Paths:
  - `scripts/daily_feedback_reprocess.py`
  - `deploy/Dockerfile`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New optional CLI flag: `--force-retrain` for `scripts/daily_feedback_reprocess.py`.

### 2026-03-24 | Commit <pending>
- Summary:
  - Optimized runtime startup without changing detection logic: module-availability checks no longer import heavy YOLO/DeepFace/TensorFlow packages during UI render.
  - Switched Docker default to `IRIS_ENABLE_DEEPFACE=0` to avoid automatic heavy TensorFlow/DeepFace model downloads unless explicitly enabled.
  - Pinned `numpy` and `opencv-python-headless` versions to reduce dependency drift and avoid multi-version conflicts.
  - Added conservative runtime thread/log env tuning in Docker for better responsiveness.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `deploy/docker-compose.yml`
  - `deploy/Dockerfile`
  - `requirements.txt`
  - `deploy/requirements.docker.txt`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - DeepFace is now opt-in by default in Docker build (`IRIS_ENABLE_DEEPFACE=0`).

### 2026-03-24 | Commit <pending>
- Summary:
  - Fixed blank-page navigation edge case by decoding URL query params (`+` / encoded spaces) for module/section/page resolution.
  - Added safe page-render fallback: if page key is not mapped, show a warning and render Overview instead of a blank content area.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-24 | Commit <pending>
- Summary:
  - Fixed Windows YOLO runtime load-order issue (`c10.dll` WinError 1114) by preloading torch before numpy/pandas on non-pytest runs so true YOLO path is used again.
  - Upgraded Frame Review into validation-first workflow: image-wise validation report export, required feedback label set, editable review history, and model-version capture per feedback row.
  - Added safe feedback retrain/reprocess loop with minimum 10 new confirmed rows, model-version registration/promotion, rerun trigger, and daily batch script with end-of-day summary output.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/store_registry.py`
  - `src/iris/iris_dashboard.py`
  - `scripts/daily_feedback_reprocess.py`
  - `tests/test_store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `scripts/daily_feedback_reprocess.py`
- Infra/Config Impact:
  - Windows-only torch preload can be disabled with `IRIS_PRELOAD_TORCH=0`.

### 2026-03-23 | Commit <pending>
- Summary:
  - Fixed validated-visit KPI denominator logic and zero-denominator handling so conversion/bounce are entry-based with explicit no-data state.
  - Restored export schema stability by keeping `daily_bounced` internal and excluding it from `all_stores_summary.csv`.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

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

### 2026-03-20 | Commit 2d2050f
- Summary:
  - Added a production-safe entrance-camera classification layer with deterministic priority rules (`poster -> side-passer -> staff -> customer -> pending`), zone polygons, and auditable per-track JSON output.
  - Fixed track ID ordering to preserve 1:1 mapping with detection boxes/centroids for reliable trajectory decisions.
- Changed Paths:
  - `src/iris/entrance_pipeline.py`
  - `src/iris/iris_analysis.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `src/iris/entrance_pipeline.py`
- Infra/Config Impact:
  - Optional camera config keys supported for entrance cameras: `inside_store_zone`, `center_entry_zone`, `left_outside_ignore_zone`, `right_outside_ignore_zone`, `poster_static_zone`.

### 2026-03-21 | Commit f0cf9b4
- Summary:
  - Fixed camera filter behavior so D07-only runs can use substring tokens (example: `D07-`) instead of strict filename prefix only.
  - Added safe fallback from parallel streaming to linear execution when detector objects are not multiprocessing-picklable (prevents OpenCV HOG pickle crash and allows full scans to complete).
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `tests/test_iris_analysis.py`
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

### 2026-03-16 | committed
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

### 2026-03-16 | committed
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

### 2026-03-16 | committed
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

### 2026-03-18 | committed
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

### 2026-03-18 | committed
- Summary:
  - Switched repository workflow source-of-truth path to `Desktop\\Github\\IRIS` in agent instructions so local working convention matches requested deployment flow.
- Changed Paths:
  - `AGENTS.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | committed
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

### 2026-03-18 | committed
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

### 2026-03-18 | committed
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

### 2026-03-18 | committed
- Summary:
  - Fixed broken hover verification links by sanitizing `nan` values and resolving preview images from local `path/relative_path/source_folder` fallback logic in customer journey views.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | committed
- Summary:
  - Fixed Google Drive API sync reliability on restricted networks by adding download fallback (`drive.google.com/uc`) when `alt=media` is blocked, and skipping already-present files to speed repeated syncs.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
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

### 2026-03-19 | committed
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

### 2026-03-19 | committed
- Summary:
  - Fixed blank/zero-data dashboard regression caused by stale exports by adding empty-export detection and one-time auto-recovery analysis when source images exist; added explicit no-source message when root path has no images.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Added explicit dashboard notice when `Images Per Store` sampling is enabled to prevent confusion when totals appear capped (e.g., 200 images instead of full folder volume).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Fixed stale in-session dashboard data by auto-reloading exports when `all_stores_summary` on disk is newer than cached session output (supports terminal-triggered analysis runs without manual cache reset).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Fixed detection-cache poisoning across detector changes by adding detector signature (backend/model/conf/device) into cache key; prevents old `Detector unavailable` results from being reused after YOLO is enabled.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Fixed YOLO full-build dependency conflict by forcing `numpy<2` after YOLO install so `pandas/pyarrow` remain ABI-compatible in Docker runtime.
- Changed Paths:
  - `deploy/Dockerfile`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Full YOLO Docker builds now explicitly pin `numpy<2` with existing `pyarrow` constraint.

### 2026-03-19 | committed
- Summary:
  - Improved Pipeline Configuration date parsing to accept compact `YYYYMMDD` inputs (for example `20260317`) by normalizing to ISO before analysis.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Simplified Pipeline Configuration UX: added run mode presets (`Full Scan (Dev)`, `Test`, `Custom`), save-current-as-custom profile, store filter dropdown, date text + calendar controls, grouped toggles for on/off settings, confidence guidance text, and frozen gzip export behavior.
  - Updated defaults to full-scan dev behavior (`Images Per Store=0`, `Enable Age/Gender=True`) and wired preset page to persistent app settings.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | committed
- Summary:
  - Strengthened runtime robustness for people counting by adding OpenCV HOG detector fallback when YOLO/Torch is unavailable, and by improving gate-event fallback using D07/customer-count deltas when track crossings are sparse.
  - Pipeline mode selection now auto-applies immediately to prevent stale `Images Per Store` limits (e.g., stuck at 200), adds explicit `opencv_hog` detector option, and suppresses irrelevant TF_FRCNN warnings unless that detector is selected.
  - Age/Gender toggle now auto-disables when DeepFace runtime is missing to prevent broken-mode runs.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No new required env vars. `opencv-python-headless` fallback is already part of runtime dependencies.

### 2026-03-19 | committed
- Summary:
  - Redesigned D07 session lifecycle to be entry/exit-track aware: exit events are counted only for tracks that previously entered, reducing outside-passer inflation.
  - Added session classification (CUSTOMER, STAFF, OUTSIDE_PASSER, INVALID) and persisted session proof fields (ntry_image, ntry_image_path, xit_image, xit_image_path).
  - Added frame-level vent_label and updated dashboard KPI summary to prioritize CUSTOMER sessions from session table.
- Changed Paths:
  - src/iris/iris_analysis.py`r
  - src/iris/iris_dashboard.py`r
  - 	ests/test_iris_analysis.py`r
  - CHANGE_LEDGER.md`r
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None


### 2026-03-19 | committed
- Summary:
  - Made sampling-mode disable one-click from dashboard banner: added Disable Sampling Now and Disable + Re-run actions so users can switch to full scan without navigating to Pipeline Configuration.
- Changed Paths:
  - src/iris/iris_dashboard.py`r
  - CHANGE_LEDGER.md`r
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-20 | Commit 3510842
- Summary:
  - Enforced live/full-scan defaults across dashboard + CLI (sampling off by default), removed TF_FRCNN pipeline surfacing, and added clearer run guidance.
  - Optimized Docker runtime footprint by introducing `.dockerignore`, consolidating compose services to one shared image, and making sync service optional via profile.
  - Added encrypted Google API key persistence (`data/secrets`) and wired scheduler to auto-use stored key when env var is absent.
  - Reduced age/gender runtime overhead by limiting DeepFace frame analysis to entry/gate cameras (`D07` fallback or mapped ENTRY/EXIT roles).
- Changed Paths:
  - `.dockerignore`
  - `deploy/Dockerfile`
  - `deploy/docker-compose.yml`
  - `deploy/requirements.docker.txt`
  - `requirements.txt`
  - `scripts/analyze_stores.py`
  - `scripts/drive_delta_sync_scheduler.py`
  - `scripts/store_google_api_key.py`
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `src/iris/secret_store.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `.dockerignore`
  - `scripts/store_google_api_key.py`
  - `src/iris/secret_store.py`
- Infra/Config Impact:
  - Added `cryptography` dependency to runtime and Docker requirements.
  - `iris-sync` now runs under compose profile `sync` (start with `docker compose --profile sync up -d iris-sync`).

### 2026-03-20 | committed
- Summary:
  - Added a project sign-off security checklist covering key deletion, token rotation, and docker/cache cleanup.
- Changed Paths:
  - `SECURITY_CLEANUP_CHECKLIST.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `SECURITY_CLEANUP_CHECKLIST.md`
- Infra/Config Impact:
  - None

### 2026-03-20 | committed
- Summary:
  - Added immediate progress logging (`flush=True`) to drive delta scheduler so long first-run syncs show visible start/completion state in log files and terminal output.
- Changed Paths:
  - `scripts/drive_delta_sync_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-20 | committed
- Summary:
  - Hardened Google Drive sync networking by adding retry/backoff for Drive list and file download requests to recover from transient `ChunkedEncodingError` and incomplete reads.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `src/iris/drive_delta_sync.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-23 | committed
- Summary:
  - Upgraded single-camera tracking to configurable `botsort`/`bytetrack`/`centroid` modes and added lightweight appearance embeddings for stronger D07 identity persistence.
  - Reworked strict gate-mode sessions into track-lifecycle state machine with explicit statuses (`ENTRY_CANDIDATE`, `ACTIVE_CUSTOMER`, `EXITED`, `STAFF`, `OUTSIDE_PASSER`, `INVALID_STATIC_OBJECT`) and richer session fields for dashboard validation.
  - Updated store drill-down session UI to show validation-first columns (session id, entry/exit times, dwell, label, rejected reason) plus entry/exit thumbnail preview and clear empty-state guidance.
  - Added D07 regression tests for exited customer sessions, static-object rejection, and outside-passer suppression.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional runtime tuning env vars supported: `IRIS_TRACKER_TYPE`, `IRIS_REID_WEIGHT`, `IRIS_REID_DISTANCE_THRESHOLD`, `IRIS_TRACK_MATCH_COST`, `IRIS_STAFF_SCORE_THRESHOLD`.

### 2026-03-23 | committed
- Summary:
  - Added a validation-first D07 console in Store Drill-down with table-first workflow: top summary table, all-appearances table, unique-persons table, and rejected-cases tab.
  - Added manual verification filters (store/date/camera/role/person-id search), drive-link-first proof navigation, and preview selector for quick proof-image inspection.
  - Preserved existing dashboard analytics sections while making validation tables primary for manual audit flow.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-23 | committed
- Summary:
  - Fixed visit KPI denominator handling so conversion and bounce rates are based on validated entries, and both rates show `N/A` when there are no validated visits.
  - Updated strict D07 session validity so an entry-crossing customer session is treated as a validated visit even when it closes by timeout (not only exit crossing).
  - Updated Store Drill-down business summary to explicitly separate raw detections from validated visit metrics and avoid misleading `0.00%` when denominator is zero.
  - Added regression tests for zero-denominator (`NaN`) KPI behavior and entry-denominator conversion/bounce formulas.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `src/iris/iris_dashboard.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-26 | committed
- Summary:
  - Fixed QA feedback history prediction resolution to handle mixed `capture_date` formats (e.g., `YYYY-MM-DD` and `DD-MM-YYYY`) so per-track predicted labels are matched correctly instead of showing stale/`UNKNOWN`.
  - Normalized frame/track feedback key matching across pending table, save/update flow, retrain-queue lookup, and history rendering for stable feedback visibility.
  - Added image-level Review History rollup showing combined per-image predicted/corrected track feedback (`Tn:LABEL`) so multi-label feedback is visible in one report row.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-26 | committed
- Summary:
  - Removed the separate `Edit History Row` panel from Review History because it was confusing and not reliable for your workflow.
  - Kept Review History as a clean read-only audit view and directed all corrections through Pending Review (single-table correction path).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-30 | committed
- Summary:
  - Added feedback-aware override memory for strict gate/session classification using confirmed QA feedback with hybrid keys:
    - exact frame-track key: `(capture_date, camera_id, filename, track_id)`
    - day-track key: `(capture_date, camera_id, track_id)`
  - Integrated conservative override resolution into D07 role decisions so reviewed `BANNER` / `PEDESTRIAN` / `STAFF` corrections suppress repeat false positives without broadly forcing unrelated customer promotions.
  - Strengthened short-window static/banner detection to reduce banner-heavy false positives (especially low-motion short tracks).
  - Added regression coverage to ensure exact frame-track override takes precedence over broader day-track override and maps to `INVALID_STATIC_OBJECT` reliably.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `tests/test_iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New optional runtime flags:
    - `IRIS_FEEDBACK_OVERRIDE_ENABLED` (default `1`)
    - `IRIS_STORE_REGISTRY_DB` (optional explicit DB path; defaults to inferred `data/store_registry.db`)

### 2026-04-06 | committed
- Summary:
  - Added on-fly pipeline observability persistence (`onfly_pipeline_runs` + `onfly_pipeline_run_events`) with stage-level tracking for LIST, SKIP_CHECK, DOWNLOAD, YOLO, GPT, REPORT_WRITER, and DASHBOARD_INGEST.
  - Wired on-fly report indexing for dashboard/report discovery (`onfly_report_index`) and updated on-fly runtime to upsert report paths and ingestion markers per store/date.
  - Added business-readable `Operations > Pipeline Journey` UI with run list, stage timeline, failure inspector, report paths, and scheduler history.
  - Extended Report Module with direct on-fly exports (`On-Fly Store-Date Summary`, `On-Fly Image Results`, `On-Fly Walk-in Sessions`) so test-store output is visible even when legacy summary exports are not loaded.
  - Added scheduler history persistence in `cfg_onfly_scheduler_history_json` for execution traceability.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `src/iris/store_registry.py`
  - `src/iris/iris_dashboard.py`
  - `scripts/onfly_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No rebuild required.
  - New SQLite tables auto-created on startup: `onfly_pipeline_runs`, `onfly_pipeline_run_events`, `onfly_report_index`.

### 2026-04-06 | committed
- Summary:
  - Updated `run_iris.bat` to auto-load `OPENAI_API_KEY` and `GOOGLE_API_KEY` from local key files when env vars are empty, so `onfly-run-now`, `onfly-benchmark`, `onfly-scheduler-start`, and `gpt-test-validation-now` run without manual key paste.
- Changed Paths:
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional local key-file env overrides supported: `OPENAI_KEY_FILE`, `GOOGLE_KEY_FILE`.

### 2026-04-06 | committed
- Summary:
  - Reduced on-fly Drive slowness by making Google Drive listing stop early once `--max-images` is reached (instead of scanning full folder tree before slicing).
  - Added retry + shorter connect/read timeouts for Drive fetch operations and changed per-image download failures to continue gracefully (marking failed status/event) instead of aborting the entire run.
  - Added `ONFLY_MAX_IMAGES` env support in `run_iris.bat` for quick capped runs without editing commands.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - New optional runtime env in launcher: `ONFLY_MAX_IMAGES` (default `100`).

### 2026-04-07 | committed
- Summary:
  - Fixed Pipeline Journey crash for store loading by using `StoreRecord.store_id` (instead of dict-style `.get`) in the store filter list.
  - Normalized on-fly walk-in export `date` to folder-derived pipeline date (`item.date_display`) to prevent GPT-hallucinated dates from breaking folder/image reconciliation.
  - Re-ran full on-fly test-store pipeline (`TEST_STORE_D07`, 30 images, force reprocess, GPT enabled) and validated delta rerun behavior, stage timings, and report artifact generation.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No new env vars.

### 2026-04-07 | committed
- Summary:
  - Fixed on-fly session time assignment to use filename-derived timestamp (`HH:MM:SS`) as canonical event time instead of GPT-provided clock text.
  - Extended GPT prompt/schema for explicit event semantics (`Event Type`, `Direction Confidence`, `Match Fingerprint`) while keeping GPT responsible for entry/exit/inside semantics.
  - Added deterministic on-fly session state machine:
    - `ENTRY -> OPEN`
    - `INSIDE_ACTIVE/INSIDE_PURCHASING -> OPEN update or INFERRED_INSIDE_OPEN`
    - `EXIT -> CLOSED` when matched; otherwise `UNMATCHED_EXIT`
    - EOD closeout turns remaining `OPEN/INFERRED_INSIDE_OPEN` into `CLOSED_EOD`.
  - Added best-effort deterministic matching against open sessions (store/date scoped) with score/reason persistence for auditability.
  - Added staff manager override support (white shirt + black pant/trouser => Staff, excluded from analytics).
  - Expanded `onfly_walkin_sessions` schema with audit/debug fields (`event_type`, `event_time`, `first_seen_time`, `last_seen_time`, `matched_session_id`, `match_score`, `match_reason`, `direction_confidence`, `match_fingerprint`, debug fields, source image/folder metadata).
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - SQLite migration auto-adds new columns to `onfly_walkin_sessions` on startup.

### 2026-04-07 | committed
- Summary:
  - Cleaned test-store on-fly export directory to keep only canonical files:
    - `onfly_image_results.csv`
    - `onfly_walkin_sessions.csv`
  - Updated on-fly CSV writer to always overwrite canonical filenames and stop creating run-suffixed fallback files on file-lock conditions.
  - Added explicit lock error message instructing to close open file handles and rerun.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - If CSV is open/locked, run now fails fast with a clear message instead of generating extra files.

### 2026-04-07 | committed
- Summary:
  - Added one-click **Restore Selected Run To Canonical Files** action in `Operations > Pipeline Journey`.
  - Restore action rebuilds and overwrites only:
    - `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv`
    - `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv`
    from the selected `run_id` directly from SQLite state/tables.
  - Preserves folder/date/image normalization (`folder_name`, `Date`, `image_name`) and aligns walk-in `date` with folder display for reconciliation.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No new env vars or services.

### 2026-04-07 | committed
- Summary:
  - Fixed Pipeline Journey runtime crash source by confirming `StoreRecord` access path in the page store filter logic (`s.store_id`), avoiding dict-style `.get` access.
  - Renamed Pipeline page label and header from `Pipeline Journey` to `Maual data sync of IRIS` in Operations navigation.
  - Added backward-compatible page routing alias so old deep-links to `Pipeline Journey` still work.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No new runtime dependencies.

### 2026-04-07 | committed
- Summary:
  - Updated GPT retail prompt for on-fly pipeline with explicit manager staff rule:
    - white shirt + black pant/trouser should be treated as Staff.
  - Added deterministic post-processing rule in on-fly GPT normalization:
    - if attire markers imply white+black+pant/trouser and role is customer/uncertain, force Role=Staff and Included in Analytics=No.
  - This improves staff/customer separation for manager-like appearances without changing detector stage.
- Changed Paths:
  - `src/iris/onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - No new env vars.

### 2026-04-13 | committed
- Summary:
  - Updated `Operations > Maual data sync of IRIS` run form to support complete-folder processing from web UI.
  - Added `Max Images (0 = full folder)` control so users can run uncapped scans without PowerShell commands.
  - Changed default on-fly max images fallback from `100` to `0` (full-folder mode by default).
  - Updated ETA text to handle both capped and full-folder modes clearly.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None. UI-only behavior change; pipeline backend unchanged.

### 2026-04-13 | committed
- Summary:
  - Added web-only go-live migration checklist for moving IRIS to a complete browser-operated system (no Docker on business-user machines).
  - Checklist covers runtime split, managed infra, auth, source connectors, pipeline idempotency/versioning, observability, reporting, security, and release gates.
- Changed Paths:
  - `docs/process/web_independent_go_live_checklist.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Documentation only.

### 2026-04-24 | committed
- Summary:
  - Hardened no-Docker SQLite startup so repeated config reads do not rewrite schema state on every call, which was blocking local web/scheduler coexistence.
  - Added a core-schema fast path plus per-process init cache to reduce lock pressure during no-Docker startup.
  - Added retry-aware app-settings writes and a regression test covering cached `init_db` behavior for the same DB path.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `tests/test_store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Improves local/no-Docker service stability around SQLite; no new env vars.

### 2026-04-28 | Phase C — Cloud deployment artifacts

- Summary:
  - Created full Ubuntu cloud deployment package under `deploy/cloud/`: one-shot bootstrap script (Postgres 16 via PGDG APT, nginx, redis, systemd), `iris_user` + `iris_db` init SQL, nginx config with rate limiting + SPA catch-all + WebSocket upgrade, systemd units for iris-api / iris-web / iris-celery-worker, production `.env` template, and deployment README.
- Changed Paths:
  - `deploy/cloud/setup_ubuntu.sh`
  - `deploy/cloud/postgres_init.sql`
  - `deploy/cloud/nginx.conf`
  - `deploy/cloud/iris-api.service`
  - `deploy/cloud/iris-web.service`
  - `deploy/cloud/iris-celery-worker.service`
  - `deploy/cloud/.env.production.example`
  - `deploy/cloud/README.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `deploy/cloud/` (full directory)
- Infra/Config Impact:
  - Copy to Ubuntu server, run `bash deploy/cloud/setup_ubuntu.sh`, then follow the README 8-step checklist.

### 2026-04-28 | Phase D — Postgres-only FastAPI layer, Alembic schema, migration script

- Summary:
  - **Eliminated SQLite completely** from the FastAPI runtime: rewrote `platform_data.py` and `pipeline_log.py` as pure-async Postgres-only modules — zero `sqlite3` imports, zero fallback code.
  - All 8 FastAPI route handlers (`routes_auth`, `routes_dashboard`, `routes_detail`, `routes_jobs`) updated to call `await` directly — no `db_path` parameter, no `Settings` dependency in data-only routes.
  - Created Alembic migration `001_initial_schema_with_indexes.py` with full production schema for 150-store scale: partitioned tables for `onfly_walkin_sessions` and `onfly_pipeline_run_events`, 10 critical indexes, `pg_stat_statements` extension.
  - Created `scripts/migrate_sqlite_to_postgres.py`: one-time idempotent migration with datetime string parsing, 0/1 → bool conversion, and SAVEPOINT-per-row error isolation.
  - Ran migration: 10,268 rows transferred (stores 6/6, users 5/5, image_state 9,995/9,995, walkin_sessions 213/213, pipeline_run_log 15/15).
  - 3× test pass: all 8 endpoints, data consistency validated (213 walkins = BLRJAY 93 + BLRRRN 120), auth boundary enforced, wrong-password 401 confirmed.
  - Updated `backend/alembic.ini` sqlalchemy.url for local Postgres.
  - Added `POSTGRES_URL` and `JWT_SECRET` to `.env.local`.
  - Fixed `JobStatus` Pydantic model to accept `datetime | str` for `last_run_at` from Postgres (was `str` only).
- Changed Paths:
  - `backend/app/db/platform_data.py`
  - `backend/app/db/pipeline_log.py`
  - `backend/app/db/session.py`
  - `backend/app/api/routes_auth.py`
  - `backend/app/api/routes_dashboard.py`
  - `backend/app/api/routes_detail.py`
  - `backend/app/api/routes_jobs.py`
  - `backend/app/models/jobs.py`
  - `backend/alembic.ini`
  - `.env.local`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `backend/migrations/versions/001_initial_schema_with_indexes.py`
  - `scripts/migrate_sqlite_to_postgres.py`
- Infra/Config Impact:
  - **Requires Postgres 16+ running on localhost:5432** (`iris_db` / `iris_user` / password `iris_password`).
  - Start Postgres: `& "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" start -D "C:\Program Files\PostgreSQL\17\data"`.
  - Run migrations once: `python -m alembic -c backend/alembic.ini upgrade head`.
  - Migrate existing data once: `python scripts/migrate_sqlite_to_postgres.py`.
  - `POSTGRES_URL=postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db` must be in env.
  - SQLite (`store_registry.db`) is no longer read by the FastAPI layer — Postgres is the sole data store.

---

## Phase I — QA, Frame Review, Model Feedback, Direct Pipeline Sync (2026-04-28)
- Summary:
  - Replaced Celery-based scheduler trigger with direct `run_onfly_pipeline()` execution via `ThreadPoolExecutor`. Sync Now button in the React UI now actually runs the pipeline — no Redis/Celery required.
  - Added `engine_sync` (psycopg2/sync SQLAlchemy) to `session.py` so background threads can write to Postgres without an asyncio event loop.
  - Added `routes_onfly.py`: `/api/onfly/stores`, `/api/onfly/sync/{store_id}`, `/api/onfly/status/{store_id}`. Stores sync state in `store_sync_state` Postgres table.
  - Added `routes_qa.py`: full CRUD for `qa_feedback` table, annotated image serving at `/api/qa/image`, retrain endpoint at `/api/qa/retrain/{store_id}` (writes JSON rule file + registers in `model_versions`), accuracy summary at `/api/qa/accuracy/{store_id}`.
  - Added `FrameReview.tsx`: image grid of QA feedback rows with confirm/reject/delete per frame. Corrected label dropdown + comment. Store + status filter.
  - Added `ModelFeedback.tsx`: accuracy summary cards, Generate Rule File button, retrain workflow guide, rule file version history.
  - Updated `SchedulerDashboard.tsx`: wired to `onFlySync()` / `onFlyStoreStatus()`. GPT checkbox + BoT-SORT tracker checkbox both pass through to `OnFlyConfig`.
  - Updated `StoreMapping.tsx`: added "Last Sync" column with live badge + per-row quick-sync Play button.
  - Updated `Sidebar.tsx`: Quality Assurance is now a collapsible group with QA Overview, Frame Review, Model Feedback children. Multi-group open state via `openGroups` Record.
  - Updated `App.tsx`: added `/qa/frame-review` and `/qa/model-feedback` routes.
  - Deleted `frontend/src/pages/StoreAdmin.tsx` (dead code, superseded by StoreMapping).
  - Rebuilt React and re-deployed to `backend/app/static/`.
  - Installed `psycopg2-binary` for sync engine support.
- Changed Paths:
  - `backend/app/db/session.py` (engine_sync added)
  - `backend/app/main.py` (onfly + qa routers registered)
  - `frontend/src/components/layout/Sidebar.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `backend/app/static/` (rebuilt React dist)
- New Modules Introduced:
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/routes_qa.py`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/ModelFeedback.tsx`
- Deleted:
  - `frontend/src/pages/StoreAdmin.tsx`
- Infra/Config Impact:
  - `psycopg2-binary` must be installed (`pip install psycopg2-binary`).
  - Postgres must have `store_sync_state`, `qa_feedback`, and `model_versions` tables (created by Alembic migrations or canonical_metadata.py init).
  - No Celery or Redis required — pipeline runs in-process via ThreadPoolExecutor.

### 2026-05-02 | Global store selector, QualityFeedback redesign, FrameReview hover previews, QA performance indexes

- Summary:
  - Added global store selector dropdown in TopNav with search, showing all stores (filtered to sync-enabled first). All data pages now load without requiring a store to be pre-selected — "All Stores" is the default context.
  - Wired StoreContext to include `drive_folder_url` and `sync_enabled` so the TopNav dropdown can filter to sync-ready stores.
  - Removed "select a store first" gates from Overview, ReportsPage, CustomerJourneys, and StoreDetail — all load data immediately with optional store filtering.
  - Redesigned QualityFeedback page: shows GPT-analysed sessions as a table with source image thumbnails (hover to enlarge), role badges, entry/exit columns, dwell time, gender, camera, and approve/reject toggles. Paginated at 20 rows per page.
  - Added HoverPreview component to FrameReview so thumbnail cards show a large popup on hover without navigating away.
  - Added SQLite performance indexes for QA review queue queries (`onfly_image_state` and `onfly_walkin_sessions`) in both `onfly_pipeline.py` (schema-time) and `routes_qa.py` (runtime lazy-ensure for existing DBs).
  - Increased QA image cache-control from 60s to 3600s to reduce redundant image fetches.
  - Rebuilt frontend static assets.
- Changed Paths:
  - `frontend/src/components/layout/TopNav.tsx`
  - `frontend/src/context/StoreContext.tsx`
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/CustomerJourneys.tsx`
  - `frontend/src/pages/StoreDetail.tsx`
  - `frontend/src/pages/QualityFeedback.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `backend/app/api/routes_qa.py`
  - `src/iris/onfly_pipeline.py`
  - `backend/app/static/` (rebuilt)
- Infra/Config Impact:
  - No schema migration required — indexes are additive and idempotent.
  - Restart the API server after deploying so the new static build is served.

### 2026-04-30 | RR Nagar live-sync status hardening, store mapping cleanup, and report enrichment

- Summary:
  - Hardened on-fly status reporting so stale runs are auto-marked failed, active runs show `running` instead of stale `error`, and current source/stage/report-path details can be surfaced cleanly in the UI.
  - Updated sync-state writes to persist the active source URI/provider, mark `running` at pipeline start, and retain the most recent meaningful failure reason for admin visibility.
  - Enriched footfall detail rows with source-image context (`Source Image`, `Drive Actual Image Name`, `Drive Folder Name`, `Drive Image Link`, `Drive Relative Path`, `Seeded Data`) and rebuilt validation mapping to emit one row per walk-in/image match using actual scan windows or nearest available images.
  - Added walk-in report explainer copy in the UI so seeded/demo sessions are distinguishable from live GPT-derived sessions.
  - Removed the `Add Store` / delete controls from `Store Mapping`; that page now focuses on source mapping + auto-sync toggles and points add/remove actions back to `Admin → Store Master`.
  - Improved store mapping / scheduler status cells so operators can see `running`, current stage, and the latest sync message instead of a confusing static badge.
- Changed Paths:
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/routes_reports.py`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `tests/test_routes_onfly.py`
  - `CHANGE_LEDGER.md`
- Infra/Config Impact:
  - No rebuild-first requirement. Restart the API/static host after frontend rebuild so the new report/store-mapping behaviors are visible at `http://127.0.0.1:8767`.


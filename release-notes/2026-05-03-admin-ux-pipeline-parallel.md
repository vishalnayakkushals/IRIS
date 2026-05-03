# Release Notes - 2026-05-03

## Feature Name
- IRIS Admin UX Overhaul, Pipeline Parallel Execution, User Management Improvements & Critical Pipeline Bug Fixes

## What's New

### CRITICAL FIX — GOOGLE_API_KEY Not Reaching Pipeline
- **Problem**: The scheduler was failing with `GOOGLE_API_KEY is required for Drive on-the-fly ingestion` even though the key existed in the key file. Root cause: `pydantic_settings` was not configured with `env_file`, so `.env` was never read on startup. `onfly_pipeline.py` was also reading the key from `os.getenv()` directly — bypassing Settings entirely.
- **Fix**: Added `env_file=".env"` to `Settings.model_config` in `config.py`. Added `google_api_key` field to `OnFlyConfig`. `build_source_client()` now receives the key directly from config rather than from the ambient OS environment. `routes_onfly.py` passes `settings.google_api_key` into the pipeline config.
- **Key type**: The `GOOGLE_API_KEY` (`AIzaSy…`) is a **Google Simple API Key** — the correct key type for Drive API v3. No service account JSON or OAuth credentials are needed. Enable "Google Drive API" on the key in Google Cloud Console → APIs & Services → Credentials.

### CRITICAL FIX — Pipeline Crash on Duplicate Image Insert
- **Problem**: When two pipeline runs triggered close together (scheduler fires while a previous run is still processing), both runs would pass the `SELECT` existence check and then both attempt `INSERT INTO onfly_image_state` for the same `(store_id, image_id)`, causing a `UNIQUE constraint failed` crash that killed the second run entirely.
- **Fix**: Changed `INSERT INTO` to `INSERT OR IGNORE`. The second concurrent insert for an already-existing row is now a silent no-op instead of a fatal error.

### Store Access — Dual Listbox
- Replaced the old checkbox grid with a professional dual-panel listbox.
- Left panel shows Available stores; right panel shows Granted Access stores.
- Both panels have live search. Left panel has Select All / Deselect All.
- Click a store to highlight it, double-click to move it instantly.
- Arrow buttons move the current selection or all filtered stores if nothing is selected.
- Cascading State → Zone filter dropdowns narrow the available list.
- "Grant All Stores" toggle grants or revokes access to every store in one click.
- Store metadata (state, zone) pulled from Store Master for filtering.

### YOLO + GPT Parallel Execution
- GPT analysis no longer waits for the entire YOLO scan to finish before starting.
- A shared ThreadPoolExecutor submits each image to GPT immediately when YOLO marks it relevant.
- The live pipeline progress view now reflects both YOLO and GPT counts advancing simultaneously.
- A drain loop collects completed GPT futures each iteration; remaining in-flight futures are resolved before Phase 3 session writes.
- Thread-safe: all SQLite writes remain on the main thread; GPT futures only call the OpenAI HTTP API.

### Login — Forgot Password
- Added "Forgot password?" link below the Sign In button.
- Expands an amber information box directing users to contact their IRIS administrator for a reset.
- No email infrastructure required — admins reset passwords directly from the Users page.

### Users — Change Password in Edit Form
- Edit User form now includes an optional "Change Password" field with show/hide toggle.
- If filled, the new password is saved via the reset endpoint immediately after the profile update.
- A green banner (10-second auto-dismiss, manually closeable) displays the new password so the admin can share it securely with the user.

### Users — Default Store Field Removed
- The "Default Store" dropdown is removed from the Add User and Edit User forms.
- Store assignments are now managed exclusively through the Store Access dual listbox.
- Existing `store_id` values in the database are preserved and unaffected.

### Admin Pages — Global Store Context (carried forward)
- Camera Zones, Employee Management, and Model Feedback all now respond to the TopNav store selector.
- Camera Zones shows a prompt when "All Stores" is selected (zone config requires a specific store).
- Employee Management shows all employees across stores when "All Stores" is active; upload is disabled in that mode.

### Roles & Permissions — Bulk Checkboxes (carried forward)
- Master checkbox in the Read and Write column headers selects or clears all rows at once.
- Header checkbox shows indeterminate state when only some rows are checked.

### CTO Bot Removed
- `CTO/` and `tools/cto_bot/` directories deleted in full.
- These were a standalone Streamlit HTTP response-time observer with zero production dependencies.

## Impact
- Admins can assign store access to a user in seconds using filters and bulk-select instead of scrolling through a flat grid.
- GPT analysis starts processing relevant images immediately during the YOLO scan — total pipeline wall-clock time reduced proportionally to GPT throughput.
- Password management is now self-contained in the UI: admins set, view, and share passwords without touching the database.
- A single TopNav store selector controls all admin pages — no per-page store dropdowns to keep in sync.

## Metrics / Monitoring
- KPI: Pipeline run duration (YOLO + GPT combined) — expected reduction where GPT latency previously added serially to YOLO duration.
- KPI: Admin task completion time for store access assignment — dual listbox with filters vs. flat grid.
- Dashboard: Scheduler → Pipeline view shows live YOLO Done + GPT Done counts.
- Monitoring owner: Development Team

## Availability
- Web — `http://localhost:8766`
- All changes deployed to `main` branch (commits `168deae3`, `1747fb2a`)

## Risks / Known Issues
- YOLO+GPT parallel execution uses a shared ThreadPoolExecutor. If OpenAI rate limits are hit, GPT futures will fail and be counted as `gpt_failed`. The pipeline continues; only GPT results are missing for rate-limited images.
- Store Access page requires Store Master data (city/state/zone) to be populated for State/Zone filters to work. Stores without master data still appear in the available list but with blank filter fields.

## Rollback Plan
- `git revert 1747fb2a 168deae3` and rebuild frontend (`npm run build`, copy to `backend/app/static/`).
- For pipeline parallel revert only: `git revert` the `onfly_pipeline.py` changes and restart the scheduler service.
- No database schema changes in this release — rollback has no data impact.

## Validation
- `npm run build` — clean TypeScript compile, zero errors.
- `GET http://localhost:8766/api/health` → `{"status":"ok","service":"iris-api"}` after deploy.
- `python -m py_compile src/iris/onfly_pipeline.py` → clean (no syntax errors).
- Store Access page: loaded for a test user, moved stores between panels, saved — confirmed via `GET /admin/store-access/{email}`.
- Users page: opened Edit form — Default Store field absent, Change Password field present.

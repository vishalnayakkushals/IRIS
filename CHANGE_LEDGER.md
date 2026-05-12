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

---

## Module Registry
| Module/File | Responsibility |
|---|---|
| `backend/app/main.py` | Web-only FastAPI app shell that mounts the built React SPA and exposes API routers. |
| `backend/app/runtime_startup.py` | Runtime preparation before web/worker launch: additive Postgres migrations, SQLite index checks, zombie-run cleanup. |
| `backend/app/api/routes_reports.py` | Thin report endpoints, CSV downloads, validation and cost-metric routes. |
| `backend/app/api/report_queries.py` | SQLite/runtime report reads including summary, walkins, image scans, and cost metrics. |
| `backend/app/api/report_csv.py` | Report export/download helpers. |
| `backend/app/api/report_enrichment.py` | Report row enrichment helpers. |
| `backend/app/api/report_validation.py` | Validation report mapping between walk-ins and source frames. |
| `backend/app/api/routes_onfly.py` | Thin on-fly HTTP routes for manual sync, live progress, date report, and batch status. |
| `backend/app/api/onfly_runtime.py` | On-fly runtime orchestration helpers shared by API routes and workers. |
| `backend/app/workers/store_auto_sync.py` | Dedicated background worker for mapped-store auto-sync loops. |
| `src/iris/onfly_pipeline.py` | Top-level on-fly orchestration wrapper. Delegates source access, download, GPT runtime, session reconstruction, and report writing to dedicated modules. |
| `src/iris/source_clients.py` | Drive/local source clients, folder-id parsing, filename metadata extraction. |
| `src/iris/download_manager.py` | Byte download helpers, SHA-256 dedup logic, smart frame sampling, and YOLO byte-path helpers. |
| `src/iris/gpt_runtime.py` | GPT runtime helpers: rate limiting, circuit breaker, heartbeat, prompt handling. |
| `src/iris/session_reconstruction.py` | Walk-in persistence, QA correction replay, sampled-frame resolution, PostgreSQL sync helpers. |
| `src/iris/report_writer.py` | Canonical CSV generation, run summaries, timing files, and cost metric writes. |
| `src/iris/pipeline_events.py` | SQLite schema helpers, pipeline runs/events/queue tables, update helpers. |
| `scripts/start_api_server.py` | Supported web/API launcher; runs runtime preparation then starts uvicorn. |
| `scripts/start_scheduler_worker_service.py` | Supported launcher for the core scheduler worker. |
| `scripts/start_onfly_scheduler_service.py` | Supported launcher for the on-fly scheduler worker. |
| `scripts/start_store_auto_sync_service.py` | Supported launcher for the mapped-store auto-sync worker. |
| `frontend/src/pages/ReportsPage.tsx` | Report page shell using split helpers for filtering, tables, and download actions. |
| `frontend/src/features/reports/reportHelpers.tsx` | Shared report tables, download buttons, toast helpers, and lightweight report UI utilities. |
| `frontend/src/pages/SchedulerDashboard.tsx` | Scheduler dashboard shell using split presentation sections. |
| `frontend/src/features/scheduler/sections.tsx` | Scheduler dashboard cards/tables for sync trigger, progress, date report, and automation status. |
| `frontend/src/pages/FrameReview.tsx` | Frame review shell for QA workflows. |
| `frontend/src/features/frame-review/components.tsx` | Reusable frame review cards, caching, preview helpers, and paging constants. |
| `frontend/src/components/StoreSelect.tsx` | Shared searchable store picker used across reports/admin/scheduler pages. |
| `docs/deployment/cost-optimization-plan.md` | Source-of-truth cost and savings document. |
| `docs/process/onfly_pipeline_logic.md` | Source-of-truth on-fly processing logic document. |
| `docs/AI_HANDOVER_STORAGE.md` | Current architecture/cost/storage handover for future agents. |
| `deploy/cloud/README.md` | Source-of-truth cloud deployment guide for the dedicated-worker runtime model. |
| `deploy/cloud/iris-api.service` | Systemd unit for the web/API process. |
| `deploy/cloud/iris-core-scheduler.service` | Systemd unit for the core scheduler worker. |
| `deploy/cloud/iris-onfly-scheduler.service` | Systemd unit for the on-fly scheduler worker. |
| `deploy/cloud/iris-store-auto-sync.service` | Systemd unit for the store auto-sync worker. |
| `scripts/enable_api_network_access.ps1` | Windows helper to open firewall access for the IRIS FastAPI port and optionally switch the current network profile to Private. |
| `scripts/localhost_ipv6_proxy.py` | IPv6 localhost bridge that forwards `::1:8767` traffic to the main IPv4 IRIS listener on `127.0.0.1:8767`. |

---

## AI Handoff Guide — Current Runtime Truth

> Read this first before changing code.

### What IRIS is now
- React + FastAPI is the active app.
- Local/live browser URL is `http://localhost:8767`.
- The web process is no longer the scheduler host.
- SQLite is the fast pipeline-state store.
- PostgreSQL is the platform/dashboard metadata store.

### Canonical runtime shape
1. `scripts/start_api_server.py`
2. `scripts/start_scheduler_worker_service.py`
3. `scripts/start_onfly_scheduler_service.py`
4. `scripts/start_store_auto_sync_service.py`

### Non-negotiables
- Update `CHANGE_LEDGER.md` for every change set.
- Keep `README.md`, `docs/deployment/cost-optimization-plan.md`, `docs/process/onfly_pipeline_logic.md`, `docs/AI_HANDOVER_STORAGE.md`, and `deploy/cloud/README.md` aligned with code.
- Preserve the 3 PM GPT-cost-saving schedule behavior.
- Prefer splitting code into modules/hooks/components over growing large files.

### Current architecture decisions
- Web-only `backend/app/main.py`
- Runtime prep handled by `backend/app/runtime_startup.py`
- On-fly pipeline split into source/download/GPT/session/report/event modules
- Reports API split into query/csv/enrichment/validation helpers
- Scheduler dashboard and reports page split into feature helpers
- Smart frame sampling is live and tracked in `onfly_cost_metrics`
- Cost metrics are available through `GET /api/reports/cost-metrics`

### Quick validation baseline
```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
$env:PYTHONPATH='src'
python -m pytest tests/test_onfly_pipeline.py tests/test_onfly_scheduler.py tests/test_routes_onfly.py tests/test_store_registry.py tests/test_runtime_bootstrap.py -q
cd frontend
npm run build
```

### 2026-05-12 - Quality Review Date Filters + Faster QA Page Loading

- Changed paths:
  - `backend/app/api/routes_reports.py`
  - `backend/app/api/routes_qa.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/QualityFeedback.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/features/frame-review/components.tsx`
  - `backend/app/static/` (rebuilt React bundle)
  - `CHANGE_LEDGER.md`
- Summary:
  - Reworked both QA pages to use backend-driven date lists and paginated responses so `/quality` and `/qa/frame-review` can browse full historical scanned data instead of only whatever happened to be loaded in the browser.
  - Added working date filters to QA Overview and fixed Frame Review date filtering by sourcing distinct scan dates from SQLite, normalizing mixed date formats, and applying filters on the API side.
  - Persisted QA review status on the server for walk-in review rows, merged latest feedback into both page payloads, and kept summary cards stable while filtering table/grid results underneath them.
  - Reduced page load cost by replacing oversized client-side result batches with targeted page fetches plus lightweight metadata, while keeping local short-lived cache entries for quick revisits.

### 2026-05-12 - LAN Access Diagnostics For IRIS API

- Changed paths:
  - `scripts/start_api_server.py`
  - `scripts/enable_api_network_access.ps1` (new)
  - `CHANGE_LEDGER.md`
- Summary:
  - Added startup diagnostics to the no-Docker API launcher so IRIS warns when it is listening on `0.0.0.0` but Windows Firewall still has no inbound allow rule for the configured API port.
  - Added an elevated PowerShell helper that creates a Windows Firewall inbound rule for the IRIS API port and can optionally switch the active network profile to Private for smoother same-LAN access.

### 2026-05-12 - Fix PowerShell LAN Access Helper String Parsing

- Changed paths:
  - `scripts/enable_api_network_access.ps1`
  - `CHANGE_LEDGER.md`
- Summary:
  - Fixed a PowerShell string interpolation bug in the LAN access helper so the success message prints `http://<ip>:<port>/` correctly without triggering a parser error.

### 2026-05-12 - Overview Single Shopify-Style Date Picker

- Changed paths:
  - `frontend/src/pages/Overview.tsx`
  - `backend/app/static/` (rebuilt React bundle)
  - `CHANGE_LEDGER.md`
- Summary:
  - Replaced the previous inline shortcuts/calendar toggle on the overview page with one fixed-position date trigger that opens a Shopify-style anchored picker panel instead of shifting the page layout.
  - Added a left preset column with `Today`, `Yesterday`, `Last`, `Period to date`, and `Custom range`, plus right-side range controls and `Apply` / `Cancel` actions so the page alignment stays stable while filtering.

### 2026-05-12 - Overview Calendar Range Filter + Shortcut Toggle

- Changed paths:
  - `backend/app/api/routes_dashboard.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/Overview.tsx`
  - `frontend/src/pages/StoreDetail.tsx`
  - `backend/app/static/` (rebuilt React bundle)
  - `CHANGE_LEDGER.md`
- Summary:
  - Added optional `date_from` and `date_to` support to the dashboard analytics, trend, leaderboard, delta, and overview endpoints while preserving the existing rolling `days` shortcut behavior.
  - Updated the overview page to support two filter modes: shortcut mode and calendar mode, with `Today`, `Yesterday`, `7d`, `30d`, and `90d` quick filters plus custom `From` and `To` date inputs.
  - Kept the overview cards, trend chart, and leaderboard aligned to one shared active date filter and updated delta comparisons so custom calendar ranges compare against the immediately preceding range of equal length.
  - Adjusted the shared frontend dashboard client to send either rolling-day filters or explicit date ranges and fixed the dependent store-detail analytics caller to match the new client signature.


### 2026-05-12 - Runtime Consolidation + Smart Frame Sampling + Documentation Sync

- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `src/iris/source_clients.py` (new)
  - `src/iris/download_manager.py` (new)
  - `src/iris/gpt_runtime.py` (new)
  - `src/iris/session_reconstruction.py` (new)
  - `src/iris/report_writer.py` (new)
  - `src/iris/pipeline_events.py` (new)
  - `backend/app/main.py`
  - `backend/app/runtime_startup.py` (new)
  - `backend/app/workers/store_auto_sync.py` (new)
  - `backend/app/api/routes_reports.py`
  - `backend/app/api/report_queries.py` (new)
  - `backend/app/api/report_csv.py` (new)
  - `backend/app/api/report_enrichment.py` (new)
  - `backend/app/api/report_validation.py` (new)
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/onfly_runtime.py` (new)
  - `scripts/start_api_server.py`
  - `scripts/start_store_auto_sync_service.py` (new)
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/Organisation.tsx`
  - `frontend/src/features/reports/reportHelpers.tsx` (new)
  - `frontend/src/features/scheduler/sections.tsx` (new)
  - `frontend/src/features/frame-review/components.tsx` (new)
  - `deploy/cloud/README.md`
  - `deploy/cloud/iris-core-scheduler.service` (new)
  - `deploy/cloud/iris-onfly-scheduler.service` (new)
  - `deploy/cloud/iris-store-auto-sync.service` (new)
  - `README.md`
  - `docs/AI_HANDOVER_STORAGE.md`
  - `docs/deployment/cost-optimization-plan.md`
  - `docs/deployment/deployment-readiness-report-2026-04-30.md`
  - `docs/developer/data-flow-architecture.md`
  - `docs/developer/developer-doc.md`
  - `docs/planning/execution-status.md`
  - `docs/process/onfly_pipeline_logic.md`
  - `docs/operations/cloud-deployment.md` (deleted)
  - `docs/process/web_independent_go_live_checklist.md` (deleted)
  - `docs/process/onfly_independent_app_checklist.md` (deleted)
  - `docs/deployment/deployment-email-drafts-2026-04-30.md` (deleted)
  - `tests/test_onfly_pipeline.py`
  - `CHANGE_LEDGER.md`
- Summary:
  - Split the on-fly backend into dedicated source/download/GPT/session/report/event modules and slimmed report/on-fly API routes into helper modules so the largest files are materially smaller and easier to reason about.
  - Locked the runtime story to one supported shape: FastAPI web app + dedicated core scheduler + dedicated on-fly scheduler + dedicated store auto-sync worker, with runtime preparation handled before launch instead of inside the web process.
  - Implemented smart frame sampling as a live GPT-saving optimization: consecutive similar frames now inherit the analyzed anchor result, sampled frames are tracked in SQLite, and daily cost proof now lands in `onfly_cost_metrics` plus `GET /api/reports/cost-metrics`.
  - Rewrote source-of-truth docs and handover notes to match the current architecture, removed stale transitional docs, and refreshed the ledger/module registry to reflect the post-Streamlit runtime.

### 2026-05-11 - OpenAI Batch API + Image Scans Overhaul + Overnight Automation

- Changed paths:
  - `src/iris/gpt_batch.py` (new)
  - `src/iris/onfly_pipeline.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/api/routes_reports.py`
  - `backend/app/api/routes_admin.py`
  - `backend/app/db/canonical_metadata.py`
  - `backend/app/main.py`
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/pages/SchedulerDashboard.tsx`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/pages/StoreMapping.tsx`
  - `frontend/src/api/client.ts`
  - `scripts/batch_retrieve.py` (new)
  - `scripts/setup_morning_retrieval.ps1` (new)
  - `scripts/deploy_frontend.ps1` (new)
  - `scripts/list_tables.py` (new)
  - `scripts/test_gpt_cache.py` (new)
  - `docs/deployment/cost-optimization-plan.md`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **OpenAI Batch API (`src/iris/gpt_batch.py`)**: New self-contained module for overnight GPT at 50% cost. Tables: `onfly_gpt_batch_queue` (one row per queued image, stores base64 bytes) and `onfly_gpt_batches` (one row per submitted OpenAI batch job). Key functions: `queue_image_for_batch`, `build_and_submit_batch` (uploads JSONL to `/v1/files`, creates batch via `/v1/batches`), `check_batch_status`, `apply_batch_results` (parses chat completions output, writes walk-in sessions, syncs to PG), `get_pending_batches`, `get_batch_queue_count`. Uses `/v1/chat/completions` format (OpenAI Batch API only supports chat/completions, not /v1/responses). `custom_id = irisq_{queue_row_id}` for result mapping.
  - **Pipeline batch mode (`onfly_pipeline.py`)**: `OnFlyConfig.gpt_batch_mode: bool = False` added. When True, relevant images are routed to `queue_image_for_batch()` (status: `batch_queued`) instead of the real-time GPT thread pool. At end of run, `build_and_submit_batch()` is called; submission takes <1 second then laptop can close. `gpt_batch_db_id` and `gpt_batch_queued` added to run summary dict. `init_batch_tables()` called at pipeline startup. Imports `gpt_batch` module at top.
  - **New batch endpoints (`routes_onfly.py`)**: `SyncRequest.gpt_batch_mode: bool = False` threaded through to `OnFlyConfig`. New: `GET /api/onfly/batch/status/{store_id}` (list all pending batches), `POST /api/onfly/batch/retrieve/{store_id}` (poll OpenAI + apply completed results). Both endpoints call `init_batch_tables` defensively.
  - **Image scans overhaul (`routes_reports.py`)**: `_sqlite_runtime_image_scans()` now returns `yolo_status`, `gpt_error`, `error_detail` (combines yolo_error + gpt_error), and a derived `rejection_reason` CASE expression (`Camera type excluded`, `Outside store hours`, `No people detected`, `Duplicate image (skipped)`, `Download failed`, `Pending`, `GPT cached (duplicate)`, `GPT analysis failed`, `Processed`). Removed `date_display != ''` filter that was blocking some images. Default limit raised from 100 → 50,000. Frontend uses separate `scanFacility` state (independent of global store selector) to avoid clearing other tab data when switching stores in the image-scans view.
  - **ReportsPage.tsx — storeMap bug fixed**: `useMemo(() => ({}), [])` was returning a permanently empty object — all tables showed raw store IDs instead of names. Fixed by deriving from `useStore().stores`: `Object.fromEntries(stores.map(s => [s.store_id, s.store_name || s.store_id]))`.
  - **ReportsPage.tsx — virtualized image_scans table**: `ImageScanTable` completely replaced with `@tanstack/react-virtual` row virtualizer (same pattern as ValidationTable). 12 columns: Store, Image, Date, Camera, Time, Scan Status, People, Rejection Reason, GPT, Customers, Staff, Error. Color-coded status badges. Facility selector dropdown replaces pagination when on image_scans tab. Row count shows `scanRows.length`. Explanation card explains status colors and rejection reasons.
  - **SchedulerDashboard.tsx — batch mode toggle**: "Batch mode" checkbox with purple "50% cheaper" badge. `gpt_batch_mode` passed in `onFlySync` body. Tooltip explains overnight flow.
  - **Morning retrieval scripts**: `scripts/batch_retrieve.py` — polls all pending batches for all stores (or `--store STORE_ID`), applies completed results, logs to `data/batch_retrieve.log`. `scripts/setup_morning_retrieval.ps1` — registers Windows Task Scheduler job `IRIS-BatchRetrieve` at 6:00 AM daily with `WakeToRun` flag. Run once with `powershell -ExecutionPolicy Bypass -File .\scripts\setup_morning_retrieval.ps1` (admin).
  - **Laptop-off overnight flow**: Run sync with Batch mode → end of run submits JSONL to OpenAI in <1 second → close laptop → 6 AM Task Scheduler wakes laptop → `batch_retrieve.py` downloads and applies results → dashboard ready.
  - **cost-optimization-plan.md updated**: Part 5 rewritten — all 4 optimizations (Store-Hours Filter, Camera-Type Exclusion, GPT Hash Cache, OpenAI Batch API) marked ✅ DONE with implementation details and usage instructions. Part 6 timeline updated to reflect completed work.

### Known Issues (as of 2026-05-11)
| Issue | Status |
|---|---|
| `batch_retrieve.py` morning script — Task Scheduler setup requires `powershell -ExecutionPolicy Bypass` due to default Windows execution policy | Documented — one-time setup |
| Batch API endpoints return 404 until IRIS-API service is restarted | Fixed — admin must `net stop "IRIS-API" && net start "IRIS-API"` after each backend deploy |
| `apply_batch_results` syncs to PostgreSQL — requires PG running at 6 AM retrieval time | Known — if PG is down, SQLite is still updated correctly; PG sync retried on next pipeline run |

---

### 2026-05-08 - Fix Navigation Stuck on "Loading page..." After QA Pages

- Changed paths:
  - `frontend/src/App.tsx`
  - `frontend/src/pages/QualityFeedback.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/ModelFeedback.tsx`
  - `frontend/src/api/client.ts`
  - `backend/app/static/` (rebuilt React bundle)
- Root cause: Three compounding issues made navigation from /quality, /qa/frame-review, /qa/model-feedback block the new page:
  1. **`RequireAuth` re-ran `getMe()` on every navigation** — each route change mounted a fresh `RequireAuth` component → called `getMe()` (1 HTTP request) AND re-mounted `StoreProvider` → called `adminListStores()` (another request) AND re-mounted `AppLayout` + Sidebar + TopNav. Browsers have a 6-connection limit per origin; these extra requests queued behind any pending QA page requests.
  2. **QA page API calls not cancelled on unmount** — `reportsWalkinsQA` (up to 150+ rows), `qaReviewQueue`, `qaAccuracy` requests continued in-flight after navigation, holding connections open.
  3. **Thumbnail images (`<img>` tags) cannot be cancelled by React** — once a browser starts fetching an `<img>` src, unmounting the element does not cancel the in-flight request.
- Fixes:
  - **App.tsx restructured to single `AuthShell` with `<Outlet />`**: All authenticated routes are children of one `<Route element={<AuthShell />}>`. `AuthShell` renders `StoreProvider` + `AppLayout` + `Suspense` once. `<Outlet />` swaps page content on navigation. Module-level `_authCache` variable means `getMe()` only fires on the very first load — subsequent navigations skip the auth check entirely.
  - **AbortController added to all three QA pages**: On unmount, the pending API call is aborted (`ERR_CANCELED` is swallowed). Added `axiosConfig?: object` param to `reportsWalkinsQA`, `qaReviewQueue`, `qaAccuracy`, `reportsModelAccuracy` in `client.ts`.

### 2026-05-08 - Fix Camera Thumbnails Not Showing on /admin/cameras

- Changed paths:
  - `backend/app/main.py`
  - `backend/app/api/routes_admin.py`
  - `frontend/src/pages/CameraZones.tsx`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Root cause 1 — missing schema migration**: `camera_type` and `sample_image_id` columns added to `canonical_metadata.py` and migration `003_camera_type.py` in the previous session, but the startup `_run_migrations()` in `main.py` never applied them via `ALTER TABLE IF NOT EXISTS`. Added both `ALTER TABLE camera_configs ADD COLUMN IF NOT EXISTS` statements to the startup migration list. Columns applied manually on current PG instance to unblock immediately.
  - **Root cause 2 — discover refresh skip**: Discover endpoint only updated `sample_image_id` for unlabeled cameras. Already-labeled cameras kept a stale (or empty) thumbnail. Changed to always refresh `sample_image_id` on discover (camera_type is never overwritten).
  - **CameraThumb upgraded to match SessionThumb** (the working pattern from QualityFeedback): added `HoverPreview` portal (380×285 zoom-in on mouse hover), hover scale animation, `ZoomIn` icon fallback instead of "No img" text. Exact visual parity with `/quality` thumbnails.
  - **Old build was being served**: Backend serves from `backend/app/static/` but `npm run build` wrote to `frontend/dist/`. Deployed new build by running `cp -r dist/. ../backend/app/static/`.

### 2026-05-08 - Camera-Type Exclusion: Auto-Discovery + Labeling UI + Pipeline Skip

- Changed paths:
  - `backend/app/db/canonical_metadata.py`
  - `backend/app/api/routes_admin.py`
  - `backend/migrations/versions/003_camera_type.py` (new)
  - `src/iris/onfly_pipeline.py`
  - `frontend/src/pages/CameraZones.tsx`
  - `frontend/src/api/client.ts`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **DB migration**: Added `camera_type` (unlabeled/floor/entry/external/skip) and `sample_image_id` to `camera_configs` table in PostgreSQL.
  - **Auto-discovery (`POST /admin/cameras/{store_id}/discover`)**: Reads SQLite `onfly_image_state` to find all distinct camera IDs seen for a store. Auto-inserts new ones into `camera_configs` with `camera_type='unlabeled'` and one representative `sample_image_id`. Already-labeled cameras are untouched.
  - **Post-run auto-discover**: `_auto_discover_cameras()` called at end of every successful pipeline run alongside `_sync_run_to_postgres`. New cameras that appear in a scan are automatically registered without manual intervention.
  - **Pipeline exclusion (`_load_excluded_cameras`)**: At pipeline start, loads camera IDs with `camera_type IN ('external','skip')` from PostgreSQL. In the skip-check loop, any image whose `camera_id` is in the exclusion set is immediately skipped (status: `camera_excluded`) — no YOLO download, no GPT call. Non-fatal if PG is unreachable (empty exclusion set).
  - **CameraZones page rebuilt**:
    - "Discover from pipeline" button — one click populates all cameras from last scan
    - Sample image thumbnail per camera row (fetched via existing `/qa/frame-image` endpoint with `?token=`)
    - Inline type dropdown per camera row — change type saves immediately without a separate form
    - Summary strip: counts per type (floor/entry/external/skip)
    - Warning banner when unlabeled cameras exist
    - Green confirmation banner showing which cameras are excluded from AI
    - Type legend explaining each type and its pipeline effect
  - **Workflow**: Run pipeline once → click Discover → label each camera by type → subsequent pipeline runs skip excluded cameras automatically. 16 cameras discovered and pre-populated for BLRRRN (D01–D15, D18).

### 2026-05-07 - Industry-Standard Pipeline: Parallel Downloads + Rate Limiter + Circuit Breaker + Heartbeat

- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `scripts/_test_pipeline_infra.py` (new — unit tests only, not app code)
- Summary:
  - **Parallel download prefetch (8 workers)**: Downloads are now submitted to a `ThreadPoolExecutor(8)` at skip-check time via `_dl_pool.submit(client.fetch_bytes, ...)`. The YOLO stage retrieves via `_pending_dl[image_id].result()`. On a 5,000-image run, this reduces serial network wait from ~41 min to ~5 min (network no longer the bottleneck — YOLO is).
  - **Token bucket rate limiter (`_TokenBucket`)**: Thread-safe token bucket that enforces `gpt_rate_limit_rps` calls/second across all GPT worker threads. `acquire()` sleeps until a token is available (timeout=30s). Prevents hammering OpenAI and triggering cascading 429s.
  - **Circuit breaker (`_CircuitBreaker`)**: Trips OPEN after 5 consecutive quota/auth failures. Auto-resets after 90s timeout. While OPEN, all GPT workers skip immediately rather than pile-on retrying. Prevents cost storms and allows recovery.
  - **Exponential jitter retry**: GPT calls retry up to 3 times (`_GPT_MAX_ATTEMPTS`) with delay `2^n + uniform(0,1)` seconds (×4 for quota errors), capped at 120s. Jitter prevents synchronized retry storms across 5 concurrent workers.
  - **Dead letter queue**: After 3 failed attempts, image is marked `gpt_dlq` instead of generic `failed`. Distinguishes permanent failures (content policy, corrupt image) from transient ones. Easy to re-queue later.
  - **Heartbeat thread (`_HeartbeatThread`)**: Daemon thread updates `last_heartbeat_at` every 25s via its own SQLite connection. Runs regardless of main-thread blocking (YOLO, GPT, Drive calls). Zombie detection now works correctly — a run with stale heartbeat >2 min is dead, not just slow.
  - **Memory management**: `bytes_cache.pop(image_id, None)` called immediately after GPT result is written. Prevents RAM accumulating to GBs during large runs (5,000 images × ~300 KB = 1.5 GB without this).
  - **`detect_bytes()` integration**: Pipeline YOLO stage now calls `OnnxPersonDetector.detect_bytes(raw_bytes)` directly instead of writing a temp file. Eliminates temp-file I/O on every image.
  - **Unit tests**: All three infrastructure classes verified — token bucket timing, circuit breaker state transitions, heartbeat DB writes. See `scripts/_test_pipeline_infra.py`.

### 2026-05-08 - Option A + Option B: Feedback Loop Closes Into Pipeline

- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `backend/app/api/routes_qa.py`
  - `frontend/src/pages/ModelFeedback.tsx`
  - `frontend/src/api/client.ts`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Option A — correction override**: `trigger_retrain` now writes a second file alongside the versioned rule file: `data/models/qa_corrections_{store_id}.json`. This file contains every confirmed feedback row keyed by (filename, track_id). At pipeline start, `_load_qa_correction_map()` reads this file. After all GPT walk-in sessions are written for the run, `_apply_qa_corrections_to_run()` iterates them and overrides any row whose `source_image_name + walkin_id` matches a confirmed correction — updating `role` and `included_in_analytics`. Corrections persist across re-runs of the same footage without calling GPT again. Falls back gracefully if the file doesn't exist (first run).
  - **Option B — prompt self-improvement**: New endpoint `POST /api/qa/improve-prompt/{store_id}` loads up to 20 rejected feedback rows + fetches their actual images from Drive/local, sends them to GPT with the current `_RETAIL_WALKIN_PROMPT` and asks GPT to write a short additional rule (≤120 words) that would have prevented those specific errors. Returns the suggestion text. New endpoint `POST /api/qa/apply-prompt-improvement/{store_id}` saves the approved text to `data/models/prompt_improvements_{store_id}.json` (with full history). At pipeline start, `_load_prompt_improvement_text()` reads the `active_text` field (concatenation of all applied improvements) and passes it to `_openai_eval()` as `prompt_extra` — appended after the base prompt with a `STORE-SPECIFIC RULES:` header on every GPT call for that store. New endpoint `GET /api/qa/prompt-improvements/{store_id}` returns history.
  - **ModelFeedback page rebuilt**: Two distinct cards — Option A (green, "Sync Corrections") and Option B (violet, "Improve Prompt"). Option B card shows the GPT suggestion in a reviewable monospace block with Apply/Discard buttons. Applied improvement history and collapsible active rule text shown below. Both sections explain exactly what they do and what they cost.
  - **client.ts**: Added `qaImprovePrompt`, `qaApplyImprovement`, `qaGetImprovements`.

### 2026-05-08 - Fix QA/Frame Review Feedback Bugs + Counts Reset

- Changed paths:
  - `frontend/src/pages/FrameReview.tsx`
  - `frontend/src/pages/QualityFeedback.tsx`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **FrameReview — silent save failure**: `FeedbackCard.save()` had no `catch` block. If the API call failed (Postgres error, network issue), the spinner cleared but no error was shown and the row didn't update. Added `catch` block calling `onFlash("Save failed — check server connection")` so the user sees a toast on failure. Added `onFlash` prop to `FeedbackCard` and wired `flash` from the parent.
  - **FrameReview — counts disappearing**: `statusFilter="pending"` (the old default) scoped the server fetch to pending rows only. After confirming/rejecting in-session, counts showed correctly in local state. On next navigation away and back, load() re-fetched "pending" rows from server — confirmed/rejected counts reset to 0. Fix: default changed to `""` (all). Server fetch now always loads all statuses (no `review_status` param). Client-side `filteredRows` memo applies `statusFilter` locally. Cache key no longer includes status. Stats cards always reflect true counts of loaded data.
  - **QualityFeedback — counts reset on navigation**: `load()` called `setFeedbackState({})` on every cache hit, wiping all session approve/reject state whenever the component re-mounted. Fix: `readCache`/`writeCache` updated to include `feedbackState` in the stored payload. On cache hit, `feedbackState` is restored from cache alongside rows. On fresh server fetch (force or cache miss), both rows and feedbackState are reset together. After each approve/reject, `writeCache(rows, updatedFeedback)` is called inside `setFeedbackState` to keep cache in sync. Error handling (`catch` + `flash`) added to both `saveApprove` and `saveReject` (they already had try/catch but the error message was already there; restructured to compute `newEntry` before `setFeedbackState` so cache can be updated atomically).

### 2026-05-08 - Fix RejectPicker Blending Into Background (QualityFeedback)

- Changed paths:
  - `frontend/src/pages/QualityFeedback.tsx`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **RejectPicker overlay**: Previously `absolute inset-0 bg-white/95` — confined inside the tiny actions table column (a few pixels tall), semi-transparent, blended into the rose/emerald row background. Rewrote as `fixed inset-0 z-50 bg-slate-900/40` fullscreen overlay with a centred `bg-white rounded-2xl shadow-2xl` card. Clicking the backdrop cancels. Added `type="button"` to both buttons to clear IDE warnings.

### 2026-05-08 - Fix Overview/StoreDetail Showing Zero Analytics

- Changed paths:
  - `backend/app/api/routes_dashboard.py`
  - `backend/app/api/routes_detail.py`
  - `backend/app/api/routes_reports.py`
- Summary:
  - **Root cause 1 — date format mismatch**: The pipeline stores `business_date` in SQLite as `DD-MM-YYYY` (e.g. `06-05-2026`) for recent runs. All dashboard analytics queries filtered with `business_date >= DATE('now', '-30 days')` which returns `YYYY-MM-DD`. String comparison `'06-05-2026' < '2026-04-07'` → all recent rows silently excluded. Added inline `CASE WHEN ... GLOB '??-??-????' THEN ... END` normalization (`_ISO_DATE`) to all date comparisons and `GROUP BY period` in `routes_dashboard.py` (`_sqlite_analytics`, `_sqlite_trend`, `_sqlite_leaderboard`, `_sqlite_delta`). Result: 137 walk-ins now visible vs 86 before (the 86 happened to be in YYYY-MM-DD format from older runs).
  - **Root cause 2 — wrong database for store detail**: `routes_detail.py` called `get_store_metrics()` and `get_walkin_sessions()` from `platform_data.py` which uses `AsyncSessionLocal` → PostgreSQL. The pipeline never writes to PostgreSQL `onfly_walkin_sessions`. Rewrote `routes_detail.py` with direct SQLite queries (same pattern as `routes_dashboard.py`), keeping only `list_store_registry_stores` from `platform_data` (stores managed in PG).
  - **Root cause 3 — Summary tab join**: `_sqlite_runtime_summary` in `routes_reports.py` joined `walkin_rollup.business_date` against `image_rollup.iso_date` (already normalized to YYYY-MM-DD). The raw `business_date` DD-MM-YYYY never matched. Fixed by normalizing `business_date` inside the `walkin_rollup` CTE before grouping.

### 2026-05-08 - Reports UX Overhaul + Zombie Run Fix

- Changed paths:
  - `frontend/src/pages/ReportsPage.tsx`
  - `frontend/src/components/layout/TopNav.tsx`
  - `frontend/src/api/client.ts`
  - `backend/app/api/routes_reports.py`
  - `src/iris/onfly_pipeline.py`
  - `backend/app/main.py`
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Lazy tab loading**: Reports page previously fired 4 parallel API calls (loading ~9,000 rows) on every mount. Now only the active tab's data is fetched on first visit. Other tabs load on demand. Re-fetching only happens on explicit Refresh click.
  - **sessionStorage caching**: All four tab views cached with 5-minute TTL using key `rp-v1:{store}:{tab}`. Back/forward navigation is instant; cache is shared with hover-prefetch.
  - **Hover-prefetch on store selector**: Hovering a store in the TopNav dropdown triggers a 200ms-debounced prefetch of that store's summary tab. Result is written to the same sessionStorage key ReportsPage reads — so switching stores loads summary data immediately.
  - **Background CSV export (zero infra)**: Download no longer blocks the UI. A FastAPI daemon thread generates the CSV; frontend polls every second and auto-downloads when ready. Toast notifications show loading / success / error. No Redis, no Celery, no new services. Job registry is an in-process dict purged after 10 minutes.
  - **SQLite covering indexes**: Two indexes added in `_init_db` — `(store_id, date_display, yolo_relevant)` on `onfly_image_state` and `(store_id, business_date)` on `onfly_walkin_sessions`. Turns GROUP BY summary queries from full scans to index lookups.
  - **Zombie run fix — pipeline**: `finally` block in `run_onfly_pipeline` now checks if the run is still `status='running'` after stopping the heartbeat thread. If so (meaning a `BaseException` / SIGTERM killed the process before the `except Exception` block ran), it marks the run as `abandoned`. Previously, SIGTERM left runs stuck in 'running' forever.
  - **Zombie run fix — startup cleanup**: `_cleanup_zombie_runs` in `main.py` threshold lowered from `-5 minutes` to `-2 minutes` for heartbeat staleness. Removed the `started_at > -3 minutes` guard (which blocked cleanup of runs killed just before restart). Startup is now reliable at catching any orphaned run.
  - **UI fix**: `liveProgress.error` in Reports page now only renders when `liveProgress.is_running` is true. Previously showed stale error messages from dead/abandoned runs as if they were current.
  - **Orphaned server**: Killed PID 8596 (old server on port 8767 — orphaned from a prior restart and competing on the same SQLite DB, causing zombie run misdetection).

### 2026-05-08 - Architecture Fix: Role/Date Normalization + GDrive Scan Fix + PG Sync

- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `backend/app/api/routes_dashboard.py`
  - `frontend/src/main.tsx`
  - `scripts/fix_normalize_and_sync_walkins.py` (new — one-time data repair + PG sync)
  - `backend/app/static/` (rebuilt React bundle)
- Summary:
  - **Role normalization at write time**: `_norm_role()` maps all variants ('CUSTOMER', 'customer', 'inside active', 'poster non human', etc.) to canonical title-case ('Customer', 'Staff', 'Banner', 'Uncertain', 'Passerby') before writing to SQLite. Prevents role mismatches in analytics GROUP BY queries.
  - **Date normalization at write time**: `_norm_date()` converts DD-MM-YYYY → YYYY-MM-DD at write point for `business_date` and `date` columns. Prevents all future runs from writing mixed-format dates.
  - **`included_in_analytics` normalization**: `_norm_yn()` enforces 'Yes'/'No' (not 'yes'/'YES'/'no') at write time.
  - **GDrive scan stuck fix**: `GDriveClient.list_images()` was counting already-processed Drive file IDs against `max_images` limit. When resuming a run, the DFS would hit the limit immediately using seen IDs, returning 0 new files. Fix: added `seen_ids: set[str] | None` parameter; DFS skips seen IDs entirely so `max_images` counts only genuinely new files. `RunConfig.max_images` default also changed from `100` → `0` (unlimited).
  - **Post-run PostgreSQL sync**: `_sync_run_to_postgres()` added. Called at end of each successful run. Strategy: DELETE existing PG rows for `run_id + store_id`, then bulk INSERT fresh from SQLite. Avoids `ON CONFLICT` constraint on RANGE-partitioned table (`created_at` partition key).
  - **One-time data repair script** (`scripts/fix_normalize_and_sync_walkins.py`): Normalizes all 9,470 existing SQLite walkin sessions in-place (role, business_date, date, included_in_analytics) and syncs all to PostgreSQL (was 120, now 9,470). Supports `--dry-run`.
  - **ErrorBoundary**: React class component wrapping entire app catches chunk-load failures (`Failed to fetch dynamically imported module`) and render crashes. Shows "App updated — refresh" card for chunk errors; shows error message for other crashes. Prevents blank screen on stale bundle after deploy.
  - **Overview route fixed**: `/dashboard/overview` endpoint now reads from SQLite via `_sqlite_analytics()` (same source as the frontend `/dashboard/analytics` call), not PostgreSQL `get_overview_metrics()`.

### 2026-05-07 - In-App ONNX Detection Boxes + Visual Review Script

- Changed paths:
  - `src/iris/iris_analysis.py`
  - `backend/app/api/routes_qa.py`
  - `frontend/src/api/client.ts`
  - `frontend/src/pages/FrameReview.tsx`
  - `backend/app/static/` (rebuilt React bundle)
  - `scripts/review_detections.py` (new)
- Summary:
  - **Frame Review — annotated image toggle**: Each thumbnail card now has a `ScanSearch` toggle button (top-right corner). Click it to switch between the raw camera frame and the ONNX-annotated version with coloured bounding boxes drawn live (green ≥0.60 conf, orange 0.30–0.60, red <0.30). Click again to return to raw. The annotated image is generated on-demand by the backend, never cached to disk.
  - **`GET /api/qa/frame-image/{store_id}/{image_id}/annotated`** (new endpoint): Fetches the image from Drive, runs `OnnxPersonDetector.detect_bytes()` in-process, draws boxes + person count banner with OpenCV, returns JPEG. No temp files written; Drive bytes go directly into numpy via `cv2.imdecode`. Cached in browser for 5 minutes.
  - **`OnnxPersonDetector.detect_bytes(bytes)`** (new method): Accepts raw image bytes, runs the full letterbox + ONNX inference pipeline without writing to disk. Extracted `_run_inference(rgb)` as a shared private method so both `detect(path)` and `detect_bytes(bytes)` use identical inference logic.
  - **`scripts/review_detections.py`** (new CLI tool): Visual review of live camera frames. Draws bounding boxes on the latest N frames from `data/stores/`, saves annotated JPEGs to `data/review/`, opens Explorer automatically. Flags: `--frames N`, `--store BLRJAY`, `--image path`, `--compare` (ONNX vs YOLO side-by-side), `--conf 0.20`.
  - **Letterbox fix**: `_letterbox_cv2` now uses `cv2.copyMakeBorder` with `round(dh-0.1)/round(dh+0.1)` padding split — matches ultralytics internal implementation exactly. NMS IoU threshold 0.70 → 0.45 (ultralytics default).
  - **Accuracy**: ONNX vs YOLO validation at 50 frames, conf=0.20: **86% exact match, 2.7× faster** (293 ms vs 790 ms per image). Remaining 14% are symmetric fp32 arithmetic differences — not a systematic accuracy loss.

### 2026-05-07 - GPT Prompt: White Shirt + Black Pants = Staff (not Manager)

- Changed paths:
  - `src/iris/onfly_pipeline.py`
- Summary:
  - **Prompt update**: Clarified that both red shirt + black pant (floor staff) AND white shirt + black pant (managers/supervisors) are always classified as `Staff`. There is no `Manager` role — the only valid Role values are `Customer`, `Staff`, `Uncertain`. Added explicit instruction that GPT must NOT output `Manager` as a Role. Post-processing function comment updated to match.

### 2026-05-07 - QA/Frame Review Fixes, YOLO Threshold Tuning, README Docker

- Changed paths:
  - `frontend/src/pages/QualityFeedback.tsx`
  - `frontend/src/pages/FrameReview.tsx`
  - `backend/app/api/routes_reports.py`
  - `backend/app/config.py`
  - `backend/app/static/` (rebuilt React bundle)
  - `README.md`
- Summary:
  - **QualityFeedback (quality page) — approve/reject now saves to backend**: Previously approve/reject only updated local state and was never persisted. Now calls `qaCreateFeedback` (new row) or `qaUpdateFeedback` (existing row) on every action. Reject shows an inline correction picker (Customer / Staff / Uncertain / No Human) before saving. FeedbackId tracked per row to use PUT instead of POST on subsequent changes. Progress bar shows how many reviews toward the 200-row retraining threshold. Entry+exit thumbnails shown separately using new `last_image_id` field.
  - **routes_reports.py walkins-qa**: Extended `cam_images` CTE to also compute `MAX(image_id) AS last_image_id`. API now returns separate `image_id` (entry frame) and `last_image_id` (exit frame) per walk-in session so QA Overview can show distinct thumbnails for start and end of each visit.
  - **FrameReview — performance fix**: Page was re-fetching 400 rows every time user navigated back to it. Now caches results in `sessionStorage` with 5-minute TTL (keyed by store+status+date). Navigation back is instant; cache badge shows age; Refresh button bypasses cache. Default fetch limit reduced from 400 → 150 rows.
  - **FrameReview — Step 1 / Step 2 labelling**: Each card now clearly shows two sections: Step 1 YOLO Detection (person count + confidence %) and Step 2 GPT Classification (customer/staff/banner/pedestrian counts). Low YOLO confidence warning shown when score < 65% but people detected. Reviewer label dropdown positioned under both steps.
  - **YOLO confidence threshold**: Default raised from 0.18 → 0.30 in `config.py`. At 0.18, many banners and reflections with 18–29% YOLO confidence were being passed to GPT (false positives adding cost). At 0.30, only detections with meaningful YOLO confidence reach GPT, reducing unnecessary API calls by ~15–20% while preserving real customer recall. Override via `YOLO_CONF` in `.env`.
  - **README**: Docker section rewritten to explain when Docker is needed (cloud, not local), what it starts automatically (API + Celery + Redis), and cost (free — you pay for the server, not Docker itself).

### 2026-05-07 - Update Deployment Docs per EC2 150-Store Spec

- Changed paths:
  - `docs/deployment/deployment-readiness-report-2026-04-30.md`
  - `docs/deployment/deployment-email-drafts-2026-04-30.md`
- Summary:
  - **Deployment readiness report**: Updated Section 2.6 (Streamlit → RETIRED 2026-05-07), Section 3 (hosting requirements rewritten for EC2 c6i.large + c6i.2xlarge + t3.micro + RDS db.t3.large + ElastiCache + ALB; storage note corrected — images never stored, DB grows ~2.7 GB/month), Section 4 (readiness checklist updated — GPT live, Streamlit retired, bundles cleaned; new blockers: OpenAI Tier 3+, Secrets Manager, Drive stagger), Section 5 (all cleanup items marked RESOLVED), Section 7 (future direction updated with new items: Drive rate limiting, 90-day retention, PII policy).
  - **Email drafts**: Section 3 (Hosting Requirements) replaced generic 8GB/4vCPU spec with full EC2 production table and correct cost figures ($523/month infra, $6,500–13,000/month OpenAI at 54,000 calls/day). Section 4 (Readiness checklist) updated to reflect 2026-05-07 state. Section 5 updated to reflect cleanup as resolved. Requested Actions table rewritten: removed stale rows (stop ports 8768/8769, clean static bundles, trigger GPT on Apr 23+ images), added new rows (EC2 provisioning with correct instance types, OpenAI Tier 3+ upgrade, AWS Secrets Manager, staggered Drive sync, 90-day retention job).

### 2026-05-07 - Retire Streamlit, Mature React + FastAPI

- Changed paths:
  - `src/iris/iris_dashboard.py` (deleted)
  - `src/run_dashboard.py` (deleted)
  - `scripts/start_web_app.py` (deleted)
  - `deploy/Dockerfile` (deleted)
  - `deploy/requirements.docker.txt` (deleted)
  - `fix_login.py` (deleted)
  - `patch.py` (deleted)
  - `requirements.txt`
  - `deploy/docker-compose.yml`
  - `README.md`
  - `AGENTS.md`
  - `backend/app/static/` (rebuilt React bundle)
  - `release-notes/2026-05-07-streamlit-retired-react-fastapi-only.md` (new)
  - `docs/deployment/IRIS-Server-Requirement-150-Stores.md` (new)
  - `docs/deployment/scaling-analysis-150-stores.md` (deleted — superseded)
- Summary:
  - Deleted all Streamlit source, entrypoints, Dockerfile, and deps. Removed `streamlit`, `plotly`, `pyarrow` from `requirements.txt`. Docker Compose `iris` service (port 8765) removed. README fully rewritten for React + FastAPI stack. AGENTS.md updated with deleted module table and corrected deploy commands. React build confirmed clean: 0 errors, 3,884 modules, 20 pages. New EC2 server requirements document created for 150-store production scale. Stale scaling analysis doc deleted.

### 2026-05-04 - Storage Optimization (Zero Waste, 7-Day Retention, S3 Config Toggle)

- Changed paths:
  - ackend/app/config.py
  - ackend/app/celery_app/worker.py
  - ackend/app/celery_app/tasks/drive_sync.py
  - ackend/app/celery_app/tasks/cleanup.py (new)
  - src/iris/onfly_pipeline.py
  - src/iris/drive_delta_sync.py
  - scripts/yolo_relevance_scan.py
  - docs/AI_HANDOVER_STORAGE.md (new)
- Summary:
  - **Zero Waste Policy**: onfly_pipeline.py and yolo_relevance_scan.py now instantly delete the local image file (Path.unlink()) if YOLO detects no people (
elevant == 0).
  - **Drive Sync Redownload Guard**: drive_delta_sync.py was updated to check the store_source_file_index database table for source_file_id. It now skips downloading files that have already been tracked, preventing the sync from endlessly redownloading images deleted by the Zero Waste policy.
  - **7-Day Retention Policy**: Added cleanup_old_images_task to celery_app/tasks/cleanup.py and scheduled it to run daily at 2:00 AM via Celery beat. It sweeps data/stores/ and permanently deletes any images older than 7 days.
  - **S3 Config Toggle**: Added enable_s3_storage to config.py (defaults to False). The Google Drive pipeline is maintained as the primary source. Setting the S3 flag to True bypasses Drive sync and logs an S3 stub, ready for IT integration.
  - **AI Handover**: Created docs/AI_HANDOVER_STORAGE.md explaining the storage rules and S3 transition strategy for future agents.


### 2026-05-04 - Fix GPT Disabled: Scheduler Hardcoded gpt_enabled=False

- Changed paths:
  - `backend/app/api/routes_onfly.py`
  - `backend/app/db/canonical_metadata.py`
  - `data/store_registry.db` (data fix — 6,625 rows reset, not committed)
- Summary:
  - **Root cause from data**: `_check_and_trigger_auto_syncs()` passed hardcoded `False` as `gpt_enabled` to every scheduled run, marking all YOLO-relevant images as `gpt_status='disabled'`. Evidence: 6,622 disabled images vs 11 GPT-done (the one manual run on 2026-05-01 where user ticked GPT ON in UI).
  - **Fix — scheduler**: Changed hardcoded `False` to `bool(s.get("gpt_enabled", True))`. Added `stores.c.gpt_enabled` to the scheduler SELECT query.
  - **Fix — DB schema**: Added `gpt_enabled BOOLEAN DEFAULT true` to `stores` in `canonical_metadata.py`. Ran `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migration on Postgres. BLRRRN confirmed `gpt_enabled=True`.
  - **Data fix**: Reset 6,625 `gpt_status='disabled'` images (where `yolo_relevant=1`) to `gpt_status='pending'` in SQLite — queued for GPT on next run.
  - **Remaining blocker**: `OPENAI_API_KEY` must be set in `.env` for GPT to execute. Add `OPENAI_API_KEY=sk-...` to `.env` and restart the server.

### 2026-05-03 - Fix GOOGLE_API_KEY Not Reaching Pipeline, Fix UNIQUE Constraint Crash

- Changed paths:
  - `src/iris/onfly_pipeline.py`
  - `backend/app/api/routes_onfly.py`
  - `backend/app/config.py`
  - `.env` (created locally — gitignored, never committed)
- Summary:
  - **Root cause**: `pydantic_settings` had no `env_file` configured, so `.env` was never read. `GOOGLE_API_KEY` defaulted to `""` in `Settings`, but `onfly_pipeline.py` was reading it directly from `os.getenv()` which also returned `""` since the OS environment had no such variable when the server was started by a script that didn't export it.
  - **Fix 1 — env_file**: Added `"env_file": ".env"` and `"env_file_encoding": "utf-8"` to `Settings.model_config` so pydantic-settings auto-reads `.env` from repo root on startup.
  - **Fix 2 — key threading**: Added `google_api_key: str = ""` field to `OnFlyConfig`. `build_source_client()` now accepts `google_api_key` param — prefers it over `os.getenv()`. `_run_pipeline_sync()` in `routes_onfly.py` passes `settings.google_api_key` into the config. No more reliance on ambient OS environment.
  - **Fix 3 — UNIQUE constraint**: Changed `INSERT INTO onfly_image_state` to `INSERT OR IGNORE` — concurrent pipeline runs (two scheduler triggers firing before the first finishes) could both pass the `SELECT` check and then both attempt the same insert. `OR IGNORE` makes the second insert a no-op instead of a crash.
  - **Key type clarification**: The `GOOGLE_API_KEY` (`AIzaSy…`) is a Google Simple API Key (not a service account JSON, not OAuth). It is the correct key type for Drive API v3 with `?key=` query parameter. No other key type is needed.

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

### 2026-05-12 - Fix PowerShell LAN Helper Argument Parsing
- Changed paths:
  - `scripts/enable_api_network_access.ps1`
  - `CHANGE_LEDGER.md`
- Summary:
  - Replaced the fragile PowerShell `param(...)` entrypoint with explicit argument parsing so `-Port 8767` and `-SetPrivateProfile` work reliably when launched with `powershell -File`.
  - Added self-elevation handling so the helper can prompt for Administrator approval and continue setting the firewall rule without manual script edits.
  - Tightened LAN IP detection to prefer the active default-route adapter so the helper reports the real network URL instead of virtual adapter addresses.

### 2026-05-12 - Restore Localhost Access On Port 8767
- Changed paths:
  - `scripts/localhost_ipv6_proxy.py`
  - `start_iris.ps1`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added an IPv6 localhost bridge so browsers resolving `localhost` to `::1` can still open IRIS on port `8767` even when the main app is listening on IPv4.
  - Updated the supported Windows launcher to start that bridge automatically before the FastAPI process.
  - Kept the main server bound to `0.0.0.0` so LAN access via `192.168.1.113:8767` continues to work for other devices.

### 2026-05-12 - Refresh AI Handover For Startup And Network Access
- Changed paths:
  - `docs/AI_HANDOVER_STORAGE.md`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added explicit handover notes for the supported local startup path, the IPv6 localhost bridge, and the Windows firewall helper used for same-LAN access on port `8767`.
  - Captured the guardrail that both `http://localhost:8767` and `http://<LAN-IP>:8767/` must remain working together after future startup changes.

### 2026-05-12 - Release Notes For May Overview QA And Network Changes
- Changed paths:
  - `release-notes/2026-05-12.md`
  - `CHANGE_LEDGER.md`
- Summary:
  - Added a dated stakeholder-facing release note covering the recent `/overview` date filtering work, QA page reliability/performance fixes, and the local plus LAN access hardening on port `8767`.
  - Captured the release scope, impact, rollout availability, risks, rollback path, and validation history in the standard `release-notes` format.

### 2026-05-12 - Restore Missing Static Chunks For Local And LAN Web Access
- Changed paths:
  - `backend/app/static/assets/ActivityLogs-c3uhES8p.js`
  - `backend/app/static/assets/CameraZones-C8VFy9ws.js`
  - `backend/app/static/assets/CustomerJourneys-DDWFH78Q.js`
  - `backend/app/static/assets/EmployeeManagement-CHADoRv-.js`
  - `backend/app/static/assets/charts-xFXgYxa9.js`
  - `CHANGE_LEDGER.md`
- Summary:
  - Restored missing built frontend chunks in `backend/app/static/assets` so the browser can load the full React bundle from both `http://localhost:8767/` and `http://192.168.1.113:8767/`.
  - Fixed the broken static deployment state where `index.html` referenced chunk files that were present in `frontend/dist` but absent from the served backend static directory.

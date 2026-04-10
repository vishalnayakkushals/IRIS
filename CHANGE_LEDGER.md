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
| `release-notes/2026-04-01-onfly-pipeline.md` | Release-note summary for the on-fly pipeline rollout and deprecation note for bulk upload nav. |
| `scripts/benchmark_onfly_pipeline.py` | Before/after timing benchmark utility (3-run profile) for slowness diagnosis and optimization tracking. |
| `scripts/onfly_scheduler.py` | Hourly + nightly catch-up scheduler for on-the-fly runtime with app-setting status persistence. |
| `scripts/run_onfly_pipeline.py` | CLI wrapper for on-the-fly runtime execution (manual/hourly/nightly modes). |
| `scripts/scan_b2b_template.py` | External B2B template + SOP scanner that generates IRIS-ready incorporation reports (JSON + Markdown). |
| `scripts/setup_local_env.ps1` | Local-only secure env bootstrapper: reads API keys from key files and writes `.env.local` for Docker/run commands. |
| `scripts/optimize_docker_runtime.ps1` | Lightweight runtime switcher: stops optional high-memory services and keeps only core on-fly services running. |
| `src/iris/onfly_pipeline.py` | Lightweight URL-first runtime: source listing, YOLO relevance, optional GPT pass, idempotent state, and store/date exports. |
| `docs/process/onfly_pipeline_logic.md` | Canonical human-readable on-fly logic reference (stage flow, timestamp rules, session behavior, and output artifacts). |
| `docs/process/onfly_independent_app_checklist.md` | Readiness checklist for moving on-fly workflow to an independent app mode (no manual shell dependency). |
| `CTO/scripts/perf_common.py` | Shared isolated CTO log utilities (single JSONL sink, path setup, run id, percentile). |
| `CTO/scripts/perf_cycle.py` | Single-command CTO run tracker: optional fix-command timing + page probe timing + run lifecycle events. |
| `CTO/scripts/perf_run.py` | Manual run lifecycle logger (start/end) for custom workflows. |
| `CTO/scripts/perf_analyze.py` | CTO analyzer for slow paths/regressions and latest markdown/csv report generation. |
| `CTO/scripts/perf_watch.py` | Continuous interval-based page probe logger for browsing-speed trend capture. |
| `CTO/run_cto_cycle.bat` | Windows wrapper to run a CTO perf cycle quickly with default dashboard URLs. |
| `CTO/run_cto_watch.bat` | Windows wrapper for continuous CTO browse-speed watch mode. |
| `CTO/README.md` | Usage and isolation guarantees for the CTO observer layer. |

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

### 2026-04-03 | Commit pending
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

### 2026-04-03 | Commit pending

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

### 2026-04-03 | Commit pending
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

### 2026-04-03 | Commit pending
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

### 2026-04-01 | Commit pending
- Summary:
  - Fixed CI lint failure by importing `Any` used in GPT frame-index type annotations.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None.

### 2026-04-01 | Commit pending
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

### 2026-04-01 | Commit pending
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

### 2026-04-01 | Commit pending
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

### 2026-04-01 | Commit pending
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


### 2026-04-01 | Commit pending
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


### 2026-04-01 | Commit pending
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


### 2026-04-01 | Commit pending
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

### 2026-03-31 | Commit pending
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

### 2026-03-31 | Commit pending
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

### 2026-03-31 | Commit pending
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

### 2026-03-27 | Commit pending
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

### 2026-03-27 | Commit pending
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

### 2026-03-30 | Commit pending
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

### 2026-03-30 | Commit pending
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

### 2026-03-16 | Commit pending
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

### 2026-03-16 | Commit pending
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

### 2026-03-16 | Commit pending
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

### 2026-03-18 | Commit pending
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

### 2026-03-18 | Commit pending
- Summary:
  - Switched repository workflow source-of-truth path to `Desktop\\Github\\IRIS` in agent instructions so local working convention matches requested deployment flow.
- Changed Paths:
  - `AGENTS.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | Commit pending
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

### 2026-03-18 | Commit pending
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

### 2026-03-18 | Commit pending
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

### 2026-03-18 | Commit pending
- Summary:
  - Fixed broken hover verification links by sanitizing `nan` values and resolving preview images from local `path/relative_path/source_folder` fallback logic in customer journey views.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-18 | Commit pending
- Summary:
  - Fixed Google Drive API sync reliability on restricted networks by adding download fallback (`drive.google.com/uc`) when `alt=media` is blocked, and skipping already-present files to speed repeated syncs.
- Changed Paths:
  - `src/iris/store_registry.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
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

### 2026-03-19 | Commit pending
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

### 2026-03-19 | Commit pending
- Summary:
  - Fixed blank/zero-data dashboard regression caused by stale exports by adding empty-export detection and one-time auto-recovery analysis when source images exist; added explicit no-source message when root path has no images.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Added explicit dashboard notice when `Images Per Store` sampling is enabled to prevent confusion when totals appear capped (e.g., 200 images instead of full folder volume).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed stale in-session dashboard data by auto-reloading exports when `all_stores_summary` on disk is newer than cached session output (supports terminal-triggered analysis runs without manual cache reset).
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed detection-cache poisoning across detector changes by adding detector signature (backend/model/conf/device) into cache key; prevents old `Detector unavailable` results from being reused after YOLO is enabled.
- Changed Paths:
  - `src/iris/iris_analysis.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
- Summary:
  - Fixed YOLO full-build dependency conflict by forcing `numpy<2` after YOLO install so `pandas/pyarrow` remain ABI-compatible in Docker runtime.
- Changed Paths:
  - `deploy/Dockerfile`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Full YOLO Docker builds now explicitly pin `numpy<2` with existing `pyarrow` constraint.

### 2026-03-19 | Commit pending
- Summary:
  - Improved Pipeline Configuration date parsing to accept compact `YYYYMMDD` inputs (for example `20260317`) by normalizing to ISO before analysis.
- Changed Paths:
  - `src/iris/iris_dashboard.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-19 | Commit pending
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

### 2026-03-19 | Commit pending
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

### 2026-03-19 | Commit pending
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


### 2026-03-19 | Commit pending
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

### 2026-03-20 | Commit pending
- Summary:
  - Added a project sign-off security checklist covering key deletion, token rotation, and docker/cache cleanup.
- Changed Paths:
  - `SECURITY_CLEANUP_CHECKLIST.md`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - `SECURITY_CLEANUP_CHECKLIST.md`
- Infra/Config Impact:
  - None

### 2026-03-20 | Commit pending
- Summary:
  - Added immediate progress logging (`flush=True`) to drive delta scheduler so long first-run syncs show visible start/completion state in log files and terminal output.
- Changed Paths:
  - `scripts/drive_delta_sync_scheduler.py`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - None

### 2026-03-20 | Commit pending
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

### 2026-03-23 | Commit pending
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

### 2026-03-23 | Commit pending
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

### 2026-03-23 | Commit pending
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

### 2026-03-26 | Commit pending
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

### 2026-03-26 | Commit pending
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

### 2026-03-30 | Commit pending
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

### 2026-04-06 | Commit pending
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

### 2026-04-06 | Commit pending
- Summary:
  - Updated `run_iris.bat` to auto-load `OPENAI_API_KEY` and `GOOGLE_API_KEY` from local key files when env vars are empty, so `onfly-run-now`, `onfly-benchmark`, `onfly-scheduler-start`, and `gpt-test-validation-now` run without manual key paste.
- Changed Paths:
  - `run_iris.bat`
  - `CHANGE_LEDGER.md`
- New Modules Introduced:
  - None
- Infra/Config Impact:
  - Optional local key-file env overrides supported: `OPENAI_KEY_FILE`, `GOOGLE_KEY_FILE`.

### 2026-04-06 | Commit pending
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

### 2026-04-07 | Commit pending
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

### 2026-04-07 | Commit pending
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

### 2026-04-07 | Commit pending
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

### 2026-04-07 | Commit pending
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

### 2026-04-07 | Commit pending
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

### 2026-04-07 | Commit pending
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


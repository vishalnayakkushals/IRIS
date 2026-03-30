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
| `scripts/refresh_and_check.ps1` | One-command local automation: pull/build(or restart)/recreate/wait/log-scan with fast failure for troubleshooting. |
| `scripts/scheduler_worker.py` | Dedicated background scheduler worker: executes sync/feedback/retrain/predict cycles and updates scheduler runtime state in app settings. |
| `run_iris.bat` | Windows launcher wrapper for one-command IRIS refresh in restart/rebuild mode. |
| `scripts/store_google_api_key.py` | One-time utility to encrypt and persist Google API key in local data/secrets path. |
| `scripts/benchmark_drive_sync.py` | Throughput benchmark utility to estimate first-day and daily sync times. |
| `.dockerignore` | Excludes heavy runtime data/cache from Docker build context to reduce build time and storage usage. |
| `SECURITY_CLEANUP_CHECKLIST.md` | Sign-off checklist to remove temporary keys/tokens and development artifacts. |
| `tests/test_iris_analysis.py` | Analysis pipeline and detector tests. |
| `tests/test_store_registry.py` | Registry, sync, access-control, and persistence tests. |
| `tests/test_drive_delta_sync.py` | Delta-sync planner/scope/deletion behavior tests. |

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


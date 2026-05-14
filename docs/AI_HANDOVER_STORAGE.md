# AI Handover — Runtime, Storage, and Cost State

**Last updated:** 2026-05-14

This is the short operational handover for the current IRIS architecture.

Use `docs/INDEX.md` as the documentation ownership map. Use `docs/developer/generated-vs-source-policy.md` before editing built assets or runtime/export artifacts.

---

## Runtime Shape (Current Truth)

IRIS now runs as four explicit services:

1. `start_api_server.py`
2. `start_scheduler_worker_service.py`
3. `start_onfly_scheduler_service.py`
4. `start_store_auto_sync_service.py`

The FastAPI web process no longer owns scheduler loops. Runtime preparation is handled before launch through `backend/app/runtime_startup.py`.

Important local runtime note:
- `scripts/start_store_auto_sync_service.py` must put both the repo root and `src/` on `sys.path`, because the worker imports `backend.app.workers.store_auto_sync` as well as `iris.*` modules.

### Local Launch And Network Access

- The single supported local startup path is `start_iris.bat` -> `start_iris.ps1`.
- For quick local recovery when `localhost:8767/login` fails, use `scripts/restart_iris_local.ps1`; it stops stale listeners, loads `.env.local`, starts FastAPI on `0.0.0.0:8767` through `scripts/run_api_server_detached.py`, starts the IPv6 proxy, and verifies `/api/health`.
- The main FastAPI app listens on IPv4 `0.0.0.0:8767` so the same instance can serve both the local machine and same-LAN devices.
- Some Windows environments resolve `localhost` to IPv6 `::1` first. To keep `http://localhost:8767` reliable, `start_iris.ps1` also launches `scripts/localhost_ipv6_proxy.py`, which forwards `::1:8767` to `127.0.0.1:8767`.
- Same-LAN access depends on the Windows firewall allowing TCP `8767`. The supported helper is `scripts/enable_api_network_access.ps1`.
- If LAN access works for some devices but not others, check the firewall/profile first before assuming the FastAPI app is down.

---

## Data Stores

### PostgreSQL
Primary platform system-of-record for:
- users / auth / roles
- stores / cameras / admin metadata
- dashboard-facing platform tables

### SQLite (`data/store_registry.db`)
Fast pipeline-state store for:
- `onfly_image_state`
- `onfly_walkin_sessions`
- `onfly_pipeline_runs`
- `onfly_pipeline_run_events`
- `onfly_task_queue`
- `onfly_cost_metrics`
- batch queue tables

Reports and operational screens can read directly from SQLite for live pipeline visibility.

---

## Current Storage Behavior

- Images are fetched from Drive/local source into memory.
- No permanent raw-image store is required for normal processing.
- Irrelevant local-only images can still be removed after processing according to pipeline policy.
- Canonical outputs are written under `data/exports/current/onfly/`.
- Each run now also writes lightweight YOLO-review manifest CSVs under `data/exports/current/onfly/<store_id>/yolo_review_manifests/`, including one combined file plus one same-date folder per scanned date with Drive links for relevant images only.
- Exact processing stats can now be exported with `scripts/export_onfly_processing_stats.py`, which writes `onfly_processing_stats.csv` plus `onfly_processing_stats_summary.json` under `data/exports/current/onfly/` by reconciling live source-folder counts, SQLite state, run-event failures, walk-in rows, and report-file visibility.
- On-fly runs now copy YOLO-relevant Google Drive files back into the same store parent folder under `Relevant image/<date-folder>/<original filename>`.
- The `/scheduler` page now has a YOLO Relevant Review Table card. It can start a full-folder YOLO run with OpenAI GPT calls forced off (`max_images=0`) and can generate/download the same relevant-image CSV table as `scripts/export_relevant_review_table.py`.
- The review-table CSV is generated from existing `onfly_image_state` rows only. It does not change relevance logic, YOLO thresholds, GPT logic, source folders, or Drive image output behavior.
- IRIS preserves the scanned date-folder name and original filename for Drive review copies. If the same filename already exists in the destination date folder, the exporter skips the copy to keep the flow idempotent.
- IRIS can create Google Drive review folders and file copies when a real write-capable service account is configured. The preferred local setup is `GOOGLE_SERVICE_ACCOUNT_FILE=.local-secrets/google_service_account.json`, configured with `scripts/configure_drive_service_account.py`.
- The read-only API key path still works for source listing/fetching, but the write path remains inactive until a real service-account JSON key or real `GOOGLE_PRIVATE_KEY` is configured and the source Drive parent folder is shared with that service-account email as Editor.

### Large Folder Scan Guardrail

- Full-folder scans must use `max_images = 0`; the runtime default now preserves that instead of falling back to a legacy 10,000-image cap.
- After Drive listing completes, the pipeline seeds all discovered images into `onfly_image_state` before download/YOLO/GPT work begins. This is important because scheduler reports, Frame Review date filters, and other runtime screens depend on that table for date completeness.
- The old background download pool has been removed from the on-fly runtime because it was not delivering real prefetch gains and had produced unstable shutdown behavior during large runs.
- SQLite heartbeat writes now use WAL plus a longer busy timeout so long-running scans are less likely to be marked stale while write traffic is high.
- The scheduler UI and run-status summaries should stay aligned with this behavior: no frontend copy should claim manual runs are capped at 10,000 anymore.
- Date-wise scan views should sort by normalized ISO business date internally, not by display text such as `dd-mm-yyyy`.
- Exact full-store Drive stats are intentionally slower than dashboard reads because they rescan the live source folder for proof. For very large stores, use the script's `--date dd-mm-yyyy` filter when you need a single-date audit, because the Drive walk now prunes directly to that date folder.
- Google Drive review-write support is implemented in code, but live execution still depends on a real service-account key. Placeholder `GOOGLE_PRIVATE_KEY` values make the Drive copy path safely self-disable and log why instead of failing the full pipeline run.
- The source scanners now ignore `_IRIS_` prefixed folders, the `Relevant image` review folder, and Google Drive shortcut items so review-output folders do not get re-ingested as source images on later runs.

---

## Cost Controls Live Today

The following cost controls are already implemented in code and should be treated as live architecture, not future ideas:

| Optimization | Code path |
| --- | --- |
| YOLO relevance gate | `src/iris/onfly_pipeline.py` |
| SHA-256 duplicate reuse | `src/iris/onfly_pipeline.py`, `src/iris/download_manager.py` |
| Store-hours skip | `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| Camera exclusion | `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| OpenAI GPT kill switch | `/scheduler` -> `OpenAI GPT calls`, backed by `cfg_onfly_scheduler_enable_gpt` in `store_registry.db` |
| OpenAI batch mode | `src/iris/gpt_batch.py`, `src/iris/onfly_pipeline.py` |
| Smart frame sampling | `src/iris/download_manager.py`, `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| Cost metrics materialization | `src/iris/report_writer.py`, `backend/app/api/report_queries.py`, `backend/app/api/routes_reports.py` |

Operational note:
- When `cfg_onfly_scheduler_enable_gpt=0`, manual syncs and hourly on-fly automation still run listing, YOLO, relevant-image Drive storage, and reports, but they do not call OpenAI and GPT-derived customer/staff/session fields remain unfilled until GPT is re-enabled and rerun.

### Smart Frame Sampling (newly live)
Consecutive frames with similar YOLO person-box signatures on the same date/camera are now skipped for GPT after the first anchor frame. Sampled frames inherit the resolved GPT/session result from the anchor frame later in the run.

Relevant fields written to SQLite:
- `sampled_anchor_image_id`
- `sampled_signature`
- `sampled_skip_reason`

Cost metric table contributions:
- `sampled_skips`
- `gpt_calls`
- `gpt_batch_images`
- `gpt_realtime_images`

---

## Cost Observability (Current)

`onfly_cost_metrics` now records per-store/day runtime proof points for management and engineering review:
- GPT calls per store/day
- images listed
- YOLO relevant images
- hash cache hits
- smart sampled skips
- duplicate skips
- outside-hours skips
- excluded-camera skips
- quota failures
- batch vs realtime GPT split
- estimated GPT spend (INR)

Runtime API:
- `GET /api/reports/cost-metrics`

## Admin Recovery Settings

- The canonical settings keys are now:
  - `emergency_admin_password`
  - `emergency_admin_password_hint`
- Older `streamlit_password` naming is legacy only and should not be reintroduced in new code or docs.

---

## Known Architectural Guardrails

- The 3 PM GPT-saving schedule must remain intact.
- The web process must stay request-serving only.
- Live operational progress comes from SQLite; long-term platform analytics may still synchronize into PostgreSQL.
- If GPT quota is unavailable, YOLO must continue and GPT work should queue for retry instead of repeatedly burning calls.
- Keep local and LAN access behavior stable on port `8767`; avoid changes that break either `http://localhost:8767` or `http://<LAN-IP>:8767/`.

---

## Documents That Matter

Keep aligned with code:
- `README.md`
- `docs/deployment/cost-optimization-plan.md`
- `docs/process/onfly_pipeline_logic.md`
- `deploy/cloud/README.md`
- `CHANGE_LEDGER.md`

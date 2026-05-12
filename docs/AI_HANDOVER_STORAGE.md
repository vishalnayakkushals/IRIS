# AI Handover — Runtime, Storage, and Cost State

**Last updated:** 2026-05-12

This is the short operational handover for the current IRIS architecture.

---

## Runtime Shape (Current Truth)

IRIS now runs as four explicit services:

1. `start_api_server.py`
2. `start_scheduler_worker_service.py`
3. `start_onfly_scheduler_service.py`
4. `start_store_auto_sync_service.py`

The FastAPI web process no longer owns scheduler loops. Runtime preparation is handled before launch through `backend/app/runtime_startup.py`.

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

---

## Cost Controls Live Today

The following cost controls are already implemented in code and should be treated as live architecture, not future ideas:

| Optimization | Code path |
| --- | --- |
| YOLO relevance gate | `src/iris/onfly_pipeline.py` |
| SHA-256 duplicate reuse | `src/iris/onfly_pipeline.py`, `src/iris/download_manager.py` |
| Store-hours skip | `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| Camera exclusion | `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| OpenAI batch mode | `src/iris/gpt_batch.py`, `src/iris/onfly_pipeline.py` |
| Smart frame sampling | `src/iris/download_manager.py`, `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| Cost metrics materialization | `src/iris/report_writer.py`, `backend/app/api/report_queries.py`, `backend/app/api/routes_reports.py` |

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

---

## Known Architectural Guardrails

- The 3 PM GPT-saving schedule must remain intact.
- The web process must stay request-serving only.
- Live operational progress comes from SQLite; long-term platform analytics may still synchronize into PostgreSQL.
- If GPT quota is unavailable, YOLO must continue and GPT work should queue for retry instead of repeatedly burning calls.

---

## Documents That Matter

Keep aligned with code:
- `README.md`
- `docs/deployment/cost-optimization-plan.md`
- `docs/process/onfly_pipeline_logic.md`
- `deploy/cloud/README.md`
- `CHANGE_LEDGER.md`

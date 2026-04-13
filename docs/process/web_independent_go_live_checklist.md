# IRIS Web-Only Go-Live Checklist (No Docker on User Machines)

## Goal
Move from local Docker-dependent development to a fully web-hosted, independent system where users run pipeline and review reports from browser only.

## Phase 1: Runtime Split
- [ ] Keep Streamlit/dashboard as web frontend service.
- [ ] Keep on-fly pipeline as backend worker service (separate process).
- [ ] Move scheduler to managed/background worker (no UI thread execution).
- [ ] Ensure `max_images=0` means full-folder processing in web run form.

## Phase 2: Managed Infrastructure
- [ ] Host web app on cloud VM/app service (single URL, HTTPS).
- [ ] Move SQLite to managed Postgres for concurrent web + worker safety.
- [ ] Move exports/artifacts to object storage (S3/GCS/Azure Blob), not local disk.
- [ ] Configure DNS + TLS certs.

## Phase 3: Identity and Access
- [ ] Add role-based access (Admin, Ops, Viewer).
- [ ] Restrict pipeline-run permissions to Admin/Ops.
- [ ] Add per-store data visibility controls if required.
- [ ] Audit log every pipeline trigger/change.

## Phase 4: Source Connectors
- [ ] Finalize Google Drive connector with service account + scoped folder access.
- [ ] Add AWS S3 connector with prefix-based source mapping.
- [ ] Add source health checks (folder reachable, file count, permission status).
- [ ] Show explicit UI guard: "No files visible from source (access/scope issue)".

## Phase 5: Pipeline Idempotency + Versioning
- [ ] Keep image-level processing state (`onfly_image_state`) as source of truth.
- [ ] Persist separate `yolo_version` and `gpt_version`.
- [ ] Re-run YOLO only when YOLO version changes.
- [ ] Re-run GPT only when GPT/session logic version changes.
- [ ] Keep force-reprocess override at store/date level.

## Phase 6: Observability
- [ ] Keep run-level table (`onfly_pipeline_runs`) with stage and counters.
- [ ] Keep event-level table (`onfly_pipeline_run_events`) with timeline.
- [ ] Add stage SLA metrics (LIST, SKIP_CHECK, DOWNLOAD, YOLO, GPT, REPORT_WRITER, DASHBOARD_INGEST).
- [ ] Add failure diagnostics (stage, image_id, reason, retry state).
- [ ] Publish time-consumption report per run.

## Phase 7: Business Reporting Readiness
- [ ] Primary KPIs from `onfly_walkin_sessions`:
  - Total Groups
  - Total Walk-ins
  - Avg Time Spent
  - Conversion Rate
- [ ] Keep image-centric metrics as secondary technical diagnostics.
- [ ] Region/state/store filters from store master.
- [ ] Day/month/year trend and period-vs-period delta.

## Phase 8: Data Quality and Controls
- [ ] Validate folder/date parsing and filename-time parsing quality.
- [ ] Validate session state transitions (OPEN, CLOSED, CLOSED_EOD, UNMATCHED_EXIT).
- [ ] Validate staff rules (red shirt + black pant, white shirt + black pant).
- [ ] Validate banner/pedestrian/customer separation samples weekly.
- [ ] Add "data freshness" and "last successful run" indicators.

## Phase 9: Security and Compliance
- [ ] Move secrets to secret manager (no plaintext on host).
- [ ] Rotate API keys and service credentials.
- [ ] Encrypt data at rest/in transit.
- [ ] Mask sensitive fields in logs/reports.
- [ ] Define retention policy for run artifacts.

## Phase 10: CI/CD and Release
- [ ] Build once, deploy automatically per environment (Dev/UAT/Prod).
- [ ] Add migrations pipeline for DB schema changes.
- [ ] Add smoke test suite:
  - source check
  - run trigger
  - report generation
  - dashboard read path
- [ ] Add rollback strategy and release health gate.

## Exit Criteria (Web-Only Ready)
- [ ] Users can trigger full-folder run from web UI (no terminal).
- [ ] Scheduler runs reliably and visible in UI.
- [ ] Reports are downloadable from UI and consistent with DB state.
- [ ] No local Docker requirement for business users.
- [ ] Production runbook documented and handed over.

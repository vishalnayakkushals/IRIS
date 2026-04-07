# On-Fly Independent App Readiness Checklist

Goal: run IRIS on-fly workflow from UI/API/scheduler without manual PowerShell dependency.

## 1) Runtime & Deployment
- [ ] Container services auto-start (`iris`, `iris-onfly-scheduler`, optional API worker).
- [ ] Health endpoints available (`/health` for API, Streamlit reachable).
- [ ] `.env.local`/secret source loaded automatically at process startup.
- [ ] No manual key paste required.

## 2) Source Input UX
- [ ] UI form supports:
  - [ ] full Drive URL
  - [ ] Drive folder id
  - [ ] local path
- [ ] Input normalization shown back to user.
- [ ] Validation errors are user-readable.

## 3) Pipeline Orchestration
- [ ] Manual run trigger in UI.
- [ ] Scheduler trigger (hourly + nightly).
- [ ] Retry/resume path on failed stage.
- [ ] Version-aware delta logic:
  - [ ] `yolo_version`
  - [ ] `gpt_version`
  - [ ] backward compatibility with legacy `pipeline_version`.

## 4) Processing Correctness
- [ ] List -> Skip -> Download -> YOLO -> GPT -> Report writer -> Dashboard ingest all traced.
- [ ] If YOLO unchanged and GPT changed:
  - [ ] only GPT re-runs for relevant images.
- [ ] If YOLO changed:
  - [ ] YOLO re-runs.
- [ ] Timestamp source-of-truth from filename for session times.

## 5) Observability
- [ ] `onfly_pipeline_runs` populated per run.
- [ ] `onfly_pipeline_run_events` populated per stage.
- [ ] UI timeline shows current stage + failure reason.
- [ ] Scheduler history visible.

## 6) Outputs & Reports
- [ ] Canonical outputs present:
  - [ ] `onfly_image_results.csv`
  - [ ] `onfly_walkin_sessions.csv`
  - [ ] `onfly_store_date_report.csv`
- [ ] Audit output present:
  - [ ] `onfly_walkin_sessions_audit.csv`
- [ ] Timing dataset present:
  - [ ] `onfly_process_timings.csv`
- [ ] Run summary JSON path visible in UI.

## 7) Data Governance
- [ ] Idempotent image state trail preserved.
- [ ] Re-run does not duplicate unchanged rows.
- [ ] Report overwrite/lock behavior is non-blocking and traceable.

## 8) Cutover to “Independent App”
- [ ] Single UI button flow works end-to-end.
- [ ] API endpoint exists for external trigger (optional next phase).
- [ ] Auth/roles cover run + report access.
- [ ] Alerting configured for failed scheduled runs.


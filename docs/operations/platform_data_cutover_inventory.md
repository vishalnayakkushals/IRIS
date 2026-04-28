# IRIS Platform Data Cutover Inventory

## Platform Direction

- Current live local app at the time of this inventory:
  - `http://localhost:8767` = active FastAPI + React app
  - `http://localhost:8765` = deprecated Streamlit fallback
- Recommended end-state:
  - Keep only `http://localhost:8767` as the product app.
  - Treat `http://localhost:8765` as legacy Streamlit and retire it after parity and migration.
- "Brain must not be touched" boundary:
  - Keep these logic engines intact and reuse them from the new platform:
    - `src/iris/iris_analysis.py`
    - `src/iris/onfly_pipeline.py`
    - `src/iris/entrance_pipeline.py`
  - Rebuild and replace only platform/state layers around them:
    - UI
    - API
    - auth
    - runtime state
    - report persistence
    - scheduler state

## Current Live SQLite Tables

The current production-style local runtime database is `data/store_registry.db`.

| Domain | Live Table | Defined In | Current Consumers | Postgres Target | Action |
|---|---|---|---|---|---|
| Store registry | `stores` | `src/iris/store_registry.py` | Streamlit admin, auth, scheduler, sync | `stores` | Migrate as-is |
| Store metadata | `store_master` | `src/iris/store_registry.py` | Store detail/admin views | `store_master` | Migrate as-is |
| Sync runtime | `store_sync_state` | `src/iris/store_registry.py` | Sync screens, scheduler | `store_sync_state` | Migrate as-is |
| Source index | `store_source_file_index` | `src/iris/store_registry.py` | Drive/local sync state | `store_source_file_index` | Migrate as-is |
| Employees | `employees` | `src/iris/store_registry.py` | Store/admin flows | `employees` | Migrate as-is |
| Camera config | `camera_configs` | `src/iris/store_registry.py` | Walk-in logic, config UI | `camera_configs` | Migrate as-is |
| Location config | `location_master` | `src/iris/store_registry.py` | Hotspot/location UI | `location_master` | Migrate as-is |
| Users | `users` | `src/iris/store_registry.py` | Streamlit auth, FastAPI auth, admin | `users` | Migrate as-is |
| Roles | `roles` | `src/iris/store_registry.py` | Auth/admin | `roles` | Migrate as-is |
| Permissions | `role_permissions` | `src/iris/store_registry.py` | Auth/admin | `role_permissions` | Migrate as-is |
| User-role map | `user_roles` | `src/iris/store_registry.py` | Auth/admin | `user_roles` | Migrate as-is |
| User-store map | `user_store_access` | `src/iris/store_registry.py` | Restricted store access | `user_store_access` | Migrate as-is |
| Sessions | `user_sessions` | `src/iris/store_registry.py` | Streamlit/local session flow | `user_sessions` | Migrate, then converge with JWT/session policy |
| Settings | `app_settings` | `src/iris/store_registry.py` | Scheduler config, feature toggles, runtime flags | `app_settings` | Migrate first; used everywhere |
| Licenses | `licenses` | `src/iris/store_registry.py` | License admin | `licenses` | Migrate as-is |
| License audit | `license_audit` | `src/iris/store_registry.py` | Audit/admin | `license_audit` | Migrate as-is |
| Alerts | `alert_routes` | `src/iris/store_registry.py` | Alert config | `alert_routes` | Migrate as-is |
| Alert events | `alert_events` | `src/iris/store_registry.py` | Alert history | `alert_events` | Migrate as-is |
| User activity | `user_activity` | `src/iris/store_registry.py` | Audit trail | `user_activity` | Migrate as-is |
| Models | `model_versions` | `src/iris/store_registry.py` | Model/version admin | `model_versions` | Migrate as-is |
| QA review | `qa_feedback` | `src/iris/store_registry.py` | Quality feedback UI | `qa_feedback` | Migrate as-is |
| QA false positives | `qa_false_positive_signatures` | `src/iris/store_registry.py` | QA filtering | `qa_false_positive_signatures` | Migrate as-is |
| Generic run log | `pipeline_run_log` | `src/iris/store_registry.py`, `backend/app/db/pipeline_log.py` | FastAPI jobs/runs, scheduler views | `pipeline_run_log` | Migrate first; active backend dependency |
| On-fly image state | `onfly_image_state` | `src/iris/onfly_pipeline.py` | On-fly pipeline | `onfly_image_state` | Migrate as-is |
| On-fly queue | `onfly_task_queue` | `src/iris/onfly_pipeline.py` | GPT retry / stage queue | `onfly_task_queue` | Migrate as-is |
| On-fly run metrics | `onfly_run_metrics` | `src/iris/onfly_pipeline.py` | Performance/runtime tracking | `onfly_run_metrics` | Migrate as-is |
| On-fly runs | `onfly_pipeline_runs` | `src/iris/store_registry.py`, `src/iris/onfly_pipeline.py` | Scheduler, pipeline journey | `onfly_pipeline_runs` | Migrate as-is |
| On-fly run events | `onfly_pipeline_run_events` | `src/iris/store_registry.py`, `src/iris/onfly_pipeline.py` | Pipeline journey, troubleshooting | `onfly_pipeline_run_events` | Migrate as-is |
| On-fly report index | `onfly_report_index` | `src/iris/store_registry.py`, `src/iris/onfly_pipeline.py` | Report lookup | `onfly_report_index` | Migrate now, then phase out CSV path dependence |
| On-fly walk-ins | `onfly_walkin_sessions` | `src/iris/onfly_pipeline.py` | Reports, APIs, Streamlit dashboards | `onfly_walkin_sessions` | Migrate first; active business fact table |

## Current Live CSV Artifacts

These files are still being used by active production-style paths. In the target architecture, they should become generated exports, not source-of-truth.

| Artifact | Current Path / Pattern | Used By | Canonical PG Replacement | Keep or Retire |
|---|---|---|---|---|
| Storewise scan results | `data/exports/current/onfly/<STORE_ID>/onfly_image_results.csv` | Streamlit report module, customer journey | `report_image_scan_results` | Retire as source-of-truth; keep as export |
| Walk-in sessions export | `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions.csv` | Streamlit reports, dashboard API, troubleshooting | `onfly_walkin_sessions` | Retire as source-of-truth; keep as export |
| Walk-in audit export | `data/exports/current/onfly/<STORE_ID>/onfly_walkin_sessions_audit.csv` | Audit/debug only | `onfly_walkin_sessions` + event tables | Keep optional debug export only |
| Store-date summary | `data/exports/current/onfly/onfly_store_date_report.csv` | Streamlit reports, detail API | `report_store_day_summary` | Retire as source-of-truth; keep as export |
| Legacy all-store summary | `data/exports/current/all_stores_summary.csv(.gz)` | Streamlit overview/report pages | `report_store_day_summary` | Retire as source-of-truth |
| Legacy customer sessions | `data/exports/current/store_<STORE_ID>_customer_sessions.csv` and datewise variants | Legacy Streamlit reports | `onfly_walkin_sessions` or future normalized session views | Retire as source-of-truth |
| Legacy location hotspots | `data/exports/current/store_<STORE_ID>_location_hotspots.csv` and datewise variants | Streamlit hotspot report | `report_location_hotspots` | Retire as source-of-truth |
| Legacy daily proof | `data/exports/current/store_<STORE_ID>_daily_proof.csv` and datewise variants | Streamlit proof report | `report_daily_proof` | Retire as source-of-truth |
| Stage-1 relevance output | `data/exports/current/stage1_relevance/stage1_relevance_all.csv(.gz)` | YOLO relevance workflows and report generation | Future optional PG table if stage-1 becomes first-class; not required for initial management cutover | Keep as temporary pipeline export |
| Vision eval / test outputs | `data/exports/current/vision_eval/*.csv` | Test/evaluation utilities | None in canonical prod schema | Non-production; retire from go-live critical path |

## Canonical Postgres Target Schema

The target schema is defined in:

- `backend/app/db/canonical_metadata.py`

This target schema keeps the brain untouched and moves platform ownership into Postgres.

### Canonical Tables to Migrate First

These unblock the React/FastAPI app and let us stop depending on local SQLite:

1. `users`
2. `roles`
3. `role_permissions`
4. `user_roles`
5. `user_store_access`
6. `stores`
7. `store_master`
8. `camera_configs`
9. `location_master`
10. `app_settings`
11. `pipeline_run_log`
12. `onfly_pipeline_runs`
13. `onfly_pipeline_run_events`
14. `onfly_walkin_sessions`
15. `onfly_report_index`

### Canonical Report Fact Tables

These remove CSV dependence from management dashboards and reports:

1. `report_store_day_summary`
2. `report_image_scan_results`
3. `report_location_hotspots`
4. `report_daily_proof`

### Tables That Stay Platform-State But Not Brain

These remain important, but can move after the first cutover:

1. `store_sync_state`
2. `store_source_file_index`
3. `employees`
4. `licenses`
5. `license_audit`
6. `alert_routes`
7. `alert_events`
8. `user_activity`
9. `model_versions`
10. `qa_feedback`
11. `qa_false_positive_signatures`
12. `onfly_image_state`
13. `onfly_task_queue`
14. `onfly_run_metrics`
15. `user_sessions`

## Single-Platform Recommendation

If the goal is one platform only:

- Build and test on `8767` only.
- Move all management-critical reads/writes to Postgres-backed FastAPI routes.
- Keep the brain modules under `src/iris/` as callable engines only.
- Once parity is proven:
  - stop daily use of `8765`
  - remove Streamlit-only platform code gradually
  - keep only export compatibility where the business still needs CSV downloads

## Next Implementation Step After This Inventory

The next phase should be:

1. backfill `stores`, `users`, `app_settings`, `pipeline_run_log`, `onfly_pipeline_runs`, `onfly_pipeline_run_events`, `onfly_walkin_sessions`, and `onfly_report_index` into Postgres
2. switch FastAPI auth/jobs/runs/detail/dashboard routes to Postgres
3. stop reading report CSVs directly from API routes

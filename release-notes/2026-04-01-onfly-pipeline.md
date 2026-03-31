# 2026-04-01 - On-Fly Pipeline + Scheduler

## Highlights
- Added a lightweight URL-first pipeline (`scripts/run_onfly_pipeline.py`) with:
  - YOLO relevance filtering
  - optional ChatGPT pass for relevant images only
  - idempotent skip of already processed images using SQLite state
- Added hourly + nightly scheduler wrapper (`scripts/onfly_scheduler.py`).
- Added benchmark utility (`scripts/benchmark_onfly_pipeline.py`) to measure before/after timing (3 runs each).
- Added compose profile/service `iris-onfly-scheduler` and launcher commands in `run_iris.bat`.
- Hid `Bulk Access Upload` from navigation (deprecated in lightweight mode).

## New Output Artifacts
- `data/exports/current/onfly/<store_id>/onfly_image_results.csv`
- `data/exports/current/onfly/onfly_store_date_report.csv`
- `data/exports/current/onfly/onfly_run_summary_<run_id>.json`
- `data/exports/current/onfly/benchmarks/*`

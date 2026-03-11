# Release Notes - 2026-03-11

## Feature Name
- Hotstar-like acceleration foundation: async queue worker, daily model learning loop, and customer conversion reporting

## What’s New
- Added event queue abstraction and async worker runner for near-real-time processing (`src/iris/event_queue.py`, `scripts/run_async_worker.py`).
- Added training dataset writer + daily retrain job (`scripts/build_training_dataset.py`, `scripts/daily_retrain.py`).
- Added model registry table and rollback helpers in DB (`model_versions` + promote/auto-rollback functions).
- Added daily walk-in/conversion report with unique individual and group customer metrics.
- Added page persistence in UI using query-parameter-backed page selection.

## Impact
- Improves processing scalability readiness for 100+ stores with async worker pattern.
- Improves model improvement workflow by adding repeatable daily retraining plumbing.
- Improves business reporting with daily actual customer and conversion visibility.

## Metrics / Monitoring
- KPI being tracked: actual daily customers, actual daily conversions, conversion rate.
- Expected improvement: faster analysis scheduling and higher model governance maturity.
- Dashboard / Tool used: Streamlit Store Detail and exported daily report CSV.
- Monitoring owner: IRIS Engineering + Analytics Ops.

## Availability
- Web
- Release version (if applicable): main @ 2026-03-11 fast-pipeline patch

## Risks / Known Issues
- Current customer identity remains heuristic track-based in MVP and is not true biometric identity.
- Daily retrain script currently calibrates lightweight metrics; full model retraining infra is next hardening step.

## Rollback Plan
- Revert commit and redeploy:
  - `git revert <commit_sha>`
  - `docker compose -f deploy/docker-compose.yml up --build -d`

## Validation
- `python -m py_compile src/iris/iris_analysis.py src/iris/iris_dashboard.py src/iris/store_registry.py src/iris/event_queue.py src/run_dashboard.py scripts/run_async_worker.py scripts/build_training_dataset.py scripts/daily_retrain.py`
- `PYTHONPATH=src pytest -q tests/test_store_registry.py::test_model_registry_and_auto_rollback tests/test_event_queue.py`

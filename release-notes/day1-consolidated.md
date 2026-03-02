# Day-1 Consolidated Release Note

## Feature Name
- IRIS MVP Foundation (Analytics, Dashboard, Registry, Governance)

## What’s New
- Added snapshot analysis engine with person detection abstraction (YOLO/mock), visit estimation, hotspots, footfall logic, and baseline loss-of-sale alerts.
- Added operator-facing Streamlit dashboard with Overview, Store Detail, Quality, and Store Admin flows.
- Added SQLite-backed store registry with store mapping, camera calibration persistence, employee image handling, and Drive sync support.
- Added API/schema contracts and governance docs (planning, process, org architecture, cloud deployment, and checklist tracking).
- Added automated tests and CI workflow for lint/test quality gates.

## Impact
- Improves decision speed for store operations using structured footfall/dwell/hotspot insights.
- Reduces manual analysis effort through repeatable CLI + dashboard workflows.
- Establishes delivery governance and release hygiene for future feature scale-up.

## Metrics / Monitoring
- KPI being tracked: estimated visits, avg dwell seconds, bounce rate, footfall, loss-of-sale alerts.
- Expected improvement: faster operational review cycle and higher analysis consistency.
- Dashboard / Tool used: Streamlit dashboard + CSV exports + GitHub Actions CI.
- Monitoring owner: Engineering + QA (transition to Ops owner during production rollout).

## Availability
- Web (Streamlit dashboard) + CLI analysis interface.
- Release version (if applicable): Day-1 MVP baseline.

## Risks / Known Issues
- Some advanced features remain pipeline items (license workflow runtime, alert routing integrations, multi-cam stitching).
- Detection quality depends on snapshot quality and model/runtime availability.

## Rollback Plan
- Revert to previous stable commit on `main`.
- Restore prior release-note baseline and disable new workflow changes if needed.

## Validation
- Local unit tests passed.
- CI workflow configured for lint + tests on push/PR.

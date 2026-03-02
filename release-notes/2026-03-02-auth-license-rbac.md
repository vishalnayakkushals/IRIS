# Release Notes - 2026-03-02

## Feature Name
- Runtime auth/RBAC, license workflow, alert routing, QA timeline, and store-master operations

## What’s New
- Added DB-backed users/password authentication and role-based permission model (admin/store_user/management_viewer + custom roles).
- Added trade/display license runtime with state transitions and audit timeline.
- Added alert routing registry for email/webhook/slack/whatsapp channels and delivery event logs.
- Added Store Master bulk-import (TSV paste in UI) with DB persistence and optional store auto-upsert.
- Added operator QA timeline tab and multi-camera visit stitching field (`global_visit_id`) for cross-camera grouping support.

## Impact
- Enables production-style user access control and workflow governance directly from UI.
- Adds auditable compliance workflow for license handling.
- Prepares platform for 100+ stores and N-camera ingestion with configurable camera roles.

## Metrics / Monitoring
- KPI being tracked: authenticated users, role coverage, license transition count, routed alerts, stitched visit IDs.
- Expected improvement: reduced manual operations effort and clearer auditability.
- Dashboard / Tool used: Streamlit admin tabs + SQLite logs + exports.
- Monitoring owner: engineering/admin.

## Availability
- Web / App / Both: Web (Streamlit) + DB runtime.
- Release version (if applicable): main.

## Risks / Known Issues
- Alert routing currently logs deliveries; external dispatch adapters can be expanded provider-by-provider.

## Rollback Plan
- Revert this commit to restore previous schema/UI behavior.

## Validation
- `PYTHONPATH=src pytest -q` passed.
- `python -m py_compile src/iris/iris_dashboard.py src/iris/store_registry.py src/iris/iris_analysis.py scripts/analyze_stores.py` passed.

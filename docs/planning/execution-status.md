# IRIS Execution Status (Live Tracker)

Last updated: 2026-03-02

This file translates the original checklist into a clear **Done / In Pipeline** tracker.

## 1) Delivery status snapshot

### ✅ Done in repository

- Store onboarding + mapping + drive links + email mapping.
- Camera configuration persistence (`camera_id`, role, entry line x, entry direction).
- Person detection pipeline (YOLO + mock fallback).
- Single-camera anonymous track IDs.
- Footfall based on entrance line crossing logic.
- Dwell and bounce proxy metrics from snapshot sessions.
- Hotspot analytics and camera ranking exports.
- Baseline loss-of-sale suspicion alerts with risk score + reason codes.
- Export pipeline for summary, per-image insights, hotspots, and alerts (CSV + gzip support).
- Dashboard tabs for Overview, Store Detail, Quality, and Store Admin.
- SQLite registry for stores, camera config, employee assets, and sync metadata.
- Automated tests for analysis + registry modules.

### 🟡 In pipeline (next development waves)

- Trade/display license workflow runtime (API endpoints, state machine UI, audit timeline).
- Alert routing integrations (email/webhook/Slack/WhatsApp).
- Operator QA timeline view with keyframe review.
- Multi-camera handoff and cross-camera visit stitching.
- POS integration for conversion/loss-of-sale validation.
- Production-grade auth/RBAC and per-role dashboards.

---

## 2) Checklist closure report

Legend:
- ✅ Completed
- 🟡 Planned / in pipeline

### Phase 1

- ✅ Store & camera onboarding + calibration persistence.
- ✅ Person detection on snapshots.
- ✅ Single-camera tracking IDs (anonymous).
- ✅ Footfall from entrance crossing events.
- ✅ Dwell and bounce proxy metrics.
- ✅ Hotspots.
- ✅ Baseline loss-of-sale alert generation.
- 🟡 Trade/display license workflow + full audit trail (partially documented, runtime pending).

### Phase 2

- 🟡 Visit stitching improvements + confidence scoring.
- 🟡 Alert routing integrations.
- 🟡 Engagement conversion proxy with business validation.
- 🟡 Operator QA timeline.

### Phase 3

- 🟡 Multi-cam handoff at scale.
- 🟡 Compliance-gated appearance linking.
- 🟡 POS integration.

---

## 3) Next 3 sprint plan

### Sprint A (License + audit)

- Build license domain model and DB tables.
- Add CRUD and status transitions (draft/review/approved/rejected/expired).
- Add audit event log per state change.
- Expose dashboard panel for license lifecycle.

### Sprint B (Alerts to action)

- Add notification connectors (email + webhook first).
- Add alert acknowledgement and owner assignment.
- Add SLA clocks and escalation levels.

### Sprint C (Ops hardening)

- Add managed Postgres + migration path from SQLite.
- Add RBAC + secure secrets handling.
- Add staging/prod deployment automation and uptime checks.

# IRIS Execution Status (Live Tracker)

Last updated: 2026-03-11

This file translates the original checklist into a clear **Done / In Pipeline** tracker.

## Hotstar-fast Buildout Checklist

Legend:
- ✅ Implemented baseline in repo
- 🟡 Partial / hardening in progress
- ⏳ Not started

1. Ingestion layer (near-real-time queue backbone): 🟡
   - ✅ Queue abstraction exists: `src/iris/event_queue.py` (`InMemoryEventQueue`, `JsonlEventQueue`)
   - ✅ Async consumer exists: `scripts/run_async_worker.py`
   - ✅ Event producer added for practical rollout: `scripts/enqueue_store_frames.py`
   - 🟡 Next hardening: Kafka/PubSub adapter + backlog lag metrics
2. Async workers autoscaled by queue lag: 🟡
   - ✅ Worker process is operational for local queue
   - 🟡 Next hardening: multi-worker orchestration + autoscale policy
3. Feature + label store: 🟡
   - ✅ Dataset writer exists: `scripts/build_training_dataset.py`
   - 🟡 Next hardening: partitioned feature store schema + label QA checks
4. Daily training pipeline: 🟡
   - ✅ Daily retrain script exists: `scripts/daily_retrain.py`
   - 🟡 Next hardening: scheduler integration (Airflow/Prefect) + validation gate + canary promotion
5. Model registry + rollback: ✅
   - ✅ Version table and promotion/rollback helpers in `src/iris/store_registry.py`
6. Serving split (online vs offline): 🟡
   - ✅ Offline analytics/export path exists
   - 🟡 Next hardening: dedicated online inference service endpoint
7. Observability (latency, drop-rate, sync-failure, drift): ⏳
   - ⏳ Dashboard/metrics service not yet implemented

## 1) Delivery status snapshot

### ✅ Done in repository

- Auth/RBAC runtime with DB-backed users, passwords, default admin seeding, and custom roles.
- License workflow runtime with status transitions and audit timeline logging.
- Alert route configuration and route event logging for email/webhook/slack/whatsapp channels.
- Store Master bulk import with DB persistence and admin UI.
- Operator QA timeline view and multi-camera visit stitching field (`global_visit_id`).
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

- POS integration for conversion/loss-of-sale validation.
- Slack/WhatsApp live provider adapters for external alert dispatch.

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

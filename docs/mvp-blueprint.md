# IRIS MVP Blueprint

## 1) Scope and assumptions

- **Scale**: 6 stores × 2 cameras/store = 12 cameras.
- **Cameras**:
  - `ENTRANCE`: door area + directional crossing.
  - `INSIDE`: meaningful floor coverage + doorway interior if possible.
- **Ingest**: 1 snapshot per second per camera.
- **Privacy**: anonymous analytics only; no face recognition, no identity features persisted.
- **Retention**: metadata retained; keyframes retained only for alerts/QA with short TTL; raw video disabled by default.

## 2) Open questions (max-impact)

1. Does entrance framing reliably support both in/out direction classification?
2. Does inside camera include 2–3m interior doorway coverage for handoff?
3. Alert channel priorities for MVP: in-app only, email, SMS, WhatsApp, webhook?
4. Compliance retention constraints for keyframes (7/14/30 days)?
5. Should POS integration be planned in schema now for future conversion validation?

## 3) Product decisions (defaulted)

- **Dwell definition**: `STORE_DWELL` (entry→exit), plus optional observed dwell field.
- **Loss-of-sale strategy**: `HIGH_PRECISION` in MVP (fewer, higher-confidence alerts).

## 4) Phased roadmap

### Phase 1 (Week 1–2): MVP core

- Store/camera onboarding + calibration (zones/lines/doorway).
- Snapshot ingestion pipeline.
- Person + bag detection on snapshots.
- Per-camera tracking IDs (anonymous).
- Footfall, dwell, bounce, hotspots.
- Probabilistic loss-of-sale alerting.
- License workflow: upload → submit → approve/reject → expiry + audit logs.

### Phase 2 (3–6 weeks)

- Stronger visit stitching and QA tooling.
- Alert routing integrations (webhook, Slack, WhatsApp).
- Engagement conversion proxies (billing-zone/hotspot dwell).

### Phase 3 (later)

- Advanced multi-camera linking at scale.
- Optional appearance-based linking under explicit compliance controls.
- POS validation loop for conversion and loss-of-sale.

## 5) Canonical metric definitions

### 5.1 Footfall

- Count unique `ENTRY_DETECTED` events at entrance crossing.
- De-dup using `reentry_cooldown_sec` (default: 60s).
- Output hourly/daily with confidence.

### 5.2 Dwell

- `observed_dwell_sec = last_seen_inside_ts - first_seen_inside_ts`
- `store_dwell_sec = exit_ts - entry_ts` (recommended default)
- Confidence tiers:
  - `HIGH`: clear entry + clear exit + doorway corroboration.
  - `MED`: clear entry + clear exit, weak corroboration.
  - `LOW`: inferred endpoint(s) or weak stitching.

### 5.3 Bounce

- `bounce_flag = store_dwell_sec < bounce_threshold_sec`
- Default `bounce_threshold_sec = 120`.

### 5.4 Hotspots

- For each inside frame, add +1 occupancy-second per person per grid cell/zone.
- Outputs: heatmap + top N zones by occupancy seconds.

### 5.5 Loss-of-sale (probabilistic)

Trigger candidate when:

- `store_dwell_sec >= engaged_dwell_threshold_sec` (default: 180),
- exit is detected,
- no bag evidence in `bag_check_window_sec` (default: 10),
- optional hotspot engagement threshold met.

Finalize alert only when:

- `los_risk_score >= los_alert_threshold` (default: 0.75)

Always include reason codes, e.g.:

- `NO_BAG_EVIDENCE`
- `LONG_DWELL`
- `HOTSPOT_VISIT`

## 6) Feasibility at 1 FPS

- **High confidence**: footfall, hotspots, trend analytics.
- **Medium confidence**: dwell, bounce, co-entry groups (with confidence scoring).
- **Low confidence for MVP**: demographics, fine product interactions.

## 7) Architecture options

### Cloud-first MVP

Fastest to ship; ingest snapshots in cloud, infer, track, stitch, aggregate, persist metadata, retain keyframes only for alerts.

### Edge-first MVP

Best long-term privacy/bandwidth posture; run inference + tracking + stitching on edge, upload metadata + alert keyframes only.

## 8) Multi-camera linking strategy (anonymous)

### Level 1 stitching (MVP)

- Use doorway zone constraints and temporal windows (`Δ = 5–10s`).
- Link entrance entry/exit events to inside tracks appearing near doorway in expected windows.
- Persist `stitch_confidence` for all visits.

### Tracking model notes

- Use tracking-by-detection with motion + IoU at 1 FPS.
- Optional appearance embeddings are allowed only in-memory and ephemeral.

## 9) Event taxonomy (MVP)

### Ingest/ML

- `FRAME_INGESTED`
- `DETECTIONS_CREATED`

### Tracking

- `TRACK_STARTED`
- `TRACK_UPDATED`
- `TRACK_ENDED`

### Entrance lifecycle

- `ENTRY_DETECTED`
- `EXIT_DETECTED`

### Store visit lifecycle

- `VISIT_STARTED`
- `VISIT_STITCHED`
- `VISIT_ENDED`
- `BOUNCE_DETECTED`

### Hotspots

- `HEATMAP_UPDATED`

### Loss-of-sale

- `BAG_EVIDENCE_DETECTED`
- `LOSS_OF_SALE_SUSPECTED`

### License workflow

- `LICENSE_UPLOADED`
- `LICENSE_SUBMITTED`
- `LICENSE_APPROVED`
- `LICENSE_REJECTED`
- `LICENSE_EXPIRING_SOON`
- `LICENSE_EXPIRED`

## 10) Data model entities

- `Store`, `Camera`, `CameraCalibration`, `Zone`
- `Frame`, `Detection`, `Track`, `TrackPoint`
- `Visit`, `VisitLink`, `Group`, `GroupMember`
- `HeatmapCellAgg`, `ZoneAgg`
- `Alert`
- `License`, `LicenseDecision`, `AuditLog`

## 11) License workflow rules

State machine:

- `UPLOADED -> PENDING_APPROVAL -> APPROVED -> EXPIRED`
- `PENDING_APPROVAL -> REJECTED`
- Expired/rejected requires **new license record** upload; no overwrite.

UI constraints:

- Approved and valid: show countdown, hide upload CTA.
- Pending: show pending state and preview.
- Rejected/expired: enable “Upload New License”.

## 12) Week-1 execution plan

### Day 1

- Finalize metric config schema.
- Build store/camera/calibration APIs + basic admin UI.
- Add snapshot ingest mock path.

### Day 2

- Implement detection service and persistence.
- Add throughput + latency telemetry.

### Day 3

- Implement per-camera tracking and entry/exit.
- Ship footfall aggregator and dashboard view.

### Day 4

- Implement visit lifecycle and doorway stitching.
- Ship dwell/bounce APIs with confidence tiers.

### Day 5

- Implement heatmap + top-zone aggregators.
- Ship hotspot dashboard.

### Day 6

- Implement bag evidence + loss-of-sale risk scoring.
- Ship alert list + acknowledge/close.

### Day 7

- Complete license lifecycle and expiry jobs.
- Validate audit logging and UI behavior.

## 13) Acceptance criteria (pilot)

- Footfall variance vs manual count ≤ ±10–15% in pilot constraints.
- Dashboard latency < 5 minutes; alert latency < 2 minutes.
- Alert usefulness > 70% perceived precision in pilot review.
- Retention policies enforced: metadata retained, keyframes TTL applied, no raw video retention.

## 14) Permanent project operating rules

The following apply to all IRIS initiatives and releases:

- Daily release cadence with explicit release notes for each date.
- Mandatory idea board with both feature ideas and problem statements.
- Full-stack delivery accountability across product, marketing, design, engineering, QA, and business functions.
- Three-layer execution structure: process/innovation engineering, functional specialists, output/QC controllers.
- System usage rules: UI consistency, tooling consistency, database-connection discipline, and local-first promotion to shared environments.

Reference implementation artifacts:

- `docs/process/system-foundations.md`
- `release-notes/_template.md`
- `ideas/board.md`

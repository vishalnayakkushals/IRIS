# MVP Actionable Review Checklist (GitHub Review Source)

This checklist is the operational truth for scope progress.

Legend:
- ✅ Done in current codebase
- 🟡 In pipeline / scheduled

## Phase 1 (MVP Core)

### Must-have

- ✅ Store & camera onboarding + calibration persistence.
- ✅ Person detection on snapshots.
- ✅ Single-camera tracking IDs (anonymous).
- ✅ Footfall using entrance-line crossing logic.
- ✅ Dwell time and bounce proxy metrics.
- ✅ Hotspots (camera-level).
- ✅ Basic loss-of-sale alerts with risk score + reason codes.
- 🟡 Trade/display license workflow runtime + audit logs.

### Nice-to-have

- 🟡 Co-entry group detection.
- 🟡 Advanced alert tuning UI.

## Phase 2 (3–6 weeks)

- 🟡 Visit stitching improvements + confidence tiers.
- 🟡 Alert routing integrations (email/webhook/chat).
- 🟡 Engagement conversion proxy with validation loop.
- 🟡 Operator QA timeline with keyframes.

## Phase 3 (later)

- 🟡 Multi-cam handoff at scale.
- 🟡 Appearance-based linking (compliance-gated).
- 🟡 POS integration for validated conversion/loss analysis.

## Linked tracker

For sprint-level Done vs Pipeline view, use:
- `docs/planning/execution-status.md`


## Explicit pending integration note

- 🟡 POS live integration adapters are pending.
- 🟡 Full external dispatch providers (real Slack/WhatsApp APIs) are pending; current implementation is registry/log-first.

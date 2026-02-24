# IRIS

IRIS is an **anonymous retail intelligence platform** built for low-frame-rate camera snapshots (1 FPS) with strong privacy defaults.

## MVP at a glance

- Scale target: 6 stores, 2 cameras per store (12 total).
- Camera roles: `ENTRANCE` + `INSIDE`.
- Ingest: timestamped snapshots (`1 image/sec/camera`), not continuous video.
- Privacy: no face recognition, no identity persistence, ephemeral appearance embeddings only.
- Required analytics: footfall, dwell, bounce, hotspots, and basic loss-of-sale alerts.
- Retention default: metadata long-term, alert keyframes short-term, no raw video retention.

## What is implemented in this repository

This repo now contains a concrete build package for the MVP:

1. Product + technical blueprint with definitions, phase plan, and execution plan.
2. Event taxonomy and data model for analytics and auditability.
3. REST API contract (OpenAPI 3.1) for onboarding, analytics, alerts, ingest, and license workflow.
4. Machine-readable schemas for core configuration and event payload validation.

See:

- `docs/mvp-blueprint.md`
- `api/openapi.yaml`
- `schemas/store-config.schema.json`
- `schemas/event-envelope.schema.json`

## Defaults requiring confirmation

If not explicitly overridden per store, IRIS uses:

- Dwell definition: `STORE_DWELL` (entry→exit) with confidence tiers.
- Alert strategy: `HIGH_PRECISION` for loss-of-sale in MVP.
- Alert channels: in-app + email.
- Keyframe retention: 14 days.
- POS integration: planned later (schema-ready now).


## Operating model artifacts

Permanent system foundations and execution assets:

- `docs/process/system-foundations.md`
- `release-notes/README.md` and `release-notes/_template.md`
- `ideas/README.md` and `ideas/board.md`
- `docs/planning/project-delivery-plan.md`

## Next engineering action

Start with the Day 1 vertical slice from the blueprint: onboarding + calibration + ingest mock path.

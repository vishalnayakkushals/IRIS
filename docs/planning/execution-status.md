# IRIS Execution Status

**Last updated:** 2026-05-12

## Overall Status

IRIS is in a **hardening + consolidation** phase.

### Completed recently
- React/FastAPI UI is the active app surface.
- On-fly pipeline was split into smaller backend modules.
- Reports and scheduler backend routes were split into helper modules.
- Web/runtime story now uses dedicated worker entry points.
- Smart frame sampling is implemented and writing measurable cost metrics.
- Report export/download paths remain stable.

### In progress
- Final cleanup of stale docs and legacy references.
- Full live verification after rebuild/deploy.

### Deferred intentionally
- Any change that would disturb the 3 PM GPT-cost-saving schedule.
- Any broad business-metric redesign unrelated to runtime hardening.

## Current Priorities

1. Keep runtime predictable and smooth.
2. Keep docs synchronized with actual code.
3. Keep cost instrumentation visible and audit-friendly.
4. Avoid re-expanding mega-files.

## Next Engineering Phase (after this hardening batch)

- expose cost metrics in the dashboard/admin UI
- centralize frontend polling hooks further
- finish any remaining legacy cleanup in admin/auth wording
- add deeper alerting around stuck run heartbeat anomalies

# IRIS BRD (Current Baseline)

## 1) Business Problem
Retail teams need reliable store-level insights (footfall, dwell, hotspots, loss-of-sale indicators) from privacy-safe snapshot cameras. Current manual review is slow and inconsistent.

## 2) Business Objectives
- Standardize store analytics output across all configured stores.
- Reduce manual operations review time with dashboard + exports.
- Establish a governed release process with clear status tracking.

## 3) Success Metrics
- Analysis run completion rate.
- Time to produce store summary.
- Weekly usage of dashboard and exports.
- Trend tracking for footfall, bounce, and loss-of-sale alerts.

## 4) Scope
### In Scope
- Snapshot analysis pipeline.
- Store/camera configuration and sync utilities.
- Dashboard and CLI operations.
- Release/PRD governance artifacts.

### Out of Scope
- Face recognition and personal identity linking.
- POS-verified conversion model (future phase).

## 5) Key Business Requirements
- Anonymous analytics only.
- Clear done vs pipeline status each sprint.
- Release notes per agreed template.
- Operational usability for store-level review.

- Lightweight on-the-fly pipeline path: URL ingestion -> YOLO relevance -> optional GPT analysis (relevant-only) with idempotent state and scheduler separation.

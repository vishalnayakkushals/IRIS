# IRIS Platform — Cost Optimization Plan
**Prepared by:** Engineering Team  
**For:** Management Review  
**Date:** May 2026  
**Version:** 4.0

---

## The One-Sentence Summary

> IRIS costs ~₹9,000/month today (1 store pilot). At 150 stores without optimization it would cost ₹80–90 lakh/month. With the optimizations already implemented, the operating range is now **~₹8–12 lakh/month**, with one more next-wave optimization plan available beyond that.

---

## Part 1 — What Costs Money (Simple Breakdown)

| Layer | Cost driver | Why it matters |
| --- | --- | --- |
| GPT layer | OpenAI image analysis | highest variable cost |
| Detection layer | YOLO inference + downloads | compute + runtime duration |
| Infrastructure layer | servers, DB, networking | mostly fixed monthly cost |

The rule remains simple: **the more intelligently we stop frames before GPT, the lower the operating cost.**

---

## Part 2 — What We Have Already Fixed (Done ✅)

All items below are already developed and reflected in the current codebase.

| # | Optimization | How it saves money | Evidence / code path |
| --- | --- | --- | --- |
| 1 | YOLO relevance gate | only relevant frames go to GPT | `src/iris/onfly_pipeline.py` |
| 2 | SHA-256 duplicate reuse | exact duplicate frames reuse GPT result for free | `src/iris/download_manager.py`, `src/iris/onfly_pipeline.py` |
| 3 | Already-processed/version skip | prevents full rerun charges on retries/restarts | `src/iris/onfly_pipeline.py`, `src/iris/pipeline_events.py` |
| 4 | GPT-4.1-mini instead of GPT-4o | lower price per semantic call | runtime config + prompt path |
| 5 | CPU-only ONNX Runtime | removes mandatory GPU instances | `src/iris/iris_analysis.py` |
| 6 | Circuit breaker + quota-aware retry | avoids retry storms during GPT outages/quota issues | `src/iris/gpt_runtime.py`, `src/iris/onfly_pipeline.py` |
| 7 | Memory cleanup after GPT | prevents OOM → rerun waste | `src/iris/onfly_pipeline.py` |
| 8 | Parallel downloads | reduces runtime and worker occupancy | `src/iris/onfly_pipeline.py`, `src/iris/download_manager.py` |
| 9 | Role/date normalization | avoids bad data and reprocessing work | `src/iris/session_reconstruction.py` |
| 10 | SQLite → PostgreSQL sync path | avoids manual recovery work | `src/iris/session_reconstruction.py` |
| 11 | Store-hours filter | excludes outside-hours frames before expensive stages | `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |
| 12 | Camera exclusion | excludes non-business cameras | `src/iris/session_reconstruction.py`, `src/iris/onfly_pipeline.py` |
| 13 | OpenAI Batch API | 50% price reduction for overnight GPT work | `src/iris/gpt_batch.py`, `src/iris/onfly_pipeline.py` |
| 14 | **Frame Sampling (Smart Skip)** | skips repetitive consecutive frames after the anchor frame is analyzed | `src/iris/download_manager.py`, `src/iris/onfly_pipeline.py`, `src/iris/session_reconstruction.py` |

### Frame Sampling (Smart Skip) — now live

**What changed:**
- consecutive frames on the same camera/date with similar YOLO box signatures now reuse the first “anchor” frame
- only the anchor goes to GPT
- later sampled frames are marked and resolved from the anchor result

**Expected saving:**
- **20–30% of the remaining GPT cost** after the earlier filters
- At 150 stores, this is expected to remove another **₹5–12 lakh/month** from the pre-optimization GPT envelope, depending on store density and repeat-frame frequency

---

## Part 3 — Current Cost (Pilot)

| Item | Monthly Cost | Notes |
| --- | --- | --- |
| Server | ₹0 | local/dev mode |
| OpenAI GPT | ~₹1,500–3,000 | pilot-scale activity |
| Google Drive API | ₹0 | within quota |
| PostgreSQL | ₹0 | local/dev mode |
| **Total** | **~₹1,500–3,000/month** | pilot scale |

---

## Part 4 — Projected Cost at Scale (150 Stores)

| Cost Item | Without optimization | With implemented optimizations | Estimated reduction |
| --- | --- | --- | --- |
| GPT API | ₹54–1,05,000/day | ₹7,000–14,000/day | ~87% lower |
| Infrastructure | ₹63,000/month | ₹45,075/month | 28% lower |
| **Total monthly** | **₹82–1,20 lakh/month** | **₹8–12 lakh/month** | **~87% lower variable cost** |

---

## Part 5 — What Still Needs Instrumentation / Proof

The engineering work is largely live. The remaining maturity gap is **visibility**, not missing optimization code.

The app now writes the following per-store/day proof points into `onfly_cost_metrics`:
- GPT calls/store/day
- images listed
- YOLO relevant images
- hash cache hits
- smart sampled skips
- duplicate skips
- outside-hours skips
- excluded-camera skips
- quota failures / paused retries
- batch vs realtime image split
- estimated GPT spend (INR)

Runtime API:
- `GET /api/reports/cost-metrics`

This is the bridge from “good engineering idea” to “management-trustworthy measurement.”

---

## Part 6 — Implementation Status Timeline

```text
COMPLETED ✅
─────────────────────────────────────────────
YOLO relevance gate
GPT-4.1-mini switch
CPU-only ONNX Runtime
Parallel downloads
Already-processed skip
SHA-256 duplicate reuse
Circuit breaker + quota queueing
Store-hours filter
Camera exclusion
OpenAI Batch API
Frame Sampling (Smart Skip)
Cost-metric writes

NEXT WAVE (planning)
─────────────────────────────────────────────
store/day anomaly alerts
adaptive sampling by camera density
business-priority GPT routing
regional cost dashboard
```

---

## Part 7 — ROI Summary

| Item | Value |
| --- | --- |
| Conservative monthly IRIS run cost (150 stores) | ~₹3–5.5 lakh |
| Manual counting replacement + staffing gains | ~₹50 lakh/month or more |
| Conservative monthly ROI | ~9× |

---

## Part 8 — Measured Facts vs Assumptions

### Measured facts (from system behavior / current implementation)
- GPT calls are reduced before inference by multiple live filters.
- Batch mode halves the price for images processed through the OpenAI batch path.
- Smart sampling is now implemented in the pipeline and writes `sampled_skips` metrics.
- Cost metrics are persisted into SQLite in `onfly_cost_metrics`.

### Projected assumptions (management planning numbers)
- 150-store scale ranges
- ₹5–12 lakh/month incremental saving attributed to smart sampling
- total monthly range of ₹8–12 lakh at scale

These assumptions should continue to be validated against live `cost-metrics` exports as more real stores go online.

---

## Part 9 — Engineering Appendix

### Exact code paths per optimization

| Optimization | Primary code path |
| --- | --- |
| Relevance gate | `src/iris/onfly_pipeline.py` |
| Duplicate reuse | `src/iris/download_manager.py`, `src/iris/onfly_pipeline.py` |
| Smart sampling | `src/iris/download_manager.py`, `src/iris/session_reconstruction.py`, `src/iris/onfly_pipeline.py` |
| Cost metrics | `src/iris/report_writer.py`, `backend/app/api/report_queries.py`, `backend/app/api/routes_reports.py` |
| Batch mode | `src/iris/gpt_batch.py`, `src/iris/onfly_pipeline.py` |
| Store-hours skip | `src/iris/session_reconstruction.py`, `src/iris/onfly_pipeline.py` |
| Camera exclusion | `src/iris/session_reconstruction.py`, `src/iris/onfly_pipeline.py` |

### Measurement basis
- Source of proof: `onfly_cost_metrics`
- Granularity: per store, per day, per run
- Sample stores used in the current code path: pilot / RR Nagar / test-store flows where available

---

## Part 10 — Next Cost Optimization Plan (Proposal)

These are the next opportunities **after** the currently shipped savings.

| Priority | Opportunity | Why it matters | Complexity |
| --- | --- | --- | --- |
| P0 | Adaptive sampling by camera density | aggressive sampling on slow-changing static cameras, conservative sampling on billing/entry cameras | Medium |
| P0 | Store-priority routing | force realtime only for billing/entry cameras and queue the rest to batch by policy | Medium |
| P1 | Prompt compaction / schema slimming | reduce tokens per GPT call while keeping required fields stable | Medium |
| P1 | Cross-run visual fingerprint reuse | reuse GPT output for “same attire + same camera + short interval” even when SHA hash differs | High |
| P1 | Regional cost anomaly dashboard | catch runaway stores/cameras before the month-end bill | Low |
| P2 | Hybrid lightweight classifier before GPT | add a cheap internal non-GPT semantic gate for banner/pedestrian/staff-heavy frames | High |

### Recommended next move
Start with:
1. adaptive sampling by camera density
2. store-priority realtime-vs-batch routing
3. cost dashboard on top of `GET /api/reports/cost-metrics`

These give the best next ROI without destabilizing the main app.

---

## Part 11 — Document Notes

- This file is a source-of-truth cost document.
- Update it whenever a cost-saving optimization becomes live.
- Do not move implemented work back into “planned” sections.

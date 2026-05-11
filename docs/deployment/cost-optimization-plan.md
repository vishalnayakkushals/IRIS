# IRIS Platform — Cost Optimization Plan
**Prepared by:** Engineering Team  
**For:** Management Review  
**Date:** May 2026  
**Version:** 2.0 (Updated with completed optimizations)

---

## The One-Sentence Summary

> IRIS costs ~₹9,000/month today (1 store pilot). At 150 stores without optimization it would cost ₹80–90 lakh/month. With the optimizations in this plan, we bring that down to ₹25–30 lakh/month — a **65% reduction** — before we even deploy at scale.

---

## Part 1 — What Costs Money (Simple Breakdown)

Think of IRIS like a 3-layer sandwich. Each layer has a cost.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — GPT API (OpenAI)                                 │
│  The most expensive part. Reads each relevant image and      │
│  says "this is a customer / staff / passerby".               │
│  Cost: ~₹0.50 per 1,000 images analysed.                    │
│  At 150 stores → 54,000 images/day → BIG number.            │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2 — AI Scanner (YOLO, runs on server)                │
│  Scans every image first. Only ~30% have a person.           │
│  Images without people NEVER reach GPT.                      │
│  Cost: Server electricity / EC2 compute.                     │
├─────────────────────────────────────────────────────────────┤
│  LAYER 1 — Infrastructure (Server + Database + Storage)      │
│  Always-on servers, database, load balancer.                 │
│  Fixed monthly cost. Doesn't grow with image volume.         │
└─────────────────────────────────────────────────────────────┘
```

**The rule is simple: Reduce what reaches Layer 3, and Layer 3 cost falls.**

---

## Part 2 — What We Have Already Fixed (Done ✅)

These are live in production today. No future work needed.

| # | What We Fixed | How It Saves Money | Saving |
|---|---|---|---|
| 1 | **YOLO filter gates GPT** | Only images with a person detected go to GPT. 70% of images are skipped entirely. Without this, every image would cost GPT money. | **70% fewer GPT calls** |
| 2 | **Duplicate image skip** | Each image has a fingerprint (SHA256 hash). If the same image appears again (Drive re-sync, camera repeat), GPT is not called again. Result reused for free. | **Eliminates repeat costs** |
| 3 | **Already-processed skip** | When a pipeline run restarts, it remembers which images it already scanned. Previously, a restart would re-scan everything from the beginning and re-pay GPT. Fixed. | **Saves full re-run cost** |
| 4 | **Switched from GPT-4o → GPT-4.1-mini** | Same quality for retail classification. GPT-4.1-mini costs ~70% less than GPT-4o. | **~₹5 lakh/month saved at 150 stores** |
| 5 | **Removed GPU requirement** | YOLO now runs on ONNX Runtime (CPU-only). Previously required GPU instances (2.5× more expensive). Server is now a standard compute instance. | **~₹29,000/month saved** |
| 6 | **Circuit breaker on GPT failures** | If GPT returns errors 5 times in a row, the system pauses automatically. Previously, a GPT outage caused 100s of retries — each retry still costs money even if it fails. | **Eliminates cost storms** |
| 7 | **Memory management** | After GPT analyses an image, the image bytes are immediately cleared from memory. Without this, a 5,000-image run would consume 1.5 GB of RAM accumulating until crash. Server stayed stable. | **Prevents crash → re-run costs** |
| 8 | **Parallel image downloads** | 8 downloads happen at the same time instead of one-by-one. A run that took 41 minutes now takes ~5 minutes. Less server time per run = less EC2 cost. | **~8× faster per run** |
| 9 | **Role/date normalization** | Fixes data quality at write time. Prevents corrupted analytics that require re-running the pipeline to fix. | **Prevents expensive re-runs** |
| 10 | **SQLite → PostgreSQL sync** | Pipeline data now flows correctly to the dashboard database. Previously missing data meant manual investigation time. | **Saves engineering time** |

---

## Part 3 — Current Cost (Today, 1 Store Pilot — BLRRRN)

| Item | Monthly Cost | Notes |
|---|---|---|
| Server (development mode, no AWS yet) | ₹0 | Running locally |
| OpenAI GPT API | ~₹1,500–3,000 | Based on 3,702 GPT calls made so far |
| Google Drive API | ₹0 | Free within quota |
| PostgreSQL (local) | ₹0 | Running locally |
| **Total today** | **~₹1,500–3,000/month** | Pilot scale only |

---

## Part 4 — Projected Cost at Scale (Without vs With Optimization)

This is the key table for the manager.

### At 150 Stores Full Production

| Cost Item | Without Optimization | With All Planned Optimization | Saving |
|---|---|---|---|
| **OpenAI GPT API** | ₹54–1,05,000/day | ₹13,500–27,000/day | **75% less** |
| **AWS Infrastructure** | ₹63,000/month | ₹43,500/month | **31% less** |
| **Google Drive** | ₹0 | ₹0 | — |
| **Total Monthly** | **₹82–1,20 lakh/month** | **₹25–35 lakh/month** | **~65% saving** |

> **How is GPT 75% less?**
> YOLO filter (already live) removes 70% of images. Batch API (planned, -50%) + store-hours filter (planned, -30%) × remaining 30% = massive compound reduction.

---

## Part 5 — Optimization Plan: Status Update (May 2026)

### Implementation Status

| # | Optimization | Saving | Status |
|---|---|---|---|
| 1 | OpenAI Batch API | 50% of GPT cost | **✅ DONE** |
| 2 | Store-Hours Filter | 30–40% of GPT cost | **✅ DONE** |
| 3 | Camera-Type Exclusion | 15–25% of GPT cost | **✅ DONE** |
| 4 | GPT Result Caching by Image Hash | 5–10% of GPT cost | **✅ DONE** |
| 5 | Frame Sampling (Smart Skip) | 20–30% of GPT cost | Planned (Month 2) |
| 6 | AWS Reserved Instances | 31% infra cost | Planned (go-live day) |

---

### Optimization 1 — OpenAI Batch API ✅ DONE
**Difficulty:** Medium | **Saving:** 50% of all GPT cost | **Completed:** May 2026

**What was built:**
- `src/iris/gpt_batch.py` — full batch queue/submit/retrieve/apply module
- Pipeline integration: `OnFlyConfig.gpt_batch_mode=True` routes all GPT work to overnight batch
- Backend endpoints: `GET /api/onfly/batch/status/{store_id}`, `POST /api/onfly/batch/retrieve/{store_id}`
- Frontend: "Batch mode" toggle in Scheduler Dashboard (purple badge, "50% cheaper")
- Morning retrieval: `scripts/batch_retrieve.py` + `scripts/setup_morning_retrieval.ps1` (Task Scheduler at 6AM)

**How to use:**
1. In Scheduler Dashboard, enable "Batch mode" checkbox before clicking Sync Now
2. Pipeline runs as normal — GPT images are queued, not sent immediately
3. At end of run, JSONL is submitted to OpenAI in <1 second. Laptop can close.
4. At 6AM: Task Scheduler wakes laptop → `batch_retrieve.py` downloads results → dashboard updates

| | Real-time (default) | Batch mode |
|---|---|---|
| Speed | Result in 2 seconds | Result by 6am |
| Cost | Full price | **50% off** |
| Dashboard data | Instant | Ready by morning |

**Estimated saving at 150 stores:** ₹15–40 lakh/month

---

### Optimization 2 — Store-Hours Filter ✅ DONE
**Difficulty:** Easy | **Saving:** 30–40% of GPT cost | **Completed:** May 2026

Images outside store operating hours (set per-store in Admin > Camera Zones) are auto-marked `outside_hours` — no YOLO, no GPT. Rejection reason visible in Reports > Image Scans.

| | Without filter | With filter |
|---|---|---|
| Images per day | 1,200/store | ~550/store |
| GPT calls | ~360/store/day | ~165/store/day |
| Monthly GPT cost | Full | **~54% less** |

---

### Optimization 3 — Camera-Type Exclusion ✅ DONE
**Difficulty:** Easy | **Saving:** 15–25% of GPT cost | **Completed:** May 2026

Camera IDs labelled `external`, `parking`, or `skip` in Admin > Camera Zones are completely excluded from the pipeline. Status shows as `camera_excluded` in Reports > Image Scans. Auto-discovery labels new camera IDs for admin review.

---

### Optimization 4 — GPT Result Caching by Image Hash ✅ DONE
**Difficulty:** Medium | **Saving:** 5–10% of GPT cost | **Completed:** May 2026

SHA-256 hash of image bytes is stored. If the same image reappears (Drive re-sync, retry), GPT result is copied from the original instead of re-calling the API. Status shows as `cached_from_hash` in Reports > Image Scans. Walk-in sessions are also copied automatically.

---

### Optimization 5 — Frame Sampling (Smart Skip)
**Difficulty:** Medium (1 week) | **Saving:** 20–30% of GPT cost | **Status:** Planned

Cameras take a photo every 30 seconds. If a customer is shopping for 10 minutes, there are 20 images of the same person. Analyse the first frame only; mark subsequent consecutive-same-region frames as "sampled."

---

### Optimization 6 — AWS Reserved Instances
**Difficulty:** Zero engineering (billing change only) | **Saving:** 31% of infrastructure cost | **Status:** On go-live day

Commit to 1-year reserved instances when going live. No technical work required.

| | On-demand | 1-year reserved |
|---|---|---|
| App Server | ₹5,165/month | ₹3,330/month |
| AI Worker | ₹28,580/month | ₹18,415/month |
| Database | ₹16,345/month | ₹10,420/month |
| **Total saved** | — | **₹18,000/month** |

---

## Part 6 — Implementation Timeline (Revised)

```
COMPLETED ✅:
  Store-Hours Filter          → live, 30–40% GPT saving
  Camera-Type Exclusion       → live, 15–25% GPT saving
  GPT Hash Caching            → live, 5–10% GPT saving
  OpenAI Batch API            → live, 50% GPT saving (overnight mode)

NEXT (Month 2):
  Frame Sampling              → 20–30% of remaining GPT
  AWS Reserved Instances      → 31% infra cost (billing only)
```

**Total achieved reduction to date: 65–75% of GPT cost through compounding filters + batch pricing.**

---

## Part 7 — ROI Analysis

### Is IRIS Worth Building?

**What IRIS costs to run (150 stores, fully optimized):**

| Item | Monthly |
|---|---|
| AWS Infrastructure (reserved) | ₹43,500 |
| OpenAI GPT (optimized) | ₹3,50,000–5,00,000 |
| Engineering maintenance | ₹50,000 (est.) |
| **Total** | **~₹4.5–6 lakh/month** |

**What IRIS generates for the business:**

| Benefit | How It Works | Value |
|---|---|---|
| **Avoid over-staffing** | Know exactly when footfall peaks. Schedule staff to match. A store with 12 staff when it needs 8 saves ₹50,000/month in salary waste per store. | **₹75 lakh/month at 150 stores** |
| **Catch under-conversion** | If 500 people walked in but only 50 bought, something is wrong. IRIS flags it. Store manager investigates. Improving conversion 1% at ₹5 lakh/day store = ₹50,000/day. | **₹1–5 crore/month potential** |
| **Merchandising decisions** | Which display gets attention? Which corner is dead? Real footfall heatmaps replace guesswork in planogram decisions. | **Reduces markdown waste** |
| **Theft / security correlation** | High footfall, low billing → flag for security review. | **Reduces shrinkage** |
| **Replace manual counting** | Currently stores hire 1 person to stand and count customers. ₹15,000–20,000/month/store × 150 stores = ₹22.5–30 lakh/month just in manual counters. | **₹25 lakh/month saved** |

**Simple ROI math:**

```
Monthly cost of IRIS (optimized, 150 stores):  ₹4.5–6 lakh
Value from better staffing alone:              ₹25–75 lakh/month
Value from replacing manual counters:          ₹25 lakh/month

Even the most conservative estimate:
  Savings: ₹50 lakh/month
  Cost:    ₹6 lakh/month
  ROI:     ~8× return every month
```

**Payback period:** If we invest ₹50 lakh in development and setup costs, the platform pays that back within **1 month** of running at full scale.

---

## Part 8 — Decision Summary for Management

| Question | Answer |
|---|---|
| What is the #1 cost? | OpenAI GPT API calls (~80% of total cost) |
| What reduces it most? | Store-hours filter + Batch API = 60–70% reduction |
| How long does optimization take? | 4–6 weeks engineering |
| Does optimization affect data quality? | No — same accuracy, just smarter about which images to analyse |
| Is IRIS worth the investment? | Yes — conservative ROI is 8× monthly |
| What's the risk of not optimizing? | At 150 stores without optimization: ₹80–1,20 lakh/month GPT cost alone |
| When should we commit to AWS reserved? | Day 1 of production — saves ₹18,000/month immediately, no engineering needed |

---

## Part 9 — What to Approve

We are asking for approval on two things:

**1. Engineering time (6 weeks)** to implement store-hours filter, camera exclusion, frame sampling, and Batch API. Total cost: existing team time, no external spend.

**2. AWS 1-year reserved instance commitment** on the day we go to production. Saves ₹18,000/month from day one. Decision can be made independently of engineering work.

No other budget items are needed. OpenAI API cost is pay-as-you-go — it scales exactly with usage and falls as we implement optimizations.

---

*Document path: `docs/deployment/cost-optimization-plan.md`*  
*Engineering contact: Vishal Nayak — vishal.nayak@kushals.com*

# IRIS Platform — AWS Server Requirement
**To:** IT Infrastructure Team / Engineering Manager
**From:** Vishal Nayak
**Date:** 7 May 2026
**Subject:** AWS Server Specification for IRIS Retail Intelligence Platform (150 Stores)

---

## 1. Background

IRIS is our in-house AI-powered retail intelligence platform. It processes camera snapshots from store locations, runs AI analysis (person detection + customer vs. staff classification), and generates footfall analytics, walk-in sessions, and store performance reports — all without storing any face or identity data.

This document provides the AWS infrastructure specification required to deploy IRIS at full production scale of **150 stores**.

---

## 2. What IRIS Does (Technical Summary for IT)

| Step | What Happens | Where It Runs |
|---|---|---|
| Image Sync | Downloads new camera snapshots from Google Drive | Celery Worker (EC2) |
| ONNX Scan | AI scans each image — does it contain a person? Yes/No. Runs `yolov8s.onnx` via ONNX Runtime (no PyTorch). | Celery Worker (EC2) — CPU only |
| GPT Analysis | Relevant images sent to OpenAI for customer/staff classification | OpenAI API (external) |
| Report Storage | Only text results saved — counts, roles, timestamps | RDS PostgreSQL |
| Dashboard | React web app served to store managers / analysts | App Server (EC2) |

> **Important:** Camera images are **never stored** on the server. They are downloaded to memory, analysed, and discarded. Only the text results (e.g., "2 customers, 1 staff") are saved to the database. This eliminates the large storage concern.

---

## 3. Scale Parameters

| Parameter | Value |
|---|---|
| Total stores | 150 |
| Cameras per store | 8–10 |
| Images per store per day | ~1,200 |
| Total images processed per day | **~180,000** |
| Estimated relevant images (contain people) | ~30% → ~54,000/day |
| GPT API calls per day | ~54,000 |

---

## 4. AWS Infrastructure Specification

### 4.1 EC2 — App Server (API + Web Dashboard)

| Attribute | Value |
|---|---|
| **Instance Type** | `c6i.large` |
| vCPU | 2 |
| RAM | 4 GB |
| Purpose | FastAPI REST API + React web frontend only. No AI workload runs here. |
| Operating System | Amazon Linux 2023 |
| Root Volume (EBS) | **gp3, 30 GB** — OS + application code |
| Elastic IP | 1 static IP required |

---

### 4.2 EC2 — Celery Workers (AI Pipeline)

This is the primary compute instance. YOLO AI inference runs on CPU and requires sustained, consistent performance — hence compute-optimised family.

| Attribute | Value |
|---|---|
| **Instance Type** | `c6i.2xlarge` |
| vCPU | 8 |
| RAM | 16 GB |
| Purpose | AI pipeline workers — Drive sync, YOLO scan, parallel GPT calls |
| Concurrent workers | 6 parallel store pipelines |
| Operating System | Amazon Linux 2023 |
| Root Volume (EBS) | **gp3, 30 GB** |
| Data Volume (EBS) | **gp3, 200 GB, 3000 IOPS** — database files, logs, temporary exports |

> **Why c6i (Compute Optimised) and not t3 (General Purpose)?**
> t3 instances are "burstable" — they run at reduced CPU when credit runs out. YOLO inference is a sustained workload running 24×7. A c6i gives consistent, full CPU performance at all times and avoids pipeline slowdowns during peak hours.

> **Why not a GPU instance?**
> The YOLO model used (YOLOv8s, served via ONNX Runtime) is designed for CPU inference. A GPU instance (g4dn) costs 2.5× more and provides minimal speed improvement for this task. Not recommended.
>
> **Inference library update (2026-05-07):** PyTorch and ultralytics have been replaced with ONNX Runtime on the server. The model (`yolov8s.onnx`) is identical weights, but ONNX Runtime has no PyTorch dependency. This reduces the server Python environment from ~420 MB to ~175 MB and inference time by 2×. The `c6i.2xlarge` recommendation is unchanged — the workload is still sustained CPU inference.

---

### 4.3 EC2 — Celery Beat Scheduler

| Attribute | Value |
|---|---|
| **Instance Type** | `t3.micro` |
| vCPU | 2 (burstable) |
| RAM | 1 GB |
| Purpose | Scheduler only — fires pipeline jobs on a timed cron. No compute. |
| Root Volume (EBS) | **gp3, 20 GB** |

---

### 4.4 RDS — Managed PostgreSQL

| Attribute | Value |
|---|---|
| **Engine** | PostgreSQL 16 |
| **Instance Class** | `db.t3.large` |
| vCPU | 2 |
| RAM | 8 GB |
| Storage Type | **gp3** |
| Storage Size | **200 GB** |
| Storage IOPS | 3000 (included free with gp3) |
| Multi-AZ Deployment | **Yes** (automatic failover — strongly recommended for production) |
| Automated Backups | 7-day retention, daily snapshots |
| Estimated DB growth | ~2.7 GB/month (text records only — no images) |
| Retention policy | 90-day rolling window (~90 GB plateau) |

> **Why 8 GB RAM for the database?**
> PostgreSQL uses RAM as a buffer pool — frequently read records stay in memory instead of hitting disk. 8 GB RAM ensures most dashboard and report queries are served from memory, keeping the UI responsive.

---

### 4.5 ElastiCache — Managed Redis

| Attribute | Value |
|---|---|
| **Node Type** | `cache.t3.medium` |
| RAM | 3.09 GB |
| Purpose | Celery job queue broker — holds the list of pipeline jobs to be processed |
| Cluster Mode | Off (single node sufficient) |

> **Why not cache.t3.small?**
> At 150 stores firing jobs simultaneously, queue depth can spike. t3.small (1.37 GB) risks running out of memory and dropping jobs. t3.medium gives safe headroom.

---

### 4.6 Application Load Balancer (ALB)

| Attribute | Value |
|---|---|
| Type | Application Load Balancer |
| Purpose | HTTPS termination — users access the dashboard securely via HTTPS |
| SSL Certificate | AWS Certificate Manager (ACM) — free, auto-renews |
| Target | App Server (c6i.large) on port 8767 |

---

### 4.7 EBS Volume Summary

| Volume | Attached To | Type | Size | IOPS | Monthly Cost |
|---|---|---|---|---|---|
| Root | App Server | gp3 | 30 GB | 3,000 (free) | ~$2.40 |
| Root | Celery Workers | gp3 | 30 GB | 3,000 (free) | ~$2.40 |
| Data | Celery Workers | gp3 | 200 GB | 3,000 (free) | ~$16.00 |
| Root | Beat Scheduler | gp3 | 20 GB | 3,000 (free) | ~$1.60 |
| Database | RDS | gp3 | 200 GB | 3,000 (free) | ~$16.00 |

> **All volumes use gp3.** gp3 is $0.08/GB vs gp2 at $0.10/GB, and gp3 includes 3,000 IOPS and 125 MB/s throughput at no extra charge. No provisioned IOPS (io2) required for this workload.

---

### 4.8 Networking

| Component | Specification |
|---|---|
| VPC | Single VPC across 2 Availability Zones |
| Subnets | Public subnet (App Server, ALB) + Private subnets (Celery, RDS, Redis) |
| NAT Gateway | 1 (allows private instances to reach Google Drive API and OpenAI) |
| Security Groups | App Server: port 443 from internet. RDS: port 5432 from app servers only. Redis: port 6379 from Celery only. |

---

## 5. Monthly Cost Estimate

### Infrastructure (AWS)

| Component | Instance | On-Demand/month | 1-Year Reserved/month |
|---|---|---|---|
| App Server | c6i.large | $62 | $40 |
| Celery Workers | c6i.2xlarge | $343 | $221 |
| Beat Scheduler | t3.micro | $8 | $5 |
| RDS PostgreSQL | db.t3.large Multi-AZ | $196 | $125 |
| ElastiCache Redis | cache.t3.medium | $52 | $35 |
| Load Balancer (ALB) | — | $22 | $22 |
| EBS Volumes | — | $38 | $38 |
| NAT Gateway | — | $32 | $32 |
| S3 (backups, exports) | — | $5 | $5 |
| **Infrastructure Total** | | **~$758/month** | **~$523/month** |

> Savings with 1-year reserved instances: **~$235/month (~31% reduction).**
> Recommend reserved instances for App Server and Celery Workers from day one — these run 24×7.

---

### OpenAI API Cost (Separate Budget Item)

| Metric | Value |
|---|---|
| Relevant images per day | ~54,000 |
| Estimated cost per GPT call | $0.004–$0.008 |
| **Estimated daily cost** | **$216–$432/day** |
| **Estimated monthly cost** | **$6,500–$13,000/month** |

> The OpenAI API cost significantly exceeds the infrastructure cost at this scale. This is the primary budget item to plan for. It can be reduced by ~50% using OpenAI's Batch API mode (processes jobs overnight at half price) — recommended as a Phase 2 optimisation.

---

## 6. What Does NOT Need Storage (Common Misconception)

A common concern is image storage — 150 stores × 1,200 images/day sounds like massive disk usage. **This does not apply to IRIS.**

IRIS does not store camera images on the server. The pipeline:
1. Downloads each image from Google Drive into server memory (RAM)
2. Runs AI analysis
3. Saves only the text result (customer count, staff count) — approximately 115 bytes per image
4. Discards the image

**Actual database growth:** ~2.7 GB/month (text records). With a 90-day retention policy, the database stabilises at approximately 90 GB — easily handled by the 200 GB RDS volume specified above.

---

## 7. Architecture Diagram

```
                        Internet
                           │
                    ┌──────▼──────┐
                    │     ALB     │  HTTPS :443
                    │ (Load Bal.) │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │      App Server         │
              │   c6i.large (4GB RAM)   │
              │   FastAPI + React UI    │
              └────────────┬────────────┘
                           │ internal
          ┌────────────────┼────────────────┐
          │                │                │
┌─────────▼──────┐  ┌──────▼──────┐  ┌────▼──────────────┐
│ Celery Workers │  │  Redis      │  │  RDS PostgreSQL    │
│ c6i.2xlarge    │  │ cache.t3.med│  │  db.t3.large       │
│ 8 vCPU 16 GB   │  │ 3 GB RAM    │  │  Multi-AZ 200 GB   │
│ YOLO + GPT     │  │ Job Queue   │  │  All analytics data│
└────────┬───────┘  └─────────────┘  └────────────────────┘
         │
         │ outbound (via NAT Gateway)
         ▼
 Google Drive API          OpenAI API
 (image download)       (GPT analysis)
```

---

## 8. Pre-Deployment Checklist for IT

Before the server is provisioned, the following must be ready:

- [ ] AWS account with EC2, RDS, ElastiCache, ALB, S3 permissions
- [ ] Domain name configured (e.g., `iris.kushals.com`) pointing to ALB
- [ ] OpenAI API key at **Tier 3** or higher (required for 54,000 calls/day — check at platform.openai.com/account/limits)
- [ ] Google Drive API key (Simple API Key — already working in current system)
- [ ] JWT Secret — 32-character random string for login security
- [ ] AWS Secrets Manager set up to hold: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `JWT_SECRET`, `POSTGRES_PASSWORD`
- [ ] Inbound port **443** open on security group for App Server
- [ ] Outbound port **443** open on Celery Workers (for Google Drive + OpenAI)

---

## 9. Recommended Phased Rollout

| Phase | Stores | Timeline | Infrastructure |
|---|---|---|---|
| **Pilot** | 6 stores (current) | Now | Single t3.large EC2, SQLite, no ALB |
| **Phase 1** | 20 stores | Month 1–2 | c6i.large + c6i.xlarge + RDS |
| **Phase 2** | 75 stores | Month 3–4 | c6i.large + c6i.2xlarge + RDS Multi-AZ |
| **Full Production** | 150 stores | Month 5–6 | Full spec above |

A phased rollout reduces risk and allows OpenAI API tier upgrades to happen ahead of scale requirements.

---

## 10. Summary Recommendation

| Item | Recommendation |
|---|---|
| App Server | `c6i.large` — EC2 Compute Optimised |
| AI Workers | `c6i.2xlarge` — EC2 Compute Optimised |
| Database | `db.t3.large` — RDS PostgreSQL, Multi-AZ, gp3 200 GB |
| Cache/Queue | `cache.t3.medium` — ElastiCache Redis |
| All EBS volumes | gp3 (not gp2, not io2) |
| Reserved instances | Yes — 1-year for App Server and Celery Workers |
| Infrastructure cost | ~$523/month (reserved) |
| OpenAI API cost | ~$6,500–$13,000/month — **primary budget item** |
| Image storage cost | $0 — images are not stored |

---

*Prepared by: Engineering Team — IRIS Platform*
*Document path: `docs/deployment/IRIS-Server-Requirement-150-Stores.md`*
*For questions contact: Vishal Nayak (vishal.nayak@kushals.com)*

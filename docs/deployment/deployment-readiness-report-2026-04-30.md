# IRIS Platform — Deployment Readiness Report
**Date:** 2026-04-30
**Prepared by:** Engineering / Project Management
**Distribution:** Engineering Head, Product Head, Lead Developer
**Status:** PRE-DEPLOYMENT — Not yet cloud-ready. See Section 4.

---

## 1. Project Requirement Reference

All governing documents are present and up to date in this repository:

| Document | Path |
|---|---|
| Business Requirements Document (BRD) | `docs/business/iris-brd.md` |
| Product Requirements Document (PRD) | `docs/prd/iris-platform-prd-v1.md` |
| MVP Blueprint | `docs/mvp-blueprint.md` |
| Data Flow Architecture | `docs/developer/data-flow-architecture.md` |
| Developer Documentation | `docs/developer/developer-doc.md` |
| Cloud Deployment Guide | `docs/operations/cloud-deployment.md` |
| Deployment Runbook | `docs/operations/deployment-runbook.md` |
| Change Ledger (all code changes) | `CHANGE_LEDGER.md` |
| Execution Status | `docs/planning/execution-status.md` |

**Summary of Business Requirement (from BRD):**
IRIS is an anonymous retail intelligence platform. It ingests timestamped camera snapshots from store cameras, runs AI-based person detection and semantic analysis, and delivers store-level analytics — footfall, dwell time, customer walk-in sessions, conversion signals, and hotspot maps — all without face recognition or identity persistence. Current scope: Kushals Jewellery stores, 2 cameras per store.

---

## 2. Complete Tech Stack — What, Where, Why, and Alternatives

### 2.1 Frontend

| Technology | Version | Where Used | Why Used |
|---|---|---|---|
| **React 18** | `^18.3.1` | All UI pages — Dashboard, Reports, Scheduler, Frame Review, Store Admin | Industry-standard component model, large ecosystem, type-safe with TypeScript |
| **TypeScript** | `^5.5.3` | Entire frontend codebase | Catches type errors at compile time, reduces runtime bugs |
| **Vite** | `^5.3.3` | Build toolchain and dev server | 10x faster builds than Webpack/CRA, native ESM, hot module replacement |
| **TailwindCSS** | `^3.4.6` | All styling | Utility-first, no CSS files to maintain, consistent design tokens |
| **Tremor** | `^3.18.7` | Charts (Line, Bar, Donut), KPI cards, Badges | Production-ready analytics UI components, zero custom chart code needed |
| **Recharts** | (via Tremor) | Trend, engagement, leaderboard charts | Declarative React chart library |
| **Axios** | `^1.7.2` | All API calls from frontend to backend | Interceptor support for JWT auth and 401 redirect, consistent error handling |
| **React Router DOM** | `^6.24.0` | Page routing (`/login`, `/dashboard`, `/reports`, etc.) | Standard React routing |
| **Lucide React** | `^1.11.0` | All icons | Lightweight, consistent icon set |

**Why NOT alternatives:**
- **Vue / Angular:** Team has React expertise; switching adds ramp-up cost with no functional benefit.
- **Next.js:** SSR is not needed — this is an internal analytics dashboard, not a public site. Vite SPA is simpler and faster to deploy (single static bundle served by FastAPI).
- **Material UI / Ant Design:** Tremor is purpose-built for analytics dashboards and significantly reduces custom chart work.

---

### 2.2 Backend — API Layer

| Technology | Version | Where Used | Why Used |
|---|---|---|---|
| **Python 3.11** | runtime | All backend logic | AI/ML libraries (YOLO, GPT wrappers, OpenCV, Pandas) are Python-native. No equivalent ecosystem exists in Node/Go for this use case |
| **FastAPI** | `>=0.111` | REST API (`/api/*` routes) | Async-native, auto-generates OpenAPI docs, Pydantic validation built-in. Fastest Python web framework |
| **Uvicorn** | `>=0.29` | ASGI server running FastAPI | Production-grade async server; runs on Windows via NSSM service and Docker |
| **SQLAlchemy 2.0** | `>=2.0` | ORM for PostgreSQL (async) | Async-native ORM, works with both SQLite (runtime fallback) and PostgreSQL |
| **Pydantic Settings** | `>=2.0` | Config management (`config.py`) | Type-safe env var parsing, default handling |
| **python-jose** | `>=3.3` | JWT token creation and verification | Industry-standard JWT library for Python |
| **passlib[bcrypt]** | `>=1.7` | Password hashing for user auth | bcrypt is the correct algorithm for password storage |
| **slowapi** | `>=0.1.9` | Rate limiting on all API routes | Prevents abuse, pairs directly with FastAPI |
| **python-multipart** | `>=0.0.9` | File upload handling (employee images, store master CSV) | Required by FastAPI for form/file endpoints |
| **httpx** | `>=0.27` | Async HTTP client for internal requests | Used in pipeline for Drive API calls |
| **Celery** | `>=5.3` | Background task queue | Pipeline runs (YOLO scan, GPT analysis) are long-running; must not block API thread |
| **Redis** | `>=5.0` | Celery broker + result backend | Lightweight in-memory queue; required by Celery |

**Why NOT alternatives:**
- **Node.js/Express for API:** All AI/ML logic (YOLO, OpenCV, GPT pipeline) is Python. A Node layer would add a cross-language bridge, network hop, and deployment complexity for zero benefit.
- **Django:** Heavier framework; async support is bolted on. FastAPI is async-native and 3–5x faster for API throughput.
- **Flask:** No async, no auto-validation, no OpenAPI auto-doc. FastAPI is strictly superior for new APIs.
- **RabbitMQ instead of Redis:** Redis serves dual purpose (cache + queue broker). Adding RabbitMQ adds an extra service with no benefit at this scale.

---

### 2.3 Backend — AI/ML Pipeline

| Technology | Version | Where Used | Why Used |
|---|---|---|---|
| **YOLOv8n (ultralytics)** | `>=8.3` | YOLO relevance scan — filters camera images that contain people | State-of-the-art real-time object detection; `yolov8n` (nano) runs on CPU without GPU. Fastest path to "does this frame have a person?" |
| **OpenAI GPT-4.1-mini** | API call | Semantic analysis of YOLO-relevant frames — identifies customer vs staff vs banner vs pedestrian, extracts count, purchase signals | Eliminates need for custom classification model. GPT vision understands retail context out of the box |
| **OpenCV (headless)** | `4.10.0.84` | Image pre-processing before YOLO and GPT | Industry standard for image I/O and manipulation in Python |
| **Pillow** | `>=10.4` | Image compression/optimization for employee uploads and Drive-synced images | Lightweight image library for JPEG normalization |
| **NumPy** | `>=1.26` | Numerical operations in analysis pipeline | YOLO and OpenCV return NumPy arrays natively |
| **Pandas** | `>=2.2` | CSV export, session data aggregation, report generation | Standard dataframe library; used for all report building |

**Why NOT alternatives:**
- **Custom-trained classifier instead of GPT:** Would require labelled training data, model training pipeline, retraining on drift — all high-cost. GPT-4.1-mini gives retail-context-aware classification on day one with no training data.
- **MediaPipe / Detectron2 instead of YOLO:** YOLO is the industry standard for real-time snapshot detection. YOLOv8n is the smallest/fastest variant and is sufficient for a relevance filter (binary: person yes/no).
- **PyTorch directly instead of ultralytics:** Ultralytics provides the pre-trained YOLOv8n weights and a clean inference API. Writing raw PyTorch would add weeks of work.

---

### 2.4 Database

| Technology | Where Used | Why Used |
|---|---|---|
| **SQLite** | Primary runtime DB (`data/store_registry.db`) | Zero-config, file-based, no server process. Works on local Windows dev machine and in Docker. Holds all store config, sessions, image state, users, roles, walk-in sessions |
| **PostgreSQL 17** | Planned for cloud production | Required for multi-instance concurrency (SQLite locks on write). SQLAlchemy async driver (`asyncpg`) already wired |

**Why NOT alternatives:**
- **MySQL / MariaDB:** PostgreSQL has better JSON support, row-level locking, and is preferred for analytics workloads.
- **MongoDB:** Data is relational (stores → sessions → images → users → roles). A document DB would lose JOIN capability and add complexity.
- **DynamoDB / Firestore:** Cloud-vendor lock-in; overkill for current scale; no local dev story.

---

### 2.5 Infrastructure / DevOps

| Technology | Where Used | Why Used |
|---|---|---|
| **Docker + Docker Compose** | Container packaging and local/cloud deployment | Single-command deploy, consistent environments across dev/staging/prod |
| **NSSM (Windows Service)** | Local dev auto-start of uvicorn on port 8767 | Ensures API restarts automatically after machine sleep/reboot during development on Windows |
| **GitHub Actions** | CI — lint (flake8) + tests (pytest) | Automated quality gate on every push to main |

---

### 2.6 Legacy Component — Retired

| Technology | Where Used | Status |
|---|---|---|
| **Streamlit** | Was `src/iris/iris_dashboard.py`, port 8765 | **RETIRED 2026-05-07.** All files deleted. React + FastAPI is now the sole UI. Port 8765 no longer in use. |

---

## 3. Server Hosting Requirements

> **Updated 2026-05-07:** IT has confirmed deployment on AWS EC2. Requirements below reflect the full 150-store production target. Full specification with all instance details is in `docs/deployment/IRIS-Server-Requirement-150-Stores.md`.

### 3.1 Minimum (Development / Pilot — up to 10 stores)

| Resource | Minimum | Notes |
|---|---|---|
| **RAM** | 4 GB | FastAPI + uvicorn: ~200 MB; YOLOv8n inference: ~600 MB; GPT pipeline workers: ~300 MB; OS + overhead: ~1 GB |
| **CPU** | 2 vCPUs | YOLO runs on CPU. 2 cores handles concurrent pipeline + API requests |
| **Storage** | 20 GB SSD (gp3) | OS (8 GB) + app code (2 GB) + database text records only — images are never stored on disk |
| **Network** | 100 Mbps | For Google Drive sync and OpenAI API calls |
| **Redis** | 512 MB RAM | Celery broker; in-memory only |

> **Image storage correction:** Images are processed in memory and discarded — never written to disk permanently. Storage requirement is metadata only (~4.7 KB/image in the database).

### 3.2 Production — AWS EC2 (150 Stores, IT-confirmed)

| Component | AWS Instance | vCPU | RAM | Storage | Est. Cost (reserved) |
| --- | --- | --- | --- | --- | --- |
| **App Server** (API + React) | `c6i.large` | 2 | 4 GB | gp3 30 GB | ~$40/month |
| **Celery Workers** (YOLO + pipeline) | `c6i.2xlarge` | 8 | 16 GB | gp3 30 GB root + gp3 200 GB data | ~$221/month |
| **Beat Scheduler** | `t3.micro` | 2 | 1 GB | gp3 20 GB | ~$5/month |
| **RDS PostgreSQL 16** | `db.t3.large` Multi-AZ | 2 | 8 GB | gp3 200 GB | ~$125/month |
| **ElastiCache Redis** | `cache.t3.medium` | — | 3 GB | — | ~$35/month |
| **ALB** (HTTPS termination) | — | — | — | — | ~$22/month |
| **NAT Gateway + EBS + S3** | — | — | — | — | ~$75/month |
| **Infrastructure total** | | | | | **~$523/month** |
| **OpenAI GPT API** (54K calls/day) | — | — | — | — | **~$6,500–13,000/month** |

> **Why c6i (Compute Optimised)?** YOLO inference is a sustained CPU workload. c6i instances (Intel Ice Lake) are compute-optimised — no burst credits, consistent full CPU at all times. t3 instances are burstable and will throttle during peak pipeline hours.
>
> **Why not a GPU instance?** YOLOv8n (nano) is designed for CPU inference. GPU instances cost 2.5× more with minimal speed improvement for this task.
>
> **All EBS volumes use gp3** — $0.08/GB with 3,000 IOPS baseline included free. No io2 provisioned IOPS needed.

### 3.3 Cloud Provider — AWS EC2 (IT Decision)

IT has confirmed AWS EC2. The configuration below is AWS-specific:

- **App Server:** `c6i.large` — EC2 Compute Optimised, Amazon Linux 2023
- **AI Workers:** `c6i.2xlarge` — 8 vCPU, 16 GB RAM, 6 concurrent Celery workers
- **Database:** `db.t3.large` RDS PostgreSQL 16, Multi-AZ, gp3 200 GB
- **Cache/Queue:** `cache.t3.medium` ElastiCache Redis 7.x
- **Load Balancer:** Application Load Balancer + ACM certificate (free HTTPS)
- **Infrastructure cost (1-year reserved):** ~$523/month
- **OpenAI API cost:** ~$6,500–$13,000/month — this is the dominant budget item

Full specification: `docs/deployment/IRIS-Server-Requirement-150-Stores.md`

---

## 4. Deployment Readiness Assessment

### Current Status: IN PROGRESS — Local Production, Cloud Pending

| Check | Status | Notes |
|---|---|---|
| Application runs locally | PASS | Runs on port 8767 via `start_api_server.py` |
| Docker image builds | PASS | `deploy/docker-compose.yml` builds and runs |
| API endpoints functional | PASS | All FastAPI routes tested and working |
| React frontend served | PASS | Built bundle served from `/` via FastAPI static mount |
| Auth (JWT + bcrypt) | PASS | Login, token, protected routes working |
| YOLO pipeline | PASS | YOLOv8n relevance scan working |
| GPT pipeline | PASS | GPT-4.1-mini live — `OPENAI_API_KEY` set in `.env.local` |
| Walk-in sessions | PASS | Sessions created and stored; 5,948+ rows live |
| Reports + downloads | PASS | All CSV downloads working |
| Streamlit retired | PASS | Streamlit fully deleted 2026-05-07. React + FastAPI is sole UI |
| Static asset bundles | PASS | Cleaned 2026-05-07 — single fresh build in `backend/app/static/` |
| PostgreSQL running locally | PASS | PG17 running locally; `gpt_enabled` column added to stores table |
| **JWT_SECRET hardened** | **PENDING** | Must be set to a 32-char random string before cloud deploy |
| **PostgreSQL migration (cloud)** | **PENDING** | Local PG17 working. Cloud RDS `db.t3.large` to be provisioned and `alembic upgrade head` run against it |
| **CORS origins locked** | **PENDING** | Currently allows localhost. Must be updated to production domain before cloud deploy |
| **Cloud not tested** | **PENDING** | Application has NOT been deployed to or smoke-tested on AWS EC2 yet |
| **HTTPS / TLS** | **PENDING** | ALB + ACM certificate required. No TLS configured locally |
| **Secrets management** | **PENDING** | API keys in `.env.local`. Cloud deploy requires AWS Secrets Manager |
| **OpenAI tier** | **PENDING** | Requires Tier 3+ for 54,000 GPT calls/day at 150-store scale |
| **Drive API rate limiting** | **PENDING** | 150 stores must be staggered — not all firing at midnight simultaneously |
| **90-day DB retention job** | **PENDING** | Celery periodic task to archive old `onfly_image_state` rows (prevents unbounded DB growth) |

### Blockers Before Cloud Deployment

1. **Set `JWT_SECRET`** — 32-char random string in AWS Secrets Manager, injected as env var
2. **Provision AWS EC2** — see `docs/deployment/IRIS-Server-Requirement-150-Stores.md` for exact instance types
3. **Run PostgreSQL migration** — `alembic upgrade head` against RDS `db.t3.large`
4. **Update CORS origins** — set production domain in `config.py` or `CORS_ORIGINS` env var
5. **Configure TLS** — ALB with ACM certificate (free, auto-renews)
6. **Move secrets to AWS Secrets Manager** — `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `JWT_SECRET`, `POSTGRES_PASSWORD`
7. **Upgrade OpenAI account to Tier 3+** — required for 54,000 calls/day throughput
8. **Stagger store scheduler** — spread 150 store syncs across 6-hour window, not simultaneous midnight

---

## 5. Redundant Files — Audit and Cleanup

### 5.1 Static Asset Bundles — RESOLVED

**Status: Cleaned 2026-05-07.** Old multi-generation JS/CSS bundles removed. A single clean build is now live in `backend/app/static/`. No action required.

For future builds, always run:

```bash
rm -rf backend/app/static/* && cp -r frontend/dist/* backend/app/static/
```

### 5.2 Leftover Dev Processes — RESOLVED

**Status: Resolved.** Ports 8768 and 8769 are no longer in use. Only port 8767 (no-Docker) and 8766 (Docker) are active.

### 5.3 Streamlit — RESOLVED

**Status: Fully deleted 2026-05-07.** `src/iris/iris_dashboard.py`, `src/run_dashboard.py`, `scripts/start_web_app.py`, `deploy/Dockerfile`, and `deploy/requirements.docker.txt` all deleted. Port 8765 is gone.

### 5.4 Files Safe to Delete Before Cloud Deploy

| Path | Reason |
|---|---|
| `data/exports/current/gpt_validation/` | Test run outputs from validation phase. Not needed in production |
| `.env` or `.env.local` on the server | Must never be committed — use AWS Secrets Manager instead |
| `deploy/no_docker/runtime_logs/` | Local dev runtime logs. Not needed in cloud (use CloudWatch) |

---

## 6. Project Flow (End to End)

```
Step 1 — Image Capture
  Store cameras take snapshots every 1 second per camera
  Files named: HH-MM-SS_D<cam>-N.jpg (e.g., 12-27-16_D13-1.jpg)
  Uploaded to Google Drive → date-folder structure (YYYY-MM-DD/)

Step 2 — Drive Sync
  IRIS scheduler (Celery beat or manual trigger) calls Google Drive API
  Delta sync: downloads only new files not yet seen in local DB
  Images saved to: data/stores/<store_id>/<date>/
  State tracked in: onfly_image_state (SQLite table)

Step 3 — YOLO Relevance Scan
  YOLOv8n runs on each downloaded image
  Output: binary flag yolo_relevant = 1/0 (person detected or not)
  Non-relevant images are skipped in next step
  Confidence threshold: 0.18 (configurable)

Step 4 — GPT Vision Analysis (relevant images only)
  GPT-4.1-mini receives each YOLO-relevant image
  Prompt: identify person count, role (customer/staff/banner/pedestrian),
           purchase signal (bag visible), gender, age band
  Output stored in: onfly_image_state (gpt_customer_count, gpt_staff_count, gpt_status)

Step 5 — Walk-in Session Creation
  GPT results are grouped into sessions by time-window + camera
  Each session = one person's presence: entry_time, exit_time, camera_id, role, group_id
  Sessions stored in: onfly_walkin_sessions (SQLite table)
  Walk-in IDs generated: W-BLR-YYYYMMDD-XXXX

Step 6 — API (FastAPI)
  React frontend polls /api/reports/*, /api/dashboard/*, /api/onfly/*
  All data served from SQLite via route handlers
  JWT auth required on all endpoints
  Downloads: streaming CSV responses

Step 7 — React Dashboard
  Reports Page: walk-in detail, summary, image scan results
  Validation Sub-report: session ↔ Drive image cross-reference (camera-filtered, fixed 2026-04-30)
  Scheduler Page: pipeline run status, manual trigger buttons
  Frame Review: QA review of individual frames (paginated, lazy-loaded)
  Overview: KPI cards, trend charts, store leaderboard, gender/age analytics

Step 8 — Exports
  CSV downloads available for all report types
  Walk-in detail, summary by date, image scan log, validation map
```

---

## 7. What Can Be Improved / Future Stack Direction

| Area | Current State | Recommended Next Step |
|---|---|---|
| Database | PostgreSQL running locally; SQLite for pipeline state | Migrate pipeline state (onfly_image_state) to RDS on cloud deploy |
| Image storage | Not stored — pipeline discards images after analysis | No action needed. Images are never written to disk. |
| Secrets | `.env.local` file (local dev only) | AWS Secrets Manager — inject as env vars into EC2 at launch |
| TLS | None | ALB + ACM certificate (free, auto-renews) — included in EC2 spec |
| Monitoring | None | AWS CloudWatch for API logs + pipeline errors; set alert on `gpt_status=failed` spike |
| GPT cost | Per-image API call (~$6,500–13,000/month at 150 stores) | OpenAI Batch API mode — 50% cost reduction, processes overnight |
| Streamlit | **RETIRED 2026-05-07** | Complete. React + FastAPI is the sole UI. |
| Drive API rate limiting | All stores fire simultaneously | Stagger 150-store syncs across 6-hour window to avoid `userRateLimit exceeded` |
| DB retention | Grows unbounded | Celery periodic task to archive/delete rows older than 90 days (~76 GB plateau) |

---

*Document end. For questions contact Engineering Lead.*
*Paths to governing docs: `docs/business/iris-brd.md`, `docs/prd/iris-platform-prd-v1.md`*

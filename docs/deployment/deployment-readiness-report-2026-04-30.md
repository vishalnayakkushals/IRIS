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

### 2.6 Legacy Component (Being Phased Out)

| Technology | Where Used | Status |
|---|---|---|
| **Streamlit** | Original dashboard (`src/iris/iris_dashboard.py`), port 8765 | Active but being replaced by React + FastAPI. Will be retired after React dashboard reaches full feature parity |

---

## 3. Server Hosting Requirements

### 3.1 Minimum (Functional, development-grade)

| Resource | Minimum | Notes |
|---|---|---|
| **RAM** | 4 GB | FastAPI + uvicorn: ~200MB; YOLOv8n inference: ~600MB; GPT pipeline workers: ~300MB; OS + overhead: ~1GB |
| **CPU** | 2 vCPUs | YOLO runs on CPU. 2 cores handles concurrent pipeline + API requests |
| **Storage** | 20 GB | OS (8GB) + app code (2GB) + SQLite DB (1GB) + image snapshots per store (varies; ~1GB/store/month at 1 img/sec/camera) |
| **Network** | 100 Mbps | For Google Drive sync and OpenAI API calls |
| **Redis** | 512 MB RAM | Celery broker; in-memory only |

### 3.2 Recommended (Production-grade, 6 stores, 2 cameras)

| Resource | Recommended | Reason |
|---|---|---|
| **RAM** | 8 GB | Headroom for parallel YOLO + GPT workers, PostgreSQL, Redis, API, and future growth |
| **CPU** | 4 vCPUs | Parallel Celery workers for concurrent store pipelines |
| **Storage** | 100 GB SSD | ~2 stores × 2 cameras × 1 img/sec = ~17 GB/month image data. 100GB gives 5+ months runway. Use object storage (S3/GCS) beyond this |
| **Database** | Managed PostgreSQL (2 vCPU, 4GB) | Separate from app server; required for multi-user concurrency |
| **Redis** | Managed Redis (1GB) | Celery queue persistence |

### 3.3 Cloud Provider Options

Any of the following work with zero code changes:
- **AWS:** EC2 t3.large (8GB RAM, 2 vCPU) + RDS PostgreSQL + ElastiCache Redis
- **GCP:** e2-standard-2 + Cloud SQL + Memorystore
- **Azure:** B2ms + Azure Database for PostgreSQL + Azure Cache for Redis
- **Estimated monthly cost:** USD 80–150/month (app server + managed DB + Redis, all reserved instances)

---

## 4. Deployment Readiness Assessment

### Current Status: NOT CLOUD-READY

| Check | Status | Notes |
|---|---|---|
| Application runs locally | PASS | Runs on port 8767 via NSSM Windows service |
| Docker image builds | PASS | `deploy/docker-compose.yml` builds and runs |
| API endpoints functional | PASS | All FastAPI routes tested and working |
| React frontend served | PASS | Built bundle served from `/` via FastAPI static mount |
| Auth (JWT + bcrypt) | PASS | Login, token, protected routes working |
| YOLO pipeline | PASS | YOLOv8n relevance scan working |
| GPT pipeline | PASS | GPT-4.1-mini analysis working (requires `OPENAI_API_KEY`) |
| Walk-in sessions | PASS | Sessions created and stored in SQLite |
| Reports + downloads | PASS | All CSV downloads working |
| Validation report | PASS (just fixed) | Camera-correct image matching fixed in this session |
| **JWT_SECRET hardened** | **FAIL** | Config default is `change_me_in_env`. Must be set to a 32-char random string before cloud deploy |
| **PostgreSQL migration** | **FAIL** | SQLite in use. SQLite cannot handle concurrent writes from multiple workers in cloud. Must migrate to managed PostgreSQL |
| **CORS origins locked** | **FAIL** | Currently allows localhost origins. Must be updated to production domain |
| **Cloud not tested** | **FAIL** | Application has NOT been deployed to or smoke-tested on any cloud provider |
| **Real-time output** | PARTIAL | Walk-in sessions are generated from seeded Apr 8–9 data. Live pipeline on Apr 23+ images needs to be run to produce real-time output |
| **HTTPS / TLS** | **FAIL** | No TLS configured. Production requires HTTPS |
| **Secrets management** | **FAIL** | API keys in `.env` file. Cloud deploy needs secrets manager (AWS Secrets Manager / GCP Secret Manager) |

### Blockers Before Cloud Deployment

1. **Set `JWT_SECRET`** to a random 32-character string in production `.env`
2. **Run PostgreSQL migration** — `alembic upgrade head` against managed PostgreSQL instance
3. **Update CORS origins** in `config.py` or env var to production domain
4. **Run full GPT pipeline** on live Apr 23+ images to replace seeded data with real walk-in sessions
5. **Configure TLS** via reverse proxy (nginx or cloud load balancer)
6. **Move secrets** to cloud secret manager; do not pass `OPENAI_API_KEY` as plain env var in production

---

## 5. Redundant Files — Audit and Cleanup

### 5.1 Identified Redundant Asset Bundles

Every `npm run build` generates new hashed JS/CSS bundle files in `backend/app/static/assets/`. Old bundles from prior builds are NOT auto-cleaned. Currently there are multiple generations of named bundles (e.g., `ActivityLogs-94r3kSSM.js`, `ActivityLogs-BInep-HX.js`, `ActivityLogs-BIYdEyKAg.js`... 7 versions of the same page). These old files are dead code.

**Action:** Run the following before deployment to keep only the current build:

```powershell
# Delete all old static assets and replace with fresh build
Remove-Item -Recurse -Force backend\app\static\assets\*
Copy-Item -Recurse -Force frontend\dist\* backend\app\static\
```

The `vite build` config already sets `emptyOutDir: true`, so `frontend/dist` is always clean. The problem is manual copy does not clean the destination. This is now fixed in the build workflow.

### 5.2 Leftover Dev Processes on Ports 8768 and 8769

Currently three Python processes are running:
- PID 11732 → port 8767 (NSSM service — correct)
- PID 20492 → port 8768 (leftover — should be stopped)
- PID 17944 → port 8769 (Codex workaround — should be stopped)

**Action:** From admin PowerShell:
```powershell
Stop-Process -Id 20492, 17944 -Force
```

### 5.3 Files That Are Safe to Delete (Not Required for Runtime)

| Path | Reason |
|---|---|
| `data/exports/current/gpt_validation/` | Test run outputs from validation phase. Not needed for production |
| Old `.env` backups if present | Must not be committed or deployed |
| `CTO/logs/perf_events.jsonl` | Local performance observation logs, not needed in cloud |

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

| Area | Current | Recommended Next Step |
|---|---|---|
| Database | SQLite | PostgreSQL (Alembic migration scripts already present) |
| Image storage | Local filesystem | AWS S3 or GCS (avoids disk capacity limits at scale) |
| Secrets | .env file | AWS Secrets Manager / GCP Secret Manager |
| TLS | None | nginx reverse proxy or cloud load balancer with managed cert |
| Monitoring | None | Datadog / Grafana Cloud for API latency and pipeline errors |
| GPT cost | Per-image API call | Batch API mode (reduces cost 50% at scale) |
| Streamlit | Port 8765, legacy | Retire once React reaches full feature parity (2–3 more features) |

---

*Document end. For questions contact Engineering Lead.*
*Paths to governing docs: `docs/business/iris-brd.md`, `docs/prd/iris-platform-prd-v1.md`*

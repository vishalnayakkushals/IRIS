# IRIS — Retail Intelligence Platform

IRIS is an anonymous retail intelligence platform. It ingests timestamped camera snapshots from store cameras, runs AI-based person detection (YOLO) and semantic analysis (GPT-4.1-mini), and delivers store-level analytics — footfall, walk-in sessions, customer vs. staff classification, and conversion signals — all without face recognition or identity persistence.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Tremor |
| Backend API | Python 3.11, FastAPI, Uvicorn |
| AI Pipeline | YOLOv8n (person detection), OpenAI GPT-4.1-mini (semantic analysis) |
| Database | PostgreSQL 17 (production), SQLite (pipeline state) |
| Task Queue | Celery + Redis |
| Auth | JWT (python-jose), bcrypt (passlib) |

---

## Running Locally (No Docker)

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"

# Install Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Copy and configure environment
Copy-Item .env.local.example .env.local
# Edit .env.local — set OPENAI_API_KEY, GOOGLE_API_KEY, JWT_SECRET

# Start the API server (port 8767)
python scripts/start_api_server.py
```

Open: `http://localhost:8767`

---

## Running with Docker

Docker is **not required for local development** — the no-Docker mode above works fine on Windows.

Docker becomes necessary when deploying to a cloud server (AWS EC2). It packages the entire application — Python, all libraries, Redis — into a sealed container that runs identically on any Linux server with a single command.

| Mode | When to use | Port |
| --- | --- | --- |
| No Docker (`start_api_server.py`) | Local development, testing | 8767 |
| Docker Compose | Cloud server deployment | 8766 |

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"

# Build and start all services (API + Celery worker + Beat scheduler + Redis)
docker compose -f deploy/docker-compose.yml up --build -d

# View logs
docker compose -f deploy/docker-compose.yml logs -f iris-api

# Stop all services
docker compose -f deploy/docker-compose.yml down
```

Open: `http://localhost:8766`

**What Docker starts automatically:** FastAPI server, Celery worker (pipeline jobs), Celery beat (scheduler), and Redis. Without Docker, you need to start each of these separately. Docker cost: free — you only pay for the cloud server it runs on.

---

## Project Structure

```text
IRIS/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # App factory, mounts React static files
│   │   ├── config.py           # Pydantic settings (env vars)
│   │   ├── api/                # Route handlers
│   │   │   ├── routes_auth.py
│   │   │   ├── routes_admin.py
│   │   │   ├── routes_dashboard.py
│   │   │   ├── routes_reports.py
│   │   │   ├── routes_onfly.py
│   │   │   ├── routes_qa.py
│   │   │   └── routes_detail.py
│   │   ├── auth/               # JWT + dependency injection
│   │   ├── db/                 # SQLAlchemy models + CRUD
│   │   └── celery_app/         # Celery worker + beat schedule
│   ├── requirements.txt        # FastAPI + pipeline dependencies
│   ├── Dockerfile              # Multi-stage: Node build → Python runtime
│   └── app/static/             # Built React files (served by FastAPI)
├── frontend/                   # React application
│   └── src/
│       ├── pages/              # 20 pages (Overview, Reports, FrameReview, etc.)
│       ├── components/         # Shared UI components
│       └── api/client.ts       # Axios API client with JWT interceptor
├── src/iris/                   # Core Python pipeline modules
│   ├── onfly_pipeline.py       # Main YOLO + GPT pipeline
│   ├── drive_delta_sync.py     # Google Drive delta sync
│   ├── store_registry.py       # SQLite + auth helpers
│   └── iris_analysis.py        # YOLO detector wrapper
├── scripts/                    # CLI pipeline scripts and schedulers
├── data/                       # Runtime data (gitignored)
│   ├── store_registry.db       # SQLite pipeline state
│   ├── stores/                 # Store image folders (temp, not persisted)
│   └── exports/                # CSV report outputs
├── deploy/                     # Docker Compose + deployment configs
├── docs/                       # Architecture, deployment, and BRD docs
└── requirements.txt            # Core Python dependencies (pipeline)
```

---

## Environment Variables

Copy `.env.local.example` to `.env.local` and fill in:

| Variable | Required | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | Yes | GPT-4.1-mini API key for semantic analysis |
| `GOOGLE_API_KEY` | Yes | Google Simple API Key for Drive folder access |
| `JWT_SECRET` | Yes | 32-char random string for login security |
| `POSTGRES_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |

---

## Key Pages (React Dashboard)

| Page | Path | Description |
| --- | --- | --- |
| Overview | `/` | KPI cards, trend charts, store leaderboard |
| Store Detail | `/detail` | Per-store walk-in analytics |
| Reports | `/reports` | Walk-in sessions, image scan log, CSV downloads |
| Frame Review | `/frame-review` | QA review of individual camera frames |
| Scheduler | `/scheduler` | Pipeline run status, manual trigger, live progress |
| Users | `/admin/users` | User management, password reset |
| Stores | `/admin/stores` | Store configuration and Drive sync settings |
| Store Access | `/admin/store-access` | Assign store access per user |
| Roles | `/admin/roles` | Role and permission management |

---

## Pipeline Flow

```text
Google Drive folder
    ↓ delta sync (new files only)
YOLO scan (YOLOv8n) — is there a person in this frame?
    ↓ relevant frames only (~30%)
GPT-4.1-mini — customer vs staff, count, purchase signal
    ↓
SQLite (per-image state) + PostgreSQL (sessions, analytics)
    ↓
React dashboard — live reports, walk-in sessions, CSV exports
```

Images are **never stored permanently**. Download → analyse → discard. Only text results (~115 bytes/image) are saved to the database.

---

## API

The FastAPI server auto-generates OpenAPI docs:

- Swagger UI: `http://localhost:8767/docs`
- ReDoc: `http://localhost:8767/redoc`

---

## Deployment

See `docs/deployment/IRIS-Server-Requirement-150-Stores.md` for full AWS EC2 specification for 150-store production deployment.

See `deploy/no_docker/README.md` for the no-Docker Linux deployment guide (systemd services).

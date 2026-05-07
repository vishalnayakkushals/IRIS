# IRIS — Retail Intelligence Platform

IRIS is an anonymous retail intelligence platform. It ingests timestamped camera snapshots from store cameras, runs AI-based person detection (YOLOv8s) and semantic analysis (GPT-4.1-mini), and delivers store-level analytics — footfall, walk-in sessions, customer vs. staff classification, and conversion signals — all without face recognition or identity persistence.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Tremor |
| Backend API | Python 3.11, FastAPI, Uvicorn |
| AI Detection | YOLOv8s — person detection (runs via ONNX Runtime, no PyTorch needed on server) |
| AI Analysis | OpenAI GPT-4.1-mini — customer vs. staff classification, purchase signals |
| Database | PostgreSQL 17 (production), SQLite (pipeline state) |
| Task Queue | Celery + Redis |
| Auth | JWT (python-jose), bcrypt (passlib) |

> **What is "ONNX" vs "YOLO"?** YOLOv8s is the AI model name — it detects people in camera frames. ONNX is just the file format the model is saved in (like a PDF vs a Word document — same content, different container). The model is always referred to as **YOLOv8s**. On the server, it runs via ONNX Runtime instead of PyTorch — 245 MB smaller, 2× faster, same accuracy.

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

Open in browser:

- **This machine:** `http://localhost:8767`
- **Any device on the same network (phone, tablet, colleague's laptop):** `http://192.168.1.113:8767`

> The server binds to `0.0.0.0` by default, so it is accessible to every device on your local network at your machine's IP address. No extra configuration needed. If Windows Firewall blocks it, allow port 8767 inbound in Windows Defender Firewall settings.

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
│   │   ├── main.py             # App factory, startup migrations, mounts React static files
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
│       ├── pages/              # 20 pages (Overview, Reports, FrameReview, QualityFeedback, etc.)
│       ├── components/         # Shared UI components
│       └── api/client.ts       # Axios API client with JWT interceptor
├── src/iris/                   # Core Python pipeline modules
│   ├── onfly_pipeline.py       # Main pipeline (YOLOv8s + GPT)
│   ├── drive_delta_sync.py     # Google Drive delta sync + filename dedup
│   ├── store_registry.py       # SQLite + auth helpers
│   └── iris_analysis.py        # YOLOv8s detector (ONNX Runtime + HOG fallback)
├── scripts/                    # CLI scripts and utilities
│   ├── start_api_server.py     # Starts the local dev server
│   ├── export_onnx.py          # One-time: exports yolov8s.pt → yolov8s.onnx (dev only)
│   └── validate_onnx.py        # Accuracy benchmark: ONNX vs YOLO on live frames
├── data/                       # Runtime data (mostly gitignored)
│   ├── models/yolov8s.onnx     # YOLOv8s model in ONNX format (committed — server gets it on git pull)
│   ├── store_registry.db       # SQLite pipeline state
│   └── stores/                 # Store image folders (temp, not persisted)
├── deploy/                     # Docker Compose + deployment configs
├── docs/                       # Architecture, deployment, and BRD docs
└── requirements.txt            # Core Python dependencies (pipeline)
```

---

## Environment Variables

Copy `.env.local.example` to `.env.local` and fill in:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | — | GPT-4.1-mini API key for semantic analysis |
| `GOOGLE_API_KEY` | Yes | — | Google Simple API Key for Drive folder access |
| `JWT_SECRET` | Yes | — | 32-char random string for login security |
| `POSTGRES_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Redis URL for Celery |
| `ONFLY_DETECTOR` | No | `onnx` | Detection engine: `onnx` (server default) or `yolo` (dev with ultralytics) |
| `YOLO_CONF` | No | `0.20` | YOLOv8s confidence threshold — 0.20 is more sensitive than 0.30, ensuring no missed detections |
| `CORS_ORIGINS` | No | `http://localhost:8767` | Comma-separated allowed origins. Add your network IP to allow access from other devices |
| `ENVIRONMENT` | No | `development` | Set to `production` to enforce hard security checks on startup |

### Allowing network access from other devices

If you want colleagues or mobile devices on the same WiFi to access the app at `http://192.168.1.113:8767`, add your local IP to CORS_ORIGINS in `.env.local`:

```env
CORS_ORIGINS=http://localhost:3000,http://localhost:8767,http://127.0.0.1:8767,http://192.168.1.113:8767
```

The server already listens on all network interfaces (`0.0.0.0`) so no other change is needed. Find your local IP with `ipconfig` (look for IPv4 Address under your Wi-Fi adapter).

---

## Key Pages (React Dashboard)

| Page | Path | Description |
| --- | --- | --- |
| Overview | `/` | KPI cards, trend charts, store leaderboard, gender/age analytics |
| Store Detail | `/detail` | Per-store walk-in analytics |
| Reports | `/reports` | Walk-in sessions, image scan log, CSV downloads |
| Quality Feedback | `/quality` | QA review of GPT-analysed walk-in sessions; approve/reject labels |
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
    ↓ delta sync (new files only) + filename dedup (drops Drive duplicate uploads)
YOLOv8s scan — is there a person in this frame?  [runs via ONNX Runtime, conf=0.20]
    ↓ relevant frames only (~30%) + SHA256 content dedup (skips identical images)
GPT-4.1-mini — customer vs staff, count, purchase signal, gender, age band
    ↓
SQLite (per-image state) + PostgreSQL (sessions, analytics)
    ↓
React dashboard — live reports, walk-in sessions, CSV exports
```

Images are **never stored permanently**. Download → analyse → discard. Only text results (~115 bytes/image) are saved to the database.

---

## Validation — ONNX Accuracy

To verify the YOLOv8s ONNX detector matches the original PyTorch YOLO on your store data:

```powershell
# Compare ONNX vs PyTorch YOLO on 50 live camera frames
python scripts/validate_onnx.py --frames 50 --conf 0.20

# Test a specific store
python scripts/validate_onnx.py --frames 100 --store BLRJAY --conf 0.20
```

Expected output: **84%+ exact count match**, symmetric distribution (neither detector consistently higher), 2× speed advantage for ONNX. The remaining differences are borderline detections at the threshold — symmetric means no systematic accuracy loss.

> ONNX runs at `conf=0.20` vs the old YOLO at `conf=0.30` — this makes ONNX **more sensitive**, so it catches more borderline detections than YOLO previously did. Any extra detections are re-validated by GPT, which acts as the true classifier.

---

## API

The FastAPI server auto-generates OpenAPI docs:

- Swagger UI: `http://localhost:8767/api/docs`
- Network access: `http://192.168.1.113:8767/api/docs`

---

## Deployment

See `docs/deployment/IRIS-Server-Requirement-150-Stores.md` for full AWS EC2 specification for 150-store production deployment.

See `deploy/no_docker/README.md` for the no-Docker Linux deployment guide (systemd services).

Key deployment notes:

- `data/models/yolov8s.onnx` is committed to the repo — server gets the model file on `git pull`, no manual copy needed
- PyTorch and ultralytics are **not** installed on the server — only `onnxruntime>=1.18` is required
- To regenerate the ONNX model file (e.g. after upgrading the model): run `python scripts/export_onnx.py` on a dev machine with ultralytics installed

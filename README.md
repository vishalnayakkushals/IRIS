# IRIS — Retail Intelligence Platform

IRIS is an anonymous retail-intelligence platform for store camera snapshots. It reads timestamped images from Google Drive or local folders, filters them with YOLO, classifies relevant frames with GPT, reconstructs walk-in sessions, and serves the results in a React + FastAPI web app.

---

## Canonical Runtime Story

IRIS now follows one runtime shape everywhere:

| Component | Responsibility | Entry point |
| --- | --- | --- |
| Web app | FastAPI API + embedded React SPA | `scripts/start_api_server.py` |
| Core scheduler worker | recurring operational jobs | `scripts/start_scheduler_worker_service.py` |
| On-fly scheduler worker | store scan scheduling + retries | `scripts/start_onfly_scheduler_service.py` |
| Store auto-sync worker | mapped-store pull loop | `scripts/start_store_auto_sync_service.py` |
| PostgreSQL | platform metadata, auth, admin, dashboards | `POSTGRES_URL` |
| SQLite | fast pipeline state + report materialization | `data/store_registry.db` |

`backend/app/main.py` is now web-only. Runtime preparation, SQLite index checks, PostgreSQL additive migrations, and zombie-run cleanup happen through `backend/app/runtime_startup.py`, called by the launcher scripts instead of running inside request-serving code.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Tremor |
| Backend API | Python 3.11, FastAPI, Uvicorn |
| AI detection | YOLOv8s via ONNX Runtime |
| AI semantics | OpenAI GPT-4.1-mini |
| Platform database | PostgreSQL 17 |
| Pipeline state database | SQLite |
| Auth | JWT (python-jose), bcrypt/passlib |

---

## Running Locally (Browser + No Docker)

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"

pip install -r requirements.txt
pip install -r backend/requirements.txt
Copy-Item .env.local.example .env.local
# Fill OPENAI_API_KEY, GOOGLE_API_KEY, JWT_SECRET, POSTGRES_URL

python scripts/start_api_server.py
```

Open:
- `http://localhost:8767`
- or from the same LAN: `http://<your-local-ip>:8767`

Optional background workers for full local behavior:

```powershell
python scripts/start_scheduler_worker_service.py
python scripts/start_onfly_scheduler_service.py
python scripts/start_store_auto_sync_service.py
```

---

## Cloud / Production Runtime

Use `deploy/cloud/README.md` as the source-of-truth deployment guide.

Supported production service set:
- `iris-api.service`
- `iris-core-scheduler.service`
- `iris-onfly-scheduler.service`
- `iris-store-auto-sync.service`
- PostgreSQL
- Nginx

The production app port remains `8767` behind Nginx.

---

## Project Structure

```text
IRIS/
├── backend/
│   └── app/
│       ├── main.py                    # Web-only FastAPI app
│       ├── runtime_startup.py         # DB prep + zombie cleanup before service start
│       ├── api/
│       │   ├── routes_reports.py      # report endpoints
│       │   ├── report_queries.py      # SQLite/runtime report reads
│       │   ├── report_csv.py          # CSV/export helpers
│       │   ├── report_enrichment.py   # report enrichment logic
│       │   ├── report_validation.py   # validation report mapping
│       │   ├── routes_onfly.py        # thin on-fly HTTP routes
│       │   └── onfly_runtime.py       # on-fly runtime orchestration helpers
│       └── workers/
│           └── store_auto_sync.py     # background mapped-store sync worker
├── frontend/
│   └── src/
│       ├── pages/
│       ├── features/reports/
│       ├── features/scheduler/
│       └── features/frame-review/
├── src/iris/
│   ├── onfly_pipeline.py              # top-level orchestration (reduced wrapper)
│   ├── source_clients.py              # Drive/local source clients + filename parsing
│   ├── download_manager.py            # download + dedup + smart-frame sampling helpers
│   ├── gpt_runtime.py                 # GPT request/runtime helpers
│   ├── session_reconstruction.py      # walk-in persistence + sampled-frame resolution
│   ├── report_writer.py               # CSV/summary/report materialization
│   └── pipeline_events.py             # pipeline tables + run/event helpers
├── scripts/
│   ├── start_api_server.py
│   ├── start_scheduler_worker_service.py
│   ├── start_onfly_scheduler_service.py
│   └── start_store_auto_sync_service.py
├── deploy/
│   └── cloud/
├── docs/
└── data/
```

---

## Pipeline Flow

```text
Source folder / Drive folder
    ↓ list + delta/version skip
Download bytes in memory
    ↓
YOLO relevance gate
    ↓
Smart frame sampling (skip repetitive near-identical consecutive frames)
    ↓
GPT only for remaining relevant anchor frames
    ↓
Walk-in session reconstruction
    ↓
SQLite report materialization + PostgreSQL sync
    ↓
React dashboard / CSV exports
```

Key cost controls now live:
- YOLO relevance gate
- exact SHA-256 duplicate reuse
- store-hours filter
- camera exclusion
- OpenAI batch mode
- smart frame sampling

---

## Source-of-Truth Documents

Keep these current:
- `README.md`
- `docs/deployment/cost-optimization-plan.md`
- `docs/deployment/IRIS-Server-Requirement-150-Stores.md`
- `docs/process/onfly_pipeline_logic.md`
- `deploy/cloud/README.md`
- `CHANGE_LEDGER.md`
- `docs/AI_HANDOVER_STORAGE.md`

---

## Notes

- Images are processed in-memory where possible.
- GPT time values do **not** invent clock times; final entry/exit timing comes from filename timestamps.
- Manual sync can use parent folder, child date folder, or raw folder ID.
- Delta skip remains default; force rerun overwrites prior results for the chosen path.

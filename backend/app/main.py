from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_jobs import router as jobs_router
from backend.app.api.routes_runs import router as runs_router

app = FastAPI(title="IRIS API", version="1.0.0", docs_url="/api/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8766", "http://127.0.0.1:8766"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(runs_router, prefix="/api")

# Serve React build from /app/backend/app/static
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
if any(_static_dir.iterdir()) if _static_dir.exists() else False:
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")

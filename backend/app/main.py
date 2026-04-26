from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_jobs import router as jobs_router
from backend.app.api.routes_runs import router as runs_router
from backend.app.api.routes_dashboard import router as dashboard_router
from backend.app.api.routes_detail import router as detail_router

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
app.include_router(dashboard_router, prefix="/api/dashboard")
app.include_router(detail_router, prefix="/api/detail")

# Serve React build from /app/backend/app/static with SPA fallback
_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
_assets_dir = _static_dir / "assets"
_index_file = _static_dir / "index.html"

if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

if _index_file.exists():
    @app.get("/", include_in_schema=False)
    def spa_index() -> FileResponse:
        return FileResponse(_index_file)


    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")

        requested = (_static_dir / full_path).resolve()
        try:
            requested.relative_to(_static_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc

        if requested.is_file():
            return FileResponse(requested)
        return FileResponse(_index_file)

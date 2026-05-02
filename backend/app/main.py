from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.api.routes_admin import router as admin_router
from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_dashboard import router as dashboard_router
from backend.app.api.routes_detail import router as detail_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_jobs import router as jobs_router
from backend.app.api.routes_onfly import auto_sync_loop, router as onfly_router
from backend.app.api.routes_qa import router as qa_router
from backend.app.api.routes_reports import router as reports_router
from backend.app.api.routes_runs import router as runs_router
from backend.app.config import get_settings
from backend.app.limiter import limiter

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="IRIS API", version="1.0.0", docs_url="/api/docs", redoc_url=None)

# Attach limiter state and its 429 handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.on_event("startup")
async def startup_checks() -> None:
    cfg = get_settings()
    if cfg.jwt_is_insecure:
        logger.warning(
            "JWT_SECRET is using the insecure default value. "
            "Set the JWT_SECRET environment variable before going to production."
        )
    # Clean up any zombie runs from a previous process that died mid-run
    _cleanup_zombie_runs(cfg)
    await _run_migrations()
    asyncio.create_task(auto_sync_loop())


async def _run_migrations() -> None:
    """Apply additive schema migrations that are safe to run on every startup."""
    from backend.app.db.session import engine
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hint VARCHAR(255) DEFAULT ''",
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as exc:
                logger.warning("Migration skipped: %s — %s", sql[:60], exc)


def _cleanup_zombie_runs(cfg) -> None:
    import sqlite3
    from datetime import datetime, timezone
    db_path = cfg.db_path_obj
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        now = datetime.now(timezone.utc).isoformat()
        result = conn.execute(
            """
            UPDATE onfly_pipeline_runs
            SET status='abandoned',
                error_message='Process died — API restarted while run was active',
                ended_at=?, updated_at=?
            WHERE status='running'
              AND last_heartbeat_at < datetime('now', '-5 minutes')
            """,
            (now, now),
        )
        count = result.rowcount
        conn.commit()
        conn.close()
        if count:
            logger.info("Startup cleanup: marked %d zombie run(s) as abandoned", count)
    except Exception as exc:
        logger.warning("Startup zombie cleanup failed: %s", exc)


app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api/dashboard")
app.include_router(detail_router, prefix="/api/detail")
app.include_router(admin_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(onfly_router, prefix="/api")
app.include_router(qa_router, prefix="/api")

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

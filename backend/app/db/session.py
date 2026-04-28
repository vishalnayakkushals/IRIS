from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.config import get_settings

settings = get_settings()

# Async engine for FastAPI endpoints
engine = create_async_engine(
    settings.postgres_url,
    echo=False,
    pool_size=20,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
    execution_options={"isolation_level": "READ COMMITTED"},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Sync engine for background thread pipeline writes (no asyncio event loop)
_sync_url = settings.postgres_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
engine_sync = create_engine(
    _sync_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=3600,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from backend.app.config import get_settings

settings = get_settings()

# Production pool: 150 stores × 8-10 cameras, concurrent pipeline writes
# pool_size=20 per uvicorn worker, max_overflow=20 burst headroom
# pool_pre_ping recycles stale connections after network blips
# pool_recycle=3600 prevents stale connections behind LB/PgBouncer
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

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

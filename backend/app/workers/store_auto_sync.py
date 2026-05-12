from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from backend.app.api.onfly_runtime import _active_runs, _executor, _make_run_id, _now, _run_pipeline_sync, _set_active_run
from backend.app.db.canonical_metadata import store_sync_state, stores
from backend.app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def check_and_trigger_auto_syncs() -> None:
    from backend.app.config import get_settings

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                stores.c.store_id,
                stores.c.drive_folder_url,
                stores.c.sync_interval_hours,
                stores.c.gpt_enabled,
            ).where(
                stores.c.sync_enabled.is_(True),
                stores.c.drive_folder_url.isnot(None),
                stores.c.drive_folder_url != "",
            )
        )
        enabled_stores = [dict(row) for row in result.mappings().all()]

    now = _now()
    for store in enabled_stores:
        store_id = store["store_id"]
        if store_id in _active_runs:
            continue
        interval_hours = int(store.get("sync_interval_hours") or 1)
        async with AsyncSessionLocal() as session:
            sync_row = await session.execute(select(store_sync_state.c.last_sync_at).where(store_sync_state.c.store_id == store_id))
            sync_state = sync_row.first()
        if sync_state and sync_state[0]:
            last_sync = sync_state[0]
            if last_sync.tzinfo is None:
                from datetime import timezone as _tz

                last_sync = last_sync.replace(tzinfo=_tz.utc)
            elapsed = now - last_sync
            if elapsed.total_seconds() < interval_hours * 3600:
                continue
        run_id = _make_run_id(store_id)
        _set_active_run(store_id, run_id)
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            _executor,
            _run_pipeline_sync,
            run_id,
            store_id,
            store["drive_folder_url"],
            "scheduler",
            bool(store.get("gpt_enabled", True)),
            False,
            get_settings().max_images,
            False,
        )
        logger.info("Auto-sync triggered for %s (run_id=%s)", store_id, run_id)


async def auto_sync_loop(poll_seconds: int = 60) -> None:
    logger.info("Store auto-sync worker started (poll=%ss)", poll_seconds)
    while True:
        await asyncio.sleep(max(5, int(poll_seconds)))
        try:
            await check_and_trigger_auto_syncs()
        except Exception as exc:
            logger.exception("Store auto-sync loop error: %s", exc)

"""
Morning batch retrieval — run at 6 AM via Windows Task Scheduler.
Polls all pending OpenAI batches, applies completed results to SQLite + PostgreSQL.

Usage:
    python scripts/batch_retrieve.py [--store STORE_ID]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(repo_root / "data" / "batch_retrieve.log", mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("batch_retrieve")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve OpenAI batch results")
    parser.add_argument("--store", default=None, help="Limit to a specific store_id")
    args = parser.parse_args()

    # Load environment from .env if present
    env_file = repo_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_api_key:
        log.error("OPENAI_API_KEY not set — cannot retrieve batch results")
        sys.exit(1)

    db_candidates = [
        repo_root / "data" / "iris.db",
        repo_root / "data" / "store_registry.db",
    ]
    db_path = next((p for p in db_candidates if p.exists()), None)
    if db_path is None:
        log.error("SQLite DB not found in data/iris.db or data/store_registry.db")
        sys.exit(1)

    from iris.gpt_batch import (
        apply_batch_results,
        check_batch_status,
        get_pending_batches,
        init_batch_tables,
    )

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        init_batch_tables(conn)
        batches = get_pending_batches(conn, store_id=args.store)
        if not batches:
            log.info("No pending batches found%s", f" for store {args.store}" if args.store else "")
            return

        log.info("Found %d pending batch(es) to check", len(batches))
        applied = 0
        for b in batches:
            batch_db_id = b["batch_db_id"]
            store_id = b["store_id"]
            log.info("Checking batch %s (store=%s, images=%s)", batch_db_id, store_id, b.get("image_count", "?"))
            try:
                status_info = check_batch_status(batch_db_id, openai_api_key, conn)
                openai_status = status_info.get("openai_status", "unknown")
                log.info("  OpenAI status: %s", openai_status)

                if openai_status == "completed" and not b.get("results_applied"):
                    result = apply_batch_results(batch_db_id, openai_api_key, conn)
                    conn.commit()
                    log.info(
                        "  Applied: %d succeeded, %d failed, %d errors",
                        result.get("succeeded", 0),
                        result.get("failed", 0),
                        result.get("errors", 0),
                    )
                    applied += 1
                elif openai_status in {"failed", "expired", "cancelled"}:
                    log.warning("  Batch %s is in terminal state: %s", batch_db_id, openai_status)
                elif b.get("results_applied"):
                    log.info("  Already applied — skipping")
                else:
                    log.info("  Not yet complete (status=%s) — will retry later", openai_status)
            except Exception as exc:
                log.exception("  Error processing batch %s: %s", batch_db_id, exc)

        log.info("Done. Applied %d batch(es).", applied)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

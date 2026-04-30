from __future__ import annotations

from pathlib import Path

from backend.app.api.routes_onfly import (
    _load_live_progress_from_sqlite,
    _mark_stale_run_if_needed,
    _normalize_manual_source,
)
from iris.onfly_pipeline import init_onfly_tables


def test_normalize_manual_source_accepts_drive_folder_id() -> None:
    folder_id = "1zq08f-R00CNLtWdy2ghuSSYoU8SzMZuj"
    assert _normalize_manual_source(folder_id) == f"https://drive.google.com/drive/folders/{folder_id}"


def test_live_progress_prefers_active_run_id(tmp_path: Path) -> None:
    db_path = tmp_path / "store_registry.db"
    init_onfly_tables(db_path)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        INSERT INTO onfly_pipeline_runs(
            run_id,store_id,source_type,source_uri,status,current_stage,
            images_discovered,images_processed,images_relevant,images_skipped,
            gpt_success_count,gpt_failed_count,started_at,last_heartbeat_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "older_done",
            "BLRRRN",
            "gdrive",
            "parent",
            "done",
            "REPORT_WRITER",
            100,
            100,
            40,
            0,
            40,
            0,
            "2026-04-30T04:00:00+00:00",
            "2026-04-30T04:10:00+00:00",
            "2026-04-30T04:00:00+00:00",
            "2026-04-30T04:10:00+00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO onfly_pipeline_runs(
            run_id,store_id,source_type,source_uri,status,current_stage,
            images_discovered,images_processed,images_relevant,images_skipped,
            gpt_success_count,gpt_failed_count,started_at,last_heartbeat_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "active_run",
            "BLRRRN",
            "gdrive",
            "child",
            "running",
            "YOLO",
            3273,
            3222,
            670,
            51,
            0,
            0,
            "2026-04-30T05:00:00+00:00",
            "2026-04-30T05:01:00+00:00",
            "2026-04-30T05:00:00+00:00",
            "2026-04-30T05:01:00+00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO onfly_task_queue(
            task_key,run_id,store_id,image_id,stage,status,attempts,last_error,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "pending-1",
            "active_run",
            "BLRRRN",
            "gdrive:test-image",
            "GPT",
            "pending",
            0,
            "",
            "2026-04-30T05:01:00+00:00",
            "2026-04-30T05:01:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    progress = _load_live_progress_from_sqlite(db_path, "BLRRRN", "active_run")

    assert progress is not None
    assert progress["run_id"] == "active_run"
    assert progress["status"] == "running"
    assert progress["images_discovered"] == 3273
    assert progress["images_processed"] == 3222
    assert progress["pending_tasks"] == 1


def test_mark_stale_run_transitions_running_row_to_failed(tmp_path: Path) -> None:
    db_path = tmp_path / "store_registry.db"
    init_onfly_tables(db_path)
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO onfly_pipeline_runs(
            run_id,store_id,source_type,source_uri,status,current_stage,
            images_discovered,images_processed,images_relevant,images_skipped,
            gpt_success_count,gpt_failed_count,started_at,last_heartbeat_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "stale_run",
            "BLRRRN",
            "gdrive",
            "parent",
            "running",
            "DOWNLOAD",
            5000,
            717,
            40,
            0,
            0,
            0,
            "2026-04-30T03:00:00+00:00",
            "2026-04-30T03:00:00+00:00",
            "2026-04-30T03:00:00+00:00",
            "2026-04-30T03:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    progress = _mark_stale_run_if_needed(db_path, "BLRRRN", "stale_run")

    assert progress is not None
    assert progress["run_id"] == "stale_run"
    assert progress["status"] == "failed"
    assert "Marked stale" in progress["error"]

from __future__ import annotations

import importlib.util
from pathlib import Path

from iris.store_registry import init_db, upsert_app_settings, upsert_store


def _load_scheduler_module():
    root = Path(__file__).resolve().parents[1]
    mod_path = root / "scripts" / "onfly_scheduler.py"
    spec = importlib.util.spec_from_file_location("test_onfly_scheduler_module", mod_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_onfly_scheduler_reads_store_source_and_timing_from_db(tmp_path: Path) -> None:
    db_path = tmp_path / "store_registry.db"
    init_db(db_path)
    upsert_store(
        db_path=db_path,
        store_id="BLRRRN",
        store_name="BLR RR Nagar",
        email="blrrrn@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/mapped-folder",
    )
    upsert_app_settings(
        db_path,
        {
            "cfg_onfly_scheduler_enabled": "1",
            "cfg_onfly_scheduler_store_id": "BLRRRN",
            "cfg_onfly_scheduler_hourly_minutes": "180",
            "cfg_onfly_scheduler_nightly_run_at": "04:30",
            "cfg_onfly_scheduler_tz": "Asia/Kolkata",
            "cfg_onfly_scheduler_max_images": "0",
            "cfg_onfly_scheduler_enable_gpt": "0",
            "cfg_onfly_scheduler_conf": "0.22",
            "cfg_onfly_scheduler_detector": "yolo",
            "cfg_onfly_scheduler_pipeline_version": "pipe_v2",
            "cfg_onfly_scheduler_yolo_version": "yolo_v5",
            "cfg_onfly_scheduler_gpt_version": "gpt_v9",
            "cfg_onfly_scheduler_allow_fallback": "1",
        },
    )
    scheduler = _load_scheduler_module()
    cfg = scheduler._load_onfly_scheduler_config(db_path)

    assert cfg["enabled"] is True
    assert cfg["store_id"] == "BLRRRN"
    assert cfg["source_url"] == "https://drive.google.com/drive/folders/mapped-folder"
    assert cfg["hourly_minutes"] == 180
    assert cfg["nightly_at"] == "04:30"
    assert cfg["tz_name"] == "Asia/Kolkata"
    assert cfg["max_images"] == 0
    assert cfg["enable_gpt"] is False
    assert cfg["conf"] == "0.22"
    assert cfg["detector"] == "yolo"
    assert cfg["pipeline_version"] == "pipe_v2"
    assert cfg["yolo_version"] == "yolo_v5"
    assert cfg["gpt_version"] == "gpt_v9"
    assert cfg["allow_fallback"] is True
    out_dir = Path(cfg["out_dir"])
    assert out_dir.parts[-3:] == ("exports", "current", "onfly")


def test_onfly_scheduler_falls_back_to_saved_source_when_store_mapping_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "store_registry.db"
    init_db(db_path)
    upsert_app_settings(
        db_path,
        {
            "cfg_onfly_scheduler_store_id": "BLRRRN",
            "cfg_onfly_scheduler_source_url": "https://drive.google.com/drive/folders/fallback-folder",
        },
    )

    scheduler = _load_scheduler_module()
    cfg = scheduler._load_onfly_scheduler_config(db_path)

    assert cfg["source_url"] == "https://drive.google.com/drive/folders/fallback-folder"


def test_onfly_scheduler_collects_all_mapped_store_sources_for_nightly(tmp_path: Path) -> None:
    db_path = tmp_path / "store_registry.db"
    init_db(db_path)
    upsert_store(
        db_path=db_path,
        store_id="BLRRRN",
        store_name="BLR - RR NAGAR",
        email="blrrrn@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/rrn-folder",
    )
    upsert_store(
        db_path=db_path,
        store_id="BLRJAY",
        store_name="BLR - JAYNAGAR",
        email="blrjay@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/jay-folder",
    )
    upsert_store(
        db_path=db_path,
        store_id="BLRMAL",
        store_name="BLR - MALLESWARAM",
        email="blrmal@example.com",
        drive_folder_url="",
    )

    scheduler = _load_scheduler_module()
    rows = scheduler._scheduled_store_rows(db_path)

    assert rows == [
        {"store_id": "BLRJAY", "source_url": "https://drive.google.com/drive/folders/jay-folder"},
        {"store_id": "BLRRRN", "source_url": "https://drive.google.com/drive/folders/rrn-folder"},
    ]


def test_onfly_scheduler_parses_summary_and_accelerates_quota_retry() -> None:
    scheduler = _load_scheduler_module()
    parsed = scheduler._parse_run_summary(
        """
        {
          "run_id": "x",
          "status": "partial",
          "gpt_retry_pending": 3
        }
        """
    )

    assert parsed["status"] == "partial"
    assert parsed["gpt_retry_pending"] == 3

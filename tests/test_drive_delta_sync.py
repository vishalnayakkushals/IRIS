from __future__ import annotations

from pathlib import Path
import sqlite3

from iris.drive_delta_sync import run_delta_sync_for_store, _date_bucket_from_relative_path
from iris.store_registry import _upsert_source_index_rows, init_db, upsert_store


def test_date_bucket_from_relative_path() -> None:
    assert _date_bucket_from_relative_path("2026-03-19/09-57-27_D03-1.jpg") == "2026-03-19"
    assert _date_bucket_from_relative_path("misc/09-57-27_D03-1.jpg") == ""
    assert _date_bucket_from_relative_path("") == ""


def test_latest_delta_sync_marks_missing_and_downloads_new(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "registry.db"
    data_root = tmp_path / "stores"
    init_db(db)
    upsert_store(
        db_path=db,
        store_id="BLRJAY",
        store_name="BLR - JAYNAGAR",
        email="jaynagar.blr@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/root123",
    )

    # Existing active file in latest-date scope which will be missing in fresh listing.
    existing_local = data_root / "BLRJAY" / "2026-03-19" / "old.jpg"
    existing_local.parent.mkdir(parents=True, exist_ok=True)
    existing_local.write_bytes(b"abc")
    now = "2026-03-19T00:00:00+00:00"
    _upsert_source_index_rows(
        db_path=db,
        rows=[
            (
                "BLRJAY",
                "gdrive",
                "gone1",
                "old.jpg",
                "2026-03-19/old.jpg",
                "https://drive.google.com/file/d/gone1/view",
                str(existing_local),
                ".jpg",
                existing_local.stat().st_size,
                1,
                now,
                now,
                now,
            )
        ],
    )

    monkeypatch.setattr(
        "iris.drive_delta_sync._list_drive_date_subfolders",
        lambda parent_folder_id, api_key: [("2026-03-18", "d18"), ("2026-03-19", "d19")],
    )

    def fake_list_recursive(folder_id: str, api_key: str):
        assert folder_id == "d19"
        return [{"id": "new1", "name": "new.jpg", "relative_path": "new.jpg", "drive_web_link": "https://drive.google.com/file/d/new1/view"}]

    monkeypatch.setattr("iris.drive_delta_sync._drive_api_list_files_recursive", fake_list_recursive)

    def fake_download(file_items, target_dir, api_key):
        rows = []
        for item in file_items:
            dest = target_dir / "2026-03-19" / "new.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"new")
            rows.append(
                {
                    "file_id": "new1",
                    "name": "new.jpg",
                    "relative_path": "2026-03-19/new.jpg",
                    "drive_web_link": "https://drive.google.com/file/d/new1/view",
                    "local_path": str(dest),
                }
            )
        return len(rows), rows

    monkeypatch.setattr("iris.drive_delta_sync._drive_api_download_files", fake_download)

    result = run_delta_sync_for_store(
        db_path=db,
        data_root=data_root,
        store_id="BLRJAY",
        api_key="k",
        workers=3,
        remove_local_deleted_files=False,
    )

    assert result.mode == "latest_delta"
    assert result.scope_date == "2026-03-19"
    assert result.downloaded_new == 1
    assert result.marked_deleted == 1
    assert existing_local.exists()

    conn = sqlite3.connect(db)
    try:
        gone_row = conn.execute(
            "SELECT is_present FROM store_source_file_index WHERE store_id='BLRJAY' AND source_provider='gdrive' AND source_file_id='gone1'"
        ).fetchone()
        new_row = conn.execute(
            "SELECT is_present FROM store_source_file_index WHERE store_id='BLRJAY' AND source_provider='gdrive' AND source_file_id='new1'"
        ).fetchone()
        assert gone_row == (0,)
        assert new_row == (1,)
    finally:
        conn.close()


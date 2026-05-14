from __future__ import annotations

import csv
import sqlite3

from iris.relevant_review_table import export_relevant_review_table, relevant_review_table_path


def _create_state_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE onfly_image_state (
            store_id TEXT,
            date_source TEXT,
            date_display TEXT,
            camera_id TEXT,
            timestamp_hint TEXT,
            image_name TEXT,
            relative_path TEXT,
            source_provider TEXT,
            source_item_id TEXT,
            source_url TEXT,
            image_id TEXT,
            yolo_status TEXT,
            yolo_relevant INTEGER,
            person_count INTEGER,
            yolo_conf REAL,
            yolo_error TEXT,
            gpt_status TEXT,
            gpt_customer_count INTEGER,
            gpt_staff_count INTEGER,
            gpt_conversions INTEGER,
            gpt_bounce INTEGER,
            gpt_error TEXT,
            last_run_id TEXT,
            last_seen_at TEXT
        )
        """
    )


def test_export_relevant_review_table_filters_relevant_rows(tmp_path):
    db_path = tmp_path / "store_registry.db"
    conn = sqlite3.connect(db_path)
    _create_state_table(conn)
    conn.executemany(
        """
        INSERT INTO onfly_image_state VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            (
                "BLRRRN",
                "2026-05-10",
                "10-05-2026",
                "D01",
                "15-41-36",
                "15-41-36_D01-1.jpg",
                "2026-05-10/15-41-36_D01-1.jpg",
                "gdrive",
                "drive-file-1",
                "https://drive.google.com/file/d/drive-file-1/view",
                "img-1",
                "done",
                1,
                2,
                0.72,
                "",
                "disabled",
                0,
                0,
                0,
                0,
                "",
                "run-1",
                "2026-05-14T10:00:00",
            ),
            (
                "BLRRRN",
                "2026-05-10",
                "10-05-2026",
                "D02",
                "15-41-37",
                "15-41-37_D02-1.jpg",
                "2026-05-10/15-41-37_D02-1.jpg",
                "gdrive",
                "drive-file-2",
                "https://drive.google.com/file/d/drive-file-2/view",
                "img-2",
                "done",
                0,
                0,
                0.0,
                "",
                "",
                0,
                0,
                0,
                0,
                "",
                "run-1",
                "2026-05-14T10:00:01",
            ),
        ],
    )
    conn.commit()
    conn.close()

    result = export_relevant_review_table(db_path, tmp_path / "exports", "BLRRRN", "10-05-2026")
    assert result["rows"] == 1
    assert result["filename"] == "yolo_relevant_review_table_10-05-2026.csv"

    with open(result["output_path"], newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["image_name"] == "15-41-36_D01-1.jpg"
    assert rows[0]["drive_link"] == "https://drive.google.com/file/d/drive-file-1/view"
    assert rows[0]["review_status"] == ""


def test_relevant_review_table_path_uses_all_dates_for_blank_filter(tmp_path):
    output = relevant_review_table_path(tmp_path, "BLRRRN", "")
    assert output.name == "yolo_relevant_review_table_all_dates.csv"

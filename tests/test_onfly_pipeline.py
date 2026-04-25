from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from iris.onfly_pipeline import LocalClient, OnFlyConfig, _connect, _now, init_onfly_tables, run_onfly_pipeline


class _FakeDetector:
    def detect(self, image_path: Path):
        from iris.iris_analysis import DetectionResult

        return DetectionResult(
            person_count=1,
            max_person_conf=0.91,
            detection_error="",
            person_centroids=[(0.5, 0.5)],
            person_boxes=[(0.2, 0.1, 0.8, 0.9)],
            person_confidences=[0.91],
            bag_count=0,
        )


def test_onfly_runs_gpt_when_current_yolo_turns_stale_irrelevant_row_relevant(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    image_path = source_dir / "2026-04-23_09-30-19_D01-1.jpg"
    Image.new("RGB", (32, 32), color="white").save(image_path)

    db_path = tmp_path / "store_registry.db"
    out_dir = tmp_path / "exports"
    init_onfly_tables(db_path)

    item = LocalClient(str(source_dir)).list_images(0)[0]
    conn = _connect(db_path)
    try:
        now = _now()
        conn.execute(
            """
            INSERT INTO onfly_image_state(
                store_id,image_id,source_provider,source_uri,source_item_id,source_url,image_name,
                relative_path,date_source,date_display,camera_id,timestamp_hint,discovered_at,last_seen_at,
                pipeline_version,yolo_version,gpt_version,yolo_status,yolo_relevant,person_count,yolo_conf,yolo_error,
                gpt_status,gpt_customer_count,gpt_staff_count,gpt_conversions,gpt_bounce,gpt_result_json,gpt_error,last_run_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "TEST_STORE_D07",
                item.image_id,
                item.source_provider,
                str(source_dir),
                item.source_item_id,
                item.source_url,
                item.image_name,
                item.relative_path,
                item.date_source,
                item.date_display,
                item.camera_id,
                item.timestamp_hint,
                now,
                now,
                "onfly_v1",
                "old_yolo_version",
                "onfly_v1",
                "done",
                0,
                0,
                0.0,
                "",
                "done",
                0,
                0,
                0,
                0,
                "{}",
                "",
                "",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr("iris.onfly_pipeline.build_detector", lambda *args, **kwargs: (_FakeDetector(), ""))
    monkeypatch.setattr(
        "iris.onfly_pipeline._openai_eval",
        lambda cfg, image_bytes, image_name: {
            "customer_count": 1,
            "staff_count": 0,
            "conversions": 0,
            "bounce": 0,
            "notes": "ok",
            "walkins": [
                {
                    "Date": "23-04-2026",
                    "Walk-in ID": "20260423093019W01",
                    "Group ID": "20260423093019G01",
                    "Role": "Customer",
                    "Entry Time": "NA",
                    "Exit Time": "NA",
                    "Time Spent (mins)": "NA",
                    "Session Status": "OPEN",
                    "Entry Type": "Walk-in",
                    "Gender": "Male",
                    "Age Band": "25 - 34",
                    "Attire / Visual Marker": "Dark top",
                    "Primary Clothing": "Casual",
                    "Jewellery Load": "Minimal",
                    "Bag Type": "None",
                    "Primary Clothing Style Archetype": "Casual",
                    "Engagement Type": "Browsing",
                    "Engagement Depth": "Low",
                    "Purchase Signal (Bag)": "NA",
                    "Included in Analytics": "Yes",
                    "Event Type": "ENTRY",
                    "Direction Confidence": "High",
                    "Match Fingerprint": "fp1",
                }
            ],
        },
    )

    summary = run_onfly_pipeline(
        OnFlyConfig(
            store_id="TEST_STORE_D07",
            source_uri=str(source_dir),
            db_path=db_path,
            out_dir=out_dir,
            detector_type="yolo",
            conf_threshold=0.18,
            max_images=0,
            gpt_enabled=True,
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            pipeline_version="onfly_v1",
            yolo_version="new_yolo_version",
            gpt_version="onfly_v1",
            force_reprocess=False,
            allow_detector_fallback=True,
            run_mode="test",
        )
    )

    assert summary["yolo_relevant"] == 1
    assert summary["gpt_done"] == 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        state = conn.execute(
            "SELECT yolo_relevant, gpt_status, gpt_customer_count FROM onfly_image_state WHERE store_id=? AND image_id=?",
            ("TEST_STORE_D07", item.image_id),
        ).fetchone()
        assert state is not None
        assert int(state["yolo_relevant"]) == 1
        assert str(state["gpt_status"]) == "done"
        assert int(state["gpt_customer_count"]) == 1

        walkin_count = conn.execute(
            "SELECT COUNT(*) FROM onfly_walkin_sessions WHERE run_id=?",
            (summary["run_id"],),
        ).fetchone()[0]
        assert int(walkin_count) == 1
    finally:
        conn.close()


def test_onfly_marks_quota_errors_for_retry_without_changing_yolo_role(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for name in ["2026-04-23_09-30-19_D01-1.jpg", "2026-04-23_09-31-20_D01-2.jpg"]:
        Image.new("RGB", (32, 32), color="white").save(source_dir / name)

    db_path = tmp_path / "store_registry.db"
    out_dir = tmp_path / "exports"
    init_onfly_tables(db_path)

    monkeypatch.setattr("iris.onfly_pipeline.build_detector", lambda *args, **kwargs: (_FakeDetector(), ""))

    calls = {"count": 0}

    def _quota_raise(cfg, image_bytes, image_name):
        calls["count"] += 1
        raise RuntimeError('OpenAI error 429: {"error":{"code":"insufficient_quota"}}')

    monkeypatch.setattr("iris.onfly_pipeline._openai_eval", _quota_raise)

    summary = run_onfly_pipeline(
        OnFlyConfig(
            store_id="TEST_STORE_D07",
            source_uri=str(source_dir),
            db_path=db_path,
            out_dir=out_dir,
            detector_type="yolo",
            conf_threshold=0.18,
            max_images=0,
            gpt_enabled=True,
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            pipeline_version="onfly_v1",
            yolo_version="onfly_v1",
            gpt_version="onfly_v2",
            force_reprocess=False,
            allow_detector_fallback=True,
            run_mode="test",
        )
    )

    assert summary["yolo_relevant"] == 2
    assert summary["gpt_done"] == 0
    assert summary["gpt_retry_pending"] == 2
    assert summary["status"] == "partial"
    assert calls["count"] == 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        state = conn.execute(
            "SELECT COUNT(*) FROM onfly_image_state WHERE store_id=? AND yolo_status='done' AND yolo_relevant=1 AND gpt_status='quota_pending_retry'",
            ("TEST_STORE_D07",),
        ).fetchone()
        assert state is not None
        assert int(state[0]) == 2

        queue_row = conn.execute(
            "SELECT COUNT(*) FROM onfly_task_queue WHERE stage='chatgpt' AND status='waiting_quota'"
        ).fetchone()
        assert queue_row is not None
        assert int(queue_row[0]) == 2

        run_row = conn.execute(
            "SELECT status, retry_status FROM onfly_pipeline_runs WHERE run_id=?",
            (summary["run_id"],),
        ).fetchone()
        assert run_row is not None
        assert str(run_row["status"]) == "partial"
        assert "queued for retry" in str(run_row["retry_status"])
    finally:
        conn.close()

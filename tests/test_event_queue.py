from __future__ import annotations

from pathlib import Path

from iris.event_queue import JsonlEventQueue, new_frame_event


def test_jsonl_event_queue_roundtrip(tmp_path: Path) -> None:
    q = JsonlEventQueue(tmp_path / "q.jsonl")
    e1 = new_frame_event("S1", "D01", "/tmp/a.jpg")
    e2 = new_frame_event("S1", "D02", "/tmp/b.jpg")
    q.publish(e1)
    q.publish(e2)

    got1 = q.pull()
    got2 = q.pull()
    got3 = q.pull()

    assert got1 is not None and got1.camera_id == "D01"
    assert got2 is not None and got2.camera_id == "D02"
    assert got3 is None

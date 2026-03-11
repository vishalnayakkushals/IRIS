from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import Any


@dataclass
class FrameEvent:
    event_id: str
    store_id: str
    camera_id: str
    image_path: str
    ts: str
    payload: dict[str, Any]


class EventQueue:
    def publish(self, event: FrameEvent) -> None: ...
    def pull(self, timeout_sec: float = 0.2) -> FrameEvent | None: ...


class InMemoryEventQueue(EventQueue):
    def __init__(self) -> None:
        self._q: Queue[FrameEvent] = Queue()

    def publish(self, event: FrameEvent) -> None:
        self._q.put(event)

    def pull(self, timeout_sec: float = 0.2) -> FrameEvent | None:
        try:
            return self._q.get(timeout=timeout_sec)
        except Empty:
            return None


class JsonlEventQueue(EventQueue):
    """Lightweight append/pull queue for local async workers.

    Use as MVP queue abstraction before Kafka/PubSub.
    """

    def __init__(self, queue_file: Path) -> None:
        self.queue_file = queue_file
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.queue_file.exists():
            self.queue_file.write_text("")

    def publish(self, event: FrameEvent) -> None:
        with self._lock:
            with self.queue_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")

    def pull(self, timeout_sec: float = 0.2) -> FrameEvent | None:  # noqa: ARG002
        with self._lock:
            lines = self.queue_file.read_text(encoding="utf-8").splitlines()
            if not lines:
                return None
            first = lines[0]
            rest = lines[1:]
            self.queue_file.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")
        data = json.loads(first)
        return FrameEvent(**data)


def new_frame_event(store_id: str, camera_id: str, image_path: str, payload: dict[str, Any] | None = None) -> FrameEvent:
    now = datetime.now(timezone.utc)
    return FrameEvent(
        event_id=f"evt_{now.timestamp():.6f}".replace(".", ""),
        store_id=store_id,
        camera_id=camera_id,
        image_path=image_path,
        ts=now.isoformat(),
        payload=payload or {},
    )

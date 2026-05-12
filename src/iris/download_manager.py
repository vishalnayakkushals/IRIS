from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import tempfile
from typing import Any

from .gpt_runtime import parse_filename_time
from .source_clients import SourceImage


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_gpt_quota_error(message: str) -> bool:
    text = str(message or "").lower()
    return any(token in text for token in ["insufficient_quota", "quota", "rate limit", "429", "billing"])


def yolo_detect_direct(detector: Any, image_bytes: bytes, image_name: str) -> tuple[int, float, str]:
    if hasattr(detector, "detect_bytes"):
        result = detector.detect_bytes(image_bytes)
        return int(result.person_count or 0), float(result.max_person_conf or 0.0), str(result.detection_error or "")
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(image_name).suffix or ".jpg") as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        result = detector.detect(tmp_path)
        return int(result.person_count or 0), float(result.max_person_conf or 0.0), str(result.detection_error or "")
    finally:
        tmp_path.unlink(missing_ok=True)


def yolo_detect_full_result(detector: Any, image_bytes: bytes, image_name: str) -> Any:
    if hasattr(detector, "detect_bytes"):
        return detector.detect_bytes(image_bytes)
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(image_name).suffix or ".jpg") as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        return detector.detect(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


@dataclass(frozen=True)
class FrameSampleAnchor:
    image_id: str
    image_name: str
    camera_id: str
    business_date: str
    event_seconds: int
    person_count: int
    boxes: tuple[tuple[float, float, float, float], ...]


def _event_seconds(item: SourceImage) -> int:
    candidate = parse_filename_time(item.image_name) or str(item.timestamp_hint or "").split(" ")[-1].strip()
    try:
        hh, mm, ss = [int(part) for part in candidate.split(":")]
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return -1


def _normalized_boxes(boxes: list[tuple[float, float, float, float]]) -> tuple[tuple[float, float, float, float], ...]:
    rounded = [tuple(round(float(v), 4) for v in box) for box in boxes]
    rounded.sort(key=lambda box: (box[0], box[1], box[2], box[3]))
    return tuple(rounded)


def _box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def _centroid_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    acx, acy = (a[0] + a[2]) / 2.0, (a[1] + a[3]) / 2.0
    bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
    return math.sqrt((acx - bcx) ** 2 + (acy - bcy) ** 2)


def build_frame_anchor(item: SourceImage, person_boxes: list[tuple[float, float, float, float]], person_count: int) -> FrameSampleAnchor | None:
    if person_count <= 0 or not person_boxes:
        return None
    event_seconds = _event_seconds(item)
    return FrameSampleAnchor(
        image_id=item.image_id,
        image_name=item.image_name,
        camera_id=str(item.camera_id or ""),
        business_date=str(item.date_display or item.date_source or ""),
        event_seconds=event_seconds,
        person_count=int(person_count),
        boxes=_normalized_boxes(person_boxes),
    )


def evaluate_frame_sampling(anchor: FrameSampleAnchor | None, item: SourceImage, person_boxes: list[tuple[float, float, float, float]], person_count: int) -> tuple[bool, str, str, FrameSampleAnchor | None]:
    current = build_frame_anchor(item, person_boxes, person_count)
    if anchor is None or current is None:
        return False, "anchor_missing", "", current
    if anchor.camera_id != current.camera_id or anchor.business_date != current.business_date:
        return False, "camera_or_date_changed", "", current
    if anchor.person_count != current.person_count:
        return False, "person_count_changed", "", current
    if anchor.event_seconds >= 0 and current.event_seconds >= 0 and abs(current.event_seconds - anchor.event_seconds) > 180:
        return False, "time_gap_gt_180s", "", current
    if len(anchor.boxes) != len(current.boxes):
        return False, "box_count_changed", "", current
    ious = [_box_iou(a, b) for a, b in zip(anchor.boxes, current.boxes)]
    centroid_deltas = [_centroid_distance(a, b) for a, b in zip(anchor.boxes, current.boxes)]
    avg_iou = sum(ious) / max(1, len(ious))
    max_centroid_delta = max(centroid_deltas) if centroid_deltas else 1.0
    signature = f"iou={avg_iou:.3f}|centroid={max_centroid_delta:.3f}|count={current.person_count}"
    should_skip = avg_iou >= 0.82 or (avg_iou >= 0.72 and max_centroid_delta <= 0.05)
    return should_skip, ("smart_sampled" if should_skip else "motion_changed"), signature, current

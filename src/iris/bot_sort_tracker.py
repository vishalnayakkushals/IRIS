"""Lightweight IoU-based multi-object tracker (BoT-SORT compatible API).

No external dependencies beyond standard library and numpy.
Implements Hungarian-style greedy IoU matching across frames, sufficient for
the IRIS retail analytics use-case where frame rate is low (~1-5 fps equivalent).

Track lifecycle:
  NEW → CONFIRMED (after min_hits) → LOST (after max_age missed frames) → DEAD
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Track:
    track_id: str
    local_id: int
    bbox: tuple[float, float, float, float]  # x1,y1,x2,y2 normalised 0-1
    confidence: float
    hits: int = 1
    missed_frames: int = 0
    state: str = "new"  # new | confirmed | lost | dead
    first_image_id: str = ""
    last_image_id: str = ""
    first_frame_idx: int = 0
    last_frame_idx: int = 0
    all_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0.0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


class BotSortTracker:
    """
    Greedy IoU multi-object tracker.

    Args:
        iou_threshold:  min IoU to match a detection to an existing track.
        max_age:        frames a track can be missed before it's marked dead.
        min_hits:       frames a track must be seen before it's confirmed.
        static_thresh:  bbox IoU threshold to classify as static object (poster/mannequin).
        static_min_frames: how many frames a track must barely move to be flagged static.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_age: int = 5,
        min_hits: int = 2,
        static_thresh: float = 0.92,
        static_min_frames: int = 6,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits
        self.static_thresh = static_thresh
        self.static_min_frames = static_min_frames
        self._tracks: list[Track] = []
        self._next_local_id: int = 1
        self._frame_idx: int = 0

    # ------------------------------------------------------------------
    def update(
        self,
        detections: list[tuple[float, float, float, float]],
        confidences: list[float],
        image_id: str = "",
    ) -> list[Track]:
        """Feed one frame of detections; returns current active tracks."""
        frame_idx = self._frame_idx
        self._frame_idx += 1

        # Greedy IoU matching: O(tracks × detections)
        matched_track_indices: set[int] = set()
        matched_det_indices: set[int] = set()

        # Sort detections by confidence desc for greedy priority
        sorted_dets = sorted(
            enumerate(zip(detections, confidences)),
            key=lambda x: x[1][1],
            reverse=True,
        )

        for det_idx, (bbox, conf) in sorted_dets:
            best_iou = self.iou_threshold
            best_track_idx: Optional[int] = None
            for t_idx, track in enumerate(self._tracks):
                if t_idx in matched_track_indices:
                    continue
                if track.state == "dead":
                    continue
                score = _iou(track.bbox, bbox)
                if score > best_iou:
                    best_iou = score
                    best_track_idx = t_idx

            if best_track_idx is not None:
                matched_track_indices.add(best_track_idx)
                matched_det_indices.add(det_idx)
                track = self._tracks[best_track_idx]
                track.bbox = bbox
                track.confidence = conf
                track.hits += 1
                track.missed_frames = 0
                track.last_image_id = image_id
                track.last_frame_idx = frame_idx
                track.all_bboxes.append(bbox)
                if track.state == "new" and track.hits >= self.min_hits:
                    track.state = "confirmed"

        # Create new tracks for unmatched detections
        for det_idx, (bbox, conf) in sorted_dets:
            if det_idx in matched_det_indices:
                continue
            track = Track(
                track_id=str(uuid.uuid4()),
                local_id=self._next_local_id,
                bbox=bbox,
                confidence=conf,
                first_image_id=image_id,
                last_image_id=image_id,
                first_frame_idx=frame_idx,
                last_frame_idx=frame_idx,
                all_bboxes=[bbox],
            )
            self._next_local_id += 1
            self._tracks.append(track)

        # Age unmatched tracks
        for t_idx, track in enumerate(self._tracks):
            if t_idx not in matched_track_indices and track.state != "dead":
                track.missed_frames += 1
                if track.missed_frames >= self.max_age:
                    track.state = "lost"

        # Flag static objects: bbox barely moves over many frames
        for track in self._tracks:
            if len(track.all_bboxes) >= self.static_min_frames:
                first = track.all_bboxes[0]
                last = track.all_bboxes[-1]
                if _iou(first, last) >= self.static_thresh:
                    track.state = "static_object"

        return [t for t in self._tracks if t.state != "dead"]

    def finalize(self) -> list[Track]:
        """Mark all remaining tracks as lost. Call at end of a frame sequence."""
        for track in self._tracks:
            if track.state not in ("dead", "static_object"):
                track.state = "lost"
        return self._tracks

    def all_tracks(self) -> list[Track]:
        return list(self._tracks)

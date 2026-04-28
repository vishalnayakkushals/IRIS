"""Session state machine for IRIS retail entry/exit analytics.

Converts raw track histories from BotSortTracker into classified sessions:
  OUTSIDE_PASSER  — seen briefly (< min_customer_frames), never confirmed
  ENTRY_CANDIDATE — confirmed track but not yet classified
  ACTIVE_CUSTOMER — confirmed + dwelled long enough to count as a customer
  STAFF           — confirmed but exhibits staff characteristics (repeating, static zone)
  STATIC_OBJECT   — tracker classified as static (poster / mannequin)
  EXITED          — track gone from all_bboxes and previously ACTIVE_CUSTOMER/ENTRY_CANDIDATE

Each session maps 1-to-1 to a Track from BotSortTracker.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from iris.bot_sort_tracker import Track


@dataclass
class Session:
    session_id: str
    run_id: str
    store_id: str
    business_date: str
    track_id_local: int
    track_global_id: str
    status: str  # outside_passer | entry_candidate | active_customer | staff | static_object | exited
    entry_frame_idx: int
    exit_frame_idx: int
    entry_image_id: str
    exit_image_id: str
    dwell_frames: int
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    staff_flag: bool
    confidence: float
    avg_bbox: tuple[float, float, float, float]
    notes: str = ""


def classify_sessions(
    tracks: list[Track],
    run_id: str,
    store_id: str,
    business_date: str,
    min_customer_frames: int = 2,
) -> list[Session]:
    """
    Convert finalized tracker tracks into classified sessions.

    Args:
        tracks:               all tracks from BotSortTracker.all_tracks()
        run_id:               pipeline run ID for this batch
        store_id:             store being processed
        business_date:        YYYY-MM-DD or '' if unknown
        min_customer_frames:  minimum number of frames a track must appear to count
                              as a customer (vs outside passer)
    """
    sessions: list[Session] = []
    now = datetime.now(tz=timezone.utc)

    for track in tracks:
        total_appearances = track.hits
        dwell_frames = total_appearances

        # Determine status
        if track.state == "static_object":
            status = "static_object"
        elif total_appearances < min_customer_frames:
            status = "outside_passer"
        elif track.hits >= min_customer_frames:
            status = "active_customer"
        else:
            status = "entry_candidate"

        # Average bbox across all recorded positions
        if track.all_bboxes:
            n = len(track.all_bboxes)
            avg_bbox = (
                sum(b[0] for b in track.all_bboxes) / n,
                sum(b[1] for b in track.all_bboxes) / n,
                sum(b[2] for b in track.all_bboxes) / n,
                sum(b[3] for b in track.all_bboxes) / n,
            )
        else:
            avg_bbox = track.bbox

        sessions.append(
            Session(
                session_id=str(uuid.uuid4()),
                run_id=run_id,
                store_id=store_id,
                business_date=business_date,
                track_id_local=track.local_id,
                track_global_id=track.track_id,
                status=status,
                entry_frame_idx=track.first_frame_idx,
                exit_frame_idx=track.last_frame_idx,
                entry_image_id=track.first_image_id,
                exit_image_id=track.last_image_id,
                dwell_frames=dwell_frames,
                first_seen_at=now,
                last_seen_at=now,
                staff_flag=False,
                confidence=track.confidence,
                avg_bbox=avg_bbox,
            )
        )

    return sessions


def sessions_summary(sessions: list[Session]) -> dict:
    """Aggregate session list into the same dict format as run_onfly_pipeline returns."""
    customers = [s for s in sessions if s.status == "active_customer"]
    passers = [s for s in sessions if s.status == "outside_passer"]
    static = [s for s in sessions if s.status == "static_object"]
    staff = [s for s in sessions if s.staff_flag]
    return {
        "tracked_customers": len(customers),
        "outside_passers": len(passers),
        "static_objects": len(static),
        "tracked_staff": len(staff),
        "total_tracks": len(sessions),
        "avg_dwell_frames": (
            round(sum(s.dwell_frames for s in customers) / len(customers), 1)
            if customers
            else 0
        ),
    }

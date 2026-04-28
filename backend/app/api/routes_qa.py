"""QA / Frame Review routes.
GET  /api/qa/feedback          — list feedback rows from Postgres
PUT  /api/qa/feedback/{id}     — update review_status + corrected_label
POST /api/qa/feedback          — create feedback row
GET  /api/qa/image             — serve annotated image from filesystem (query ?path=...)
POST /api/qa/retrain/{store_id}— write rule file + log model version
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, insert, select, update

from backend.app.auth.dependencies import get_current_user
from backend.app.config import get_settings
from backend.app.db.canonical_metadata import model_versions, qa_feedback
from backend.app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/qa", tags=["qa"])


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Feedback CRUD
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    store_id: str
    capture_date: str = ""
    filename: str = ""
    camera_id: str = ""
    track_id: str = ""
    predicted_label: str = ""
    corrected_label: str = ""
    confidence: float = 0.8
    model_version: str = ""
    drive_link: str = ""
    needs_review: bool = False
    review_status: str = "pending"
    comment: str = ""


class FeedbackUpdate(BaseModel):
    review_status: str
    corrected_label: str = ""
    comment: str = ""


@router.get("/feedback")
async def list_feedback(
    store_id: str | None = None,
    review_status: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = select(qa_feedback).order_by(qa_feedback.c.created_at.desc()).limit(limit)
        if store_id:
            stmt = stmt.where(qa_feedback.c.store_id == store_id)
        if review_status:
            stmt = stmt.where(qa_feedback.c.review_status == review_status)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.post("/feedback", status_code=201)
async def create_feedback(body: FeedbackIn, actor: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            insert(qa_feedback).values(
                store_id=body.store_id,
                capture_date=body.capture_date,
                filename=body.filename,
                camera_id=body.camera_id,
                track_id=body.track_id,
                predicted_label=body.predicted_label,
                corrected_label=body.corrected_label,
                confidence=body.confidence,
                model_version=body.model_version,
                drive_link=body.drive_link,
                needs_review=body.needs_review,
                review_status=body.review_status,
                comment=body.comment,
                actor_email=actor,
                reviewer_email="",
                created_at=_now(),
                reviewed_at=None,
            ).returning(qa_feedback.c.id)
        )
        new_id = result.scalar_one()
        await session.commit()
    return {"id": new_id, "created": True}


@router.put("/feedback/{feedback_id}")
async def update_feedback(
    feedback_id: int,
    body: FeedbackUpdate,
    actor: str = Depends(get_current_user),
) -> dict:
    async with AsyncSessionLocal() as session:
        vals: dict[str, Any] = {
            "review_status": body.review_status,
            "reviewer_email": actor,
            "reviewed_at": _now(),
        }
        if body.corrected_label:
            vals["corrected_label"] = body.corrected_label
        if body.comment:
            vals["comment"] = body.comment
        result = await session.execute(
            update(qa_feedback).where(qa_feedback.c.id == feedback_id).values(**vals)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Feedback row not found")
        await session.commit()
    return {"id": feedback_id, "updated": True}


@router.delete("/feedback/{feedback_id}")
async def delete_feedback(feedback_id: int, _: str = Depends(get_current_user)) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(qa_feedback).where(qa_feedback.c.id == feedback_id))
        await session.commit()
    return {"id": feedback_id, "deleted": True}


# ---------------------------------------------------------------------------
# Image serving
# ---------------------------------------------------------------------------

@router.get("/image")
async def serve_image(
    path: str = Query(..., description="Absolute or data-root-relative path to image"),
    _: str = Depends(get_current_user),
) -> FileResponse:
    settings = get_settings()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = settings.data_root_obj / path

    # Restrict to data_root to prevent path traversal
    try:
        candidate.resolve().relative_to(settings.data_root_obj.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path outside data root")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    suffix = candidate.suffix.lower()
    media = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".bmp": "image/bmp", ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")

    return FileResponse(str(candidate), media_type=media)


# ---------------------------------------------------------------------------
# Retrain trigger
# ---------------------------------------------------------------------------

@router.post("/retrain/{store_id}")
async def trigger_retrain(
    store_id: str,
    actor: str = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Collect all confirmed feedback rows for a store, write a rule file,
    and register a new model version entry.
    """
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(qa_feedback)
            .where(qa_feedback.c.store_id == store_id)
            .where(qa_feedback.c.review_status == "confirmed")
            .order_by(qa_feedback.c.created_at.asc())
        )
        rows = [dict(r) for r in result.mappings().all()]

    if not rows:
        return {"store_id": store_id, "status": "skipped", "message": "No confirmed feedback rows found"}

    # Build rule file
    rules: list[dict] = []
    for row in rows:
        rules.append({
            "filename": row.get("filename", ""),
            "camera_id": row.get("camera_id", ""),
            "track_id": row.get("track_id", ""),
            "predicted_label": row.get("predicted_label", ""),
            "corrected_label": row.get("corrected_label", ""),
            "confidence": float(row.get("confidence") or 0.8),
            "capture_date": row.get("capture_date", ""),
        })

    version_tag = f"v{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    model_id = f"qa_rules_{store_id}_{version_tag}"
    artifact_dir = settings.data_root_obj / "models"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"qa_feedback_rules_{store_id}_{version_tag}.json"
    artifact_path.write_text(json.dumps({"store_id": store_id, "rules": rules}, indent=2))

    metrics = {
        "rule_count": len(rules),
        "confirmed_rows": len(rows),
        "store_id": store_id,
    }

    async with AsyncSessionLocal() as session:
        await session.execute(
            insert(model_versions).values(
                model_id=model_id,
                model_name=f"qa_rules_{store_id}",
                version_tag=version_tag,
                metrics_json=metrics,
                status="active",
                artifact_path=str(artifact_path),
                rollback_target_model_id="",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()

    return {
        "store_id": store_id,
        "model_id": model_id,
        "version_tag": version_tag,
        "rule_count": len(rules),
        "artifact_path": str(artifact_path),
        "status": "done",
    }


# ---------------------------------------------------------------------------
# Feedback accuracy summary
# ---------------------------------------------------------------------------

@router.get("/accuracy/{store_id}")
async def get_feedback_accuracy(
    store_id: str,
    _: str = Depends(get_current_user),
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(qa_feedback).where(qa_feedback.c.store_id == store_id)
        )
        rows = [dict(r) for r in result.mappings().all()]

    total = len(rows)
    confirmed = sum(1 for r in rows if r.get("review_status") == "confirmed")
    rejected = sum(1 for r in rows if r.get("review_status") == "rejected")
    pending = sum(1 for r in rows if r.get("review_status") == "pending")

    matched = sum(
        1 for r in rows
        if r.get("corrected_label") and r.get("predicted_label") == r.get("corrected_label")
    )
    scored = sum(1 for r in rows if r.get("corrected_label"))
    accuracy = round((matched / scored * 100), 2) if scored else 0.0

    return {
        "store_id": store_id,
        "total": total,
        "confirmed": confirmed,
        "rejected": rejected,
        "pending": pending,
        "accuracy_pct": accuracy,
        "scored_rows": scored,
        "matched_rows": matched,
    }

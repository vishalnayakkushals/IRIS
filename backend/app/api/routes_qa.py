"""QA / Frame Review routes.
GET  /api/qa/feedback          — list feedback rows from Postgres
PUT  /api/qa/feedback/{id}     — update review_status + corrected_label
POST /api/qa/feedback          — create feedback row
GET  /api/qa/image             — serve annotated image from filesystem (query ?path=...)
POST /api/qa/retrain/{store_id}— write rule file + log model version
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import requests
from sqlalchemy import case, delete, func, insert, select, update

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt_handler import verify_token
from backend.app.config import Settings, get_settings
from backend.app.db.canonical_metadata import model_versions, qa_feedback
from backend.app.db.session import AsyncSessionLocal
from iris.onfly_pipeline import GDriveClient, LocalClient, SourceImage, parse_drive_folder_id
router = APIRouter(prefix="/qa", tags=["qa"])
_bearer = HTTPBearer(auto_error=False)
_indexes_ensured = False


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


def _sqlite_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_qa_indexes(db_path: Path) -> None:
    """Add missing performance indexes for QA queries. Safe to call repeatedly."""
    if not db_path.exists():
        return
    conn = _sqlite_connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store ON onfly_image_state(store_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store_seen ON onfly_image_state(store_id, last_seen_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_image_store_date ON onfly_image_state(store_id, date_display, date_source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_walkin_store_image ON onfly_walkin_sessions(store_id, image_id)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _row_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    cols = [str(col[0]) for col in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _display_date_to_iso(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    try:
        if len(raw) == 10 and raw[2] == "-" and raw[5] == "-":
            return f"{raw[6:10]}-{raw[3:5]}-{raw[0:2]}"
        return datetime.fromisoformat(raw).date().isoformat()
    except Exception:
        return raw


def _iso_to_display(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return raw


def _dominant_predicted_label(image_row: dict[str, Any], walkin_stats: dict[str, Any]) -> str:
    customer_count = int(image_row.get("gpt_customer_count") or 0)
    staff_count = int(image_row.get("gpt_staff_count") or 0)
    pedestrian_count = int(walkin_stats.get("pedestrian_count") or 0)
    banner_count = int(walkin_stats.get("banner_count") or 0)
    if customer_count > 0:
        return "customer"
    if staff_count > 0:
        return "staff"
    if pedestrian_count > 0:
        return "pedestrian"
    if banner_count > 0:
        return "banner"
    gpt_status = str(image_row.get("gpt_status", "") or "").strip().lower()
    if gpt_status in {"failed", "quota_pending_retry", "pending"}:
        return "unknown"
    if int(image_row.get("person_count") or 0) <= 0:
        return "banner"
    return "unknown"


async def _latest_frame_feedback_map(store_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(qa_feedback)
            .where(qa_feedback.c.store_id == store_id)
            .where((qa_feedback.c.track_id == "") | (qa_feedback.c.track_id == "FRAME"))
            .order_by(qa_feedback.c.created_at.desc())
        )
        rows = [dict(r) for r in result.mappings().all()]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            _display_date_to_iso(str(row.get("capture_date", "") or "")),
            str(row.get("filename", "") or "").strip(),
        )
        if key not in out:
            out[key] = row
    return out


def _review_queue_rows(
    *,
    store_id: str,
    business_date: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        return []
    conn = _sqlite_connect(db_path)
    try:
        params: list[Any] = [store_id]
        where = ["img.store_id = ?"]
        if business_date:
            display_date = _iso_to_display(business_date)
            where.append("(img.date_display = ? OR img.date_source = ?)")
            params.extend([display_date, business_date])
        where_sql = " AND ".join(where)
        cur = conn.execute(
            f"""
            SELECT
                img.store_id,
                img.image_id,
                img.image_name,
                img.date_display,
                img.date_source,
                img.camera_id,
                img.source_provider,
                img.source_uri,
                img.source_item_id,
                img.source_url,
                img.relative_path,
                img.timestamp_hint,
                img.yolo_relevant,
                img.person_count,
                img.gpt_status,
                img.gpt_customer_count,
                img.gpt_staff_count,
                img.gpt_result_json,
                img.gpt_error,
                img.last_run_id,
                img.last_seen_at,
                SUM(CASE WHEN UPPER(COALESCE(ws.event_type,'')) = 'PASSERBY_OUTSIDE' THEN 1 ELSE 0 END) AS pedestrian_count,
                SUM(CASE WHEN UPPER(COALESCE(ws.event_type,'')) = 'POSTER_NON_HUMAN' THEN 1 ELSE 0 END) AS banner_count,
                SUM(CASE WHEN UPPER(COALESCE(ws.role,'')) = 'CUSTOMER' THEN 1 ELSE 0 END) AS customer_rows,
                SUM(CASE WHEN UPPER(COALESCE(ws.role,'')) = 'STAFF' THEN 1 ELSE 0 END) AS staff_rows
            FROM onfly_image_state img
            LEFT JOIN onfly_walkin_sessions ws
              ON ws.store_id = img.store_id
             AND ws.image_id = img.image_id
            WHERE {where_sql}
            GROUP BY img.store_id, img.image_id
            ORDER BY img.last_seen_at DESC, img.image_name DESC
            LIMIT ?
            """,
            tuple(params + [max(1, int(limit))]),
        )
        return _row_dicts(cur)
    finally:
        conn.close()


def _build_source_client_from_row(row: dict[str, Any]):
    source_provider = str(row.get("source_provider", "") or "").strip().lower()
    source_uri = str(row.get("source_uri", "") or "").strip()
    if source_provider == "local":
        return LocalClient(source_uri)
    if source_provider == "gdrive" or parse_drive_folder_id(source_uri):
        if not str(get_settings().google_api_key or "").strip():
            return None
        return GDriveClient(source_uri, get_settings().google_api_key)
    raise HTTPException(status_code=400, detail="Unsupported source provider for thumbnail preview")


def _fetch_public_gdrive_bytes(file_id: str, image_name: str) -> bytes:
    last_error: Exception | None = None
    for url, params in [
        (f"https://lh3.googleusercontent.com/d/{file_id}", None),
        ("https://drive.google.com/uc", {"id": file_id, "export": "download"}),
    ]:
        try:
            resp = requests.get(url, params=params, timeout=(10, 25))
            resp.raise_for_status()
            if "text/html" not in str(resp.headers.get("content-type", "")).lower():
                return resp.content
        except Exception as exc:
            last_error = exc
    raise HTTPException(status_code=502, detail=f"Drive fetch failed for {image_name}: {last_error}")


def _fetch_frame_bytes(store_id: str, image_id: str) -> tuple[bytes, str, str]:
    db_path = get_settings().db_path_obj
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Runtime image state DB not found")
    conn = _sqlite_connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT store_id, image_id, image_name, relative_path, source_provider, source_uri,
                   source_item_id, source_url, date_source, date_display, camera_id, timestamp_hint
            FROM onfly_image_state
            WHERE store_id=? AND image_id=?
            LIMIT 1
            """,
            (store_id, image_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    item = SourceImage(
        image_id=str(row["image_id"]),
        image_name=str(row["image_name"]),
        relative_path=str(row["relative_path"] or ""),
        source_provider=str(row["source_provider"] or ""),
        source_item_id=str(row["source_item_id"] or ""),
        source_url=str(row["source_url"] or ""),
        date_source=str(row["date_source"] or ""),
        date_display=str(row["date_display"] or ""),
        camera_id=str(row["camera_id"] or ""),
        timestamp_hint=str(row["timestamp_hint"] or ""),
    )
    client = _build_source_client_from_row(dict(row))
    if client is None:
        image_bytes = _fetch_public_gdrive_bytes(item.source_item_id, item.image_name)
    else:
        image_bytes = client.fetch_bytes(item)
    suffix = Path(item.image_name).suffix.lower()
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
    return image_bytes, media, item.image_name


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


@router.get("/review-queue")
async def review_queue(
    store_id: str,
    business_date: str | None = None,
    review_status: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    global _indexes_ensured
    if not _indexes_ensured:
        _ensure_qa_indexes(settings.db_path_obj)
        _indexes_ensured = True
    feedback_map = await _latest_frame_feedback_map(store_id)
    rows = _review_queue_rows(store_id=store_id, business_date=business_date, limit=limit)
    out: list[dict[str, Any]] = []
    for row in rows:
        capture_date_iso = _display_date_to_iso(str(row.get("date_display", "") or row.get("date_source", "") or ""))
        filename = str(row.get("image_name", "") or "").strip()
        feedback = feedback_map.get((capture_date_iso, filename), {})
        predicted_label = _dominant_predicted_label(row, row)
        person_count = int(row.get("person_count") or 0)
        # Auto-approve images where YOLO detected no people — no human review needed
        has_existing_feedback = bool(feedback)
        auto_approved = (person_count == 0) and not has_existing_feedback
        resolved_status = "confirmed" if auto_approved else str(feedback.get("review_status", "") or "pending")
        record = {
            "feedback_id": feedback.get("id"),
            "store_id": store_id,
            "image_id": row.get("image_id", ""),
            "filename": filename,
            "capture_date": capture_date_iso,
            "capture_date_display": _iso_to_display(capture_date_iso),
            "camera_id": row.get("camera_id", ""),
            "predicted_label": str(feedback.get("predicted_label", "") or predicted_label),
            "corrected_label": str(feedback.get("corrected_label", "") or ""),
            "review_status": resolved_status,
            "auto_approved": auto_approved,
            "comment": str(feedback.get("comment", "") or ""),
            "confidence": float(feedback.get("confidence") or 0.8),
            "drive_link": str(feedback.get("drive_link", "") or row.get("source_url", "") or ""),
            "thumbnail_url": f"/api/qa/frame-image/{store_id}/{row.get('image_id', '')}",
            "source_url": row.get("source_url", ""),
            "relative_path": row.get("relative_path", ""),
            "timestamp_hint": row.get("timestamp_hint", ""),
            "yolo_relevant": bool(row.get("yolo_relevant")),
            "person_count": person_count,
            "gpt_status": row.get("gpt_status", ""),
            "gpt_error": row.get("gpt_error", ""),
            "customer_count": int(row.get("gpt_customer_count") or 0),
            "staff_count": int(row.get("gpt_staff_count") or 0),
            "banner_count": int(row.get("banner_count") or 0),
            "pedestrian_count": int(row.get("pedestrian_count") or 0),
            "last_run_id": row.get("last_run_id", ""),
            "last_seen_at": row.get("last_seen_at", ""),
        }
        if review_status and str(record["review_status"]).strip().lower() != str(review_status).strip().lower():
            continue
        out.append(record)
    return out


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


@router.get("/frame-image/{store_id}/{image_id}")
async def serve_runtime_frame_image(
    store_id: str,
    image_id: str,
    token: str | None = None,
    _: str | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Response:
    # Accept token from Authorization header OR ?token= query param (needed for <img> tags)
    raw_token: str | None = None
    if _ and _.credentials:
        raw_token = _.credentials
    elif token:
        raw_token = token
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        verify_token(raw_token, settings.jwt_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    image_bytes, media_type, image_name = _fetch_frame_bytes(store_id, image_id)
    headers = {"Cache-Control": "private, max-age=3600", "Content-Disposition": f'inline; filename="{image_name}"'}
    return Response(content=image_bytes, media_type=media_type, headers=headers)


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
        stmt = (
            select(
                func.count().label("total"),
                func.sum(case((qa_feedback.c.review_status == "confirmed", 1), else_=0)).label("confirmed"),
                func.sum(case((qa_feedback.c.review_status == "rejected", 1), else_=0)).label("rejected"),
                func.sum(case((qa_feedback.c.review_status == "pending", 1), else_=0)).label("pending"),
                func.sum(
                    case(
                        (
                            (qa_feedback.c.corrected_label != None)  # noqa: E711
                            & (qa_feedback.c.corrected_label != "")
                            & (qa_feedback.c.predicted_label == qa_feedback.c.corrected_label),
                            1,
                        ),
                        else_=0,
                    )
                ).label("matched"),
                func.sum(
                    case(
                        (
                            (qa_feedback.c.corrected_label != None)  # noqa: E711
                            & (qa_feedback.c.corrected_label != ""),
                            1,
                        ),
                        else_=0,
                    )
                ).label("scored"),
            )
            .where(qa_feedback.c.store_id == store_id)
        )
        row = (await session.execute(stmt)).mappings().one()

    total = row["total"] or 0
    confirmed = row["confirmed"] or 0
    rejected = row["rejected"] or 0
    pending = row["pending"] or 0
    matched = row["matched"] or 0
    scored = row["scored"] or 0
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

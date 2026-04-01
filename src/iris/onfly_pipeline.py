from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import base64
import json
import os
import re
import sqlite3
import tempfile
import time
from typing import Any, Protocol

import pandas as pd
import requests

from iris.iris_analysis import build_detector
from iris.store_registry import parse_drive_folder_id, parse_s3_location


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
CAMERA_PATTERN = re.compile(r"_(D\d{2})[-_]", re.IGNORECASE)
TIME_PATTERN = re.compile(r"^(\d{2}-\d{2}-\d{2})_")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMPACT_DATE = re.compile(r"^\d{8}$")


@dataclass(frozen=True)
class SourceImage:
    image_id: str
    image_name: str
    relative_path: str
    source_provider: str
    source_item_id: str
    source_url: str
    date_source: str
    date_display: str
    camera_id: str
    timestamp_hint: str


@dataclass(frozen=True)
class OnFlyConfig:
    store_id: str
    source_uri: str
    db_path: Path
    out_dir: Path
    detector_type: str = "yolo"
    conf_threshold: float = 0.18
    max_images: int = 100
    gpt_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_api_base: str = "https://api.openai.com/v1"
    gpt_rate_limit_rps: float = 1.0
    pipeline_version: str = "onfly_v1"
    allow_detector_fallback: bool = False
    force_reprocess: bool = False
    keep_relevant_dir: Path | None = None
    run_mode: str = "hourly"


class SourceClient(Protocol):
    provider: str

    def list_images(self, limit: int) -> list[SourceImage]:
        ...

    def fetch_bytes(self, item: SourceImage) -> bytes:
        ...


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _parse_date_token(token: str) -> date | None:
    text = str(token).strip()
    if not text:
        return None
    try:
        if ISO_DATE.fullmatch(text):
            return date.fromisoformat(text)
        if COMPACT_DATE.fullmatch(text):
            return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}")
    except Exception:
        return None
    return None


def _image_meta(rel: Path, image_name: str) -> tuple[str, str, str, str]:
    parts = [str(p) for p in rel.parts[:-1] if str(p).strip()]
    date_source = parts[0] if parts else ""
    parsed = _parse_date_token(date_source)
    date_display = parsed.strftime("%d-%m-%Y") if parsed is not None else date_source
    cam = CAMERA_PATTERN.search(image_name)
    camera_id = cam.group(1).upper() if cam else ""
    t = TIME_PATTERN.match(image_name)
    hhmm = t.group(1).replace("-", ":") if t else ""
    ts = f"{date_source} {hhmm}".strip() if date_source else hhmm
    return date_source, date_display, camera_id, ts


class LocalClient:
    provider = "local"

    def __init__(self, uri: str) -> None:
        text = str(uri).strip()
        if text.lower().startswith("file://"):
            text = text[7:]
        self.root = Path(text).expanduser().resolve()
        if not self.root.exists():
            raise ValueError(f"Local path not found: {self.root}")

    def list_images(self, limit: int) -> list[SourceImage]:
        paths = [p for p in self.root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        paths.sort(key=lambda p: str(p.relative_to(self.root)).lower())
        if limit > 0:
            paths = paths[:limit]
        out: list[SourceImage] = []
        for p in paths:
            rel = p.relative_to(self.root)
            ds, dd, cam, ts = _image_meta(rel, p.name)
            rel_norm = str(rel).replace("\\", "/")
            out.append(SourceImage(f"local:{rel_norm.lower()}", p.name, rel_norm, "local", rel_norm, str(p), ds, dd, cam, ts))
        return out

    def fetch_bytes(self, item: SourceImage) -> bytes:
        return (self.root / item.source_item_id).read_bytes()


class GDriveClient:
    provider = "gdrive"

    def __init__(self, uri: str, api_key: str) -> None:
        folder_id = parse_drive_folder_id(uri)
        if not folder_id:
            raise ValueError("Invalid Google Drive folder URL")
        if not str(api_key).strip():
            raise ValueError("GOOGLE_API_KEY is required for Drive on-the-fly ingestion")
        self.folder_id = folder_id
        self.api_key = str(api_key).strip()

    def list_images(self, limit: int) -> list[SourceImage]:
        files: list[dict[str, str]] = []
        stack: list[tuple[str, list[str]]] = [(self.folder_id, [])]
        while stack:
            cur, rel_parts = stack.pop()
            token = None
            while True:
                params = {
                    "q": f"'{cur}' in parents and trashed = false",
                    "fields": "nextPageToken,files(id,name,mimeType)",
                    "pageSize": 1000,
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                    "key": self.api_key,
                }
                if token:
                    params["pageToken"] = token
                resp = requests.get("https://www.googleapis.com/drive/v3/files", params=params, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                for item in payload.get("files", []):
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    if str(item.get("mimeType", "")) == "application/vnd.google-apps.folder":
                        stack.append((str(item.get("id", "")).strip(), rel_parts + [name]))
                        continue
                    if Path(name).suffix.lower() not in IMAGE_EXTS:
                        continue
                    rel = (Path(*rel_parts) / name) if rel_parts else Path(name)
                    files.append({"id": str(item.get("id", "")), "name": name, "rel": str(rel).replace("\\", "/")})
                token = payload.get("nextPageToken")
                if not token:
                    break
        files.sort(key=lambda r: str(r["rel"]).lower())
        if limit > 0:
            files = files[:limit]
        out: list[SourceImage] = []
        for r in files:
            rel = Path(r["rel"])
            ds, dd, cam, ts = _image_meta(rel, r["name"])
            fid = str(r["id"])
            out.append(SourceImage(f"gdrive:{fid}", r["name"], r["rel"], "gdrive", fid, f"https://drive.google.com/file/d/{fid}/view", ds, dd, cam, ts))
        return out

    def fetch_bytes(self, item: SourceImage) -> bytes:
        fid = item.source_item_id
        media = requests.get(f"https://www.googleapis.com/drive/v3/files/{fid}", params={"alt": "media", "key": self.api_key}, timeout=45)
        if media.status_code == 200 and "text/html" not in str(media.headers.get("content-type", "")).lower():
            return media.content
        fallback = requests.get("https://drive.google.com/uc", params={"id": fid, "export": "download"}, timeout=45)
        fallback.raise_for_status()
        return fallback.content


def build_source_client(source_uri: str) -> SourceClient:
    if parse_drive_folder_id(source_uri):
        return GDriveClient(source_uri, os.getenv("GOOGLE_API_KEY", ""))
    if parse_s3_location(source_uri) is not None:
        raise RuntimeError("S3 on-the-fly adapter is configured for future use; enable in next phase.")
    return LocalClient(source_uri)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_onfly_tables(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_image_state(
                store_id TEXT NOT NULL, image_id TEXT NOT NULL, source_provider TEXT NOT NULL, source_uri TEXT NOT NULL,
                source_item_id TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', image_name TEXT NOT NULL,
                relative_path TEXT NOT NULL DEFAULT '', date_source TEXT NOT NULL DEFAULT '', date_display TEXT NOT NULL DEFAULT '',
                camera_id TEXT NOT NULL DEFAULT '', timestamp_hint TEXT NOT NULL DEFAULT '', discovered_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                pipeline_version TEXT NOT NULL DEFAULT '', yolo_status TEXT NOT NULL DEFAULT 'pending', yolo_relevant INTEGER NOT NULL DEFAULT 0,
                person_count INTEGER NOT NULL DEFAULT 0, yolo_conf REAL NOT NULL DEFAULT 0, yolo_error TEXT NOT NULL DEFAULT '',
                gpt_status TEXT NOT NULL DEFAULT 'pending', gpt_customer_count INTEGER NOT NULL DEFAULT 0, gpt_staff_count INTEGER NOT NULL DEFAULT 0,
                gpt_conversions INTEGER NOT NULL DEFAULT 0, gpt_bounce INTEGER NOT NULL DEFAULT 0, gpt_result_json TEXT NOT NULL DEFAULT '{}',
                gpt_error TEXT NOT NULL DEFAULT '', last_run_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(store_id,image_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_task_queue(
                task_key TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                image_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_task_stage_status ON onfly_task_queue(stage,status,updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_run_metrics(
                run_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, run_mode TEXT NOT NULL, source_provider TEXT NOT NULL,
                started_at TEXT NOT NULL, ended_at TEXT NOT NULL, total_listed INTEGER NOT NULL DEFAULT 0,
                new_images INTEGER NOT NULL DEFAULT 0, skipped_cached INTEGER NOT NULL DEFAULT 0, yolo_done INTEGER NOT NULL DEFAULT 0,
                yolo_relevant INTEGER NOT NULL DEFAULT 0, gpt_done INTEGER NOT NULL DEFAULT 0, total_ms REAL NOT NULL DEFAULT 0,
                list_ms REAL NOT NULL DEFAULT 0, download_ms REAL NOT NULL DEFAULT 0, yolo_ms REAL NOT NULL DEFAULT 0, gpt_ms REAL NOT NULL DEFAULT 0,
                report_ms REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ok', summary_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()




def _queue_set(conn: sqlite3.Connection, *, run_id: str, store_id: str, image_id: str, stage: str, status: str, error: str = "") -> None:
    key = f"{run_id}|{store_id}|{image_id}|{stage}"
    now = _now()
    row = conn.execute("SELECT attempts FROM onfly_task_queue WHERE task_key=?", (key,)).fetchone()
    attempts = int(row[0]) + 1 if row is not None else 0
    conn.execute(
        """
        INSERT INTO onfly_task_queue(task_key,run_id,store_id,image_id,stage,status,attempts,last_error,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(task_key) DO UPDATE SET
            status=excluded.status,
            attempts=excluded.attempts,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        (key, run_id, store_id, image_id, stage, status, attempts, str(error or "")[:1000], now, now),
    )
def _yolo_detect_from_bytes(detector: Any, image_bytes: bytes, image_name: str) -> tuple[int, float, str]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(image_name).suffix or ".jpg") as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)
    try:
        r = detector.detect(tmp_path)
        return int(r.person_count or 0), float(r.max_person_conf or 0.0), str(r.detection_error or "")
    finally:
        tmp_path.unlink(missing_ok=True)


def _openai_eval(cfg: OnFlyConfig, image_bytes: bytes, image_name: str) -> dict[str, Any]:
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    ext = Path(image_name).suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    body = {
        "model": cfg.openai_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Count customers and staff. Label printed humans as banner; outside humans as pedestrians. Return strict JSON."}, {"type": "input_image", "image_url": data_uri}]}],
        "text": {"format": {"type": "json_schema", "name": "retail_onfly_eval", "schema": {"type": "object", "additionalProperties": False, "properties": {"customer_count": {"type": "integer"}, "staff_count": {"type": "integer"}, "conversions": {"type": "integer"}, "bounce": {"type": "integer"}, "notes": {"type": "string"}}, "required": ["customer_count", "staff_count", "conversions", "bounce", "notes"]}, "strict": True}},
        "max_output_tokens": 500,
    }
    resp = requests.post(f"{cfg.openai_api_base.rstrip('/')}/responses", headers={"Authorization": f"Bearer {cfg.openai_api_key}", "Content-Type": "application/json"}, json=body, timeout=90)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    text = payload.get("output_text")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Empty output_text from Responses API")
    out = json.loads(text)
    return {
        "customer_count": int(out.get("customer_count", 0) or 0),
        "staff_count": int(out.get("staff_count", 0) or 0),
        "conversions": int(out.get("conversions", 0) or 0),
        "bounce": int(out.get("bounce", 0) or 0),
        "notes": str(out.get("notes", "") or ""),
    }


def run_onfly_pipeline(cfg: OnFlyConfig) -> dict[str, Any]:
    init_onfly_tables(cfg.db_path)
    started_at = _now()
    run_id = f"{cfg.store_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    perf0 = time.perf_counter()
    client = build_source_client(cfg.source_uri)
    detector = None
    detector_warning = ""
    timings = {"list_ms": 0.0, "detector_init_ms": 0.0, "download_ms": 0.0, "yolo_ms": 0.0, "gpt_ms": 0.0, "report_ms": 0.0}
    t_list = time.perf_counter()
    images = client.list_images(cfg.max_images)
    timings["list_ms"] = round((time.perf_counter() - t_list) * 1000.0, 2)
    conn = _connect(cfg.db_path)
    try:
        new_images = 0
        skipped = 0
        yolo_done = 0
        yolo_relevant = 0
        gpt_done = 0
        bytes_cache: dict[str, bytes] = {}
        for item in images:
            now = _now()
            row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            if row is None:
                conn.execute("INSERT INTO onfly_image_state(store_id,image_id,source_provider,source_uri,source_item_id,source_url,image_name,relative_path,date_source,date_display,camera_id,timestamp_hint,discovered_at,last_seen_at,pipeline_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (cfg.store_id, item.image_id, item.source_provider, cfg.source_uri, item.source_item_id, item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, now, cfg.pipeline_version))
                row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            else:
                conn.execute("UPDATE onfly_image_state SET source_url=?,image_name=?,relative_path=?,date_source=?,date_display=?,camera_id=?,timestamp_hint=?,last_seen_at=? WHERE store_id=? AND image_id=?", (item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, cfg.store_id, item.image_id))
            if row is None:
                continue
            same_version = str(row["pipeline_version"] or "") == cfg.pipeline_version
            done_yolo = str(row["yolo_status"] or "") == "done"
            done_gpt = str(row["gpt_status"] or "") == "done"
            if (not cfg.force_reprocess) and same_version and done_yolo and (not cfg.gpt_enabled or done_gpt or int(row["yolo_relevant"] or 0) == 0):
                skipped += 1
                continue
            new_images += 1
            _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="pending")
            dl0 = time.perf_counter()
            image_bytes = client.fetch_bytes(item)
            timings["download_ms"] += round((time.perf_counter() - dl0) * 1000.0, 2)
            bytes_cache[item.image_id] = image_bytes
            if detector is None:
                d0 = time.perf_counter()
                detector, detector_warning = build_detector(cfg.detector_type, cfg.conf_threshold, use_cache=False)
                timings["detector_init_ms"] = round((time.perf_counter() - d0) * 1000.0, 2)
                if cfg.detector_type == "yolo" and detector_warning and "fallback active" in detector_warning.lower() and not cfg.allow_detector_fallback:
                    raise RuntimeError("YOLO unavailable and fallback detected. Fix runtime or allow fallback.")
            y0 = time.perf_counter()
            pcount, max_conf, yerr = _yolo_detect_from_bytes(detector, image_bytes, item.image_name)
            timings["yolo_ms"] += round((time.perf_counter() - y0) * 1000.0, 2)
            relevant = int(pcount > 0 and not yerr)
            yolo_relevant += int(relevant == 1)
            yolo_done += 1
            conn.execute("UPDATE onfly_image_state SET pipeline_version=?,yolo_status='done',yolo_relevant=?,person_count=?,yolo_conf=?,yolo_error=?,last_run_id=? WHERE store_id=? AND image_id=?", (cfg.pipeline_version, relevant, pcount, max_conf, str(yerr)[:1000], run_id, cfg.store_id, item.image_id))
            _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="done")
            if relevant == 1 and cfg.keep_relevant_dir is not None:
                cfg.keep_relevant_dir.mkdir(parents=True, exist_ok=True)
                try:
                    (cfg.keep_relevant_dir / item.image_name).write_bytes(image_bytes)
                except Exception:
                    pass
            if relevant == 1 and cfg.gpt_enabled:
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="pending")
                g0 = time.perf_counter()
                try:
                    gpt = _openai_eval(cfg, image_bytes, item.image_name)
                    gstatus = "done"
                    gerr = ""
                except Exception as exc:
                    gpt = {"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_failed"}
                    gstatus = "failed"
                    gerr = str(exc)
                timings["gpt_ms"] += round((time.perf_counter() - g0) * 1000.0, 2)
                gpt_done += int(gstatus == "done")
                conn.execute("UPDATE onfly_image_state SET gpt_status=?,gpt_customer_count=?,gpt_staff_count=?,gpt_conversions=?,gpt_bounce=?,gpt_result_json=?,gpt_error=?,last_run_id=? WHERE store_id=? AND image_id=?", (gstatus, int(gpt.get("customer_count", 0)), int(gpt.get("staff_count", 0)), int(gpt.get("conversions", 0)), int(gpt.get("bounce", 0)), json.dumps(gpt, separators=(',', ':')), str(gerr)[:1000], run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status=gstatus, error=gerr)
                if cfg.gpt_rate_limit_rps > 0:
                    time.sleep(1.0 / max(0.01, float(cfg.gpt_rate_limit_rps)))
            else:
                status = "skipped_irrelevant" if relevant == 0 else "disabled"
                conn.execute("UPDATE onfly_image_state SET gpt_status=?,gpt_customer_count=0,gpt_staff_count=0,gpt_conversions=0,gpt_bounce=0,gpt_result_json='{}',gpt_error='',last_run_id=? WHERE store_id=? AND image_id=?", (status, run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status=status)
            conn.commit()
        t_rep = time.perf_counter()
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        store_out = cfg.out_dir / cfg.store_id
        store_out.mkdir(parents=True, exist_ok=True)
        rows = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? ORDER BY date_display,image_name", (cfg.store_id,)).fetchall()
        frame_df = pd.DataFrame([dict(r) for r in rows])
        if frame_df.empty:
            frame_df = pd.DataFrame(columns=["store_id", "date_display", "image_name", "source_url", "camera_id", "timestamp_hint", "yolo_relevant", "person_count", "gpt_customer_count", "gpt_staff_count", "gpt_conversions", "gpt_bounce"])
        frame_df = frame_df.rename(columns={"date_display": "Date", "yolo_relevant": "relevant", "gpt_customer_count": "customer_count", "gpt_staff_count": "staff_count", "gpt_conversions": "conversions", "gpt_bounce": "bounce"})
        frame_df.to_csv(store_out / "onfly_image_results.csv", index=False)
        agg_df = frame_df.groupby(["store_id", "Date"], as_index=False).agg(total_images=("image_id", "count"), relevant_images=("relevant", "sum"), customer_count=("customer_count", "sum"), conversions=("conversions", "sum"), bounce=("bounce", "sum")) if not frame_df.empty else pd.DataFrame(columns=["store_id", "Date", "total_images", "relevant_images", "customer_count", "conversions", "bounce"])
        report_csv = cfg.out_dir / "onfly_store_date_report.csv"
        if report_csv.exists():
            prev = pd.read_csv(report_csv)
            dates = set(agg_df["Date"].astype(str).tolist())
            mask = ~((prev.get("store_id", "") == cfg.store_id) & (prev.get("Date", "").astype(str).isin(dates)))
            pd.concat([prev[mask], agg_df], ignore_index=True).to_csv(report_csv, index=False)
        else:
            agg_df.to_csv(report_csv, index=False)
        timings["report_ms"] = round((time.perf_counter() - t_rep) * 1000.0, 2)
        total_ms = round((time.perf_counter() - perf0) * 1000.0, 2)
        ended_at = _now()
        summary = {"run_id": run_id, "store_id": cfg.store_id, "source_uri": cfg.source_uri, "source_provider": client.provider, "run_mode": cfg.run_mode, "pipeline_version": cfg.pipeline_version, "started_at": started_at, "ended_at": ended_at, "total_listed": len(images), "new_images": new_images, "skipped_cached": skipped, "yolo_done": yolo_done, "yolo_relevant": yolo_relevant, "gpt_done": gpt_done, "timings_ms": {**timings, "total_ms": total_ms}, "detector_warning": detector_warning, "outputs": {"image_results_csv": str((store_out / 'onfly_image_results.csv').resolve()), "store_report_csv": str(report_csv.resolve())}}
        summary_path = cfg.out_dir / f"onfly_run_summary_{run_id}.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["outputs"]["run_summary_json"] = str(summary_path.resolve())
        conn.execute("INSERT OR REPLACE INTO onfly_run_metrics(run_id,store_id,run_mode,source_provider,started_at,ended_at,total_listed,new_images,skipped_cached,yolo_done,yolo_relevant,gpt_done,total_ms,list_ms,download_ms,yolo_ms,gpt_ms,report_ms,status,summary_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, cfg.store_id, cfg.run_mode, client.provider, started_at, ended_at, len(images), new_images, skipped, yolo_done, yolo_relevant, gpt_done, total_ms, timings["list_ms"], timings["download_ms"], timings["yolo_ms"], timings["gpt_ms"], timings["report_ms"], "ok", json.dumps(summary, separators=(',', ':'))))
        conn.commit()
        return summary
    finally:
        conn.close()


def recent_onfly_runs(db_path: Path, store_id: str, limit: int = 20) -> pd.DataFrame:
    init_onfly_tables(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT run_id,store_id,run_mode,source_provider,started_at,ended_at,total_listed,new_images,skipped_cached,yolo_done,yolo_relevant,gpt_done,total_ms,list_ms,download_ms,yolo_ms,gpt_ms,report_ms,status FROM onfly_run_metrics WHERE store_id=? ORDER BY started_at DESC LIMIT ?", (store_id, int(limit))).fetchall()
        return pd.DataFrame([dict(r) for r in rows])
    finally:
        conn.close()

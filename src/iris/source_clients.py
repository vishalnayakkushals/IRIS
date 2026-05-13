from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import os
import re
import time
from typing import Protocol

import requests

from iris.store_registry import parse_drive_folder_id, parse_s3_location

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IGNORED_DRIVE_FOLDER_PREFIXES = ("_IRIS_",)
IGNORED_DRIVE_FOLDER_NAMES = ("Relevant image",)
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
    run_id: str = ""
    detector_type: str = "yolo"
    conf_threshold: float = 0.18
    max_images: int = 0
    gpt_enabled: bool = False
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_api_base: str = "https://api.openai.com/v1"
    gpt_rate_limit_rps: float = 1.0
    pipeline_version: str = "onfly_v1"
    yolo_version: str = ""
    gpt_version: str = ""
    allow_detector_fallback: bool = False
    force_reprocess: bool = False
    keep_relevant_dir: Path | None = None
    run_mode: str = "hourly"
    use_tracker: bool = False
    tracker_iou_threshold: float = 0.3
    tracker_max_age: int = 5
    tracker_min_hits: int = 2
    gpt_parallel_workers: int = 5
    google_api_key: str = ""
    gpt_batch_mode: bool = False
    export_relevant_drive_images: bool = False
    export_relevant_drive_shortcuts: bool = False


class SourceClient(Protocol):
    provider: str

    def list_images(self, limit: int, seen_ids: set[str] | None = None) -> list[SourceImage]:
        ...

    def fetch_bytes(self, item: SourceImage) -> bytes:
        ...


def parse_date_token(token: str) -> date | None:
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


def image_meta(rel: Path, image_name: str) -> tuple[str, str, str, str]:
    parts = [str(p) for p in rel.parts[:-1] if str(p).strip()]
    date_source = parts[0] if parts else ""
    parsed = parse_date_token(date_source)
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

    def list_images(self, limit: int, seen_ids: set[str] | None = None) -> list[SourceImage]:
        paths = [p for p in self.root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        paths.sort(key=lambda p: str(p.relative_to(self.root)).lower(), reverse=True)
        if limit > 0:
            paths = paths[:limit]
        out: list[SourceImage] = []
        for path in paths:
            rel = path.relative_to(self.root)
            ds, dd, cam, ts = image_meta(rel, path.name)
            rel_norm = str(rel).replace("\\", "/")
            out.append(SourceImage(f"local:{rel_norm.lower()}", path.name, rel_norm, "local", rel_norm, str(path), ds, dd, cam, ts))
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

    def _list_folder(self, folder_id: str) -> tuple[list[dict], list[dict]]:
        subfolders: list[dict] = []
        images: list[dict] = []
        token = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
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
                    if (
                        name.upper() in {ignored.upper() for ignored in IGNORED_DRIVE_FOLDER_NAMES}
                        or any(name.upper().startswith(prefix.upper()) for prefix in IGNORED_DRIVE_FOLDER_PREFIXES)
                    ):
                        continue
                    subfolders.append({"id": str(item.get("id", "")), "name": name})
                elif str(item.get("mimeType", "")) == "application/vnd.google-apps.shortcut":
                    continue
                elif Path(name).suffix.lower() in IMAGE_EXTS:
                    images.append({"id": str(item.get("id", "")), "name": name})
            token = payload.get("nextPageToken")
            if not token:
                break
        return subfolders, images

    def list_images(self, limit: int, seen_ids: set[str] | None = None) -> list[SourceImage]:
        seen = seen_ids or set()
        files: list[dict[str, str]] = []

        def _collect(folder_id: str, rel_parts: list[str]) -> bool:
            subfolders, images = self._list_folder(folder_id)
            for img in images:
                if img["id"] in seen:
                    continue
                rel = (Path(*rel_parts) / img["name"]) if rel_parts else Path(img["name"])
                files.append({"id": img["id"], "name": img["name"], "rel": str(rel).replace('\\', '/')})
                if limit > 0 and len(files) >= limit:
                    return True
            subfolders.sort(key=lambda s: s["name"], reverse=True)
            for subfolder in subfolders:
                if _collect(subfolder["id"], rel_parts + [subfolder["name"]]):
                    return True
            return False

        _collect(self.folder_id, [])
        files.sort(key=lambda row: str(row["rel"]).lower(), reverse=True)
        if limit > 0:
            files = files[:limit]
        out: list[SourceImage] = []
        for row in files:
            rel = Path(row["rel"])
            ds, dd, cam, ts = image_meta(rel, row["name"])
            fid = str(row["id"])
            out.append(SourceImage(f"gdrive:{fid}", row["name"], row["rel"], "gdrive", fid, f"https://drive.google.com/file/d/{fid}/view", ds, dd, cam, ts))
        return out

    def fetch_bytes(self, item: SourceImage) -> bytes:
        fid = item.source_item_id
        last_error: Exception | None = None
        for _ in range(2):
            try:
                media = requests.get(
                    f"https://www.googleapis.com/drive/v3/files/{fid}",
                    params={"alt": "media", "key": self.api_key},
                    timeout=(10, 25),
                )
                if media.status_code == 200 and "text/html" not in str(media.headers.get("content-type", "")).lower():
                    return media.content
                direct = requests.get(f"https://lh3.googleusercontent.com/d/{fid}", timeout=(10, 25))
                if direct.status_code == 200 and "text/html" not in str(direct.headers.get("content-type", "")).lower():
                    return direct.content
                fallback = requests.get(
                    "https://drive.google.com/uc",
                    params={"id": fid, "export": "download"},
                    timeout=(10, 25),
                )
                fallback.raise_for_status()
                return fallback.content
            except Exception as exc:
                last_error = exc
                time.sleep(0.3)
        raise RuntimeError(f"Drive fetch failed for {item.image_name} ({fid}): {last_error}")


def build_source_client(source_uri: str, google_api_key: str = "") -> SourceClient:
    if parse_drive_folder_id(source_uri):
        key = google_api_key or os.getenv("GOOGLE_API_KEY", "")
        return GDriveClient(source_uri, key)
    if parse_s3_location(source_uri) is not None:
        raise RuntimeError("S3 on-the-fly adapter is configured for future use; enable in next phase.")
    return LocalClient(source_uri)

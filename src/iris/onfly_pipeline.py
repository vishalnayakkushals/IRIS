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
PIPELINE_STAGES = (
    "LIST",
    "SKIP_CHECK",
    "DOWNLOAD",
    "YOLO",
    "GPT",
    "REPORT_WRITER",
    "DASHBOARD_INGEST",
)

# Walk-in table columns (20 fields) — must match gpt_post_relevance_test.py WALKIN_TABLE_COLUMNS
_WALKIN_COLUMNS = [
    "Date",
    "Walk-in ID",
    "Group ID",
    "Role",
    "Entry Time",
    "Exit Time",
    "Time Spent (mins)",
    "Session Status",
    "Entry Type",
    "Gender",
    "Age Band",
    "Attire / Visual Marker",
    "Primary Clothing",
    "Jewellery Load",
    "Bag Type",
    "Primary Clothing Style Archetype",
    "Engagement Type",
    "Engagement Depth",
    "Purchase Signal (Bag)",
    "Included in Analytics",
    "Event Type",
    "Direction Confidence",
    "Match Fingerprint",
]

# Comprehensive retail analytics prompt used for GPT vision analysis
_RETAIL_WALKIN_PROMPT = (
    "You are an AI system analysing retail store security camera images for offline customer intelligence.\n"
    "Output is consumed by store operations teams, analytics dashboards, and AI learning systems.\n"
    "Operate in a privacy-safe, recall-safe, non-PII manner.\n\n"
    "PRIVACY & SAFETY RULES (NON-NEGOTIABLE):\n"
    "Do NOT identify or recognise individuals. Do NOT use face recognition or biometrics.\n"
    "Do NOT persist identity across days. Do NOT infer names, religion, caste, income, or any sensitive personal trait.\n"
    "Use ONLY: visual cues, clothing, jewellery, bags, spatial position, temporal ordering, behavioural posture, group movement, entry/exit continuity.\n"
    "All identification must be session-local only.\n\n"
    "TEMPORAL REASONING (MANDATORY):\n"
    "Treat all provided frames as a time-ordered sequence. Extract visible timestamps from each frame. Sort chronologically.\n"
    "Detect new walk-ins even if they appear in only one frame. Track continuity only when visually and temporally supported.\n"
    "NEVER merge people across frames only because they have similar clothing.\n"
    "Create a NEW walk-in if a person appears at a new time window with no clear continuity from prior frames.\n"
    "Create a NEW group if: time gap is more than about 2 minutes AND no clear visual continuity AND no coordinated movement/waiting/joint browsing.\n\n"
    "PEOPLE DETECTION & ROLE SEPARATION:\n"
    "Detect all visible people in every frame. Classify each as: Customer, Staff, or Uncertain.\n"
    "Staff identification signals: repeated presence across frames, uniform/name tag/store dress, stationary near entrance or billing area,\n"
    "door handling for others, counter-side positioning, repeated customer-facing interaction pattern.\n"
    "Special staff rules: store staff commonly wear red shirt + black pant/trouser; managers (Store/Cluster/Area) commonly wear white shirt + black pant/trouser; classify both patterns as Staff.\n"
    "Clothing colour alone is NOT sufficient to classify staff.\n"
    "Staff and Uncertain must be excluded from customer analytics: set Included in Analytics = No.\n\n"
    "CRITICAL FALSE-POSITIVE CONTROL:\n"
    "Do not treat posters, banners, standees, mannequins, printed humans, wall graphics, or reflection-only humans as customers.\n"
    "If figure looks non-real (flat print, no limb articulation, no depth, fixed pose), mark as Uncertain and Included in Analytics = No.\n"
    "If no clear real-human body cues (hands/legs/joint posture/motion context), prefer Uncertain over Customer.\n\n"
    "EVENT-TYPE CLASSIFICATION (MANDATORY): choose exactly one: ENTRY, EXIT, INSIDE_ACTIVE, INSIDE_PURCHASING, PASSERBY_OUTSIDE, STAFF, POSTER_NON_HUMAN, UNCLEAR.\n"
    "Use visual cues: body orientation, movement direction, relation to door/entrance, inside vs outside context.\n"
    "Do NOT invent clock times from visual reasoning. Return event semantics only; system timestamping is handled by filename parser.\n\n"
    "WALK-IN SESSION LOGIC:\n"
    "Each detected customer walk-in is one session. Every walk-in MUST have a unique Walk-in ID and a Group ID.\n"
    "If solo: still assign a Group ID. If multiple customers together: each gets a unique Walk-in ID, all share one Group ID.\n\n"
    "GROUPING LOGIC (STRICT):\n"
    "Group customers ONLY if they enter together OR show clear in-store convergence:\n"
    "proximity, waiting together, shared browsing, coordinated movement, common engagement with the same counter/display.\n"
    "Do NOT group if: different timestamps without continuity, only spatially close once, independent posture and direction.\n\n"
    "ENTRY TYPE: Assisted Entry (staff facilitates entry) / Walk-in (customer enters independently) / Already Inside / NA.\n\n"
    "SESSION TIME:\n"
    "Entry Time: use actual timestamp of first supported entry or first seen moment; if threshold crossing not visible use earliest reliable timestamp; else NA.\n"
    "Exit Time: use actual exit timestamp only if exit is visible; else NA.\n"
    "Time Spent (mins): calculate only if both entry and exit are available; else NA.\n"
    "Session Status: OPEN if no exit observed; CLOSED if exit observed.\n\n"
    "DETERMINISTIC ID GENERATION (MANDATORY):\n"
    "Walk-in ID: YYYYMMDDHHMMSSWNN   Group ID: YYYYMMDDHHMMSSGNN\n"
    "Use Entry Time as anchor. If Entry Time is NA, use earliest reliable visible timestamp. If no timestamp visible at all, IDs = NA.\n"
    "Sort walk-ins by Entry Time asc; tie-break: smaller group size first, then left-to-right, then stable non-random order.\n"
    "Assign W01, W02, W03... Set each group anchor = earliest Entry Time among its members. Sort groups by anchor asc. Assign G01, G02, G03...\n"
    "Do NOT use random IDs. Do NOT change IDs across reruns for the same frame set.\n\n"
    "CUSTOMER PROFILE (NON-PII):\n"
    "Gender: Male / Female / Uncertain.\n"
    "Age Band (choose ONE): Under 18 / 18 - 24 / 25 - 34 / 35 - 45 / 45 - 55 / Above 55 / NA. Prefer wider bands if unsure.\n\n"
    "VISUAL ATTRIBUTES:\n"
    "Attire / Visual Marker: describe only visible clothing, accessories, bags, hairstyle cues if non-sensitive. Keep short, descriptive, recall-safe.\n"
    "Primary Clothing (ONE): Saree / Dress / Suit / Casual / Formal / Office / Workwear / Festive / Mixed / NA.\n"
    "Jewellery Load: None / Minimal / Everyday jewellery / Ethnic jewellery / Celebration / Heavy / Uncertain. If not clearly visible prefer Minimal/None/Uncertain.\n"
    "Bag Type: Tote bag / Sling bag / Handbag / Backpack / Branded paper bag / None / NA.\n"
    "Primary Clothing Style Archetype (ONE): Ethnic / Casual / Western / Office / Festive / Mixed / Uncertain.\n\n"
    "ENGAGEMENT SIGNALS:\n"
    "Engagement Type: Browsing / Assisted / Assisted Entry / Waiting / Billing / NA. If unclear prefer Browsing/NA.\n"
    "Engagement Depth: Low / Medium / High / NA. If unclear prefer Low/NA.\n\n"
    "PURCHASE SIGNAL (EXIT ONLY):\n"
    "Purchase Signal (Bag): Yes / No / NA. Carry bag is only a proxy, not a guaranteed purchase.\n\n"
    "Included in Analytics: Yes if Role = Customer. No if Role = Staff or Uncertain.\n\n"
    "OUTPUT: Return strict JSON only with key 'rows' containing an array of objects — one object per detected person — with exactly these fields: "
    "Date, Walk-in ID, Group ID, Role, Entry Time, Exit Time, Time Spent (mins), Session Status, Entry Type, Gender, Age Band, "
    "Attire / Visual Marker, Primary Clothing, Jewellery Load, Bag Type, Primary Clothing Style Archetype, "
    "Engagement Type, Engagement Depth, Purchase Signal (Bag), Included in Analytics, Event Type, Direction Confidence, Match Fingerprint. "
    "Prefer NA over guessing. Never invent data. Never output explanatory text outside the JSON."
)


def _walkin_schema() -> dict[str, Any]:
    row_props = {col: {"type": "string"} for col in _WALKIN_COLUMNS}
    return {
        "name": "retail_onfly_walkin_table",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": row_props,
                        "required": list(row_props.keys()),
                    },
                }
            },
            "required": ["rows"],
        },
    }


def _apply_staff_manager_rule(walkins: list[dict[str, str]]) -> list[dict[str, str]]:
    """Deterministic post-rules:
    - red shirt + black pant/trouser => Staff (store staff)
    - white shirt + black pant/trouser => Staff (managers)
    """
    for row in walkins:
        role = str(row.get("Role", "") or "").strip().lower()
        marker = str(row.get("Attire / Visual Marker", "") or "").lower()
        primary = str(row.get("Primary Clothing", "") or "").lower()
        style = str(row.get("Primary Clothing Style Archetype", "") or "").lower()
        text = " ".join([marker, primary, style])
        has_white = "white" in text
        has_red = "red" in text
        has_black = "black" in text
        has_pant = any(tok in text for tok in ("pant", "pants", "trouser", "trousers"))
        has_staff_uniform = (has_white or has_red) and has_black and has_pant
        if has_staff_uniform and role in {"customer", "uncertain", ""}:
            row["Role"] = "Staff"
            row["Included in Analytics"] = "No"
    return walkins


def _parse_filename_time(image_name: str) -> str:
    m = TIME_PATTERN.match(str(image_name or "").strip())
    if not m:
        return ""
    return m.group(1).replace("-", ":")


def _canonical_event_type(row: dict[str, str]) -> str:
    raw = str(row.get("Event Type", "") or "").strip().upper()
    role = str(row.get("Role", "") or "").strip().lower()
    entry_type = str(row.get("Entry Type", "") or "").strip().lower()
    engage = str(row.get("Engagement Type", "") or "").strip().lower()
    if raw in {
        "ENTRY",
        "EXIT",
        "INSIDE_ACTIVE",
        "INSIDE_PURCHASING",
        "PASSERBY_OUTSIDE",
        "STAFF",
        "POSTER_NON_HUMAN",
        "UNCLEAR",
    }:
        return raw
    if role == "staff":
        return "STAFF"
    if "assisted entry" in entry_type or "walk-in" in entry_type:
        return "ENTRY"
    if "billing" in engage:
        return "INSIDE_PURCHASING"
    if engage in {"browsing", "waiting", "assisted"}:
        return "INSIDE_ACTIVE"
    if role == "customer":
        return "INSIDE_ACTIVE"
    return "UNCLEAR"


def _event_fingerprint(row: dict[str, str], camera_id: str) -> str:
    keys = [
        camera_id,
        str(row.get("Role", "") or "").strip().lower(),
        str(row.get("Gender", "") or "").strip().lower(),
        str(row.get("Age Band", "") or "").strip().lower(),
        str(row.get("Primary Clothing", "") or "").strip().lower(),
        str(row.get("Bag Type", "") or "").strip().lower(),
        str(row.get("Jewellery Load", "") or "").strip().lower(),
        str(row.get("Primary Clothing Style Archetype", "") or "").strip().lower(),
        str(row.get("Attire / Visual Marker", "") or "").strip().lower()[:80],
    ]
    return "|".join(keys)


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
    yolo_version: str = ""
    gpt_version: str = ""
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


def _ms_to_hms(ms: float) -> str:
    total_seconds = max(0, int(round(float(ms) / 1000.0)))
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _apply_customer_group_correction(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize customer grouping for business exports."""
    if df.empty or "group_id" not in df.columns:
        return df

    out = df.copy()
    for col in ["role", "group_id", "walkin_id", "source_image_name", "store_id", "run_id"]:
        if col not in out.columns:
            out[col] = ""
    out["role_norm"] = out["role"].astype(str).str.strip().str.upper()
    out["group_id"] = out["group_id"].astype(str).str.strip()
    out["walkin_id"] = out["walkin_id"].astype(str).str.strip()
    out["source_image_name"] = out["source_image_name"].astype(str).str.strip()
    out["raw_group_id"] = out["group_id"]

    stats = (
        out.assign(
            is_customer=out["role_norm"].eq("CUSTOMER"),
            is_staff=out["role_norm"].eq("STAFF"),
        )
        .groupby(["store_id", "run_id", "source_image_name", "group_id"], dropna=False, as_index=False)
        .agg(customer_rows=("is_customer", "sum"), staff_rows=("is_staff", "sum"))
    )
    stats["preserve_group"] = (
        (stats["group_id"].astype(str).str.strip() != "")
        & (stats["customer_rows"] >= 2)
        & (stats["customer_rows"] <= 4)
        & (stats["staff_rows"] == 0)
    )
    key_cols = ["store_id", "run_id", "source_image_name", "group_id"]
    out = out.merge(stats[key_cols + ["preserve_group"]], on=key_cols, how="left")
    out["preserve_group"] = out["preserve_group"].fillna(False)

    def _session_group(row: pd.Series) -> str:
        walkin = str(row.get("walkin_id", "") or "").strip()
        if walkin:
            return walkin
        image_id = str(row.get("image_id", "") or "").strip()
        row_id = str(row.get("id", "") or "").strip()
        return f"{image_id or 'session'}_{row_id or '0'}"

    customer_mask = out["role_norm"].eq("CUSTOMER")
    split_mask = customer_mask & ((out["group_id"] == "") | (~out["preserve_group"]))
    if split_mask.any():
        out.loc[split_mask, "group_id"] = out.loc[split_mask].apply(_session_group, axis=1)
    # Keep non-customer entities explicitly isolated from customer groups.
    non_customer_mask = ~customer_mask
    if non_customer_mask.any():
        out.loc[non_customer_mask, "group_id"] = out.loc[non_customer_mask].apply(
            lambda r: f"NON_CUSTOMER_{str(r.get('id', '') or '').strip() or str(r.get('walkin_id', '') or '').strip() or '0'}",
            axis=1,
        )

    return out.drop(columns=["role_norm", "preserve_group"])


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
        stop_scan = False
        while stack:
            if stop_scan:
                break
            cur, rel_parts = stack.pop()
            token = None
            while True:
                if stop_scan:
                    break
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
                    if limit > 0 and len(files) >= limit:
                        stop_scan = True
                        break
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
                pipeline_version TEXT NOT NULL DEFAULT '', yolo_version TEXT NOT NULL DEFAULT '', gpt_version TEXT NOT NULL DEFAULT '',
                yolo_status TEXT NOT NULL DEFAULT 'pending', yolo_relevant INTEGER NOT NULL DEFAULT 0,
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
        state_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(onfly_image_state)").fetchall()}
        if "yolo_version" not in state_cols:
            conn.execute("ALTER TABLE onfly_image_state ADD COLUMN yolo_version TEXT NOT NULL DEFAULT ''")
        if "gpt_version" not in state_cols:
            conn.execute("ALTER TABLE onfly_image_state ADD COLUMN gpt_version TEXT NOT NULL DEFAULT ''")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_pipeline_runs (
                run_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                business_date TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                current_stage TEXT NOT NULL DEFAULT '',
                images_discovered INTEGER NOT NULL DEFAULT 0,
                images_skipped INTEGER NOT NULL DEFAULT 0,
                images_processed INTEGER NOT NULL DEFAULT 0,
                images_relevant INTEGER NOT NULL DEFAULT 0,
                images_irrelevant INTEGER NOT NULL DEFAULT 0,
                gpt_success_count INTEGER NOT NULL DEFAULT 0,
                gpt_failed_count INTEGER NOT NULL DEFAULT 0,
                report_image_results_csv TEXT NOT NULL DEFAULT '',
                report_walkin_sessions_csv TEXT NOT NULL DEFAULT '',
                report_store_date_csv TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                error_trace TEXT NOT NULL DEFAULT '',
                retry_status TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL DEFAULT '',
                last_heartbeat_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_pipeline_run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                event_type TEXT NOT NULL,
                image_id TEXT NOT NULL DEFAULT '',
                image_name TEXT NOT NULL DEFAULT '',
                message TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT NOT NULL DEFAULT '',
                error_trace TEXT NOT NULL DEFAULT '',
                attempt_no INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_pipeline_events_run_created ON onfly_pipeline_run_events(run_id, created_at ASC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_pipeline_events_run_stage ON onfly_pipeline_run_events(run_id, stage, created_at ASC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_report_index (
                store_id TEXT NOT NULL,
                business_date TEXT NOT NULL,
                run_id TEXT NOT NULL DEFAULT '',
                image_results_csv TEXT NOT NULL DEFAULT '',
                walkin_sessions_csv TEXT NOT NULL DEFAULT '',
                store_date_csv TEXT NOT NULL DEFAULT '',
                summary_json TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(store_id, business_date)
            )
            """
        )
        # Per-customer walk-in sessions table (20-field retail analytics output)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onfly_walkin_sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                image_id TEXT NOT NULL,
                source_image_name TEXT NOT NULL DEFAULT '',
                source_folder_name TEXT NOT NULL DEFAULT '',
                camera_id TEXT NOT NULL DEFAULT '',
                business_date TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT '',
                event_time TEXT NOT NULL DEFAULT '',
                walkin_id TEXT NOT NULL DEFAULT '',
                group_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                entry_time TEXT NOT NULL DEFAULT '',
                exit_time TEXT NOT NULL DEFAULT '',
                time_spent_mins TEXT NOT NULL DEFAULT '',
                session_status TEXT NOT NULL DEFAULT '',
                entry_type TEXT NOT NULL DEFAULT '',
                first_seen_time TEXT NOT NULL DEFAULT '',
                last_seen_time TEXT NOT NULL DEFAULT '',
                matched_session_id TEXT NOT NULL DEFAULT '',
                match_score REAL NOT NULL DEFAULT 0,
                match_reason TEXT NOT NULL DEFAULT '',
                direction_confidence TEXT NOT NULL DEFAULT '',
                match_fingerprint TEXT NOT NULL DEFAULT '',
                debug_parsed_time TEXT NOT NULL DEFAULT '',
                debug_gpt_event_type TEXT NOT NULL DEFAULT '',
                gender TEXT NOT NULL DEFAULT '',
                age_band TEXT NOT NULL DEFAULT '',
                attire_visual_marker TEXT NOT NULL DEFAULT '',
                primary_clothing TEXT NOT NULL DEFAULT '',
                jewellery_load TEXT NOT NULL DEFAULT '',
                bag_type TEXT NOT NULL DEFAULT '',
                clothing_style_archetype TEXT NOT NULL DEFAULT '',
                engagement_type TEXT NOT NULL DEFAULT '',
                engagement_depth TEXT NOT NULL DEFAULT '',
                purchase_signal_bag TEXT NOT NULL DEFAULT '',
                included_in_analytics TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_onfly_walkin_store_date ON onfly_walkin_sessions(store_id, date, walkin_id)")
        existing_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(onfly_walkin_sessions)").fetchall()}
        for col_name, col_def in [
            ("source_image_name", "TEXT NOT NULL DEFAULT ''"),
            ("source_folder_name", "TEXT NOT NULL DEFAULT ''"),
            ("camera_id", "TEXT NOT NULL DEFAULT ''"),
            ("business_date", "TEXT NOT NULL DEFAULT ''"),
            ("event_type", "TEXT NOT NULL DEFAULT ''"),
            ("event_time", "TEXT NOT NULL DEFAULT ''"),
            ("first_seen_time", "TEXT NOT NULL DEFAULT ''"),
            ("last_seen_time", "TEXT NOT NULL DEFAULT ''"),
            ("matched_session_id", "TEXT NOT NULL DEFAULT ''"),
            ("match_score", "REAL NOT NULL DEFAULT 0"),
            ("match_reason", "TEXT NOT NULL DEFAULT ''"),
            ("direction_confidence", "TEXT NOT NULL DEFAULT ''"),
            ("match_fingerprint", "TEXT NOT NULL DEFAULT ''"),
            ("debug_parsed_time", "TEXT NOT NULL DEFAULT ''"),
            ("debug_gpt_event_type", "TEXT NOT NULL DEFAULT ''"),
        ]:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE onfly_walkin_sessions ADD COLUMN {col_name} {col_def}")
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


def _json_compact(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "{}"
    try:
        return json.dumps(payload, separators=(",", ":"))
    except Exception:
        return "{}"


def _create_pipeline_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    store_id: str,
    business_date: str,
    source_type: str,
    source_uri: str,
    started_at: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO onfly_pipeline_runs(
            run_id,store_id,business_date,source_type,source_uri,status,current_stage,
            started_at,last_heartbeat_at,created_at,updated_at
        ) VALUES(?,?,?,?,?,'running',?,?,?, ?,?)
        """,
        (run_id, store_id, business_date, source_type, source_uri, PIPELINE_STAGES[0], started_at, started_at, started_at, started_at),
    )


def _update_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    **fields: Any,
) -> None:
    if not fields:
        return
    now = _now()
    fields["updated_at"] = now
    if "last_heartbeat_at" not in fields:
        fields["last_heartbeat_at"] = now
    columns = ", ".join(f"{k}=?" for k in fields.keys())
    values = list(fields.values())
    values.append(run_id)
    conn.execute(f"UPDATE onfly_pipeline_runs SET {columns} WHERE run_id=?", tuple(values))


def _append_pipeline_event(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    stage: str,
    event_type: str,
    image_id: str = "",
    image_name: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
    error_message: str = "",
    error_trace: str = "",
    attempt_no: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO onfly_pipeline_run_events(
            run_id,stage,event_type,image_id,image_name,message,payload_json,error_message,error_trace,attempt_no,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            stage,
            event_type,
            str(image_id or ""),
            str(image_name or ""),
            str(message or "")[:2000],
            _json_compact(payload),
            str(error_message or "")[:2000],
            str(error_trace or "")[:4000],
            max(1, int(attempt_no)),
            _now(),
        ),
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
    """Call GPT vision API with the comprehensive retail analytics prompt.

    Returns a dict with customer_count, staff_count, conversions, bounce, notes, and walkins (list of 20-field dicts).
    """
    if not cfg.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")
    ext = Path(image_name).suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    body = {
        "model": cfg.openai_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _RETAIL_WALKIN_PROMPT},
                    {"type": "input_image", "image_url": data_uri},
                ],
            }
        ],
        "text": {"format": {"type": "json_schema", **_walkin_schema()}},
        "max_output_tokens": 2000,
    }
    resp = requests.post(
        f"{cfg.openai_api_base.rstrip('/')}/responses",
        headers={"Authorization": f"Bearer {cfg.openai_api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    # Extract output text from Responses API (supports both output_text and output[].content[].text)
    text = payload.get("output_text")
    if not isinstance(text, str) or not text.strip():
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    chunk = content.get("text", "")
                    if isinstance(chunk, str) and chunk.strip():
                        text = chunk
                        break
            if isinstance(text, str) and text.strip():
                break
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Empty output_text from Responses API")
    parsed = json.loads(text)
    rows = parsed.get("rows", [])
    walkins: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        walkins.append({col: str(row.get(col, "NA") or "NA").strip() for col in _WALKIN_COLUMNS})
    walkins = _apply_staff_manager_rule(walkins)
    customer_count = sum(1 for w in walkins if w.get("Included in Analytics", "").lower() == "yes")
    staff_count = sum(1 for w in walkins if w.get("Role", "").lower() == "staff")
    conversions = sum(1 for w in walkins if w.get("Purchase Signal (Bag)", "").lower() == "yes")
    return {
        "customer_count": customer_count,
        "staff_count": staff_count,
        "conversions": conversions,
        "bounce": 0,
        "notes": f"{len(walkins)} persons detected ({customer_count} customers, {staff_count} staff)",
        "walkins": walkins,
    }


def run_onfly_pipeline(cfg: OnFlyConfig) -> dict[str, Any]:
    init_onfly_tables(cfg.db_path)
    yolo_version = str(cfg.yolo_version or cfg.pipeline_version or "onfly_v1").strip()
    gpt_version = str(cfg.gpt_version or cfg.pipeline_version or "onfly_v1").strip()
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
        stage = PIPELINE_STAGES[0]
        business_date = ""
        if images:
            source_dates = sorted({str(img.date_display or "").strip() for img in images if str(img.date_display or "").strip()})
            if len(source_dates) == 1:
                business_date = source_dates[0]
            elif len(source_dates) > 1:
                business_date = "MULTI_DATE"
        _create_pipeline_run(
            conn,
            run_id=run_id,
            store_id=cfg.store_id,
            business_date=business_date,
            source_type=client.provider,
            source_uri=cfg.source_uri,
            started_at=started_at,
        )
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage,
            event_type="success",
            message="List stage completed",
            payload={"images_discovered": len(images)},
        )
        stage = PIPELINE_STAGES[1]
        _update_pipeline_run(conn, run_id, images_discovered=len(images), current_stage=stage)
        conn.commit()
        new_images = 0
        skipped = 0
        yolo_done = 0
        yolo_relevant = 0
        gpt_done = 0
        gpt_failed = 0
        bytes_cache: dict[str, bytes] = {}
        _append_pipeline_event(conn, run_id=run_id, stage=PIPELINE_STAGES[1], event_type="start", message="Skip check started")
        for item in images:
            now = _now()
            row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            if row is None:
                conn.execute("INSERT INTO onfly_image_state(store_id,image_id,source_provider,source_uri,source_item_id,source_url,image_name,relative_path,date_source,date_display,camera_id,timestamp_hint,discovered_at,last_seen_at,pipeline_version,yolo_version,gpt_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (cfg.store_id, item.image_id, item.source_provider, cfg.source_uri, item.source_item_id, item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, now, cfg.pipeline_version, "", ""))
                row = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? AND image_id=?", (cfg.store_id, item.image_id)).fetchone()
            else:
                conn.execute("UPDATE onfly_image_state SET source_url=?,image_name=?,relative_path=?,date_source=?,date_display=?,camera_id=?,timestamp_hint=?,last_seen_at=? WHERE store_id=? AND image_id=?", (item.source_url, item.image_name, item.relative_path, item.date_source, item.date_display, item.camera_id, item.timestamp_hint, now, cfg.store_id, item.image_id))
            if row is None:
                continue
            row_yolo_version = str(row["yolo_version"] or row["pipeline_version"] or "").strip()
            row_gpt_version = str(row["gpt_version"] or row["pipeline_version"] or "").strip()
            done_yolo = str(row["yolo_status"] or "") == "done"
            done_gpt = str(row["gpt_status"] or "") == "done"
            existing_relevant = int(row["yolo_relevant"] or 0)
            yolo_needed = cfg.force_reprocess or not (done_yolo and row_yolo_version == yolo_version)
            gpt_needed = bool(cfg.gpt_enabled and existing_relevant == 1 and (cfg.force_reprocess or yolo_needed or not (done_gpt and row_gpt_version == gpt_version)))
            if (not yolo_needed) and (not gpt_needed):
                skipped += 1
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[1],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="Skipped by delta check",
                    payload={
                        "pipeline_version": cfg.pipeline_version,
                        "yolo_version": yolo_version,
                        "gpt_version": gpt_version,
                        "done_yolo": done_yolo,
                        "done_gpt": done_gpt,
                    },
                )
                continue
            new_images += 1
            stage = PIPELINE_STAGES[2]
            _update_pipeline_run(
                conn,
                run_id,
                images_skipped=skipped,
                images_processed=new_images,
                current_stage=stage,
            )
            _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="pending")
            _append_pipeline_event(
                conn,
                run_id=run_id,
                stage=stage,
                event_type="start",
                image_id=item.image_id,
                image_name=item.image_name,
                message="Downloading image bytes",
            )
            dl0 = time.perf_counter()
            try:
                image_bytes = client.fetch_bytes(item)
            except Exception as exc:
                err = str(exc)
                conn.execute(
                    "UPDATE onfly_image_state SET yolo_status='failed_download', yolo_error=?, gpt_status='skipped_download_error', gpt_error=?, last_run_id=? WHERE store_id=? AND image_id=?",
                    (err[:1000], err[:1000], run_id, cfg.store_id, item.image_id),
                )
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="failed_download", error=err)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="failure",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="Download failed",
                    error_message=err[:1000],
                )
                conn.commit()
                continue
            timings["download_ms"] += round((time.perf_counter() - dl0) * 1000.0, 2)
            bytes_cache[item.image_id] = image_bytes
            _append_pipeline_event(
                conn,
                run_id=run_id,
                stage=stage,
                event_type="success",
                image_id=item.image_id,
                image_name=item.image_name,
                message="Download completed",
                payload={"bytes": len(image_bytes)},
            )
            if detector is None:
                d0 = time.perf_counter()
                detector, detector_warning = build_detector(cfg.detector_type, cfg.conf_threshold, use_cache=False)
                timings["detector_init_ms"] = round((time.perf_counter() - d0) * 1000.0, 2)
                if cfg.detector_type == "yolo" and detector_warning and "fallback active" in detector_warning.lower() and not cfg.allow_detector_fallback:
                    raise RuntimeError("YOLO unavailable and fallback detected. Fix runtime or allow fallback.")
            if yolo_needed:
                stage = PIPELINE_STAGES[3]
                _update_pipeline_run(conn, run_id, current_stage=stage)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="start",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO detection started",
                )
                y0 = time.perf_counter()
                pcount, max_conf, yerr = _yolo_detect_from_bytes(detector, image_bytes, item.image_name)
                timings["yolo_ms"] += round((time.perf_counter() - y0) * 1000.0, 2)
                relevant = int(pcount > 0 and not yerr)
                yolo_relevant += int(relevant == 1)
                yolo_done += 1
                conn.execute("UPDATE onfly_image_state SET pipeline_version=?,yolo_version=?,yolo_status='done',yolo_relevant=?,person_count=?,yolo_conf=?,yolo_error=?,last_run_id=? WHERE store_id=? AND image_id=?", (cfg.pipeline_version, yolo_version, relevant, pcount, max_conf, str(yerr)[:1000], run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="yolo", status="done")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="success" if not yerr else "failure",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO detection completed",
                    payload={"person_count": int(pcount), "max_confidence_score": float(max_conf), "relevant": int(relevant), "yolo_version": yolo_version},
                    error_message=str(yerr)[:1000],
                )
                _update_pipeline_run(
                    conn,
                    run_id,
                    images_relevant=yolo_relevant,
                    images_irrelevant=max(0, yolo_done - yolo_relevant),
                )
            else:
                relevant = existing_relevant
                pcount = int(row["person_count"] or 0)
                max_conf = float(row["yolo_conf"] or 0.0)
                yerr = str(row["yolo_error"] or "")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[3],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="YOLO skipped (version match)",
                    payload={"yolo_version": yolo_version, "stored_yolo_version": row_yolo_version, "relevant": int(relevant)},
                )
            if relevant == 1 and cfg.keep_relevant_dir is not None:
                cfg.keep_relevant_dir.mkdir(parents=True, exist_ok=True)
                try:
                    (cfg.keep_relevant_dir / item.image_name).write_bytes(image_bytes)
                except Exception:
                    pass
            if relevant == 1 and cfg.gpt_enabled and gpt_needed:
                stage = PIPELINE_STAGES[4]
                _update_pipeline_run(conn, run_id, current_stage=stage)
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="pending")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="start",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT analysis started",
                )
                g0 = time.perf_counter()
                try:
                    gpt = _openai_eval(cfg, image_bytes, item.image_name)
                    gstatus = "done"
                    gerr = ""
                except Exception as exc:
                    gpt = {"customer_count": 0, "staff_count": 0, "conversions": 0, "bounce": 0, "notes": "gpt_failed", "walkins": []}
                    gstatus = "failed"
                    gerr = str(exc)
                timings["gpt_ms"] += round((time.perf_counter() - g0) * 1000.0, 2)
                gpt_done += int(gstatus == "done")
                gpt_failed += int(gstatus != "done")
                # Extract per-customer walkins before serialising to gpt_result_json
                walkins = gpt.pop("walkins", [])
                gpt_summary = json.dumps(gpt, separators=(',', ':'))
                conn.execute(
                    "UPDATE onfly_image_state SET gpt_version=?,gpt_status=?,gpt_customer_count=?,gpt_staff_count=?,gpt_conversions=?,gpt_bounce=?,gpt_result_json=?,gpt_error=?,last_run_id=? WHERE store_id=? AND image_id=?",
                    (gpt_version, gstatus, int(gpt.get("customer_count", 0)), int(gpt.get("staff_count", 0)), int(gpt.get("conversions", 0)), int(gpt.get("bounce", 0)), gpt_summary, str(gerr)[:1000], run_id, cfg.store_id, item.image_id),
                )
                # Session state machine: GPT decides event semantics, filename timestamp is source-of-truth for event time.
                event_time = _parse_filename_time(item.image_name) or str(item.timestamp_hint or "").split(" ")[-1].strip()
                business_date = str(item.date_display or "").strip()

                def _tsec(t: str) -> int:
                    try:
                        hh, mm, ss = [int(x) for x in str(t or "").split(":")]
                        return hh * 3600 + mm * 60 + ss
                    except Exception:
                        return -1

                def _find_best_open_session(row: dict[str, str]) -> tuple[int | None, float, str]:
                    fp = _event_fingerprint(row, item.camera_id)
                    candidates = conn.execute(
                        """
                        SELECT id, camera_id, gender, age_band, primary_clothing, bag_type,
                               clothing_style_archetype, jewellery_load, attire_visual_marker, last_seen_time
                        FROM onfly_walkin_sessions
                        WHERE store_id=? AND business_date=? AND role='Customer'
                          AND session_status IN ('OPEN','INFERRED_INSIDE_OPEN')
                        ORDER BY id DESC
                        """,
                        (cfg.store_id, business_date),
                    ).fetchall()
                    best_id: int | None = None
                    best_score = -1.0
                    best_reason = "no_open_session"
                    now_sec = _tsec(event_time)
                    for cand in candidates:
                        score = 0.0
                        reasons: list[str] = []
                        if str(cand["camera_id"] or "") == str(item.camera_id or ""):
                            score += 2.0
                            reasons.append("camera")
                        for key in ["gender", "age_band", "primary_clothing", "bag_type", "clothing_style_archetype", "jewellery_load"]:
                            rv = str(row.get({
                                "gender": "Gender",
                                "age_band": "Age Band",
                                "primary_clothing": "Primary Clothing",
                                "bag_type": "Bag Type",
                                "clothing_style_archetype": "Primary Clothing Style Archetype",
                                "jewellery_load": "Jewellery Load",
                            }[key], "") or "").strip().lower()
                            cv = str(cand[key] or "").strip().lower()
                            if rv and cv and rv == cv:
                                score += 1.0
                                reasons.append(key)
                        last_sec = _tsec(str(cand["last_seen_time"] or ""))
                        if now_sec >= 0 and last_sec >= 0:
                            gap = abs(now_sec - last_sec)
                            if gap <= 120:
                                score += 2.0
                                reasons.append("time<=120s")
                            elif gap <= 300:
                                score += 1.0
                                reasons.append("time<=300s")
                        if score > best_score:
                            best_score = score
                            best_id = int(cand["id"])
                            best_reason = ",".join(reasons) if reasons else "weak_match"
                    return best_id, float(best_score if best_score > 0 else 0.0), best_reason

                for walkin in walkins:
                    role = str(walkin.get("Role", "") or "").strip() or "Uncertain"
                    event_type = _canonical_event_type(walkin)
                    direction_conf = str(walkin.get("Direction Confidence", "") or "").strip() or "NA"
                    match_fingerprint = str(walkin.get("Match Fingerprint", "") or "").strip() or _event_fingerprint(walkin, item.camera_id)
                    included = str(walkin.get("Included in Analytics", "") or "").strip() or ("Yes" if role.lower() == "customer" else "No")
                    gpt_event = str(walkin.get("Event Type", "") or "").strip()

                    if event_type in {"PASSERBY_OUTSIDE", "POSTER_NON_HUMAN", "STAFF", "UNCLEAR"}:
                        conn.execute(
                            """INSERT INTO onfly_walkin_sessions(
                                   store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                                   event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                                   session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                                   direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                                   gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                                   clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                cfg.store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                                event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), role, "", "", "",
                                "CLOSED", walkin.get("Entry Type", ""), event_time, event_time, "", 0.0, "non_customer_event",
                                direction_conf, match_fingerprint, event_time, gpt_event,
                                walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                                walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                                walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), "No",
                            ),
                        )
                        continue

                    match_id, match_score, match_reason = _find_best_open_session(walkin)
                    strong_entry_match = match_id is not None and match_score >= 6.0
                    strong_match = match_id is not None and match_score >= 4.0

                    if event_type == "ENTRY":
                        if strong_entry_match:
                            conn.execute(
                                "UPDATE onfly_walkin_sessions SET last_seen_time=?, match_score=?, match_reason=? WHERE id=?",
                                (event_time, match_score, f"entry_attach:{match_reason}", int(match_id)),
                            )
                        else:
                            conn.execute(
                                """INSERT INTO onfly_walkin_sessions(
                                       store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                                       event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                                       session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                                       direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                                       gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                                       clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    cfg.store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                                    event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", event_time, "NA", "NA",
                                    "OPEN", "ENTRY", event_time, event_time, "", 0.0, "new_entry",
                                    direction_conf, match_fingerprint, event_time, gpt_event,
                                    walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                                    walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                                    walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                                ),
                            )
                        continue

                    if event_type in {"INSIDE_ACTIVE", "INSIDE_PURCHASING"}:
                        if strong_match:
                            conn.execute(
                                "UPDATE onfly_walkin_sessions SET last_seen_time=?, match_score=?, match_reason=? WHERE id=?",
                                (event_time, match_score, f"inside_update:{match_reason}", int(match_id)),
                            )
                        else:
                            conn.execute(
                                """INSERT INTO onfly_walkin_sessions(
                                       store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                                       event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                                       session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                                       direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                                       gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                                       clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    cfg.store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                                    event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", event_time, "NA", "NA",
                                    "INFERRED_INSIDE_OPEN", "INFERRED_INSIDE", event_time, event_time, "", 0.0, "inferred_inside",
                                    direction_conf, match_fingerprint, event_time, gpt_event,
                                    walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                                    walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                                    walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                                ),
                            )
                        continue

                    if event_type == "EXIT":
                        if strong_match:
                            conn.execute(
                                "UPDATE onfly_walkin_sessions SET exit_time=?, last_seen_time=?, session_status='CLOSED', match_score=?, match_reason=? WHERE id=?",
                                (event_time, event_time, match_score, f"exit_match:{match_reason}", int(match_id)),
                            )
                        else:
                            conn.execute(
                                """INSERT INTO onfly_walkin_sessions(
                                       store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                                       event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                                       session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                                       direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                                       gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                                       clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    cfg.store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                                    event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), "Customer", "NA", event_time, "NA",
                                    "UNMATCHED_EXIT", "NA", event_time, event_time, "", 0.0, "no_open_match",
                                    direction_conf, match_fingerprint, event_time, gpt_event,
                                    walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                                    walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                                    walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                                ),
                            )
                        continue

                    # Fallback deterministic record
                    conn.execute(
                        """INSERT INTO onfly_walkin_sessions(
                               store_id, run_id, image_id, source_image_name, source_folder_name, camera_id, business_date, date,
                               event_type, event_time, walkin_id, group_id, role, entry_time, exit_time, time_spent_mins,
                               session_status, entry_type, first_seen_time, last_seen_time, matched_session_id, match_score, match_reason,
                               direction_confidence, match_fingerprint, debug_parsed_time, debug_gpt_event_type,
                               gender, age_band, attire_visual_marker, primary_clothing, jewellery_load, bag_type,
                               clothing_style_archetype, engagement_type, engagement_depth, purchase_signal_bag, included_in_analytics
                           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            cfg.store_id, run_id, item.image_id, item.image_name, business_date, item.camera_id, business_date, business_date,
                            event_type, event_time, walkin.get("Walk-in ID", ""), walkin.get("Group ID", ""), role, event_time, "NA", "NA",
                            "OPEN", walkin.get("Entry Type", ""), event_time, event_time, "", 0.0, "fallback",
                            direction_conf, match_fingerprint, event_time, gpt_event,
                            walkin.get("Gender", ""), walkin.get("Age Band", ""), walkin.get("Attire / Visual Marker", ""), walkin.get("Primary Clothing", ""),
                            walkin.get("Jewellery Load", ""), walkin.get("Bag Type", ""), walkin.get("Primary Clothing Style Archetype", ""),
                            walkin.get("Engagement Type", ""), walkin.get("Engagement Depth", ""), walkin.get("Purchase Signal (Bag)", ""), included,
                        ),
                    )
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status=gstatus, error=gerr)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="success" if gstatus == "done" else "failure",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT analysis completed" if gstatus == "done" else "GPT analysis failed",
                    payload={"walkins": len(walkins), "customer_count": int(gpt.get("customer_count", 0)), "staff_count": int(gpt.get("staff_count", 0))},
                    error_message=str(gerr)[:1000],
                )
                _update_pipeline_run(conn, run_id, gpt_success_count=gpt_done, gpt_failed_count=gpt_failed)
                if cfg.gpt_rate_limit_rps > 0:
                    time.sleep(1.0 / max(0.01, float(cfg.gpt_rate_limit_rps)))
            elif relevant == 1 and cfg.gpt_enabled and not gpt_needed:
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status="skipped_version")
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=PIPELINE_STAGES[4],
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT skipped (version match)",
                    payload={"gpt_version": gpt_version, "stored_gpt_version": row_gpt_version},
                )
            else:
                status = "skipped_irrelevant" if relevant == 0 else "disabled"
                conn.execute("UPDATE onfly_image_state SET gpt_version=?,gpt_status=?,gpt_customer_count=0,gpt_staff_count=0,gpt_conversions=0,gpt_bounce=0,gpt_result_json='{}',gpt_error='',last_run_id=? WHERE store_id=? AND image_id=?", (gpt_version, status, run_id, cfg.store_id, item.image_id))
                _queue_set(conn, run_id=run_id, store_id=cfg.store_id, image_id=item.image_id, stage="chatgpt", status=status)
                _append_pipeline_event(
                    conn,
                    run_id=run_id,
                    stage=stage,
                    event_type="progress",
                    image_id=item.image_id,
                    image_name=item.image_name,
                    message="GPT skipped",
                    payload={"reason": status},
                )
            conn.commit()
        # End-of-day closeout: deterministically close remaining open sessions.
        conn.execute(
            """
            UPDATE onfly_walkin_sessions
            SET session_status='CLOSED_EOD',
                exit_time=CASE
                    WHEN COALESCE(NULLIF(last_seen_time,''), '') <> '' THEN last_seen_time
                    WHEN COALESCE(NULLIF(event_time,''), '') <> '' THEN event_time
                    ELSE '23:59:59'
                END
            WHERE store_id=? AND run_id=? AND session_status IN ('OPEN','INFERRED_INSIDE_OPEN')
            """,
            (cfg.store_id, run_id),
        )

        t_rep = time.perf_counter()
        stage = PIPELINE_STAGES[5]
        _update_pipeline_run(conn, run_id, current_stage=stage)
        _append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="start", message="Writing report artifacts")
        cfg.out_dir.mkdir(parents=True, exist_ok=True)
        store_out = cfg.out_dir / cfg.store_id
        store_out.mkdir(parents=True, exist_ok=True)
        rows = conn.execute("SELECT * FROM onfly_image_state WHERE store_id=? ORDER BY date_display,image_name", (cfg.store_id,)).fetchall()
        frame_df = pd.DataFrame([dict(r) for r in rows])
        listed_image_ids = {img.image_id for img in images}
        if not frame_df.empty and listed_image_ids:
            frame_df = frame_df[frame_df["image_id"].astype(str).isin(listed_image_ids)].copy()
        if frame_df.empty:
            frame_df = pd.DataFrame(columns=["store_id", "date_display", "image_name", "source_url", "camera_id", "timestamp_hint", "yolo_relevant", "person_count", "gpt_customer_count", "gpt_staff_count", "gpt_conversions", "gpt_bounce"])
        frame_df = frame_df.rename(columns={"date_display": "Date", "yolo_relevant": "relevant", "gpt_customer_count": "customer_count", "gpt_staff_count": "staff_count", "gpt_conversions": "conversions", "gpt_bounce": "bounce"})
        def _folder_from_rel(rel: Any) -> str:
            txt = str(rel or "").strip().replace("\\", "/")
            if not txt:
                return ""
            first = txt.split("/", 1)[0].strip()
            parsed = _parse_date_token(first)
            return parsed.strftime("%d-%m-%Y") if parsed is not None else first

        if "relative_path" in frame_df.columns:
            frame_df["folder_name"] = frame_df["relative_path"].map(_folder_from_rel)
        else:
            frame_df["folder_name"] = frame_df.get("Date", "")
        if "date_source" in frame_df.columns:
            frame_df = frame_df.drop(columns=["date_source"])
        preferred = [
            "store_id",
            "image_id",
            "relative_path",
            "folder_name",
            "Date",
            "image_name",
            "camera_id",
            "timestamp_hint",
        ]
        ordered = [c for c in preferred if c in frame_df.columns] + [c for c in frame_df.columns if c not in preferred]
        frame_df = frame_df[ordered]
        write_warnings: list[str] = []

        def _safe_write_csv(target: Path, df: pd.DataFrame, run_id_value: str) -> Path:
            target = Path(target)
            try:
                df.to_csv(target, index=False)
                return target
            except PermissionError:
                # Keep pipeline non-blocking when host tools (e.g. Excel) lock canonical files.
                # Write run-scoped fallback so run artifacts are still produced.
                fallback = target.with_name(f"{target.stem}_{run_id_value}{target.suffix}")
                df.to_csv(fallback, index=False)
                write_warnings.append(
                    f"Locked canonical file '{target.name}', wrote fallback '{fallback.name}' instead."
                )
                return fallback

        image_results_path = _safe_write_csv(store_out / "onfly_image_results.csv", frame_df, run_id)
        agg_df = frame_df.groupby(["store_id", "Date"], as_index=False).agg(total_images=("image_id", "count"), relevant_images=("relevant", "sum"), customer_count=("customer_count", "sum"), conversions=("conversions", "sum"), bounce=("bounce", "sum")) if not frame_df.empty else pd.DataFrame(columns=["store_id", "Date", "total_images", "relevant_images", "customer_count", "conversions", "bounce"])
        report_csv = cfg.out_dir / "onfly_store_date_report.csv"
        report_actual_path = report_csv
        if report_csv.exists():
            prev = pd.read_csv(report_csv)
            dates = set(agg_df["Date"].astype(str).tolist())
            mask = ~((prev.get("store_id", "") == cfg.store_id) & (prev.get("Date", "").astype(str).isin(dates)))
            merged = pd.concat([prev[mask], agg_df], ignore_index=True)
            report_actual_path = _safe_write_csv(report_csv, merged, run_id)
        else:
            report_actual_path = _safe_write_csv(report_csv, agg_df, run_id)
        # Export per-customer walk-in sessions for this store
        walkin_rows = conn.execute(
            """
            SELECT
                w.id,
                w.store_id,
                w.run_id,
                w.image_id,
                w.source_folder_name AS folder_name,
                w.source_image_name AS image_name,
                w.camera_id AS camera_id,
                w.business_date AS business_date,
                w.date,
                w.event_type,
                w.event_time,
                w.walkin_id,
                w.group_id,
                w.role,
                w.entry_time,
                w.exit_time,
                w.time_spent_mins,
                w.session_status,
                w.entry_type,
                w.first_seen_time,
                w.last_seen_time,
                w.matched_session_id,
                w.match_score,
                w.match_reason,
                w.direction_confidence,
                w.match_fingerprint,
                w.debug_parsed_time,
                w.debug_gpt_event_type,
                w.gender,
                w.age_band,
                w.attire_visual_marker,
                w.primary_clothing,
                w.jewellery_load,
                w.bag_type,
                w.clothing_style_archetype,
                w.engagement_type,
                w.engagement_depth,
                w.purchase_signal_bag,
                w.included_in_analytics,
                w.created_at
            FROM onfly_walkin_sessions w
            WHERE w.store_id=? AND w.run_id=?
            ORDER BY w.date, w.walkin_id, w.id
            """,
            (cfg.store_id, run_id),
        ).fetchall()
        if walkin_rows:
            walkin_df = pd.DataFrame([dict(r) for r in walkin_rows])
            walkin_df = _apply_customer_group_correction(walkin_df)
            # Keep canonical export business-friendly by default.
            # Full audit trail remains available in a dedicated audit CSV.
            audit_only_cols = [
                "matched_session_id",
                "match_score",
                "match_reason",
                "direction_confidence",
                "match_fingerprint",
                "debug_parsed_time",
                "created_at",
            ]
            business_df = walkin_df.drop(columns=[c for c in ["debug_gpt_event_type", *audit_only_cols] if c in walkin_df.columns])
            walkin_sessions_path = _safe_write_csv(store_out / "onfly_walkin_sessions.csv", business_df, run_id)
            _safe_write_csv(store_out / "onfly_walkin_sessions_audit.csv", walkin_df, run_id)
        else:
            walkin_sessions_path = store_out / "onfly_walkin_sessions.csv"
        timings["report_ms"] = round((time.perf_counter() - t_rep) * 1000.0, 2)
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage,
            event_type="success",
            message="Report writer completed",
            payload={
                "image_results_csv": str(image_results_path.resolve()),
                "store_date_csv": str(report_actual_path.resolve()),
                "walkin_rows": int(len(walkin_rows)),
                "warnings": write_warnings,
            },
        )
        total_ms = round((time.perf_counter() - perf0) * 1000.0, 2)
        ended_at = _now()
        summary = {"run_id": run_id, "store_id": cfg.store_id, "source_uri": cfg.source_uri, "source_provider": client.provider, "run_mode": cfg.run_mode, "pipeline_version": cfg.pipeline_version, "yolo_version": yolo_version, "gpt_version": gpt_version, "started_at": started_at, "ended_at": ended_at, "total_listed": len(images), "new_images": new_images, "skipped_cached": skipped, "yolo_done": yolo_done, "yolo_relevant": yolo_relevant, "gpt_done": gpt_done, "timings_ms": {**timings, "total_ms": total_ms}, "detector_warning": detector_warning, "write_warnings": write_warnings, "outputs": {"image_results_csv": str(image_results_path.resolve()), "store_report_csv": str(report_actual_path.resolve()), "walkin_sessions_csv": str(walkin_sessions_path.resolve()) if walkin_rows else ""}}
        summary_path = cfg.out_dir / f"onfly_run_summary_{run_id}.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        summary["outputs"]["run_summary_json"] = str(summary_path.resolve())
        timings_df = pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "store_id": cfg.store_id,
                    "pipeline_version": cfg.pipeline_version,
                    "yolo_version": yolo_version,
                    "gpt_version": gpt_version,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "list_ms": float(timings["list_ms"]),
                    "download_ms": float(timings["download_ms"]),
                    "yolo_ms": float(timings["yolo_ms"]),
                    "gpt_ms": float(timings["gpt_ms"]),
                    "report_ms": float(timings["report_ms"]),
                    "total_ms": float(total_ms),
                    "list_hms": _ms_to_hms(float(timings["list_ms"])),
                    "download_hms": _ms_to_hms(float(timings["download_ms"])),
                    "yolo_hms": _ms_to_hms(float(timings["yolo_ms"])),
                    "gpt_hms": _ms_to_hms(float(timings["gpt_ms"])),
                    "report_hms": _ms_to_hms(float(timings["report_ms"])),
                    "total_hms": _ms_to_hms(float(total_ms)),
                }
            ]
        )
        timings_path = store_out / "onfly_process_timings.csv"
        if timings_path.exists():
            try:
                prev_timings = pd.read_csv(timings_path)
                timings_df = pd.concat([prev_timings, timings_df], ignore_index=True)
            except Exception:
                pass
        _safe_write_csv(timings_path, timings_df, run_id)
        summary["outputs"]["process_timings_csv"] = str(timings_path.resolve())
        stage = PIPELINE_STAGES[6]
        _update_pipeline_run(conn, run_id, current_stage=stage)
        _append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="start", message="Updating dashboard ingestion index")
        for report_row in agg_df.to_dict(orient="records"):
            report_date = str(report_row.get("Date", "")).strip()
            if not report_date:
                continue
            conn.execute(
                """
                INSERT INTO onfly_report_index(
                    store_id,business_date,run_id,image_results_csv,walkin_sessions_csv,store_date_csv,summary_json,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(store_id,business_date) DO UPDATE SET
                    run_id=excluded.run_id,
                    image_results_csv=excluded.image_results_csv,
                    walkin_sessions_csv=excluded.walkin_sessions_csv,
                    store_date_csv=excluded.store_date_csv,
                    summary_json=excluded.summary_json,
                    updated_at=excluded.updated_at
                """,
                (
                    cfg.store_id,
                    report_date,
                    run_id,
                    str(image_results_path.resolve()),
                    str(walkin_sessions_path.resolve()) if walkin_rows else "",
                    str(report_actual_path.resolve()),
                    str(summary_path.resolve()),
                    _now(),
                ),
            )
        _append_pipeline_event(conn, run_id=run_id, stage=stage, event_type="success", message="Dashboard ingestion index updated")
        _update_pipeline_run(
            conn,
            run_id,
            status="success",
            current_stage=stage,
            ended_at=ended_at,
            images_discovered=len(images),
            images_skipped=skipped,
            images_processed=new_images,
            images_relevant=yolo_relevant,
            images_irrelevant=max(0, yolo_done - yolo_relevant),
            gpt_success_count=gpt_done,
            gpt_failed_count=gpt_failed,
            report_image_results_csv=str(image_results_path.resolve()),
            report_walkin_sessions_csv=str(walkin_sessions_path.resolve()) if walkin_rows else "",
            report_store_date_csv=str(report_actual_path.resolve()),
        )
        conn.execute("INSERT OR REPLACE INTO onfly_run_metrics(run_id,store_id,run_mode,source_provider,started_at,ended_at,total_listed,new_images,skipped_cached,yolo_done,yolo_relevant,gpt_done,total_ms,list_ms,download_ms,yolo_ms,gpt_ms,report_ms,status,summary_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, cfg.store_id, cfg.run_mode, client.provider, started_at, ended_at, len(images), new_images, skipped, yolo_done, yolo_relevant, gpt_done, total_ms, timings["list_ms"], timings["download_ms"], timings["yolo_ms"], timings["gpt_ms"], timings["report_ms"], "ok", json.dumps(summary, separators=(',', ':'))))
        conn.commit()
        return summary
    except Exception as exc:
        err = str(exc)
        _append_pipeline_event(
            conn,
            run_id=run_id,
            stage=stage if "stage" in locals() else "UNKNOWN",
            event_type="failure",
            message="Pipeline execution failed",
            error_message=err[:1000],
        )
        _update_pipeline_run(conn, run_id, status="failed", error_message=err[:1000], error_trace=err[:4000], ended_at=_now())
        conn.commit()
        raise
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

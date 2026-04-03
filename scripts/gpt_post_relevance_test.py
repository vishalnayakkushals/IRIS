from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import requests

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.store_registry import list_qa_feedback  # noqa: E402


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_OUT_ROOT = Path("data/exports/current/gpt_validation")
DEFAULT_STAGE1_ROOT = Path("data/exports/current/stage1_relevance")
LABELS = {"CUSTOMER", "STAFF", "BANNER", "PEDESTRIANS", "PRODUCT", "INVALID", "UNKNOWN"}
CAMERA_PATTERN = re.compile(r"_([A-Za-z]\d{2})[-_]")
WALKIN_TABLE_COLUMNS = [
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
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage-2 GPT post-relevance test pipeline: YOLO-relevant images only -> GPT entities -> review artifacts."
    )
    parser.add_argument("--store-id", default="TEST_STORE_D07")
    parser.add_argument(
        "--stage1-relevant",
        type=Path,
        default=DEFAULT_STAGE1_ROOT / "stage1_relevant_images.csv.gz",
        help="Stage-1 relevant list (.csv or .csv.gz). If store-specific file exists, it is preferred automatically.",
    )
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--model", default=str(os.getenv("OPENAI_VISION_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL))
    parser.add_argument("--api-base", default=str(os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")))
    parser.add_argument("--request-timeout", type=int, default=90)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--save-json", action="store_true")
    parser.add_argument("--skip-annotate", action="store_true")
    parser.add_argument("--run-note", default="test-folder-only")
    return parser.parse_args()


def _normalize_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        return str(parsed.date())
    parsed_dayfirst = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.notna(parsed_dayfirst):
        return str(parsed_dayfirst.date())
    return text


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _label_to_canonical(raw: object) -> str:
    text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"CUSTOMER", "SHOPPER", "PERSON"}:
        return "CUSTOMER"
    if text in {"STAFF", "EMPLOYEE"}:
        return "STAFF"
    if text in {"BANNER", "POSTER", "STANDEE", "PRINTED_HUMAN", "MANNEQUIN", "STATIC_OBJECT"}:
        return "BANNER"
    if text in {"PEDESTRIAN", "PEDESTRIANS", "OUTSIDE_PASSER", "PASSER", "PASSERBY"}:
        return "PEDESTRIANS"
    if text in {"PRODUCT", "MERCHANDISE"}:
        return "PRODUCT"
    if text in {"INVALID"}:
        return "INVALID"
    if text in {"NO_CUSTOMER", "NO_PERSON"}:
        return "NO_CUSTOMER"
    return "UNKNOWN"


def _load_stage1_rows(stage1_path: Path, store_id: str, limit: int) -> pd.DataFrame:
    store_specific_candidates = [
        stage1_path.parent / store_id / "stage1_relevant_images.csv.gz",
        stage1_path.parent / store_id / "stage1_relevant_images.csv",
    ]
    chosen = None
    for candidate in store_specific_candidates:
        if candidate.exists():
            chosen = candidate
            break
    if chosen is None:
        if stage1_path.exists():
            chosen = stage1_path
        elif stage1_path.with_suffix("").exists():
            chosen = stage1_path.with_suffix("")
    if chosen is None or not chosen.exists():
        raise FileNotFoundError(f"Stage-1 relevant file not found: {stage1_path}")

    df = pd.read_csv(chosen)
    if "store_id" in df.columns:
        df = df[df["store_id"].astype(str).str.lower() == str(store_id).strip().lower()].copy()
    if df.empty:
        raise RuntimeError(f"No relevant rows found for store_id={store_id} in {chosen}")

    if "capture_date" not in df.columns:
        df["capture_date"] = ""
    if "camera_id" not in df.columns:
        df["camera_id"] = ""
    if "timestamp" not in df.columns:
        df["timestamp"] = ""
    if "person_count" not in df.columns:
        df["person_count"] = 0
    if "image_name" not in df.columns:
        df["image_name"] = df.get("filename", "").astype(str)
    if "image_path" not in df.columns:
        raise RuntimeError("Stage-1 relevant file is missing required column: image_path")

    df["capture_date"] = df["capture_date"].map(_normalize_date)
    df["timestamp"] = df["timestamp"].astype(str)
    df["image_name"] = df["image_name"].astype(str)
    df["camera_id"] = df["camera_id"].astype(str)
    df["person_count"] = pd.to_numeric(df["person_count"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values(["capture_date", "timestamp", "image_name"], ascending=[False, False, True]).reset_index(drop=True)
    if limit > 0:
        df = df.head(int(limit)).copy()
    return df


def _load_feedback_memory(db_path: Path, store_id: str) -> dict[tuple[str, str, str, str], str]:
    if not db_path.exists():
        return {}
    rows = list_qa_feedback(db_path=db_path, store_id=store_id, review_status="confirmed", limit=200000)
    memory: dict[tuple[str, str, str, str], str] = {}
    for row in rows:
        track_id = str(row.get("track_id", "") or "").strip()
        if not track_id:
            continue
        corrected = _label_to_canonical(row.get("corrected_label", ""))
        if corrected in {"", "UNKNOWN"}:
            continue
        key = (
            _normalize_date(row.get("capture_date", "")),
            str(row.get("camera_id", "") or "").strip(),
            str(row.get("filename", "") or "").strip(),
            track_id.upper(),
        )
        if key not in memory:
            memory[key] = corrected
    return memory


def _vision_prompt() -> str:
    return (
        "You are analyzing a retail-store still image. Return STRICT JSON only.\n"
        "Identify each visible person-like entity and classify one label from this set only:\n"
        "CUSTOMER, STAFF, BANNER, PEDESTRIANS, PRODUCT, INVALID, UNKNOWN.\n"
        "Rules:\n"
        "- Printed humans/posters/standees/mannequins => BANNER.\n"
        "- Outside passersby => PEDESTRIANS.\n"
        "- Merchandise-only/object-only => PRODUCT.\n"
        "- If uncertain => UNKNOWN.\n"
        "Return entities sorted by left-to-right natural order if possible.\n"
        "Output keys exactly:\n"
        "{\n"
        "  \"entities\": [\n"
        "    {\n"
        "      \"label\": \"CUSTOMER\",\n"
        "      \"confidence\": 0.82,\n"
        "      \"gender\": \"female\",\n"
        "      \"age_band\": \"adult\",\n"
        "      \"bbox\": [0.1,0.1,0.4,0.8],\n"
        "      \"notes\": \"short\"\n"
        "    }\n"
        "  ],\n"
        "  \"image_notes\": \"short\"\n"
        "}"
    )


def _sequence_prompt() -> str:
    return (
        "You are analyzing retail store CCTV image frames for offline customer intelligence.\n"
        "Process all frames together as one chronological sequence and produce one consolidated table with one row per walk-in session candidate.\n"
        "Privacy rules: no identity recognition, no biometric logic, no personal sensitive inference, and no persistence across days.\n"
        "Use only session-local visual cues, timestamps, movement continuity, and behavioral context.\n"
        "Role must be one of: Customer, Staff, Uncertain.\n"
        "Exclude Staff/Uncertain from analytics using Included in Analytics = No.\n"
        "Temporal rules: do not merge solely by clothing similarity. Create new walk-in when continuity is unclear.\n"
        "If time gap > about 2 minutes and no continuity, create new group.\n"
        "Entry Type must be one of: Assisted Entry, Walk-in, Already Inside, NA.\n"
        "Session fields: Entry Time, Exit Time, Time Spent (mins), Session Status (OPEN/CLOSED).\n"
        "Deterministic IDs are mandatory:\n"
        "- Walk-in ID: YYYYMMDDHHMMSSWNN\n"
        "- Group ID: YYYYMMDDHHMMSSGNN\n"
        "If reliable timestamp not available, set Walk-in ID and Group ID to NA.\n"
        "Sort walk-ins by Entry Time asc, tie-break by smaller group size then left-to-right then stable order.\n"
        "For solo customers, still assign a Group ID.\n"
        "Gender: Male/Female/Uncertain.\n"
        "Age Band: Under 18, 18 – 24, 25 – 34, 35 – 45, 45 – 55, Above 55, NA.\n"
        "Primary Clothing: Saree, Dress, Suit, Casual, Formal, Office / Workwear, Festive, Mixed, NA.\n"
        "Jewellery Load: None, Minimal, Everyday jewellery, Ethnic jewellery, Celebration / Heavy, Uncertain.\n"
        "Bag Type: Tote bag, Sling bag, Handbag, Backpack, Branded paper bag, None, NA.\n"
        "Primary Clothing Style Archetype: Ethnic, Casual, Western, Office, Festive, Mixed, Uncertain.\n"
        "Engagement Type: Browsing, Assisted, Assisted Entry, Waiting, Billing, NA.\n"
        "Engagement Depth: Low, Medium, High, NA.\n"
        "Purchase Signal (Bag): Yes, No, NA.\n"
        "Prefer NA over guessing. Never invent continuity. Never output extra commentary.\n"
        "Return strict JSON only."
    )


def _vision_schema() -> dict[str, Any]:
    return {
        "name": "retail_post_relevance_eval",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"type": "string"},
                            "confidence": {"type": "number"},
                            "gender": {"type": "string"},
                            "age_band": {"type": "string"},
                            "bbox": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {"type": "number"},
                            },
                            "notes": {"type": "string"},
                        },
                        "required": ["label", "confidence", "gender", "age_band", "bbox", "notes"],
                    },
                },
                "image_notes": {"type": "string"},
            },
            "required": ["entities", "image_notes"],
        },
    }


def _sequence_schema() -> dict[str, Any]:
    row_props = {
        "Date": {"type": "string"},
        "Walk-in ID": {"type": "string"},
        "Group ID": {"type": "string"},
        "Role": {"type": "string"},
        "Entry Time": {"type": "string"},
        "Exit Time": {"type": "string"},
        "Time Spent (mins)": {"type": "string"},
        "Session Status": {"type": "string"},
        "Entry Type": {"type": "string"},
        "Gender": {"type": "string"},
        "Age Band": {"type": "string"},
        "Attire / Visual Marker": {"type": "string"},
        "Primary Clothing": {"type": "string"},
        "Jewellery Load": {"type": "string"},
        "Bag Type": {"type": "string"},
        "Primary Clothing Style Archetype": {"type": "string"},
        "Engagement Type": {"type": "string"},
        "Engagement Depth": {"type": "string"},
        "Purchase Signal (Bag)": {"type": "string"},
        "Included in Analytics": {"type": "string"},
    }
    return {
        "name": "retail_walkin_sequence_table",
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


def _extract_output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    output = payload.get("output", [])
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    chunk = content.get("text")
                    if isinstance(chunk, str):
                        parts.append(chunk)
        if parts:
            return "\n".join(parts).strip()
    return ""


def _normalize_table_cell(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "NA"


def _table_to_markdown(df: pd.DataFrame) -> str:
    columns = list(df.columns)
    if not columns:
        return ""
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join(["---"] * len(columns)) + "|"
    lines = [header, divider]
    for _, row in df.iterrows():
        cells = [str(row.get(col, "NA")).replace("\n", " ").strip() or "NA" for col in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _build_sequence_evidence(validation_df: pd.DataFrame, frame_df: pd.DataFrame) -> dict[str, Any]:
    frame_cols = [
        "capture_date",
        "camera_id",
        "image_name",
        "timestamp_or_sequence",
        "yolo_detected_people",
        "gpt_human_entities",
        "gpt_extra_detections",
        "customer_count",
        "staff_count",
        "banner_count",
        "pedestrian_count",
    ]
    val_cols = [
        "capture_date",
        "camera_id",
        "image_name",
        "timestamp_or_sequence",
        "entity_id",
        "gpt_label",
        "final_label",
        "reviewer_label",
        "yolo_detected",
        "gpt_extra_detection",
        "gender",
        "age_band",
        "bbox_x1",
        "bbox_y1",
        "bbox_x2",
        "bbox_y2",
        "notes",
    ]
    frames = frame_df[[c for c in frame_cols if c in frame_df.columns]].copy()
    frames = frames.sort_values(["capture_date", "timestamp_or_sequence", "image_name"], ascending=[True, True, True]).fillna("")
    entities = validation_df[[c for c in val_cols if c in validation_df.columns]].copy()
    entities = entities.sort_values(
        ["capture_date", "timestamp_or_sequence", "image_name", "entity_id"],
        ascending=[True, True, True, True],
    ).fillna("")
    return {
        "frame_count": int(len(frames)),
        "entity_count": int(len(entities)),
        "frames": frames.to_dict(orient="records"),
        "entities": entities.to_dict(orient="records"),
    }


def _call_gpt_sequence_table(
    *,
    api_key: str,
    api_base: str,
    model: str,
    sequence_evidence: dict[str, Any],
    timeout_seconds: int,
    max_retries: int,
    retry_sleep: float,
) -> pd.DataFrame:
    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _sequence_prompt()},
                    {
                        "type": "input_text",
                        "text": "SEQUENCE_EVIDENCE_JSON:\n"
                        + json.dumps(sequence_evidence, ensure_ascii=False, separators=(",", ":")),
                    },
                ],
            }
        ],
        "text": {"format": {"type": "json_schema", **_sequence_schema()}},
        "max_output_tokens": 3500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{api_base.rstrip('/')}/responses"
    attempts = max(1, int(max_retries))
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=int(timeout_seconds))
            if resp.status_code >= 400:
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise RuntimeError(f"OpenAI client error {resp.status_code}: {resp.text[:500]}")
                raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
            payload = resp.json()
            text = _extract_output_text(payload)
            if not text:
                raise RuntimeError("OpenAI sequence response did not include output text.")
            parsed = json.loads(text)
            rows = parsed.get("rows", [])
            if not isinstance(rows, list):
                raise RuntimeError("OpenAI sequence response 'rows' must be a list.")
            clean_rows: list[dict[str, str]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                clean_rows.append({col: _normalize_table_cell(row.get(col, "NA")) for col in WALKIN_TABLE_COLUMNS})
            return pd.DataFrame(clean_rows, columns=WALKIN_TABLE_COLUMNS)
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(float(retry_sleep) * float(attempt))
    raise RuntimeError("Unexpected GPT sequence table call state.")


def _call_gpt_entities(
    *,
    api_key: str,
    api_base: str,
    model: str,
    image_path: Path,
    timeout_seconds: int,
    max_retries: int,
    retry_sleep: float,
) -> dict[str, Any]:
    raw = image_path.read_bytes()
    ext = image_path.suffix.lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{base64.b64encode(raw).decode('ascii')}"
    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": _vision_prompt()},
                    {"type": "input_image", "image_url": data_uri},
                ],
            }
        ],
        "text": {"format": {"type": "json_schema", **_vision_schema()}},
        "max_output_tokens": 1300,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{api_base.rstrip('/')}/responses"

    attempts = max(1, int(max_retries))
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=int(timeout_seconds))
            if resp.status_code >= 400:
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    raise RuntimeError(f"OpenAI client error {resp.status_code}: {resp.text[:500]}")
                raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
            payload = resp.json()
            text = _extract_output_text(payload)
            if not text:
                raise RuntimeError("OpenAI response did not include output text.")
            return json.loads(text)
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(float(retry_sleep) * float(attempt))
    raise RuntimeError("Unexpected GPT call state.")


def _sorted_entities(raw_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox", [0.0, 0.0, 0.0, 0.0])
        if not isinstance(bbox, list) or len(bbox) != 4:
            bbox = [0.0, 0.0, 0.0, 0.0]
        x1, y1, x2, y2 = [max(0.0, min(1.0, _to_float(v, 0.0))) for v in bbox]
        normalized.append(
            {
                "label": _label_to_canonical(item.get("label", "UNKNOWN")),
                "confidence": max(0.0, min(1.0, _to_float(item.get("confidence", 0.0), 0.0))),
                "gender": str(item.get("gender", "unknown") or "unknown").strip().lower(),
                "age_band": str(item.get("age_band", "unknown") or "unknown").strip().lower(),
                "bbox_x1": x1,
                "bbox_y1": y1,
                "bbox_x2": x2,
                "bbox_y2": y2,
                "notes": str(item.get("notes", "") or "").strip(),
            }
        )
    normalized.sort(key=lambda e: (float(e["bbox_x1"]), float(e["bbox_y1"]), -float(e["bbox_y2"])))
    return normalized


def _annotate_image(
    image_path: Path,
    entity_rows: list[dict[str, Any]],
    out_path: Path,
) -> str:
    color_map = {
        "CUSTOMER": "#2a7fd9",
        "STAFF": "#e63946",
        "BANNER": "#ff9800",
        "PEDESTRIANS": "#607d8b",
        "PRODUCT": "#8e44ad",
        "INVALID": "#5f6368",
        "UNKNOWN": "#455a64",
    }
    with Image.open(image_path) as raw:
        canvas = raw.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    width, height = canvas.size
    stroke = max(2, int(round(min(width, height) * 0.004)))

    for row in entity_rows:
        x1 = max(0, min(width - 1, int(float(row.get("bbox_x1", 0.0)) * width)))
        y1 = max(0, min(height - 1, int(float(row.get("bbox_y1", 0.0)) * height)))
        x2 = max(x1 + 1, min(width, int(float(row.get("bbox_x2", 0.0)) * width)))
        y2 = max(y1 + 1, min(height, int(float(row.get("bbox_y2", 0.0)) * height)))
        final_label = str(row.get("final_label", "UNKNOWN") or "UNKNOWN").upper()
        color = color_map.get(final_label, "#455a64")
        tag = f"{str(row.get('entity_id', '')).upper()} {final_label}"
        if not bool(row.get("yolo_detected", False)):
            tag = f"{tag} GPT+"
        draw.rectangle((x1, y1, x2, y2), outline=color, width=stroke)
        text_bbox = draw.textbbox((0, 0), tag, font=font, stroke_width=1)
        tag_w = int(text_bbox[2] - text_bbox[0]) + 12
        tag_h = int(text_bbox[3] - text_bbox[1]) + 8
        tx = max(0, min(width - tag_w, x1))
        ty = max(0, y1 - tag_h - 2)
        if ty <= 0:
            ty = min(height - tag_h, y2 + 2)
        draw.rectangle((tx, ty, tx + tag_w, ty + tag_h), fill=color)
        draw.text((tx + 6, ty + 4), tag, fill="#ffffff", font=font, stroke_width=1, stroke_fill="#000000")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="JPEG", quality=90)
    return str(out_path.resolve())


def _build_yolo_vs_gpt(frame_df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    if frame_df.empty:
        return pd.DataFrame(), 0.0
    cmp_df = frame_df.copy()
    cmp_df["match"] = cmp_df["yolo_detected_people"] == cmp_df["gpt_human_entities"]
    accuracy = float(cmp_df["match"].mean() * 100.0) if len(cmp_df) > 0 else 0.0
    cmp_df["delta_people"] = cmp_df["gpt_human_entities"] - cmp_df["yolo_detected_people"]
    return (
        cmp_df[
            [
                "store_id",
                "capture_date",
                "camera_id",
                "image_name",
                "yolo_detected_people",
                "gpt_human_entities",
                "delta_people",
                "match",
            ]
        ].copy(),
        round(accuracy, 2),
    )


def _build_gpt_vs_reviewer(validation_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if validation_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    scoped = validation_df[validation_df["reviewer_label"].astype(str).str.strip() != ""].copy()
    if scoped.empty:
        return pd.DataFrame(), pd.DataFrame()
    scoped["match"] = scoped["gpt_label"] == scoped["reviewer_label"]
    detail = scoped[
        [
            "store_id",
            "capture_date",
            "camera_id",
            "image_name",
            "entity_id",
            "gpt_label",
            "reviewer_label",
            "final_label",
            "gpt_extra_detection",
            "match",
        ]
    ].copy()
    summary = pd.DataFrame(
        [
            {
                "store_id": str(scoped["store_id"].iloc[0]),
                "compared_entities": int(len(scoped)),
                "matched_entities": int(scoped["match"].sum()),
                "accuracy_pct": round(float(scoped["match"].mean() * 100.0), 2),
            }
        ]
    )
    return summary, detail


def main() -> None:
    args = _parse_args()
    store_id = str(args.store_id).strip()
    if not store_id:
        raise RuntimeError("store_id is required")

    api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    stage1_df = _load_stage1_rows(stage1_path=args.stage1_relevant.resolve(), store_id=store_id, limit=int(args.limit))
    feedback_memory = _load_feedback_memory(db_path=args.db.resolve(), store_id=store_id)

    out_dir = args.out_root.resolve() / store_id
    annotated_dir = out_dir / "annotated"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not bool(args.skip_annotate):
        annotated_dir.mkdir(parents=True, exist_ok=True)

    run_started = datetime.utcnow().isoformat() + "Z"
    validation_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []

    for _, src in stage1_df.iterrows():
        image_path = Path(str(src.get("image_path", "") or "").strip())
        image_name = str(src.get("image_name", image_path.name) or image_path.name).strip()
        if not image_path.exists():
            continue
        capture_date = _normalize_date(src.get("capture_date", ""))
        camera_id = str(src.get("camera_id", "") or "").strip().upper()
        if not camera_id:
            cam_match = CAMERA_PATTERN.search(image_name)
            camera_id = cam_match.group(1).upper() if cam_match else ""
        timestamp = str(src.get("timestamp", "") or "").strip()
        yolo_people = max(0, _to_int(src.get("person_count", 0), 0))

        try:
            gpt_raw = _call_gpt_entities(
                api_key=api_key,
                api_base=str(args.api_base),
                model=str(args.model),
                image_path=image_path,
                timeout_seconds=int(args.request_timeout),
                max_retries=int(args.max_retries),
                retry_sleep=float(args.retry_sleep),
            )
            entities = _sorted_entities(gpt_raw.get("entities", []))
            image_notes = str(gpt_raw.get("image_notes", "") or "").strip()
            gpt_error = ""
        except Exception as exc:
            entities = []
            image_notes = ""
            gpt_error = str(exc)

        if not entities:
            entities = [
                {
                    "label": "UNKNOWN",
                    "confidence": 0.0,
                    "gender": "unknown",
                    "age_band": "unknown",
                    "bbox_x1": 0.0,
                    "bbox_y1": 0.0,
                    "bbox_x2": 0.0,
                    "bbox_y2": 0.0,
                    "notes": gpt_error or "no_entities",
                }
            ]

        entity_rows_for_frame: list[dict[str, Any]] = []
        for idx, ent in enumerate(entities, start=1):
            entity_id = f"T{idx}"
            gpt_label = _label_to_canonical(ent.get("label", "UNKNOWN"))
            if gpt_label not in LABELS:
                gpt_label = "UNKNOWN"
            yolo_detected = bool(idx <= yolo_people)
            gpt_extra = not yolo_detected
            memory_key = (capture_date, camera_id, image_name, entity_id.upper())
            alt_memory_key = (capture_date, camera_id, image_name, str(idx))
            reviewer_label = feedback_memory.get(memory_key, feedback_memory.get(alt_memory_key, ""))
            reviewer_label = _label_to_canonical(reviewer_label) if reviewer_label else ""
            final_label = reviewer_label if reviewer_label else gpt_label
            is_reviewed = bool(reviewer_label)

            row = {
                "store_id": store_id,
                "Date": capture_date,
                "capture_date": capture_date,
                "camera_id": camera_id,
                "image_id": str(src.get("relative_path", image_name) or image_name),
                "image_name": image_name,
                "image_path": str(image_path.resolve()),
                "image_url": str(src.get("drive_link", "") or ""),
                "timestamp_or_sequence": timestamp,
                "entity_id": entity_id,
                "yolo_detected": bool(yolo_detected),
                "yolo_label": "PERSON" if yolo_detected else "",
                "gpt_detected": True,
                "gpt_label": gpt_label,
                "reviewer_label": reviewer_label,
                "final_label": final_label,
                "gpt_extra_detection": bool(gpt_extra),
                "is_reviewed": bool(is_reviewed),
                "confidence": float(ent.get("confidence", 0.0)),
                "gender": str(ent.get("gender", "unknown") or "unknown"),
                "age_band": str(ent.get("age_band", "unknown") or "unknown"),
                "bbox_x1": float(ent.get("bbox_x1", 0.0)),
                "bbox_y1": float(ent.get("bbox_y1", 0.0)),
                "bbox_x2": float(ent.get("bbox_x2", 0.0)),
                "bbox_y2": float(ent.get("bbox_y2", 0.0)),
                "notes": str(ent.get("notes", "") or ""),
                "image_notes": image_notes,
                "gpt_error": gpt_error,
            }
            validation_rows.append(row)
            entity_rows_for_frame.append(row)

        annotated_path = ""
        if not bool(args.skip_annotate):
            annotated_path = _annotate_image(
                image_path=image_path,
                entity_rows=entity_rows_for_frame,
                out_path=annotated_dir / image_name,
            )
        for row in entity_rows_for_frame:
            row["annotated_image_path"] = annotated_path

        frame_counter = defaultdict(int)
        gpt_human_entities = 0
        gpt_extra_count = 0
        for row in entity_rows_for_frame:
            final_label = str(row.get("final_label", "UNKNOWN") or "UNKNOWN").upper()
            frame_counter[final_label] += 1
            if final_label in {"CUSTOMER", "STAFF", "PEDESTRIANS"}:
                gpt_human_entities += 1
            if bool(row.get("gpt_extra_detection", False)):
                gpt_extra_count += 1

        frame_rows.append(
            {
                "store_id": store_id,
                "Date": capture_date,
                "capture_date": capture_date,
                "camera_id": camera_id,
                "image_name": image_name,
                "image_path": str(image_path.resolve()),
                "annotated_image_path": annotated_path,
                "timestamp_or_sequence": timestamp,
                "yolo_detected_people": yolo_people,
                "gpt_human_entities": int(gpt_human_entities),
                "gpt_extra_detections": int(gpt_extra_count),
                "customer_count": int(frame_counter.get("CUSTOMER", 0)),
                "staff_count": int(frame_counter.get("STAFF", 0)),
                "banner_count": int(frame_counter.get("BANNER", 0)),
                "pedestrian_count": int(frame_counter.get("PEDESTRIANS", 0)),
                "product_count": int(frame_counter.get("PRODUCT", 0)),
                "invalid_count": int(frame_counter.get("INVALID", 0)),
                "unknown_count": int(frame_counter.get("UNKNOWN", 0)),
            }
        )

    validation_df = pd.DataFrame(validation_rows)
    frame_df = pd.DataFrame(frame_rows)
    if validation_df.empty:
        raise RuntimeError("No GPT validation rows produced. Check Stage-1 input and image availability.")

    yolo_vs_gpt_df, yolo_vs_gpt_acc = _build_yolo_vs_gpt(frame_df)
    gpt_vs_reviewer_df, gpt_vs_reviewer_detail_df = _build_gpt_vs_reviewer(validation_df)
    sequence_table_error = ""
    sequence_table_df = pd.DataFrame(columns=WALKIN_TABLE_COLUMNS)
    try:
        sequence_evidence = _build_sequence_evidence(validation_df=validation_df, frame_df=frame_df)
        sequence_table_df = _call_gpt_sequence_table(
            api_key=api_key,
            api_base=str(args.api_base),
            model=str(args.model),
            sequence_evidence=sequence_evidence,
            timeout_seconds=int(args.request_timeout),
            max_retries=int(args.max_retries),
            retry_sleep=float(args.retry_sleep),
        )
    except Exception as exc:
        sequence_table_error = str(exc)
        sequence_table_df = pd.DataFrame(columns=WALKIN_TABLE_COLUMNS)

    if frame_df.empty:
        summary_df = pd.DataFrame(
            columns=[
                "store_id",
                "Date",
                "total_images",
                "relevant_images",
                "yolo_detected_people",
                "customer_count",
                "staff_count",
                "banner_count",
                "pedestrian_count",
                "estimated_visits",
                "avg_dwell_sec",
                "bounce_rate",
                "footfall",
                "los_alerts",
                "daily_walkins",
                "daily_conversions",
            ]
        )
    else:
        grouped = (
            frame_df.groupby(["store_id", "Date"], as_index=False)
            .agg(
                total_images=("image_name", "count"),
                relevant_images=("image_name", "count"),
                yolo_detected_people=("yolo_detected_people", "sum"),
                customer_count=("customer_count", "sum"),
                staff_count=("staff_count", "sum"),
                banner_count=("banner_count", "sum"),
                pedestrian_count=("pedestrian_count", "sum"),
            )
            .sort_values(["Date", "store_id"], ascending=[False, True])
            .reset_index(drop=True)
        )
        grouped["estimated_visits"] = grouped["customer_count"]
        grouped["avg_dwell_sec"] = 0.0
        grouped["bounce_rate"] = 0.0
        grouped["footfall"] = grouped["customer_count"]
        grouped["los_alerts"] = 0
        grouped["daily_walkins"] = grouped["customer_count"]
        grouped["daily_conversions"] = 0
        summary_df = grouped[
            [
                "store_id",
                "Date",
                "total_images",
                "relevant_images",
                "yolo_detected_people",
                "customer_count",
                "staff_count",
                "banner_count",
                "pedestrian_count",
                "estimated_visits",
                "avg_dwell_sec",
                "bounce_rate",
                "footfall",
                "los_alerts",
                "daily_walkins",
                "daily_conversions",
            ]
        ].copy()

    validation_path = out_dir / "gpt_validation_results.csv"
    frame_path = out_dir / "gpt_validation_frame_summary.csv"
    store_summary_path = out_dir / "gpt_store_date_summary.csv"
    yolo_vs_gpt_path = out_dir / "yolo_vs_gpt_accuracy.csv"
    gpt_vs_reviewer_path = out_dir / "gpt_vs_reviewer_accuracy.csv"
    gpt_vs_reviewer_detail_path = out_dir / "gpt_vs_reviewer_detail.csv"
    walkin_sequence_table_path = out_dir / "gpt_walkin_sequence_table.csv"
    walkin_sequence_markdown_path = out_dir / "gpt_walkin_sequence_table.md"

    validation_df.to_csv(validation_path, index=False)
    frame_df.to_csv(frame_path, index=False)
    summary_df.to_csv(store_summary_path, index=False)
    yolo_vs_gpt_df.to_csv(yolo_vs_gpt_path, index=False)
    gpt_vs_reviewer_df.to_csv(gpt_vs_reviewer_path, index=False)
    gpt_vs_reviewer_detail_df.to_csv(gpt_vs_reviewer_detail_path, index=False)
    sequence_table_df.to_csv(walkin_sequence_table_path, index=False)
    walkin_sequence_markdown_path.write_text(_table_to_markdown(sequence_table_df), encoding="utf-8")

    if bool(args.save_json):
        (out_dir / "gpt_validation_results.json").write_text(json.dumps(validation_df.to_dict(orient="records"), indent=2), encoding="utf-8")
        (out_dir / "gpt_store_date_summary.json").write_text(json.dumps(summary_df.to_dict(orient="records"), indent=2), encoding="utf-8")

    run_ended = datetime.utcnow().isoformat() + "Z"
    summary = {
        "run_note": str(args.run_note),
        "run_started_at": run_started,
        "run_ended_at": run_ended,
        "store_id": store_id,
        "images_selected": int(len(frame_df)),
        "entity_rows": int(len(validation_df)),
        "gpt_model": str(args.model),
        "yolo_vs_gpt_accuracy_pct": float(yolo_vs_gpt_acc),
        "gpt_vs_reviewer_compared_entities": int(gpt_vs_reviewer_df["compared_entities"].iloc[0]) if not gpt_vs_reviewer_df.empty else 0,
        "gpt_vs_reviewer_accuracy_pct": float(gpt_vs_reviewer_df["accuracy_pct"].iloc[0]) if not gpt_vs_reviewer_df.empty else None,
        "gpt_extra_detections": int(validation_df["gpt_extra_detection"].fillna(False).astype(bool).sum()),
        "walkin_sequence_rows": int(len(sequence_table_df)),
        "walkin_sequence_error": sequence_table_error,
        "outputs": {
            "gpt_validation_results_csv": str(validation_path.resolve()),
            "gpt_validation_frame_summary_csv": str(frame_path.resolve()),
            "gpt_store_date_summary_csv": str(store_summary_path.resolve()),
            "yolo_vs_gpt_accuracy_csv": str(yolo_vs_gpt_path.resolve()),
            "gpt_vs_reviewer_accuracy_csv": str(gpt_vs_reviewer_path.resolve()),
            "gpt_vs_reviewer_detail_csv": str(gpt_vs_reviewer_detail_path.resolve()),
            "gpt_walkin_sequence_table_csv": str(walkin_sequence_table_path.resolve()),
            "gpt_walkin_sequence_table_md": str(walkin_sequence_markdown_path.resolve()),
            "annotated_dir": str(annotated_dir.resolve()) if not bool(args.skip_annotate) else "",
        },
    }
    run_summary_path = out_dir / "gpt_pipeline_run_summary.json"
    run_summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["outputs"]["run_summary_json"] = str(run_summary_path.resolve())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

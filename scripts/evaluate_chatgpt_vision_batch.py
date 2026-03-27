from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any

import pandas as pd
import requests

from iris.store_registry import StoreRecord, sync_store_from_source

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_OUT_DIR = Path("data/exports/current/vision_eval")
DEFAULT_DATA_ROOT = Path("data/vision_eval")
DEFAULT_GROUND_TRUTH_KEYS = {
    "image_name": ("image_name", "filename", "image", "file_name"),
    "customer_count": ("customer_count", "valid_customers", "customers"),
    "purchased_count": ("purchased_count", "purchased", "red_bag_customers"),
    "gender": ("gender", "primary_gender"),
    "age_band": ("age_band", "primary_age_band"),
    "final_label": ("final_label", "expected_final_label"),
    "final_labels": ("final_labels", "labels", "expected_labels"),
}


@dataclass
class EvalConfig:
    model: str = DEFAULT_MODEL
    max_output_tokens: int = 1500
    request_timeout_seconds: int = 90
    max_retries: int = 3
    retry_sleep_seconds: float = 2.0
    red_bag_terms: tuple[str, ...] = ("red bag", "red handbag", "red shopping bag", "red carry bag")
    banner_labels: tuple[str, ...] = (
        "banner",
        "poster",
        "standee",
        "printed_human",
        "printed-human",
        "mannequin",
    )
    outside_labels: tuple[str, ...] = ("pedestrian", "outside_passer", "passerby", "passer")
    product_labels: tuple[str, ...] = ("product", "merchandise")
    staff_labels: tuple[str, ...] = ("staff",)
    customer_labels: tuple[str, ...] = ("customer", "person", "shopper")
    enable_staff_repeat_pattern: bool = True
    staff_repeat_min_images: int = 3
    carry_forward_max_center_distance: float = 0.15
    carry_forward_max_sequence_gap: int = 4


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch retail evaluation using ChatGPT vision + business rules.")
    parser.add_argument("--gdrive-url", required=True, help="Google Drive folder URL (root folder, recursive sync).")
    parser.add_argument("--ground-truth", type=Path, required=True, help="Path to manual ground truth CSV/JSON.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--store-id", default="TEST_STORE_D07")
    parser.add_argument("--limit", type=int, default=30, help="Number of images to evaluate after sorting.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI vision-capable model.")
    parser.add_argument("--api-base", default="https://api.openai.com/v1")
    parser.add_argument("--config", type=Path, default=None, help="Optional JSON config overrides.")
    parser.add_argument("--skip-sync", action="store_true", help="Use already-downloaded local images, skip gdrive sync.")
    parser.add_argument("--save-json", action="store_true", help="Also write JSON outputs in addition to CSV.")
    parser.add_argument(
        "--create-ground-truth-template",
        action="store_true",
        help="Create a ground-truth CSV template from selected images and exit.",
    )
    return parser.parse_args()


def _load_config(args: argparse.Namespace) -> EvalConfig:
    cfg = EvalConfig(model=str(args.model or DEFAULT_MODEL).strip() or DEFAULT_MODEL)
    if args.config is None:
        return cfg
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    for key, value in payload.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y"}


def _normalize_label(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(" ", "_")
    text = text.replace("-", "_")
    return text


def _normalize_image_name(value: object) -> str:
    return Path(str(value or "").strip()).name.strip()


def _parse_filename_metadata(path: Path, sequence: int) -> dict[str, str]:
    filename = path.name
    camera_match = re.search(r"_([A-Za-z]\\d{2})[-_]", filename)
    camera_id = camera_match.group(1).upper() if camera_match else ""
    time_match = re.match(r"(\\d{2}-\\d{2}-\\d{2})_", filename)
    hhmmss = time_match.group(1).replace("-", ":") if time_match else ""
    date_guess = ""
    for part in path.parts:
        if re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", part):
            date_guess = part
            break
    timestamp = f"{date_guess} {hhmmss}".strip()
    if not timestamp:
        timestamp = str(sequence)
    return {
        "image_name": filename,
        "camera_id": camera_id,
        "timestamp_or_sequence": timestamp,
    }


def _encode_image_data_uri(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if ext == "jpg" else ext
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def _vision_prompt() -> str:
    return (
        "You are analyzing a retail-store still image. Detect visible entities and output strict JSON only. "
        "Do not include markdown.\n\n"
        "Entity rules:\n"
        "- Include people and person-like visuals (real humans, posters, mannequins, standees).\n"
        "- Include obvious product-only objects if they could be mistaken for people-related detections.\n"
        "- For each entity, infer: raw_label, inside_or_outside, red_bag_detected, gender, age_band, confidence, notes.\n"
        "- raw_label must be one of: customer, staff, pedestrian, outside_passer, banner, poster, standee, printed_human, mannequin, product, unknown.\n"
        "- inside_or_outside must be one of: inside, outside, unknown.\n"
        "- gender must be one of: male, female, unknown.\n"
        "- age_band must be one of: child, teen, young_adult, adult, senior, unknown.\n"
        "- If entity is printed human / poster / standee, set is_printed_human=true.\n"
        "- If entity is product-only, set is_product_only=true.\n"
        "- Bounding box coordinates should be normalized [x1, y1, x2, y2], each value in [0,1].\n\n"
        "Output schema keys exactly:\n"
        "{\n"
        "  \"entities\": [\n"
        "    {\n"
        "      \"entity_local_id\": \"e1\",\n"
        "      \"raw_label\": \"customer\",\n"
        "      \"inside_or_outside\": \"inside\",\n"
        "      \"is_printed_human\": false,\n"
        "      \"is_product_only\": false,\n"
        "      \"red_bag_detected\": false,\n"
        "      \"likely_staff\": false,\n"
        "      \"gender\": \"female\",\n"
        "      \"age_band\": \"adult\",\n"
        "      \"bbox\": [0.1,0.1,0.4,0.8],\n"
        "      \"confidence\": 0.82,\n"
        "      \"notes\": \"short reason\"\n"
        "    }\n"
        "  ],\n"
        "  \"notes\": \"short image-level notes\"\n"
        "}"
    )


def _json_schema() -> dict[str, Any]:
    return {
        "name": "retail_image_eval",
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
                            "entity_local_id": {"type": "string"},
                            "raw_label": {"type": "string"},
                            "inside_or_outside": {"type": "string"},
                            "is_printed_human": {"type": "boolean"},
                            "is_product_only": {"type": "boolean"},
                            "red_bag_detected": {"type": "boolean"},
                            "likely_staff": {"type": "boolean"},
                            "gender": {"type": "string"},
                            "age_band": {"type": "string"},
                            "bbox": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {"type": "number"},
                            },
                            "confidence": {"type": "number"},
                            "notes": {"type": "string"},
                        },
                        "required": [
                            "entity_local_id",
                            "raw_label",
                            "inside_or_outside",
                            "is_printed_human",
                            "is_product_only",
                            "red_bag_detected",
                            "likely_staff",
                            "gender",
                            "age_band",
                            "bbox",
                            "confidence",
                            "notes",
                        ],
                    },
                },
                "notes": {"type": "string"},
            },
            "required": ["entities", "notes"],
        },
    }


def _extract_output_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str) and payload.get("output_text"):
        return str(payload["output_text"])
    output = payload.get("output", [])
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            for content in item.get("content", []) if isinstance(item, dict) else []:
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    return ""


def _call_openai_vision(
    *,
    api_base: str,
    api_key: str,
    model: str,
    image_path: Path,
    cfg: EvalConfig,
) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/responses"
    data_uri = _encode_image_data_uri(image_path)
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
        "text": {"format": {"type": "json_schema", "json_schema": _json_schema()}},
        "max_output_tokens": int(cfg.max_output_tokens),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    attempts = max(1, int(cfg.max_retries))
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=int(cfg.request_timeout_seconds))
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text[:500]}")
            payload = resp.json()
            text = _extract_output_text(payload)
            if not text:
                raise RuntimeError("OpenAI response did not include parseable output_text.")
            return json.loads(text)
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(float(cfg.retry_sleep_seconds) * attempt)
    raise RuntimeError("Unexpected call state.")


def _collect_images(local_store_dir: Path, limit: int) -> list[Path]:
    images = [p for p in local_store_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    images.sort(key=lambda p: str(p.relative_to(local_store_dir)).lower())
    if limit > 0:
        images = images[:limit]
    return images


def _apply_business_rules(entities: list[dict[str, Any]], cfg: EvalConfig) -> list[dict[str, Any]]:
    banner_set = {_normalize_label(x) for x in cfg.banner_labels}
    outside_set = {_normalize_label(x) for x in cfg.outside_labels}
    product_set = {_normalize_label(x) for x in cfg.product_labels}
    staff_set = {_normalize_label(x) for x in cfg.staff_labels}
    customer_set = {_normalize_label(x) for x in cfg.customer_labels}

    out: list[dict[str, Any]] = []
    for idx, entity in enumerate(entities, start=1):
        raw_label = _normalize_label(entity.get("raw_label", "unknown"))
        inside = _normalize_label(entity.get("inside_or_outside", "unknown")) or "unknown"
        is_printed = _safe_bool(entity.get("is_printed_human"))
        is_product_only = _safe_bool(entity.get("is_product_only"))
        likely_staff = _safe_bool(entity.get("likely_staff"))
        red_bag = _safe_bool(entity.get("red_bag_detected"))
        confidence = max(0.0, min(1.0, _safe_float(entity.get("confidence", 0.0), 0.0)))
        bbox = entity.get("bbox", [0.0, 0.0, 0.0, 0.0])
        if not isinstance(bbox, list) or len(bbox) != 4:
            bbox = [0.0, 0.0, 0.0, 0.0]
        bbox = [max(0.0, min(1.0, _safe_float(v, 0.0))) for v in bbox]

        final_label = "customer"
        excluded_reason = ""
        if is_printed or raw_label in banner_set:
            final_label = "banner"
            excluded_reason = "printed_human_or_banner"
        elif inside == "outside" or raw_label in outside_set:
            final_label = "pedestrians"
            excluded_reason = "outside_or_passer"
        elif is_product_only or raw_label in product_set:
            final_label = "product"
            excluded_reason = "product_only"
        elif likely_staff or raw_label in staff_set:
            final_label = "staff"
            excluded_reason = "staff_candidate"
        elif raw_label in customer_set or raw_label == "unknown":
            final_label = "customer"
        else:
            final_label = "unknown"
            excluded_reason = "unknown_label"

        out.append(
            {
                "entity_local_id": str(entity.get("entity_local_id", f"e{idx}") or f"e{idx}"),
                "raw_label": raw_label,
                "final_label": final_label,
                "inside_or_outside": inside,
                "excluded_reason": excluded_reason,
                "red_bag_detected": bool(red_bag),
                "gender": _normalize_label(entity.get("gender", "unknown")) or "unknown",
                "age_band": _normalize_label(entity.get("age_band", "unknown")) or "unknown",
                "confidence": float(confidence),
                "notes": str(entity.get("notes", "") or "").strip(),
                "bbox_x1": float(bbox[0]),
                "bbox_y1": float(bbox[1]),
                "bbox_x2": float(bbox[2]),
                "bbox_y2": float(bbox[3]),
            }
        )
    return out


def _bbox_center(entity: dict[str, Any]) -> tuple[float, float]:
    x = (float(entity.get("bbox_x1", 0.0)) + float(entity.get("bbox_x2", 0.0))) / 2.0
    y = (float(entity.get("bbox_y1", 0.0)) + float(entity.get("bbox_y2", 0.0))) / 2.0
    return x, y


def _assign_customer_ids(rows: list[dict[str, Any]], cfg: EvalConfig, store_id: str) -> None:
    counters: dict[tuple[str, str], int] = defaultdict(int)
    track_state: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def _distance(a: dict[str, Any], b: dict[str, Any]) -> float:
        ax, ay = _bbox_center(a)
        bx, by = _bbox_center(b)
        return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

    rows.sort(key=lambda r: (str(r.get("camera_id", "")), str(r.get("capture_date", "")), int(r.get("_sequence", 0))))
    for row in rows:
        row["entity_id"] = ""
        if str(row.get("final_label", "")) != "customer":
            continue
        camera = str(row.get("camera_id", "") or "UNK")
        day = str(row.get("capture_date", "") or "no_date")
        key = (camera, day)
        seq = int(row.get("_sequence", 0))
        candidates = [
            s
            for s in track_state[key]
            if seq - int(s.get("last_sequence", -9999)) <= int(cfg.carry_forward_max_sequence_gap)
        ]
        best = None
        best_dist = 999.0
        for state in candidates:
            if state.get("gender") not in {"", "unknown"} and row.get("gender") not in {"", "unknown"}:
                if str(state.get("gender")) != str(row.get("gender")):
                    continue
            if state.get("age_band") not in {"", "unknown"} and row.get("age_band") not in {"", "unknown"}:
                if str(state.get("age_band")) != str(row.get("age_band")):
                    continue
            dist = _distance(row, state)
            if dist < best_dist:
                best_dist = dist
                best = state
        if best is not None and best_dist <= float(cfg.carry_forward_max_center_distance):
            row["entity_id"] = str(best["entity_id"])
            best.update(
                {
                    "bbox_x1": row["bbox_x1"],
                    "bbox_y1": row["bbox_y1"],
                    "bbox_x2": row["bbox_x2"],
                    "bbox_y2": row["bbox_y2"],
                    "last_sequence": seq,
                    "gender": row.get("gender", "unknown"),
                    "age_band": row.get("age_band", "unknown"),
                }
            )
        else:
            counters[key] += 1
            new_id = f"{store_id}_{camera}_{day}_{counters[key]:04d}"
            row["entity_id"] = new_id
            track_state[key].append(
                {
                    "entity_id": new_id,
                    "bbox_x1": row["bbox_x1"],
                    "bbox_y1": row["bbox_y1"],
                    "bbox_x2": row["bbox_x2"],
                    "bbox_y2": row["bbox_y2"],
                    "last_sequence": seq,
                    "gender": row.get("gender", "unknown"),
                    "age_band": row.get("age_band", "unknown"),
                }
            )


def _apply_staff_repeat_pattern(rows: list[dict[str, Any]], cfg: EvalConfig) -> None:
    if not cfg.enable_staff_repeat_pattern:
        return
    candidate_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row.get("final_label") == "staff":
            key = (str(row.get("camera_id", "")), str(row.get("entity_id", "")))
            candidate_counts[key] += 1
    for row in rows:
        if row.get("final_label") != "customer":
            continue
        entity_id = str(row.get("entity_id", ""))
        if not entity_id:
            continue
        key = (str(row.get("camera_id", "")), entity_id)
        if candidate_counts.get(key, 0) >= int(cfg.staff_repeat_min_images):
            row["final_label"] = "staff"
            row["excluded_reason"] = "staff_repeat_pattern"


def _write_ground_truth_template(path: Path, image_paths: list[Path]) -> None:
    rows = []
    for image_path in image_paths:
        rows.append(
            {
                "image_name": image_path.name,
                "customer_count": "",
                "purchased_count": "",
                "gender": "",
                "age_band": "",
                "final_label": "",
                "final_labels": "",
                "notes": "",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).drop_duplicates(subset=["image_name"], keep="first").to_csv(path, index=False)


def _load_ground_truth(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {path}")
    if path.suffix.lower() in {".json"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rows = payload.get("rows", [])
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
        gt_df = pd.DataFrame(rows)
    else:
        gt_df = pd.read_csv(path)
    if gt_df.empty:
        return {}

    col_map: dict[str, str] = {}
    available = {str(c).strip().lower(): c for c in gt_df.columns}
    for canonical, options in DEFAULT_GROUND_TRUTH_KEYS.items():
        for option in options:
            if option.lower() in available:
                col_map[canonical] = available[option.lower()]
                break
    if "image_name" not in col_map:
        raise ValueError("Ground truth must include one image-name column (image_name/filename/image/file_name).")

    out: dict[str, dict[str, Any]] = {}
    for _, row in gt_df.iterrows():
        image_name = _normalize_image_name(row.get(col_map["image_name"], ""))
        if not image_name:
            continue
        mapped: dict[str, Any] = {"image_name": image_name}
        for key, source_col in col_map.items():
            mapped[key] = row.get(source_col, "")
        out[image_name] = mapped
    return out


def _aggregate_image_summary(entity_rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not entity_rows:
        return pd.DataFrame()
    df = pd.DataFrame(entity_rows).copy()
    grouped = []
    for image_name, part in df.groupby("image_name", sort=False):
        valid_customers = part[(part["final_label"] == "customer") & (part["inside_or_outside"] != "outside")]
        purchased = valid_customers[valid_customers["red_bag_detected"] == True]
        genders = [str(v) for v in valid_customers["gender"].tolist() if str(v) not in {"", "unknown"}]
        ages = [str(v) for v in valid_customers["age_band"].tolist() if str(v) not in {"", "unknown"}]
        dominant_gender = Counter(genders).most_common(1)[0][0] if genders else "unknown"
        dominant_age = Counter(ages).most_common(1)[0][0] if ages else "unknown"
        labels_sorted = sorted({str(v) for v in part["final_label"].tolist() if str(v)})
        grouped.append(
            {
                "image_name": image_name,
                "camera_id": str(part.iloc[0].get("camera_id", "")),
                "timestamp_or_sequence": str(part.iloc[0].get("timestamp_or_sequence", "")),
                "customer_count": int(len(valid_customers)),
                "purchased_count": int(len(purchased)),
                "dominant_gender": dominant_gender,
                "dominant_age_band": dominant_age,
                "predicted_final_labels": "|".join(labels_sorted),
                "predicted_primary_label": labels_sorted[0] if labels_sorted else "unknown",
            }
        )
    return pd.DataFrame(grouped)


def _compare_with_ground_truth(summary_df: pd.DataFrame, gt_map: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if summary_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    merged_rows: list[dict[str, Any]] = []
    for _, row in summary_df.iterrows():
        image_name = str(row.get("image_name", ""))
        gt = gt_map.get(image_name, {})
        merged_rows.append(
            {
                "image_name": image_name,
                "camera_id": row.get("camera_id", ""),
                "timestamp_or_sequence": row.get("timestamp_or_sequence", ""),
                "pred_customer_count": int(row.get("customer_count", 0) or 0),
                "gt_customer_count": gt.get("customer_count", ""),
                "pred_purchased_count": int(row.get("purchased_count", 0) or 0),
                "gt_purchased_count": gt.get("purchased_count", ""),
                "pred_gender": row.get("dominant_gender", ""),
                "gt_gender": str(gt.get("gender", "") or "").strip().lower(),
                "pred_age_band": row.get("dominant_age_band", ""),
                "gt_age_band": str(gt.get("age_band", "") or "").strip().lower(),
                "pred_primary_label": str(row.get("predicted_primary_label", "") or "").strip().lower(),
                "gt_primary_label": str(gt.get("final_label", "") or "").strip().lower(),
                "pred_final_labels": str(row.get("predicted_final_labels", "") or ""),
                "gt_final_labels": str(gt.get("final_labels", "") or ""),
            }
        )
    merged_df = pd.DataFrame(merged_rows)
    if merged_df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def _as_int(value: object) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return int(float(text))
        except Exception:
            return None

    mismatch_rows: list[dict[str, Any]] = []
    field_stats: list[dict[str, Any]] = []
    checks = [
        ("customer_count", "pred_customer_count", "gt_customer_count"),
        ("purchased_count", "pred_purchased_count", "gt_purchased_count"),
        ("gender", "pred_gender", "gt_gender"),
        ("age_band", "pred_age_band", "gt_age_band"),
        ("primary_label", "pred_primary_label", "gt_primary_label"),
    ]

    for field_name, pred_col, gt_col in checks:
        compared = 0
        matched = 0
        for _, row in merged_df.iterrows():
            pred = row.get(pred_col, "")
            gt = row.get(gt_col, "")
            if field_name in {"customer_count", "purchased_count"}:
                gt_int = _as_int(gt)
                if gt_int is None:
                    continue
                compared += 1
                if int(pred) == int(gt_int):
                    matched += 1
                else:
                    mismatch_rows.append(
                        {
                            "image_name": row["image_name"],
                            "field": field_name,
                            "predicted": pred,
                            "ground_truth": gt_int,
                            "camera_id": row["camera_id"],
                        }
                    )
            else:
                gt_text = str(gt or "").strip().lower()
                if not gt_text:
                    continue
                compared += 1
                if str(pred or "").strip().lower() == gt_text:
                    matched += 1
                else:
                    mismatch_rows.append(
                        {
                            "image_name": row["image_name"],
                            "field": field_name,
                            "predicted": pred,
                            "ground_truth": gt_text,
                            "camera_id": row["camera_id"],
                        }
                    )
        field_stats.append(
            {
                "field": field_name,
                "compared_rows": compared,
                "matched_rows": matched,
                "accuracy_pct": round((matched / compared * 100.0), 2) if compared > 0 else None,
            }
        )

    confusion_rows: list[dict[str, Any]] = []
    subset = merged_df[
        (merged_df["gt_primary_label"].astype(str).str.strip() != "")
        & (merged_df["pred_primary_label"].astype(str).str.strip() != "")
    ].copy()
    if not subset.empty:
        grouped = subset.groupby(["gt_primary_label", "pred_primary_label"], as_index=False).size()
        for _, row in grouped.iterrows():
            confusion_rows.append(
                {
                    "ground_truth_label": str(row["gt_primary_label"]),
                    "predicted_label": str(row["pred_primary_label"]),
                    "count": int(row["size"]),
                }
            )

    mismatch_df = pd.DataFrame(mismatch_rows)
    accuracy_df = pd.DataFrame(field_stats)
    confusion_df = pd.DataFrame(confusion_rows)
    return mismatch_df, accuracy_df, confusion_df


def _to_markdown_summary(
    *,
    run_at: str,
    store_id: str,
    image_count: int,
    entity_rows: int,
    accuracy_df: pd.DataFrame,
    mismatch_df: pd.DataFrame,
    model: str,
) -> str:
    lines = [
        f"# Vision Evaluation Report ({store_id})",
        "",
        f"- Run at: `{run_at}`",
        f"- Model: `{model}`",
        f"- Images evaluated: `{image_count}`",
        f"- Entity rows: `{entity_rows}`",
        f"- Mismatch rows: `{len(mismatch_df)}`",
        "",
        "## Field Accuracy",
    ]
    if accuracy_df.empty:
        lines.append("- No comparable ground-truth fields found.")
    else:
        for _, row in accuracy_df.iterrows():
            lines.append(
                f"- `{row['field']}`: compared={int(row['compared_rows'])}, "
                f"matched={int(row['matched_rows'])}, accuracy={row['accuracy_pct']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = _parse_args()
    cfg = _load_config(args)
    run_at = _now_utc()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    out_dir = Path(args.out_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)

    store_id = str(args.store_id).strip()
    now = _now_utc()
    store_record = StoreRecord(
        store_id=store_id,
        store_name=store_id,
        email="vision-eval@local",
        drive_folder_url=str(args.gdrive_url).strip(),
        created_at=now,
        updated_at=now,
    )

    sync_ok = True
    sync_msg = "sync skipped"
    if not bool(args.skip_sync):
        sync_ok, sync_msg = sync_store_from_source(store=store_record, data_root=data_root, db_path=None)
        if not sync_ok:
            raise RuntimeError(f"Drive sync failed: {sync_msg}")
    local_store_dir = data_root / store_id
    if not local_store_dir.exists():
        raise RuntimeError(f"Local store image directory does not exist: {local_store_dir}")

    image_paths = _collect_images(local_store_dir, int(args.limit))
    if not image_paths:
        raise RuntimeError(f"No images found under: {local_store_dir}")

    gt_path = Path(args.ground_truth).expanduser().resolve()
    if not gt_path.exists():
        if bool(args.create_ground_truth_template):
            _write_ground_truth_template(gt_path, image_paths)
            print(
                json.dumps(
                    {
                        "status": "template_created",
                        "ground_truth_template": str(gt_path),
                        "images_in_template": len(image_paths),
                    },
                    indent=2,
                )
            )
            return
        raise FileNotFoundError(
            f"Ground truth file not found: {gt_path}. "
            "Run once with --create-ground-truth-template to generate a fillable CSV."
        )
    gt_map = _load_ground_truth(gt_path)

    entity_rows: list[dict[str, Any]] = []
    for seq, image_path in enumerate(image_paths, start=1):
        meta = _parse_filename_metadata(image_path, sequence=seq)
        try:
            raw_resp = _call_openai_vision(
                api_base=str(args.api_base),
                api_key=api_key,
                model=str(cfg.model),
                image_path=image_path,
                cfg=cfg,
            )
            entities = raw_resp.get("entities", [])
            if not isinstance(entities, list):
                entities = []
            normalized = _apply_business_rules(entities, cfg)
            image_level_note = str(raw_resp.get("notes", "") or "").strip()
        except Exception as exc:
            normalized = []
            image_level_note = f"vision_error: {exc}"

        if not normalized:
            normalized = [
                {
                    "entity_local_id": "",
                    "raw_label": "unknown",
                    "final_label": "unknown",
                    "inside_or_outside": "unknown",
                    "excluded_reason": "no_entities",
                    "red_bag_detected": False,
                    "gender": "unknown",
                    "age_band": "unknown",
                    "confidence": 0.0,
                    "notes": image_level_note,
                    "bbox_x1": 0.0,
                    "bbox_y1": 0.0,
                    "bbox_x2": 0.0,
                    "bbox_y2": 0.0,
                }
            ]

        for idx, entity in enumerate(normalized, start=1):
            row = {
                "store_id": store_id,
                "image_name": meta["image_name"],
                "camera_id": meta["camera_id"],
                "capture_date": str(meta["timestamp_or_sequence"]).split(" ")[0] if " " in meta["timestamp_or_sequence"] else "",
                "timestamp_or_sequence": meta["timestamp_or_sequence"],
                "_sequence": seq,
                "entity_local_id": entity.get("entity_local_id", f"e{idx}") or f"e{idx}",
                "raw_label": entity.get("raw_label", "unknown"),
                "final_label": entity.get("final_label", "unknown"),
                "red_bag_detected": bool(entity.get("red_bag_detected", False)),
                "gender": entity.get("gender", "unknown"),
                "age_band": entity.get("age_band", "unknown"),
                "inside_or_outside": entity.get("inside_or_outside", "unknown"),
                "excluded_reason": entity.get("excluded_reason", ""),
                "confidence": float(entity.get("confidence", 0.0)),
                "notes": entity.get("notes", "") or image_level_note,
                "bbox_x1": float(entity.get("bbox_x1", 0.0)),
                "bbox_y1": float(entity.get("bbox_y1", 0.0)),
                "bbox_x2": float(entity.get("bbox_x2", 0.0)),
                "bbox_y2": float(entity.get("bbox_y2", 0.0)),
                "source_path": str(image_path),
            }
            entity_rows.append(row)

    _assign_customer_ids(entity_rows, cfg, store_id=store_id)
    _apply_staff_repeat_pattern(entity_rows, cfg)

    entity_df = pd.DataFrame(entity_rows)
    if entity_df.empty:
        raise RuntimeError("No entity rows produced.")

    image_summary_df = _aggregate_image_summary(entity_rows)
    if not image_summary_df.empty:
        idx_df = image_summary_df.set_index("image_name")
        entity_df["customer_count"] = entity_df["image_name"].map(idx_df["customer_count"]).fillna(0).astype(int)
        entity_df["purchased_count"] = entity_df["image_name"].map(idx_df["purchased_count"]).fillna(0).astype(int)
    else:
        entity_df["customer_count"] = 0
        entity_df["purchased_count"] = 0

    mismatch_df, accuracy_df, confusion_df = _compare_with_ground_truth(image_summary_df, gt_map)

    image_results_path = out_dir / "image_results.csv"
    summary_path = out_dir / "accuracy_summary.csv"
    mismatch_path = out_dir / "mismatch_report.csv"
    confusion_path = out_dir / "confusion_breakdown.csv"
    image_summary_path = out_dir / "image_summary.csv"
    markdown_path = out_dir / "evaluation_report.md"

    required_fields = [
        "image_name",
        "camera_id",
        "timestamp_or_sequence",
        "entity_id",
        "raw_label",
        "final_label",
        "customer_count",
        "purchased_count",
        "red_bag_detected",
        "gender",
        "age_band",
        "inside_or_outside",
        "excluded_reason",
        "confidence",
        "notes",
    ]
    entity_df["entity_id"] = entity_df["entity_id"].fillna("").astype(str)
    export_df = entity_df.copy()
    for field in required_fields:
        if field not in export_df.columns:
            export_df[field] = ""
    export_df = export_df[required_fields]
    export_df.to_csv(image_results_path, index=False)
    image_summary_df.to_csv(image_summary_path, index=False)
    accuracy_df.to_csv(summary_path, index=False)
    mismatch_df.to_csv(mismatch_path, index=False)
    confusion_df.to_csv(confusion_path, index=False)

    markdown = _to_markdown_summary(
        run_at=run_at,
        store_id=store_id,
        image_count=len(image_paths),
        entity_rows=len(export_df),
        accuracy_df=accuracy_df,
        mismatch_df=mismatch_df,
        model=cfg.model,
    )
    markdown_path.write_text(markdown, encoding="utf-8")

    if bool(args.save_json):
        (out_dir / "image_results.json").write_text(
            json.dumps(export_df.to_dict(orient="records"), indent=2),
            encoding="utf-8",
        )
        (out_dir / "accuracy_summary.json").write_text(
            json.dumps(accuracy_df.to_dict(orient="records"), indent=2),
            encoding="utf-8",
        )
        (out_dir / "mismatch_report.json").write_text(
            json.dumps(mismatch_df.to_dict(orient="records"), indent=2),
            encoding="utf-8",
        )
        (out_dir / "confusion_breakdown.json").write_text(
            json.dumps(confusion_df.to_dict(orient="records"), indent=2),
            encoding="utf-8",
        )

    overall_field_accuracy = None
    if not accuracy_df.empty:
        valid = accuracy_df.dropna(subset=["accuracy_pct"]).copy()
        if not valid.empty:
            overall_field_accuracy = round(float(valid["accuracy_pct"].mean()), 2)

    summary = {
        "run_at": run_at,
        "store_id": store_id,
        "sync_ok": sync_ok,
        "sync_message": sync_msg,
        "images_scanned": len(image_paths),
        "entity_rows": len(export_df),
        "ground_truth_rows": len(gt_map),
        "overall_field_accuracy_pct": overall_field_accuracy,
        "files": {
            "image_results_csv": str(image_results_path.resolve()),
            "image_summary_csv": str(image_summary_path.resolve()),
            "accuracy_summary_csv": str(summary_path.resolve()),
            "mismatch_report_csv": str(mismatch_path.resolve()),
            "confusion_breakdown_csv": str(confusion_path.resolve()),
            "markdown_report": str(markdown_path.resolve()),
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

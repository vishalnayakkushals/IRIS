from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image


ZONE_INSIDE = "INSIDE_STORE_ZONE"
ZONE_CENTER = "CENTER_ENTRY_ZONE"
ZONE_LEFT_OUTSIDE = "LEFT_OUTSIDE_IGNORE_ZONE"
ZONE_RIGHT_OUTSIDE = "RIGHT_OUTSIDE_IGNORE_ZONE"
ZONE_POSTER = "POSTER_STATIC_ZONE"
ZONE_UNKNOWN = "UNKNOWN"

OUTSIDE_ZONES = {ZONE_LEFT_OUTSIDE, ZONE_RIGHT_OUTSIDE}


@dataclass(frozen=True)
class EntranceZoneConfig:
    inside_store_zone: list[tuple[float, float]]
    center_entry_zone: list[tuple[float, float]]
    left_outside_ignore_zone: list[tuple[float, float]]
    right_outside_ignore_zone: list[tuple[float, float]]
    poster_static_zone: list[tuple[float, float]]


def _safe_json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                return decoded
        except Exception:
            return []
    return []


def _parse_box_list(value: object) -> list[tuple[float, float, float, float]]:
    out: list[tuple[float, float, float, float]] = []
    for item in _safe_json_list(value):
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            continue
        try:
            x1 = float(item[0])  # type: ignore[index]
            y1 = float(item[1])  # type: ignore[index]
            x2 = float(item[2])  # type: ignore[index]
            y2 = float(item[3])  # type: ignore[index]
        except Exception:
            continue
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))
        x2 = max(0.0, min(1.0, x2))
        y2 = max(0.0, min(1.0, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        out.append((x1, y1, x2, y2))
    return out


def _parse_int_list(value: object) -> list[int]:
    out: list[int] = []
    for item in _safe_json_list(value):
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _parse_float_list(value: object, expected: int) -> list[float]:
    out: list[float] = []
    for item in _safe_json_list(value):
        try:
            out.append(float(item))
        except Exception:
            out.append(0.0)
    if len(out) < expected:
        out.extend([0.0] * (expected - len(out)))
    return out[:expected]


def _coerce_polygon(value: object) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    raw_points = _safe_json_list(value)
    if not raw_points and isinstance(value, str):
        try:
            parsed = json.loads(value)
            raw_points = parsed if isinstance(parsed, list) else []
        except Exception:
            raw_points = []
    for point in raw_points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            x = max(0.0, min(1.0, float(point[0])))  # type: ignore[index]
            y = max(0.0, min(1.0, float(point[1])))  # type: ignore[index]
        except Exception:
            continue
        points.append((x, y))
    return points


def _default_zone_config() -> EntranceZoneConfig:
    return EntranceZoneConfig(
        inside_store_zone=[(0.20, 0.34), (0.80, 0.34), (0.88, 1.0), (0.12, 1.0)],
        center_entry_zone=[(0.42, 0.08), (0.58, 0.08), (0.62, 0.55), (0.38, 0.55)],
        left_outside_ignore_zone=[(0.0, 0.0), (0.34, 0.0), (0.34, 0.78), (0.0, 0.78)],
        right_outside_ignore_zone=[(0.66, 0.0), (1.0, 0.0), (1.0, 0.78), (0.66, 0.78)],
        poster_static_zone=[],
    )


def _zone_config_from_camera(camera_cfg: dict[str, object]) -> EntranceZoneConfig:
    defaults = _default_zone_config()
    inside = _coerce_polygon(camera_cfg.get("inside_store_zone", []))
    center = _coerce_polygon(camera_cfg.get("center_entry_zone", []))
    left = _coerce_polygon(camera_cfg.get("left_outside_ignore_zone", []))
    right = _coerce_polygon(camera_cfg.get("right_outside_ignore_zone", []))
    poster = _coerce_polygon(camera_cfg.get("poster_static_zone", []))
    return EntranceZoneConfig(
        inside_store_zone=inside if len(inside) >= 3 else defaults.inside_store_zone,
        center_entry_zone=center if len(center) >= 3 else defaults.center_entry_zone,
        left_outside_ignore_zone=left if len(left) >= 3 else defaults.left_outside_ignore_zone,
        right_outside_ignore_zone=right if len(right) >= 3 else defaults.right_outside_ignore_zone,
        poster_static_zone=poster if len(poster) >= 3 else defaults.poster_static_zone,
    )


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (max(1e-9, (yj - yi))) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _zone_for_point(point: tuple[float, float], zones: EntranceZoneConfig) -> str:
    if _point_in_polygon(point, zones.left_outside_ignore_zone):
        return ZONE_LEFT_OUTSIDE
    if _point_in_polygon(point, zones.right_outside_ignore_zone):
        return ZONE_RIGHT_OUTSIDE
    if _point_in_polygon(point, zones.center_entry_zone):
        return ZONE_CENTER
    if _point_in_polygon(point, zones.inside_store_zone):
        return ZONE_INSIDE
    return ZONE_UNKNOWN


def _box_center(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _box_footpoint(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, box[3])


def _box_area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, (box[2] - box[0]) * (box[3] - box[1]))


def _rgb_crop(
    image_rgb: np.ndarray,
    box: tuple[float, float, float, float],
) -> np.ndarray:
    h, w = image_rgb.shape[:2]
    x1 = max(0, min(w - 1, int(box[0] * w)))
    y1 = max(0, min(h - 1, int(box[1] * h)))
    x2 = max(x1 + 1, min(w, int(box[2] * w)))
    y2 = max(y1 + 1, min(h, int(box[3] * h)))
    return image_rgb[y1:y2, x1:x2]


def _color_stats(rgb_crop: np.ndarray) -> dict[str, float]:
    if rgb_crop.size == 0:
        return {"red_ratio": 0.0, "dark_ratio": 1.0, "black_ratio": 1.0}
    rgb = rgb_crop.astype(np.float32) / 255.0
    r = rgb[..., 0]
    g = rgb[..., 1]
    b = rgb[..., 2]
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    delta = max_c - min_c
    # Hue in degrees, wrapped [0, 360)
    hue = np.zeros_like(max_c)
    mask = delta > 1e-6
    idx = (max_c == r) & mask
    hue[idx] = (60 * ((g[idx] - b[idx]) / delta[idx]) + 360) % 360
    idx = (max_c == g) & mask
    hue[idx] = 60 * ((b[idx] - r[idx]) / delta[idx]) + 120
    idx = (max_c == b) & mask
    hue[idx] = 60 * ((r[idx] - g[idx]) / delta[idx]) + 240
    sat = np.where(max_c <= 1e-6, 0.0, delta / np.maximum(max_c, 1e-6))
    val = max_c
    red_mask = (((hue <= 20) | (hue >= 340)) & (sat >= 0.35) & (val >= 0.20))
    dark_mask = val < 0.35
    black_mask = (val < 0.25) & (sat < 0.45)
    return {
        "red_ratio": float(np.mean(red_mask)),
        "dark_ratio": float(np.mean(dark_mask)),
        "black_ratio": float(np.mean(black_mask)),
    }


def _classify_clothing(
    image_rgb: np.ndarray,
    box: tuple[float, float, float, float],
) -> tuple[str, str, str, float]:
    crop = _rgb_crop(image_rgb, box)
    if crop.size == 0:
        return "unknown", "unknown", "unknown", 0.0
    h = crop.shape[0]
    split = max(1, int(h * 0.52))
    upper = crop[:split, :, :]
    lower = crop[split:, :, :]
    upper_stats = _color_stats(upper)
    lower_stats = _color_stats(lower)

    upper_color = "red" if upper_stats["red_ratio"] >= 0.10 else "other"
    if lower_stats["black_ratio"] >= 0.32:
        lower_color = "black"
    elif lower_stats["dark_ratio"] >= 0.50:
        lower_color = "dark"
    elif lower_stats["red_ratio"] >= 0.10:
        lower_color = "red"
    else:
        lower_color = "other"

    # Red dress is treated as customer, not staff.
    if upper_color == "red" and lower_color == "red":
        clothing_type = "dress"
    elif upper_color == "red" and lower_color in {"black", "dark", "other"}:
        clothing_type = "shirt_and_pants"
    else:
        clothing_type = "unknown"

    staff_score = 0.0
    if upper_color == "red" and lower_color in {"black", "dark"} and clothing_type != "dress":
        staff_score = min(1.0, 0.5 + upper_stats["red_ratio"] + max(lower_stats["black_ratio"], lower_stats["dark_ratio"]) * 0.5)
    return upper_color, lower_color, clothing_type, round(float(staff_score), 4)


def _is_entrance_camera(camera_id: str, camera_cfg: dict[str, object]) -> bool:
    role = str(camera_cfg.get("camera_role", "")).strip().upper()
    return role in {"ENTRANCE", "EXIT", "GATE", "ENTRY", "ENTRY_EXIT"} or str(camera_id).strip().upper() == "D07"


def enrich_entrance_camera_classification(
    image_insights: pd.DataFrame,
    camera_configs: dict[str, dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Apply deterministic entrance-camera customer/staff/ignore classification."""
    if camera_configs is None:
        camera_configs = {}
    if image_insights.empty:
        return image_insights

    df = image_insights.copy()
    for col, default in {
        "track_audit_json": "[]",
        "upper_colors": "[]",
        "lower_colors": "[]",
        "clothing_types": "[]",
        "ignore_reasons": "[]",
        "box_labels": "[]",
    }.items():
        if col not in df.columns:
            df[col] = default

    row_observations: dict[int, list[dict[str, Any]]] = {}
    track_observations: dict[int, list[dict[str, Any]]] = {}
    image_cache: dict[str, np.ndarray] = {}

    scoped = df[df["timestamp"].notna()].sort_values("timestamp")
    for idx, row in scoped.iterrows():
        camera_id = str(row.get("camera_id", "")).strip().upper()
        cfg = camera_configs.get(camera_id, {})
        if not _is_entrance_camera(camera_id, cfg):
            continue
        boxes = _parse_box_list(row.get("person_boxes", "[]"))
        if not boxes:
            continue
        tids = _parse_int_list(row.get("track_ids", "[]"))
        confs = _parse_float_list(row.get("person_confidences", "[]"), expected=len(boxes))
        zones = _zone_config_from_camera(cfg)

        path = str(row.get("path", "")).strip()
        image_rgb = np.zeros((1, 1, 3), dtype=np.uint8)
        if path:
            if path not in image_cache:
                try:
                    with Image.open(Path(path)) as image:
                        image_cache[path] = np.array(image.convert("RGB"))
                except Exception:
                    image_cache[path] = np.zeros((1, 1, 3), dtype=np.uint8)
            image_rgb = image_cache[path]

        for box_idx, box in enumerate(boxes):
            tid = tids[box_idx] if box_idx < len(tids) else -(int(idx) * 1000 + box_idx + 1)
            footpoint = _box_footpoint(box)
            center = _box_center(box)
            zone_name = _zone_for_point(footpoint, zones)
            in_poster_zone = _point_in_polygon(center, zones.poster_static_zone)
            upper_color, lower_color, clothing_type, staff_score = _classify_clothing(image_rgb=image_rgb, box=box)
            is_staff_uniform = (
                upper_color == "red"
                and lower_color in {"black", "dark"}
                and clothing_type != "dress"
            )
            obs = {
                "row_idx": int(idx),
                "track_id": int(tid),
                "timestamp": pd.Timestamp(row["timestamp"]),
                "camera_id": camera_id,
                "box_idx": int(box_idx),
                "bbox": box,
                "footpoint": footpoint,
                "zone": zone_name,
                "poster_zone": bool(in_poster_zone),
                "upper_color": upper_color,
                "lower_color": lower_color,
                "clothing_type": clothing_type,
                "staff_uniform": bool(is_staff_uniform),
                "staff_score": float(staff_score),
                "confidence": float(confs[box_idx]) if box_idx < len(confs) else 0.0,
            }
            row_observations.setdefault(int(idx), []).append(obs)
            track_observations.setdefault(int(tid), []).append(obs)

    if not track_observations:
        return df

    track_meta: dict[int, dict[str, Any]] = {}
    for track_id, observations in track_observations.items():
        ordered = sorted(observations, key=lambda x: x["timestamp"])
        points = np.array([o["footpoint"] for o in ordered], dtype=float)
        areas = np.array([_box_area(o["bbox"]) for o in ordered], dtype=float)
        zones_seen = [str(o["zone"]) for o in ordered]
        poster_hits = sum(1 for o in ordered if bool(o["poster_zone"]))
        staff_votes = sum(1 for o in ordered if bool(o["staff_uniform"]))
        center_std = float(max(np.std(points[:, 0]), np.std(points[:, 1]))) if len(points) > 1 else 0.0
        area_mean = float(np.mean(areas)) if len(areas) > 0 else 0.0
        area_cv = float(np.std(areas) / max(1e-9, area_mean)) if len(areas) > 1 else 0.0

        entry_direction = "pending"
        for a, b in zip(ordered, ordered[1:]):
            za = str(a["zone"])
            zb = str(b["zone"])
            if za in OUTSIDE_ZONES and zb in {ZONE_CENTER, ZONE_INSIDE}:
                entry_direction = "outside_to_inside"
                break
            if za in {ZONE_INSIDE, ZONE_CENTER} and zb in OUTSIDE_ZONES:
                entry_direction = "inside_to_outside"
                break

        entered_store = any(zone in {ZONE_CENTER, ZONE_INSIDE} for zone in zones_seen)
        outside_only = bool(zones_seen) and all(zone in OUTSIDE_ZONES for zone in zones_seen)
        poster_like = bool(
            (poster_hits >= 1 and center_std <= 0.020 and area_cv <= 0.12)
            or (len(ordered) >= 6 and center_std <= 0.010 and area_cv <= 0.08 and not entered_store)
        )
        track_meta[track_id] = {
            "first_seen": ordered[0]["timestamp"],
            "last_seen": ordered[-1]["timestamp"],
            "entry_direction": entry_direction,
            "entered_store": entered_store,
            "outside_only": outside_only,
            "poster_like": poster_like,
            "staff_vote_ratio": float(staff_votes / max(1, len(ordered))),
        }

    for idx, observations in row_observations.items():
        ordered = sorted(observations, key=lambda x: int(x["box_idx"]))
        labels: list[str] = []
        ignore_reasons: list[str] = []
        upper_colors: list[str] = []
        lower_colors: list[str] = []
        clothing_types: list[str] = []
        staff_flags: list[bool] = []
        staff_scores: list[float] = []
        row_audit: list[dict[str, object]] = []
        customer_count = 0
        staff_count = 0

        for obs in ordered:
            meta = track_meta.get(int(obs["track_id"]), {})
            zone_name = str(obs["zone"])
            entry_direction = str(meta.get("entry_direction", "pending"))
            poster_like = bool(meta.get("poster_like", False))
            is_side_passer = bool(zone_name in OUTSIDE_ZONES and not bool(meta.get("entered_store", False)))
            is_staff = bool(obs["staff_uniform"])
            label = "ignore"
            ignore_reason = "insufficient_evidence"

            # Deterministic priority order.
            if poster_like or bool(obs["poster_zone"]):
                label = "ignore"
                ignore_reason = "poster_or_flat_static"
            elif is_side_passer:
                label = "ignore"
                ignore_reason = "outside_side_passerby"
            elif is_staff:
                label = "staff"
                ignore_reason = ""
            elif zone_name == ZONE_INSIDE:
                label = "customer"
                ignore_reason = ""
            elif zone_name == ZONE_CENTER and entry_direction == "outside_to_inside":
                label = "customer"
                ignore_reason = ""
            elif zone_name == ZONE_CENTER:
                label = "pending"
                ignore_reason = "entry_direction_pending"

            if label == "customer":
                customer_count += 1
            elif label == "staff":
                staff_count += 1

            labels.append(label)
            ignore_reasons.append(ignore_reason)
            upper_colors.append(str(obs["upper_color"]))
            lower_colors.append(str(obs["lower_color"]))
            clothing_types.append(str(obs["clothing_type"]))
            staff_flags.append(label == "staff")
            staff_scores.append(float(obs["staff_score"]))
            row_audit.append(
                {
                    "track_id": int(obs["track_id"]),
                    "bbox": [round(float(v), 6) for v in obs["bbox"]],
                    "zone": zone_name,
                    "gender_optional": "",
                    "upper_color": str(obs["upper_color"]),
                    "lower_color": str(obs["lower_color"]),
                    "clothing_type": str(obs["clothing_type"]),
                    "is_staff": bool(label == "staff"),
                    "is_customer": bool(label == "customer"),
                    "ignore_reason": ignore_reason if ignore_reason else None,
                    "confidence": round(float(obs["confidence"]), 4),
                    "entry_direction": entry_direction,
                    "first_seen": str(meta.get("first_seen", "")),
                    "last_seen": str(meta.get("last_seen", "")),
                }
            )

        current_person_count = int(pd.to_numeric([df.at[idx, "person_count"]], errors="coerce")[0] or 0)
        if current_person_count <= 0:
            continue

        person_count = int(customer_count + staff_count)
        df.at[idx, "person_count"] = person_count
        df.at[idx, "customer_count"] = int(customer_count)
        df.at[idx, "staff_count"] = int(staff_count)
        df.at[idx, "staff_flags"] = json.dumps(staff_flags)
        df.at[idx, "staff_scores"] = json.dumps(staff_scores)
        df.at[idx, "upper_colors"] = json.dumps(upper_colors)
        df.at[idx, "lower_colors"] = json.dumps(lower_colors)
        df.at[idx, "clothing_types"] = json.dumps(clothing_types)
        df.at[idx, "ignore_reasons"] = json.dumps(ignore_reasons)
        df.at[idx, "box_labels"] = json.dumps(labels)
        df.at[idx, "track_audit_json"] = json.dumps(row_audit)

        is_valid = bool(df.at[idx, "is_valid"])
        det_err = str(df.at[idx, "detection_error"] or "").strip()
        df.at[idx, "relevant"] = bool(is_valid and det_err == "" and person_count > 0)
        if person_count <= 0:
            df.at[idx, "max_person_conf"] = 0.0

        if customer_count > 0:
            df.at[idx, "event_label"] = "CUSTOMER"
        elif staff_count > 0:
            df.at[idx, "event_label"] = "STAFF"
        elif any(reason == "outside_side_passerby" for reason in ignore_reasons):
            df.at[idx, "event_label"] = "OUTSIDE_PASSER"
        elif any(reason == "entry_direction_pending" for reason in ignore_reasons):
            df.at[idx, "event_label"] = "PENDING"
        else:
            df.at[idx, "event_label"] = "INVALID"

    return df

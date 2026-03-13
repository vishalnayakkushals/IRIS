from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import math
import csv
import json
import os
import re
from typing import Any, Protocol

import numpy as np
import pandas as pd
from PIL import Image


FILE_PATTERN = re.compile(
    r"(?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
)
FILE_PATTERN_WITH_DATE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})[_\s-](?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
)
FILE_PATTERN_WITH_COMPACT_DATE = re.compile(
    r"(?P<date>\d{8})[_\s-](?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DATE_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMPLOYEE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class ParsedFilename:
    timestamp: datetime
    camera_id: str
    frame_no: int


@dataclass(frozen=True)
class DetectionResult:
    person_count: int
    max_person_conf: float
    detection_error: str
    person_centroids: list[tuple[float, float]] = field(default_factory=list)
    person_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    bag_count: int = 0


@dataclass(frozen=True)
class StoreAnalysisResult:
    image_insights: pd.DataFrame
    camera_hotspots: pd.DataFrame
    location_hotspots: pd.DataFrame
    customer_sessions: pd.DataFrame
    summary_row: pd.DataFrame
    alerts: pd.DataFrame
    daily_report: pd.DataFrame
    daily_proof: pd.DataFrame


@dataclass(frozen=True)
class AnalysisOutput:
    stores: dict[str, StoreAnalysisResult]
    all_stores_summary: pd.DataFrame
    detector_warning: str
    used_root_fallback_store: bool


class PersonDetector(Protocol):
    def detect(self, image_path: Path) -> DetectionResult:
        ...


class MockPersonDetector:
    """Deterministic detector useful for tests and local fallback."""

    def __init__(self, conf_threshold: float = 0.25) -> None:
        self.conf_threshold = conf_threshold

    def detect(self, image_path: Path) -> DetectionResult:
        seed = sum(ord(ch) for ch in image_path.name)
        person_count = seed % 4
        if person_count == 0:
            return DetectionResult(person_count=0, max_person_conf=0.0, detection_error="", person_centroids=[], person_boxes=[], bag_count=0)
        max_conf = max(self.conf_threshold, min(0.95, 0.55 + (seed % 30) / 100))
        centroids = [(round(0.2 + i * 0.2, 3), round(0.45 + (seed % 10) * 0.01, 3)) for i in range(person_count)]
        boxes: list[tuple[float, float, float, float]] = []
        for cx, cy in centroids:
            boxes.append(
                (
                    max(0.0, round(cx - 0.08, 4)),
                    max(0.0, round(cy - 0.18, 4)),
                    min(1.0, round(cx + 0.08, 4)),
                    min(1.0, round(cy + 0.18, 4)),
                )
            )
        return DetectionResult(
            person_count=person_count,
            max_person_conf=round(max_conf, 3),
            detection_error="",
            person_centroids=centroids,
            person_boxes=boxes,
            bag_count=0,
        )


class UnavailableDetector:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def detect(self, image_path: Path) -> DetectionResult:
        return DetectionResult(person_count=0, max_person_conf=0.0, detection_error=self.reason, person_centroids=[], person_boxes=[], bag_count=0)


class YoloPersonDetector:
    def __init__(
        self,
        model_name: str = "data/models/yolov8n.pt",
        conf_threshold: float = 0.25,
        device: str = "cpu",
    ) -> None:
        from ultralytics import YOLO  # type: ignore

        model_path = Path(model_name)
        model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(model_path))
        self.conf_threshold = conf_threshold
        self.device = device

    def detect(self, image_path: Path) -> DetectionResult:
        try:
            results = self.model.predict(
                source=str(image_path),
                classes=[0, 26],
                conf=self.conf_threshold,
                device=self.device,
                verbose=False,
            )
            boxes = results[0].boxes if results else None
            if boxes is None or len(boxes) == 0:
                return DetectionResult(person_count=0, max_person_conf=0.0, detection_error="", person_centroids=[], person_boxes=[], bag_count=0)

            cls_values = boxes.cls.tolist() if hasattr(boxes, "cls") else []
            conf_values = boxes.conf.tolist() if hasattr(boxes, "conf") else []
            xywhn = boxes.xywhn.tolist() if hasattr(boxes, "xywhn") else []
            xyxyn = boxes.xyxyn.tolist() if hasattr(boxes, "xyxyn") else []

            person_centroids: list[tuple[float, float]] = []
            person_boxes: list[tuple[float, float, float, float]] = []
            person_conf: list[float] = []
            bag_count = 0
            for i, cls_id in enumerate(cls_values):
                if int(cls_id) == 0:
                    person_conf.append(float(conf_values[i]))
                    if i < len(xywhn):
                        person_centroids.append((float(xywhn[i][0]), float(xywhn[i][1])))
                    if i < len(xyxyn):
                        person_boxes.append(
                            (
                                float(xyxyn[i][0]),
                                float(xyxyn[i][1]),
                                float(xyxyn[i][2]),
                                float(xyxyn[i][3]),
                            )
                        )
                elif int(cls_id) == 26:
                    bag_count += 1

            if not person_conf:
                return DetectionResult(person_count=0, max_person_conf=0.0, detection_error="", person_centroids=[], person_boxes=[], bag_count=bag_count)

            return DetectionResult(
                person_count=len(person_conf),
                max_person_conf=float(max(person_conf)),
                detection_error="",
                person_centroids=person_centroids,
                person_boxes=person_boxes,
                bag_count=bag_count,
            )
        except Exception as exc:
            return DetectionResult(person_count=0, max_person_conf=0.0, detection_error=str(exc), person_centroids=[], person_boxes=[], bag_count=0)


class LegacyTfPersonDetector:
    """TensorFlow Faster-RCNN detector compatible with legacy frozen graph pipelines."""

    def __init__(
        self,
        model_path: str = "data/models/frozen_inference_graph.pb",
        conf_threshold: float = 0.25,
    ) -> None:
        import tensorflow.compat.v1 as tf  # type: ignore

        tf.disable_v2_behavior()
        self._tf = tf
        self.conf_threshold = float(conf_threshold)
        resolved = Path(model_path)
        if not resolved.exists():
            raise FileNotFoundError(
                f"frozen graph not found at '{resolved}'. "
                "Set TF_FRCNN_MODEL_PATH or place file under data/models/."
            )

        self.graph = tf.Graph()
        with self.graph.as_default():
            graph_def = tf.GraphDef()
            with tf.gfile.GFile(str(resolved), "rb") as f:
                graph_def.ParseFromString(f.read())
                tf.import_graph_def(graph_def, name="")
            self.image_tensor = self.graph.get_tensor_by_name("image_tensor:0")
            self.detection_boxes = self.graph.get_tensor_by_name("detection_boxes:0")
            self.detection_scores = self.graph.get_tensor_by_name("detection_scores:0")
            self.detection_classes = self.graph.get_tensor_by_name("detection_classes:0")
            self.num_detections = self.graph.get_tensor_by_name("num_detections:0")
            self.sess = tf.Session(graph=self.graph)

    def detect(self, image_path: Path) -> DetectionResult:
        try:
            with Image.open(image_path) as img:
                rgb = img.convert("RGB")
                image_np = np.array(rgb)
            image_expanded = np.expand_dims(image_np, axis=0)
            boxes, scores, classes, num = self.sess.run(
                [
                    self.detection_boxes,
                    self.detection_scores,
                    self.detection_classes,
                    self.num_detections,
                ],
                feed_dict={self.image_tensor: image_expanded},
            )

            num_det = int(float(num[0])) if num is not None else 0
            person_centroids: list[tuple[float, float]] = []
            person_boxes: list[tuple[float, float, float, float]] = []
            person_conf: list[float] = []
            for i in range(num_det):
                cls_id = int(classes[0][i])
                score = float(scores[0][i])
                if cls_id != 1 or score < self.conf_threshold:
                    continue
                # TensorFlow object detection format: [ymin, xmin, ymax, xmax]
                y1, x1, y2, x2 = [float(v) for v in boxes[0][i]]
                person_boxes.append((x1, y1, x2, y2))
                person_centroids.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
                person_conf.append(score)

            if not person_conf:
                return DetectionResult(
                    person_count=0,
                    max_person_conf=0.0,
                    detection_error="",
                    person_centroids=[],
                    person_boxes=[],
                    bag_count=0,
                )
            return DetectionResult(
                person_count=len(person_conf),
                max_person_conf=float(max(person_conf)),
                detection_error="",
                person_centroids=person_centroids,
                person_boxes=person_boxes,
                bag_count=0,
            )
        except Exception as exc:
            return DetectionResult(
                person_count=0,
                max_person_conf=0.0,
                detection_error=str(exc),
                person_centroids=[],
                person_boxes=[],
                bag_count=0,
            )


def build_detector(detector_type: str = "yolo", conf_threshold: float = 0.25) -> tuple[PersonDetector, str]:
    normalized = str(detector_type).strip().lower()
    if normalized in {"tensorflow_frcnn", "tf_frcnn", "legacy_tf_frcnn"}:
        model_path = os.getenv("TF_FRCNN_MODEL_PATH", "data/models/frozen_inference_graph.pb").strip()
        try:
            return LegacyTfPersonDetector(model_path=model_path, conf_threshold=conf_threshold), ""
        except Exception as exc:
            reason = f"TF_FRCNN detector unavailable: {exc}"
            return UnavailableDetector(reason), reason

    if normalized == "mock":
        return MockPersonDetector(conf_threshold=conf_threshold), ""
    if normalized != "yolo":
        return (
            UnavailableDetector(f"Unsupported detector_type='{detector_type}'"),
            f"Unsupported detector_type='{detector_type}', using unavailable detector fallback.",
        )

    try:
        return YoloPersonDetector(conf_threshold=conf_threshold), ""
    except Exception as exc:
        reason = f"Detector unavailable: {exc}"
        return UnavailableDetector(reason), reason


def _parse_date_token(token: str) -> date | None:
    text = str(token).strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{8}", text):
            return date.fromisoformat(f"{text[0:4]}-{text[4:6]}-{text[6:8]}")
        return date.fromisoformat(text)
    except ValueError:
        return None


def parse_filename(filename: str, reference_day: date | None = None) -> ParsedFilename | None:
    match = FILE_PATTERN.match(filename)
    resolved_day = reference_day
    if not match:
        dated = FILE_PATTERN_WITH_DATE.match(filename)
        compact_dated = FILE_PATTERN_WITH_COMPACT_DATE.match(filename)
        match = dated or compact_dated
        if not match:
            return None
        parsed_day = _parse_date_token(match.group("date"))
        if parsed_day is not None:
            resolved_day = parsed_day
    hh, mm, ss = [int(part) for part in match.group("time").split("-")]
    if resolved_day is None:
        resolved_day = date.today()
    ts = datetime.combine(resolved_day, datetime.min.time()).replace(
        hour=hh, minute=mm, second=ss
    )
    return ParsedFilename(
        timestamp=ts,
        camera_id=match.group("camera"),
        frame_no=int(match.group("frame")),
    )


def _extract_date_from_parts(parts: list[str]) -> date | None:
    for part in reversed(parts):
        token = part.strip()
        if DATE_FOLDER_PATTERN.match(token):
            try:
                return date.fromisoformat(token)
            except ValueError:
                continue
        match = re.search(r"(\d{4}-\d{2}-\d{2})", token)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                continue
    return None


def _infer_image_context(
    image_path: Path,
    store_dir: Path,
    fallback_day: date | None,
) -> tuple[date, str, str]:
    rel = image_path.relative_to(store_dir)
    parent_parts = [str(p) for p in rel.parts[:-1]]
    context_day = _extract_date_from_parts(parent_parts) or fallback_day or date.today()
    capture_date = context_day.isoformat()
    source_folder = "/".join(parent_parts)
    return context_day, capture_date, source_folder


def _relative_image_path(image_path: Path, store_dir: Path) -> str:
    return str(image_path.relative_to(store_dir)).replace("\\", "/")


def _load_drive_link_map(store_dir: Path) -> dict[str, str]:
    manifest_path = store_dir / "_drive_manifest.csv"
    if not manifest_path.exists():
        return {}
    mapping: dict[str, str] = {}
    try:
        with manifest_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rel = str(row.get("relative_path", "")).strip().replace("\\", "/")
                link = str(row.get("drive_web_link", "")).strip()
                if rel and link:
                    mapping[rel] = link
    except Exception:
        return {}
    return mapping


def _classify_staff_by_shirt_color(
    image_path: Path,
    person_boxes: list[tuple[float, float, float, float]],
    red_threshold: float = 0.22,
) -> tuple[list[bool], list[float]]:
    if not person_boxes:
        return [], []
    try:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            width, height = rgb.size
            flags: list[bool] = []
            scores: list[float] = []
            for box in person_boxes:
                x1 = max(0, min(width - 1, int(float(box[0]) * width)))
                y1 = max(0, min(height - 1, int(float(box[1]) * height)))
                x2 = max(x1 + 1, min(width, int(float(box[2]) * width)))
                y2 = max(y1 + 1, min(height, int(float(box[3]) * height)))
                h = max(1, y2 - y1)
                # Approximate shirt region (upper-middle body crop)
                sy1 = y1 + int(h * 0.30)
                sy2 = y1 + int(h * 0.70)
                if sy2 <= sy1:
                    sy1 = y1
                    sy2 = y2
                crop = rgb.crop((x1, sy1, x2, sy2)).resize((40, 40))
                data = list(crop.getdata())
                if not data:
                    flags.append(False)
                    scores.append(0.0)
                    continue
                red_pixels = 0
                for r, g, b in data:
                    if r >= 100 and r > g * 1.22 and r > b * 1.22:
                        red_pixels += 1
                red_ratio = red_pixels / len(data)
                flags.append(red_ratio >= float(red_threshold))
                scores.append(round(red_ratio, 4))
            return flags, scores
    except Exception:
        return [False for _ in person_boxes], [0.0 for _ in person_boxes]


def _estimate_red_ratio(path: Path) -> float:
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB").resize((64, 64))
            data = list(rgb.getdata())
            if not data:
                return 0.0
            red_pixels = 0
            for r, g, b in data:
                if r >= 100 and r > g * 1.22 and r > b * 1.22:
                    red_pixels += 1
            return float(red_pixels / len(data))
    except Exception:
        return 0.0


def _estimate_store_staff_red_threshold(
    store_id: str,
    employee_assets_root: Path | None,
) -> float:
    baseline = 0.22
    if employee_assets_root is None:
        return baseline
    store_dir = employee_assets_root / store_id
    if not store_dir.exists() or not store_dir.is_dir():
        return baseline
    ratios: list[float] = []
    for path in sorted(store_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EMPLOYEE_IMAGE_EXTENSIONS:
            continue
        ratio = _estimate_red_ratio(path)
        if ratio > 0:
            ratios.append(ratio)
        if len(ratios) >= 200:
            break
    if not ratios:
        return baseline
    avg_ratio = float(sum(ratios) / len(ratios))
    # Slightly below employee average to tolerate lighting variance.
    adaptive = avg_ratio * 0.7
    return max(0.14, min(0.35, adaptive))


def validate_image(path: Path) -> tuple[bool, str]:
    if path.stat().st_size == 0:
        return False, "zero_byte"
    try:
        with Image.open(path) as image:
            image.verify()
        return True, ""
    except Exception:
        return False, "unreadable"


def _list_store_dirs(root_dir: Path) -> tuple[list[Path], bool]:
    store_dirs: list[Path] = []
    for path in sorted([p for p in root_dir.iterdir() if p.is_dir()]):
        if path.name.startswith("."):
            continue
        has_images = any(
            child.suffix.lower() in IMAGE_EXTENSIONS for child in path.rglob("*") if child.is_file()
        )
        files = [child for child in path.iterdir() if child.is_file()]
        is_empty = len(files) == 0 and not any(child.is_dir() for child in path.iterdir())
        if has_images or is_empty:
            store_dirs.append(path)
    if store_dirs:
        return store_dirs, False

    has_images = any(
        path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS for path in root_dir.iterdir()
    )
    if has_images:
        return [root_dir], True
    return [], False


def _iter_store_images(store_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in store_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ],
        key=lambda p: str(p.relative_to(store_dir)),
    )


def _empty_camera_hotspots(store_id: str, camera_ids: list[str]) -> pd.DataFrame:
    rows = []
    for rank, camera_id in enumerate(sorted(set(camera_ids)), start=1):
        rows.append(
            {
                "store_id": store_id,
                "camera_id": camera_id,
                "relevant_images": 0,
                "total_people": 0,
                "avg_people_per_relevant_image": 0.0,
                "hotspot_rank": rank,
            }
        )
    return pd.DataFrame(rows)


def build_camera_hotspots(image_insights: pd.DataFrame, store_id: str) -> pd.DataFrame:
    cameras = [
        camera
        for camera in image_insights["camera_id"].dropna().astype(str).tolist()
        if camera.strip()
    ]
    if not cameras:
        return pd.DataFrame(
            columns=[
                "store_id",
                "camera_id",
                "relevant_images",
                "total_people",
                "avg_people_per_relevant_image",
                "hotspot_rank",
            ]
        )

    relevant = image_insights[image_insights["relevant"]].copy()
    if relevant.empty:
        return _empty_camera_hotspots(store_id, cameras)

    grouped = (
        relevant.groupby("camera_id", as_index=False)
        .agg(relevant_images=("filename", "count"), total_people=("person_count", "sum"))
        .copy()
    )
    grouped["avg_people_per_relevant_image"] = (
        grouped["total_people"] / grouped["relevant_images"]
    ).round(3)

    all_cameras = sorted(set(cameras))
    grouped = grouped.set_index("camera_id")
    for camera_id in all_cameras:
        if camera_id not in grouped.index:
            grouped.loc[camera_id] = [0, 0, 0.0]
    grouped = grouped.reset_index()
    grouped["store_id"] = store_id

    grouped = grouped.sort_values(
        by=["avg_people_per_relevant_image", "total_people", "camera_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    grouped["hotspot_rank"] = grouped.index + 1

    return grouped[
        [
            "store_id",
            "camera_id",
            "relevant_images",
            "total_people",
            "avg_people_per_relevant_image",
            "hotspot_rank",
        ]
    ]


def _peak_time_bucket(image_insights: pd.DataFrame, time_bucket_minutes: int = 1) -> str:
    relevant = image_insights[image_insights["relevant"]].copy()
    if relevant.empty:
        return ""
    relevant["bucket"] = relevant["timestamp"].dt.floor(f"{time_bucket_minutes}min")
    grouped = (
        relevant.groupby("bucket", as_index=False)
        .agg(total_people=("person_count", "sum"))
        .sort_values(by=["total_people", "bucket"], ascending=[False, True])
    )
    return grouped.iloc[0]["bucket"].strftime("%H:%M")


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


def _cross_in_out(side_a: int, side_b: int, direction: str) -> tuple[bool, bool]:
    crossed_in = False
    crossed_out = False
    if side_a == side_b:
        return crossed_in, crossed_out
    if direction == "OUTSIDE_TO_INSIDE" and side_a < 0 <= side_b:
        crossed_in = True
    if direction == "OUTSIDE_TO_INSIDE" and side_a > 0 >= side_b:
        crossed_out = True
    if direction == "INSIDE_TO_OUTSIDE" and side_a > 0 >= side_b:
        crossed_in = True
    if direction == "INSIDE_TO_OUTSIDE" and side_a < 0 <= side_b:
        crossed_out = True
    return crossed_in, crossed_out


def _compute_entry_exit_event_counts(
    image_insights: pd.DataFrame,
    camera_configs: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[pd.Timestamp, int]], dict[str, dict[pd.Timestamp, int]]]:
    entry_counts: dict[str, dict[pd.Timestamp, int]] = {}
    exit_counts: dict[str, dict[pd.Timestamp, int]] = {}
    if image_insights.empty:
        return entry_counts, exit_counts

    track_events: dict[tuple[str, str, int], list[dict[str, object]]] = {}
    rows = image_insights[image_insights["timestamp"].notna()].copy()
    for _, row in rows.iterrows():
        camera_id = str(row.get("camera_id", "")).strip()
        cfg = camera_configs.get(camera_id, {})
        role = str(cfg.get("camera_role", "INSIDE")).upper()
        if role not in {"ENTRANCE", "EXIT"}:
            continue
        capture_date = str(row.get("capture_date", "")).strip()
        if not capture_date:
            capture_date = pd.Timestamp(row["timestamp"]).date().isoformat()
        tids = [int(v) for v in _safe_json_list(row.get("track_ids", "[]")) if str(v).strip()]
        cents_raw = _safe_json_list(row.get("person_centroids", "[]"))
        for i, tid in enumerate(tids):
            cx = 0.5
            if i < len(cents_raw):
                try:
                    cx = float(cents_raw[i][0])  # type: ignore[index]
                except Exception:
                    cx = 0.5
            key = (capture_date, camera_id, int(tid))
            track_events.setdefault(key, []).append(
                {
                    "ts": pd.Timestamp(row["timestamp"]),
                    "cx": cx,
                    "role": role,
                    "line_x": float(cfg.get("entry_line_x", 0.5)),
                    "direction": str(cfg.get("entry_direction", "OUTSIDE_TO_INSIDE")).upper(),
                }
            )

    for (capture_date, _camera_id, _track_id), events in track_events.items():
        ordered = sorted(events, key=lambda x: pd.Timestamp(x["ts"]))
        for a, b in zip(ordered, ordered[1:]):
            side_a = _line_side(float(a["cx"]), float(a["line_x"]))
            side_b = _line_side(float(b["cx"]), float(a["line_x"]))
            crossed_in, crossed_out = _cross_in_out(
                side_a=side_a,
                side_b=side_b,
                direction=str(a["direction"]),
            )
            ts = pd.Timestamp(b["ts"])
            if crossed_in:
                entry_counts.setdefault(capture_date, {})
                entry_counts[capture_date][ts] = int(entry_counts[capture_date].get(ts, 0)) + 1
            if crossed_out:
                exit_counts.setdefault(capture_date, {})
                exit_counts[capture_date][ts] = int(exit_counts[capture_date].get(ts, 0)) + 1
    return entry_counts, exit_counts


def _new_store_day_customer_id(store_id: str, capture_date: str, seq: int) -> str:
    if seq > 9_999_999:
        raise ValueError("store-day customer id sequence overflowed 7-digit capacity")
    return f"C_{store_id}_{capture_date.replace('-', '')}_{seq:07d}"


def _age_bucket(age_value: float) -> str:
    if age_value < 18:
        return "0-17"
    if age_value < 26:
        return "18-25"
    if age_value < 36:
        return "26-35"
    if age_value < 51:
        return "36-50"
    return "51+"


def _analyze_age_gender_deepface(
    image_path: Path,
    person_boxes: list[tuple[float, float, float, float]],
) -> tuple[str, str, float, str]:
    if not person_boxes:
        return "{}", "{}", 0.0, ""
    try:
        from deepface import DeepFace  # type: ignore
    except Exception as exc:
        return "{}", "{}", 0.0, f"DeepFace unavailable: {exc}"

    gender_scores = {"male": 0.0, "female": 0.0}
    age_buckets: dict[str, int] = {}
    analyzed = 0
    try:
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            width, height = rgb.size
            for box in person_boxes:
                x1 = max(0, min(width - 1, int(float(box[0]) * width)))
                y1 = max(0, min(height - 1, int(float(box[1]) * height)))
                x2 = max(x1 + 1, min(width, int(float(box[2]) * width)))
                y2 = max(y1 + 1, min(height, int(float(box[3]) * height)))
                crop = np.array(rgb.crop((x1, y1, x2, y2)))
                try:
                    result = DeepFace.analyze(
                        img_path=crop,
                        actions=["age", "gender"],
                        enforce_detection=False,
                        detector_backend="skip",
                        silent=True,
                    )
                    if isinstance(result, list):
                        result = result[0] if result else {}
                    if not isinstance(result, dict):
                        continue
                    age_value = float(result.get("age", 0.0) or 0.0)
                    if age_value > 0:
                        bucket = _age_bucket(age_value)
                        age_buckets[bucket] = int(age_buckets.get(bucket, 0)) + 1
                    gender_payload = result.get("gender", {})
                    if isinstance(gender_payload, dict):
                        male = float(gender_payload.get("Man", gender_payload.get("Male", 0.0)) or 0.0)
                        female = float(gender_payload.get("Woman", gender_payload.get("Female", 0.0)) or 0.0)
                        gender_scores["male"] += male
                        gender_scores["female"] += female
                    elif isinstance(gender_payload, str):
                        key = "female" if gender_payload.lower().startswith("w") else "male"
                        gender_scores[key] += 100.0
                    analyzed += 1
                except Exception:
                    continue
    except Exception as exc:
        return "{}", "{}", 0.0, f"DeepFace analyze failed: {exc}"

    if analyzed <= 0:
        return "{}", "{}", 0.0, "DeepFace could not infer age/gender for this frame"

    total_gender = max(1.0, gender_scores["male"] + gender_scores["female"])
    likelihood = {
        "male": round(gender_scores["male"] / total_gender, 4),
        "female": round(gender_scores["female"] / total_gender, 4),
    }
    confidence = round(float(analyzed) / float(max(1, len(person_boxes))), 4)
    return json.dumps(likelihood), json.dumps(age_buckets), confidence, ""


def build_store_day_customer_sessions(
    image_insights: pd.DataFrame,
    store_id: str,
    camera_configs: dict[str, dict[str, object]] | None = None,
    session_timeout_sec: int = 180,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if camera_configs is None:
        camera_configs = {}
    df = image_insights.copy()
    df["store_day_customer_ids"] = "[]"
    df["customer_session_ids"] = "[]"
    if df.empty or "timestamp" not in df.columns:
        return df, pd.DataFrame(
            columns=[
                "store_id",
                "capture_date",
                "store_day_customer_id",
                "entry_ts",
                "exit_ts",
                "dwell_sec",
                "close_reason",
                "converted_proxy",
                "cameras_seen",
                "locations_seen",
                "floors_seen",
            ]
        )

    # Build crossing events from ENTRANCE/EXIT cameras.
    entry_counts, exit_counts = _compute_entry_exit_event_counts(
        image_insights=df,
        camera_configs=camera_configs,
    )

    billing_cameras = {
        str(cid)
        for cid, cfg in camera_configs.items()
        if str((cfg or {}).get("camera_role", "")).upper() == "BILLING"
    }
    session_state: dict[str, dict[str, Any]] = {}
    sessions_out: list[dict[str, object]] = []

    def _close_session(sid: str, close_ts: pd.Timestamp, reason: str) -> None:
        state = session_state.get(sid)
        if not state or bool(state.get("closed")):
            return
        state["closed"] = True
        state["exit_ts"] = close_ts
        state["close_reason"] = reason
        entry_ts = pd.Timestamp(state["entry_ts"])
        dwell = max(1.0, float((close_ts - entry_ts).total_seconds()) + 1.0)
        sessions_out.append(
            {
                "store_id": store_id,
                "capture_date": str(state["capture_date"]),
                "store_day_customer_id": sid,
                "entry_ts": entry_ts,
                "exit_ts": close_ts,
                "dwell_sec": round(dwell, 2),
                "close_reason": reason,
                "converted_proxy": int(bool(state.get("converted_proxy", False))),
                "cameras_seen": ",".join(sorted(state.get("cameras_seen", set()))),
                "locations_seen": ",".join(sorted(state.get("locations_seen", set()))),
                "floors_seen": ",".join(sorted(state.get("floors_seen", set()))),
            }
        )

    rows = df[df["timestamp"].notna()].copy().sort_values("timestamp")
    for capture_date, day_df in rows.groupby("capture_date"):
        day = str(capture_date).strip()
        if not day:
            continue
        seq = 1
        active_ids: list[str] = []
        day_timestamps = sorted(day_df["timestamp"].dropna().unique().tolist())
        for ts_raw in day_timestamps:
            ts = pd.Timestamp(ts_raw)
            open_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]
            for sid in list(open_ids):
                last_seen = pd.Timestamp(session_state[sid]["last_seen"])
                if (ts - last_seen).total_seconds() > float(session_timeout_sec):
                    _close_session(sid=sid, close_ts=last_seen, reason="timeout")
            active_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]

            n_entry = int(entry_counts.get(day, {}).get(ts, 0))
            for _ in range(n_entry):
                sid = _new_store_day_customer_id(store_id=store_id, capture_date=day, seq=seq)
                seq += 1
                session_state[sid] = {
                    "capture_date": day,
                    "entry_ts": ts,
                    "last_seen": ts,
                    "exit_ts": ts,
                    "closed": False,
                    "close_reason": "",
                    "converted_proxy": False,
                    "cameras_seen": set(),
                    "locations_seen": set(),
                    "floors_seen": set(),
                }
                active_ids.append(sid)

            ts_idx = day_df[day_df["timestamp"] == ts].index.tolist()
            observed_count = 0
            if ts_idx:
                observed_count = int(
                    max(pd.to_numeric(df.loc[ts_idx, "customer_count"], errors="coerce").fillna(0).astype(int).tolist())
                )
            open_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]
            while len(open_ids) < observed_count:
                sid = _new_store_day_customer_id(store_id=store_id, capture_date=day, seq=seq)
                seq += 1
                session_state[sid] = {
                    "capture_date": day,
                    "entry_ts": ts,
                    "last_seen": ts,
                    "exit_ts": ts,
                    "closed": False,
                    "close_reason": "",
                    "converted_proxy": False,
                    "cameras_seen": set(),
                    "locations_seen": set(),
                    "floors_seen": set(),
                }
                active_ids.append(sid)
                open_ids.append(sid)

            open_ids = sorted(
                [sid for sid in open_ids if not bool(session_state[sid].get("closed"))],
                key=lambda sid: (pd.Timestamp(session_state[sid]["last_seen"]), sid),
                reverse=True,
            )
            chosen_ids = open_ids[:observed_count] if observed_count > 0 else []
            for sid in chosen_ids:
                session_state[sid]["last_seen"] = ts

            for idx in ts_idx:
                row_customer_raw = pd.to_numeric([df.at[idx, "customer_count"]], errors="coerce")[0]
                row_customer_count = max(0, int(0 if pd.isna(row_customer_raw) else row_customer_raw))
                row_ids = chosen_ids[:row_customer_count]
                df.at[idx, "store_day_customer_ids"] = json.dumps(row_ids)
                df.at[idx, "customer_session_ids"] = json.dumps(row_ids)
                camera_id = str(df.at[idx, "camera_id"])
                location_name = str(df.at[idx, "location_name"]) if "location_name" in df.columns else camera_id
                floor_name = str(df.at[idx, "floor_name"]) if "floor_name" in df.columns else "Ground"
                for sid in row_ids:
                    state = session_state[sid]
                    state["last_seen"] = ts
                    state["cameras_seen"].add(camera_id)
                    state["locations_seen"].add(location_name if location_name.strip() else camera_id)
                    state["floors_seen"].add(floor_name if floor_name.strip() else "Ground")
                    if camera_id in billing_cameras:
                        state["converted_proxy"] = True

            n_exit = int(exit_counts.get(day, {}).get(ts, 0))
            if n_exit > 0:
                closable = sorted(
                    [sid for sid in active_ids if not bool(session_state[sid].get("closed"))],
                    key=lambda sid: pd.Timestamp(session_state[sid]["entry_ts"]),
                )
                for sid in closable[:n_exit]:
                    _close_session(sid=sid, close_ts=ts, reason="exit_crossing")
            active_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]

        for sid in [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]:
            _close_session(
                sid=sid,
                close_ts=pd.Timestamp(session_state[sid]["last_seen"]),
                reason="end_of_day_timeout",
            )

    sessions_df = pd.DataFrame(sessions_out)
    if sessions_df.empty:
        sessions_df = pd.DataFrame(
            columns=[
                "store_id",
                "capture_date",
                "store_day_customer_id",
                "entry_ts",
                "exit_ts",
                "dwell_sec",
                "close_reason",
                "converted_proxy",
                "cameras_seen",
                "locations_seen",
                "floors_seen",
            ]
        )
    else:
        sessions_df = sessions_df.sort_values(["capture_date", "entry_ts"]).reset_index(drop=True)
    return df, sessions_df


def build_location_hotspots(image_insights: pd.DataFrame, store_id: str) -> pd.DataFrame:
    columns = [
        "store_id",
        "floor_name",
        "location_name",
        "relevant_images",
        "total_people",
        "avg_people_per_relevant_image",
        "avg_dwell_sec",
        "hotspot_rank",
    ]
    if image_insights.empty:
        return pd.DataFrame(columns=columns)

    df = image_insights.copy()
    if "location_name" not in df.columns:
        df["location_name"] = df.get("camera_id", "").astype(str)
    if "floor_name" not in df.columns:
        df["floor_name"] = "Ground"
    df["location_name"] = df["location_name"].fillna("").astype(str).str.strip()
    df["floor_name"] = df["floor_name"].fillna("").astype(str).str.strip()
    df.loc[df["location_name"] == "", "location_name"] = df["camera_id"].fillna("UNKNOWN").astype(str)
    df.loc[df["floor_name"] == "", "floor_name"] = "Ground"

    relevant = df[df["relevant"]].copy()
    if relevant.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        relevant.groupby(["floor_name", "location_name"], as_index=False)
        .agg(relevant_images=("filename", "count"), total_people=("person_count", "sum"))
    )
    grouped["avg_people_per_relevant_image"] = (
        grouped["total_people"] / grouped["relevant_images"].clip(lower=1)
    ).round(3)
    grouped["avg_dwell_sec"] = 0.0

    if "store_day_customer_ids" in relevant.columns:
        dwell_rows: list[dict[str, object]] = []
        for _, row in relevant[relevant["timestamp"].notna()].iterrows():
            customer_ids = [str(cid) for cid in _safe_json_list(row.get("store_day_customer_ids", "[]")) if str(cid).strip()]
            for cid in customer_ids:
                dwell_rows.append(
                    {
                        "customer_id": cid,
                        "floor_name": str(row.get("floor_name", "Ground")),
                        "location_name": str(row.get("location_name", row.get("camera_id", "UNKNOWN"))),
                        "timestamp": pd.Timestamp(row["timestamp"]),
                    }
                )
        if dwell_rows:
            dwell_df = pd.DataFrame(dwell_rows)
            spans = (
                dwell_df.groupby(["customer_id", "floor_name", "location_name"], as_index=False)
                .agg(first_seen=("timestamp", "min"), last_seen=("timestamp", "max"))
            )
            spans["dwell_sec"] = (
                (spans["last_seen"] - spans["first_seen"]).dt.total_seconds().fillna(0.0) + 1.0
            ).clip(lower=1.0)
            loc_dwell = (
                spans.groupby(["floor_name", "location_name"], as_index=False)
                .agg(avg_dwell_sec=("dwell_sec", "mean"))
            )
            grouped = grouped.drop(columns=["avg_dwell_sec"]).merge(
                loc_dwell,
                on=["floor_name", "location_name"],
                how="left",
            )
            grouped["avg_dwell_sec"] = grouped["avg_dwell_sec"].fillna(0.0).round(2)

    grouped["store_id"] = store_id
    grouped = grouped.sort_values(
        by=["avg_people_per_relevant_image", "total_people", "avg_dwell_sec", "location_name"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    grouped["hotspot_rank"] = grouped.index + 1
    return grouped[columns]




def estimate_visits_and_dwell(
    image_insights: pd.DataFrame,
    session_gap_sec: int = 30,
    bounce_threshold_sec: int = 120,
) -> tuple[int, float, float]:
    """Estimate visits/dwell/bounce from relevant frames grouped by camera and time continuity."""
    relevant = image_insights[
        (image_insights["relevant"]) & (image_insights["timestamp"].notna())
    ].copy()
    if relevant.empty:
        return 0, 0.0, 0.0

    visits = 0
    dwell_values: list[float] = []
    bounce_count = 0

    for _, group in relevant.groupby("camera_id"):
        g = group.sort_values("timestamp")
        start_ts = None
        prev_ts = None
        for ts in g["timestamp"].tolist():
            if start_ts is None:
                start_ts = ts
                prev_ts = ts
                continue
            gap = (ts - prev_ts).total_seconds()
            if gap > session_gap_sec:
                dwell = max(1.0, (prev_ts - start_ts).total_seconds() + 1.0)
                visits += 1
                dwell_values.append(dwell)
                if dwell < bounce_threshold_sec:
                    bounce_count += 1
                start_ts = ts
            prev_ts = ts

        if start_ts is not None and prev_ts is not None:
            dwell = max(1.0, (prev_ts - start_ts).total_seconds() + 1.0)
            visits += 1
            dwell_values.append(dwell)
            if dwell < bounce_threshold_sec:
                bounce_count += 1

    if visits == 0:
        return 0, 0.0, 0.0

    avg_dwell = float(sum(dwell_values) / visits)
    bounce_rate = float(bounce_count / visits)
    return visits, round(avg_dwell, 2), round(bounce_rate, 4)

def build_store_summary(
    store_id: str,
    image_insights: pd.DataFrame,
    camera_hotspots: pd.DataFrame,
    time_bucket_minutes: int,
    bounce_threshold_sec: int = 120,
    session_gap_sec: int = 30,
) -> pd.DataFrame:
    total_images = int(len(image_insights))
    valid_images = int(image_insights["is_valid"].sum()) if total_images else 0
    relevant_images = int(image_insights["relevant"].sum()) if total_images else 0
    total_people = int(image_insights["person_count"].sum()) if total_images else 0

    estimated_visits, avg_dwell_sec, bounce_rate = estimate_visits_and_dwell(
        image_insights=image_insights,
        session_gap_sec=session_gap_sec,
        bounce_threshold_sec=bounce_threshold_sec,
    )

    top_camera = ""
    if not camera_hotspots.empty:
        top_row = camera_hotspots.iloc[0]
        if int(top_row["relevant_images"]) > 0:
            top_camera = str(top_row["camera_id"])

    peak_bucket = _peak_time_bucket(image_insights, time_bucket_minutes=time_bucket_minutes)

    return pd.DataFrame(
        [
            {
                "store_id": store_id,
                "total_images": total_images,
                "valid_images": valid_images,
                "relevant_images": relevant_images,
                "total_people": total_people,
                "estimated_visits": estimated_visits,
                "avg_dwell_sec": avg_dwell_sec,
                "bounce_rate": bounce_rate,
                "top_camera_hotspot": top_camera,
                "peak_time_bucket": peak_bucket,
            }
        ]
    )




def assign_single_camera_tracks(
    image_insights: pd.DataFrame,
    session_gap_sec: int = 30,
    distance_threshold: float = 0.18,
) -> pd.DataFrame:
    df = image_insights.copy()
    df["track_ids"] = "[]"
    next_id = 1

    for camera_id, cam_df in df[df["timestamp"].notna()].groupby("camera_id"):
        active: dict[int, tuple[pd.Timestamp, tuple[float, float]]] = {}
        for idx in cam_df.sort_values("timestamp").index.tolist():
            centroids = df.at[idx, "person_centroids"]
            if isinstance(centroids, str):
                try:
                    centroids = json.loads(centroids)
                except Exception:
                    centroids = []
            current_ids: list[int] = []
            ts = pd.Timestamp(df.at[idx, "timestamp"])
            for c in centroids:
                best_id = None
                best_dist = 999.0
                for tid, (last_ts, last_c) in list(active.items()):
                    gap = (ts - last_ts).total_seconds()
                    if gap > session_gap_sec:
                        continue
                    d = math.dist((float(c[0]), float(c[1])), (float(last_c[0]), float(last_c[1])))
                    if d < best_dist and d <= distance_threshold:
                        best_dist = d
                        best_id = tid
                if best_id is None:
                    best_id = next_id
                    next_id += 1
                active[best_id] = (ts, (float(c[0]), float(c[1])))
                current_ids.append(best_id)
            # prune stale
            for tid in list(active.keys()):
                if (ts - active[tid][0]).total_seconds() > session_gap_sec:
                    del active[tid]
            df.at[idx, "track_ids"] = json.dumps(sorted(set(current_ids)))
    return df


def _line_side(x: float, line_x: float) -> int:
    return -1 if x < line_x else 1


def compute_footfall_and_alerts(
    image_insights: pd.DataFrame,
    camera_configs: dict[str, dict[str, object]] | None = None,
    engaged_dwell_threshold_sec: int = 180,
) -> tuple[int, pd.DataFrame]:
    if camera_configs is None:
        camera_configs = {}
    footfall = 0
    alerts: list[dict[str, object]] = []

    # Build per-track timeline records
    track_events: dict[tuple[str, int], list[dict[str, object]]] = {}
    for _, row in image_insights[image_insights["timestamp"].notna()].iterrows():
        cam = str(row["camera_id"])
        cfg = camera_configs.get(cam, {})
        tids = row.get("track_ids", "[]")
        if isinstance(tids, str):
            try:
                tids = json.loads(tids)
            except Exception:
                tids = []
        cents = row.get("person_centroids", [])
        if isinstance(cents, str):
            try:
                cents = json.loads(cents)
            except Exception:
                cents = []
        for i, tid in enumerate(tids):
            cx = float(cents[i][0]) if i < len(cents) else 0.5
            key = (cam, int(tid))
            track_events.setdefault(key, []).append(
                {
                    "ts": pd.Timestamp(row["timestamp"]),
                    "cx": cx,
                    "bag_count": int(row.get("bag_count", 0)),
                    "cfg": cfg,
                }
            )

    for (cam, tid), evts in track_events.items():
        evts = sorted(evts, key=lambda x: x["ts"])
        cfg = evts[0].get("cfg", {})
        if str(cfg.get("camera_role", "INSIDE")).upper() != "ENTRANCE":
            continue
        line_x = float(cfg.get("entry_line_x", 0.5))
        direction = str(cfg.get("entry_direction", "OUTSIDE_TO_INSIDE")).upper()

        crossed_in = False
        crossed_out = False
        for a, b in zip(evts, evts[1:]):
            sa = _line_side(a["cx"], line_x)
            sb = _line_side(b["cx"], line_x)
            if sa == sb:
                continue
            if direction == "OUTSIDE_TO_INSIDE" and sa < 0 <= sb:
                crossed_in = True
            if direction == "OUTSIDE_TO_INSIDE" and sa > 0 >= sb:
                crossed_out = True
            if direction == "INSIDE_TO_OUTSIDE" and sa > 0 >= sb:
                crossed_in = True
            if direction == "INSIDE_TO_OUTSIDE" and sa < 0 <= sb:
                crossed_out = True

        if crossed_in:
            footfall += 1

        dwell = (evts[-1]["ts"] - evts[0]["ts"]).total_seconds() + 1
        bag_seen = any(e["bag_count"] > 0 for e in evts)
        if crossed_out and dwell >= engaged_dwell_threshold_sec and not bag_seen:
            alerts.append(
                {
                    "alert_type": "LOSS_OF_SALE_SUSPECTED",
                    "camera_id": cam,
                    "track_id": tid,
                    "dwell_sec": round(dwell, 2),
                    "risk_score": 0.78,
                    "reason_codes": "LONG_DWELL,NO_BAG_EVIDENCE,EXIT_DETECTED",
                }
            )

    return footfall, pd.DataFrame(alerts)




def stitch_multi_camera_visits(image_insights: pd.DataFrame, max_delta_sec: int = 2) -> pd.DataFrame:
    df = image_insights.copy()
    df["global_visit_id"] = ""
    if df.empty or "timestamp" not in df.columns:
        return df
    rows = df[df["timestamp"].notna()].sort_values("timestamp")
    gid = 0
    active: list[tuple[pd.Timestamp, str]] = []
    for idx, row in rows.iterrows():
        ts = row["timestamp"]
        matched = None
        for at, visit_id in active:
            if abs((ts - at).total_seconds()) <= max_delta_sec:
                matched = visit_id
                break
        if matched is None:
            gid += 1
            matched = f"V{gid:06d}"
        df.at[idx, "global_visit_id"] = matched
        active = [(t, v) for t, v in active if abs((ts - t).total_seconds()) <= max_delta_sec]
        active.append((ts, matched))
    return df


def build_daily_customer_report(
    image_insights: pd.DataFrame,
    camera_configs: dict[str, dict[str, object]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build daily walk-in and conversion report with individual/group actual-customer metrics.

    Heuristic IDs:
    - Individual customer: stable `track_id` produced by tracker.
    - Group customer: 2+ people appearing together in entrance frame-time buckets.
    """
    if camera_configs is None:
        camera_configs = {}

    df = image_insights.copy()
    if df.empty or "timestamp" not in df.columns:
        empty = pd.DataFrame(
            columns=[
                "date",
                "unique_individuals",
                "unique_groups",
                "actual_customers",
                "converted_individuals",
                "converted_groups",
                "actual_conversions",
                "conversion_rate",
            ]
        )
        return df, empty

    # explode track ids per frame
    exploded_rows: list[dict[str, object]] = []
    group_members: dict[str, set[int]] = {}
    entrance_cameras = {
        str(cid)
        for cid, cfg in camera_configs.items()
        if str((cfg or {}).get("camera_role", "")).upper() == "ENTRANCE"
    }
    billing_cameras = {
        str(cid)
        for cid, cfg in camera_configs.items()
        if str((cfg or {}).get("camera_role", "")).upper() == "BILLING"
    }

    for _, row in df[df["timestamp"].notna()].iterrows():
        tids = row.get("track_ids", "[]")
        if isinstance(tids, str):
            try:
                tids = json.loads(tids)
            except Exception:
                tids = []
        camera = str(row.get("camera_id", ""))
        ts = pd.Timestamp(row["timestamp"])
        day = ts.date().isoformat()
        for tid in tids:
            exploded_rows.append(
                {
                    "timestamp": ts,
                    "date": day,
                    "camera_id": camera,
                    "track_id": int(tid),
                }
            )

        if camera in entrance_cameras and len(tids) >= 2:
            grp_id = f"G_{day}_{camera}_{ts.floor('s').strftime('%H%M%S')}"
            group_members.setdefault(grp_id, set()).update(int(t) for t in tids)

    if not exploded_rows:
        df["customer_ids"] = "[]"
        df["group_ids"] = "[]"
        empty = pd.DataFrame(
            columns=[
                "date",
                "unique_individuals",
                "unique_groups",
                "actual_customers",
                "converted_individuals",
                "converted_groups",
                "actual_conversions",
                "conversion_rate",
            ]
        )
        return df, empty

    ex = pd.DataFrame(exploded_rows)

    # conversion by red box -> BILLING camera role
    converted_ids = set()
    if billing_cameras:
        converted_ids = set(ex[ex["camera_id"].isin(billing_cameras)]["track_id"].astype(int).tolist())

    rows: list[dict[str, object]] = []
    for day, dfg in ex.groupby("date"):
        unique_individuals = set(dfg["track_id"].astype(int).tolist())
        day_groups = {gid: members for gid, members in group_members.items() if gid.startswith(f"G_{day}_")}
        unique_groups = set(day_groups.keys())
        converted_individuals = {tid for tid in unique_individuals if tid in converted_ids}
        converted_groups = {
            gid for gid, members in day_groups.items() if any(tid in converted_ids for tid in members)
        }
        actual_customers = len(unique_individuals) + len(unique_groups)
        actual_conversions = len(converted_individuals) + len(converted_groups)
        conversion_rate = (actual_conversions / actual_customers) if actual_customers > 0 else 0.0
        rows.append(
            {
                "date": day,
                "unique_individuals": len(unique_individuals),
                "unique_groups": len(unique_groups),
                "actual_customers": actual_customers,
                "converted_individuals": len(converted_individuals),
                "converted_groups": len(converted_groups),
                "actual_conversions": actual_conversions,
                "conversion_rate": conversion_rate,
            }
        )

    # annotate frame-level with ids for downstream UI/debug
    track_to_customer = {int(tid): f"C_{int(tid):06d}" for tid in ex["track_id"].unique().tolist()}
    track_to_groups: dict[int, list[str]] = {}
    for gid, members in group_members.items():
        for tid in members:
            track_to_groups.setdefault(int(tid), []).append(gid)

    customer_ids_col: list[str] = []
    group_ids_col: list[str] = []
    for _, row in df.iterrows():
        tids = row.get("track_ids", "[]")
        if isinstance(tids, str):
            try:
                tids = json.loads(tids)
            except Exception:
                tids = []
        customers = [track_to_customer.get(int(tid), f"C_{int(tid):06d}") for tid in tids]
        groups: list[str] = []
        for tid in tids:
            groups.extend(track_to_groups.get(int(tid), []))
        customer_ids_col.append(json.dumps(sorted(set(customers))))
        group_ids_col.append(json.dumps(sorted(set(groups))))

    df["customer_ids"] = customer_ids_col
    df["group_ids"] = group_ids_col
    daily_report = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return df, daily_report


def build_daily_calculation_proof(
    store_id: str,
    image_insights: pd.DataFrame,
    daily_report: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "store_id",
        "date",
        "folder_name",
        "total_images",
        "valid_images",
        "relevant_images",
        "total_detected_people",
        "individual_people",
        "group_people",
        "converted",
        "conversion_rate",
    ]
    if image_insights.empty:
        return pd.DataFrame(columns=columns)

    proof_src = image_insights.copy()
    if "capture_date" not in proof_src.columns:
        proof_src["capture_date"] = proof_src["timestamp"].dt.date.astype(str)
    proof_src["capture_date"] = proof_src["capture_date"].fillna("").astype(str)
    proof_src = proof_src[proof_src["capture_date"].str.strip() != ""].copy()
    if proof_src.empty:
        return pd.DataFrame(columns=columns)
    if "source_folder" not in proof_src.columns:
        proof_src["source_folder"] = ""

    grouped = (
        proof_src.groupby("capture_date", as_index=False)
        .agg(
            total_images=("filename", "count"),
            valid_images=("is_valid", "sum"),
            relevant_images=("relevant", "sum"),
            total_detected_people=("person_count", "sum"),
            folder_name=("source_folder", lambda x: "|".join(sorted({str(v).strip() for v in x if str(v).strip()}))),
        )
        .rename(columns={"capture_date": "date"})
    )

    grouped["folder_name"] = grouped["folder_name"].replace("", pd.NA).fillna(grouped["date"])
    grouped["store_id"] = store_id
    grouped["individual_people"] = 0
    grouped["group_people"] = 0
    grouped["converted"] = 0
    grouped["conversion_rate"] = 0.0

    if not daily_report.empty:
        report_map = daily_report.copy()
        report_map = report_map.rename(
            columns={
                "unique_individuals": "individual_people",
                "unique_groups": "group_people",
                "actual_conversions": "converted",
            }
        )
        merge_cols = ["date", "individual_people", "group_people", "converted", "conversion_rate"]
        grouped = grouped.drop(columns=["individual_people", "group_people", "converted", "conversion_rate"]).merge(
            report_map[merge_cols],
            on="date",
            how="left",
        )
        grouped["individual_people"] = grouped["individual_people"].fillna(0)
        grouped["group_people"] = grouped["group_people"].fillna(0)
        grouped["converted"] = grouped["converted"].fillna(0)
        grouped["conversion_rate"] = grouped["conversion_rate"].fillna(0.0)

    for col in ["total_images", "valid_images", "relevant_images", "total_detected_people", "individual_people", "group_people", "converted"]:
        grouped[col] = grouped[col].astype(int)
    grouped["conversion_rate"] = grouped["conversion_rate"].astype(float).round(4)
    grouped = grouped.sort_values("date", ascending=False).reset_index(drop=True)
    return grouped[columns]

def analyze_store(
    store_id: str,
    store_dir: Path,
    detector: PersonDetector,
    reference_day: date | None = None,
    time_bucket_minutes: int = 1,
    bounce_threshold_sec: int = 120,
    session_gap_sec: int = 30,
    camera_configs: dict[str, dict[str, object]] | None = None,
    engaged_dwell_threshold_sec: int = 180,
    max_images_per_store: int | None = None,
    employee_assets_root: Path | None = None,
    capture_date_filter: date | None = None,
    session_timeout_sec: int = 180,
    enable_age_gender: bool = False,
) -> StoreAnalysisResult:
    rows: list[dict[str, object]] = []
    image_paths = _iter_store_images(store_dir)
    drive_link_map = _load_drive_link_map(store_dir)
    if camera_configs is None:
        camera_configs = {}
    staff_red_threshold = _estimate_store_staff_red_threshold(
        store_id=store_id,
        employee_assets_root=employee_assets_root,
    )
    processed_images = 0

    for image_path in image_paths:
        rel_path = _relative_image_path(image_path=image_path, store_dir=store_dir)
        drive_link = drive_link_map.get(rel_path, "")
        image_day, capture_date, source_folder = _infer_image_context(
            image_path=image_path,
            store_dir=store_dir,
            fallback_day=reference_day,
        )
        if capture_date_filter is not None and image_day != capture_date_filter:
            continue
        if max_images_per_store is not None and max_images_per_store > 0 and processed_images >= max_images_per_store:
            break
        parsed = parse_filename(image_path.name, reference_day=image_day)
        if parsed is None:
            processed_images += 1
            rows.append(
                {
                    "store_id": store_id,
                    "filename": image_path.name,
                    "camera_id": "",
                    "timestamp": pd.NaT,
                    "capture_date": capture_date,
                    "source_folder": source_folder,
                    "is_valid": False,
                    "person_count": 0,
                    "max_person_conf": 0.0,
                    "relevant": False,
                    "person_centroids": "[]",
                    "person_boxes": "[]",
                    "staff_flags": "[]",
                    "staff_scores": "[]",
                    "staff_count": 0,
                    "customer_count": 0,
                    "bag_count": 0,
                    "gender_likelihood": "{}",
                    "age_bucket_counts": "{}",
                    "age_confidence": 0.0,
                    "age_gender_error": "",
                    "floor_name": "",
                    "location_name": "",
                    "reject_reason": "bad_filename",
                    "detection_error": "",
                    "relative_path": rel_path,
                    "drive_link": drive_link,
                    "path": str(image_path),
                }
            )
            continue

        is_valid, reject_reason = validate_image(image_path)
        cfg = camera_configs.get(parsed.camera_id, {})
        location_name = str(cfg.get("location_name", parsed.camera_id)).strip() or parsed.camera_id
        floor_name = str(cfg.get("floor_name", "Ground")).strip() or "Ground"
        detection = DetectionResult(
            person_count=0,
            max_person_conf=0.0,
            detection_error="",
            person_centroids=[],
            person_boxes=[],
            bag_count=0,
        )
        if is_valid:
            detection = detector.detect(image_path)
        staff_flags: list[bool] = []
        staff_scores: list[float] = []
        if is_valid and detection.person_count > 0 and detection.person_boxes:
            staff_flags, staff_scores = _classify_staff_by_shirt_color(
                image_path=image_path,
                person_boxes=detection.person_boxes,
                red_threshold=staff_red_threshold,
            )
        staff_count = min(
            int(detection.person_count),
            int(sum(1 for flag in staff_flags if bool(flag))),
        )
        customer_count = max(0, int(detection.person_count) - int(staff_count))
        gender_likelihood = "{}"
        age_bucket_counts = "{}"
        age_confidence = 0.0
        age_gender_error = ""
        if enable_age_gender and is_valid and detection.person_boxes:
            customer_boxes: list[tuple[float, float, float, float]] = []
            for idx, box in enumerate(detection.person_boxes):
                is_staff = bool(staff_flags[idx]) if idx < len(staff_flags) else False
                if not is_staff:
                    customer_boxes.append(box)
            if customer_boxes:
                gender_likelihood, age_bucket_counts, age_confidence, age_gender_error = _analyze_age_gender_deepface(
                    image_path=image_path,
                    person_boxes=customer_boxes,
                )
        relevant = bool(
            is_valid and detection.detection_error == "" and detection.person_count >= 1
        )

        processed_images += 1
        rows.append(
            {
                "store_id": store_id,
                "filename": image_path.name,
                "camera_id": parsed.camera_id,
                "timestamp": parsed.timestamp,
                "capture_date": capture_date,
                "source_folder": source_folder,
                "is_valid": is_valid,
                "person_count": int(detection.person_count),
                "max_person_conf": float(detection.max_person_conf),
                "relevant": relevant,
                "person_centroids": json.dumps(detection.person_centroids),
                "person_boxes": json.dumps(detection.person_boxes),
                "staff_flags": json.dumps(staff_flags),
                "staff_scores": json.dumps(staff_scores),
                "staff_count": int(staff_count),
                "customer_count": int(customer_count),
                "bag_count": int(detection.bag_count),
                "gender_likelihood": gender_likelihood,
                "age_bucket_counts": age_bucket_counts,
                "age_confidence": float(age_confidence),
                "age_gender_error": age_gender_error,
                "floor_name": floor_name,
                "location_name": location_name,
                "reject_reason": reject_reason,
                "detection_error": detection.detection_error,
                "relative_path": rel_path,
                "drive_link": drive_link,
                "path": str(image_path),
            }
        )

    image_insights = pd.DataFrame(
        rows,
        columns=[
            "store_id",
            "filename",
            "camera_id",
            "timestamp",
            "capture_date",
            "source_folder",
            "is_valid",
            "person_count",
            "max_person_conf",
            "relevant",
            "person_centroids",
            "person_boxes",
            "staff_flags",
            "staff_scores",
            "staff_count",
            "customer_count",
            "bag_count",
            "gender_likelihood",
            "age_bucket_counts",
            "age_confidence",
            "age_gender_error",
            "floor_name",
            "location_name",
            "reject_reason",
            "detection_error",
            "relative_path",
            "drive_link",
            "path",
        ],
    )
    if image_insights.empty:
        image_insights = pd.DataFrame(
            columns=[
                "store_id",
                "filename",
                "camera_id",
                "timestamp",
                "capture_date",
                "source_folder",
                "is_valid",
                "person_count",
                "max_person_conf",
                "relevant",
                "person_centroids",
                "person_boxes",
                "staff_flags",
                "staff_scores",
                "staff_count",
                "customer_count",
                "bag_count",
                "gender_likelihood",
                "age_bucket_counts",
                "age_confidence",
                "age_gender_error",
                "floor_name",
                "location_name",
                "reject_reason",
                "detection_error",
                "relative_path",
                "drive_link",
                "path",
            ]
        )
    else:
        image_insights = image_insights.sort_values(
            by=["timestamp", "camera_id", "filename"], na_position="last"
        ).reset_index(drop=True)

    # Exclude billing/backroom cameras from customer analytics while retaining raw rows
    role_map = {
        str(cid).strip().upper(): (cfg.get("camera_role", "INSIDE") if isinstance(cfg, dict) else "INSIDE")
        for cid, cfg in camera_configs.items()
    }
    if "camera_id" in image_insights.columns:
        mask = image_insights["camera_id"].map(
            lambda c: str(role_map.get(str(c).strip().upper(), "INSIDE")).upper() in {"BILLING", "BACKROOM"}
        )
        image_insights.loc[mask, "relevant"] = False
    image_insights = assign_single_camera_tracks(image_insights=image_insights, session_gap_sec=session_gap_sec)
    image_insights = stitch_multi_camera_visits(image_insights=image_insights, max_delta_sec=max(1, int(session_gap_sec // 2)))
    image_insights, daily_report = build_daily_customer_report(
        image_insights=image_insights,
        camera_configs=camera_configs,
    )
    for col, default_val in {
        "customer_ids": "[]",
        "group_ids": "[]",
        "track_ids": "[]",
        "person_centroids": "[]",
        "person_boxes": "[]",
    }.items():
        if col not in image_insights.columns:
            image_insights[col] = default_val
    image_insights, customer_sessions = build_store_day_customer_sessions(
        image_insights=image_insights,
        store_id=store_id,
        camera_configs=camera_configs,
        session_timeout_sec=session_timeout_sec,
    )
    if "customer_ids" not in image_insights.columns:
        image_insights["customer_ids"] = "[]"
    image_insights["legacy_customer_ids"] = image_insights["customer_ids"].astype(str)
    image_insights["customer_ids"] = image_insights.apply(
        lambda row: str(row.get("store_day_customer_ids", "[]"))
        if str(row.get("store_day_customer_ids", "[]")).strip() not in {"", "[]"}
        else str(row.get("customer_ids", "[]")),
        axis=1,
    )
    daily_proof = build_daily_calculation_proof(
        store_id=store_id,
        image_insights=image_insights,
        daily_report=daily_report,
    )

    footfall, alerts_df = compute_footfall_and_alerts(
        image_insights=image_insights,
        camera_configs=camera_configs,
        engaged_dwell_threshold_sec=engaged_dwell_threshold_sec,
    )

    camera_hotspots = build_camera_hotspots(image_insights, store_id=store_id)
    location_hotspots = build_location_hotspots(image_insights=image_insights, store_id=store_id)
    summary_row = build_store_summary(
        store_id=store_id,
        image_insights=image_insights,
        camera_hotspots=camera_hotspots,
        time_bucket_minutes=time_bucket_minutes,
        bounce_threshold_sec=bounce_threshold_sec,
        session_gap_sec=session_gap_sec,
    )
    summary_row["footfall"] = int(footfall)
    summary_row["loss_of_sale_alerts"] = int(len(alerts_df))
    if not customer_sessions.empty:
        summary_row["daily_walkins"] = int(len(customer_sessions))
        summary_row["daily_conversions"] = int(pd.to_numeric(customer_sessions["converted_proxy"], errors="coerce").fillna(0).sum())
        summary_row["daily_conversion_rate"] = float(
            summary_row["daily_conversions"].iloc[0] / max(1, summary_row["daily_walkins"].iloc[0])
        )
    elif not daily_report.empty:
        summary_row["daily_walkins"] = int(daily_report["actual_customers"].sum())
        summary_row["daily_conversions"] = int(daily_report["actual_conversions"].sum())
        summary_row["daily_conversion_rate"] = float(
            summary_row["daily_conversions"].iloc[0] / max(1, summary_row["daily_walkins"].iloc[0])
        )
    else:
        summary_row["daily_walkins"] = 0
        summary_row["daily_conversions"] = 0
        summary_row["daily_conversion_rate"] = 0.0

    return StoreAnalysisResult(
        image_insights=image_insights,
        camera_hotspots=camera_hotspots,
        location_hotspots=location_hotspots,
        customer_sessions=customer_sessions,
        summary_row=summary_row,
        alerts=alerts_df,
        daily_report=daily_report,
        daily_proof=daily_proof,
    )


def analyze_root(
    root_dir: Path,
    conf_threshold: float = 0.25,
    detector_type: str = "yolo",
    time_bucket_minutes: int = 1,
    reference_day: date | None = None,
    bounce_threshold_sec: int = 120,
    session_gap_sec: int = 30,
    camera_configs_by_store: dict[str, dict[str, dict[str, object]]] | None = None,
    engaged_dwell_threshold_sec: int = 180,
    max_images_per_store: int | None = None,
    employee_assets_root: Path | None = None,
    store_filter: str | None = None,
    capture_date_filter: date | None = None,
    session_timeout_sec: int = 180,
    enable_age_gender: bool = False,
) -> AnalysisOutput:
    root_dir = root_dir.resolve()
    detector, detector_warning = build_detector(
        detector_type=detector_type, conf_threshold=conf_threshold
    )

    store_dirs, used_root_fallback_store = _list_store_dirs(root_dir)
    store_results: dict[str, StoreAnalysisResult] = {}
    if camera_configs_by_store is None:
        camera_configs_by_store = {}
    normalized_filter = str(store_filter or "").strip()
    if normalized_filter:
        store_dirs = [path for path in store_dirs if path.name == normalized_filter]
    summary_frames: list[pd.DataFrame] = []
    for store_dir in store_dirs:
        store_id = store_dir.name
        result = analyze_store(
            store_id=store_id,
            store_dir=store_dir,
            detector=detector,
            reference_day=reference_day,
            time_bucket_minutes=time_bucket_minutes,
            bounce_threshold_sec=bounce_threshold_sec,
            session_gap_sec=session_gap_sec,
            camera_configs=camera_configs_by_store.get(store_id, {}),
            engaged_dwell_threshold_sec=engaged_dwell_threshold_sec,
            max_images_per_store=max_images_per_store,
            employee_assets_root=employee_assets_root,
            capture_date_filter=capture_date_filter,
            session_timeout_sec=session_timeout_sec,
            enable_age_gender=enable_age_gender,
        )
        store_results[store_id] = result
        summary_frames.append(result.summary_row)

    if summary_frames:
        all_stores_summary = pd.concat(summary_frames, ignore_index=True)
        all_stores_summary = all_stores_summary.sort_values(by="store_id").reset_index(drop=True)
    else:
        all_stores_summary = pd.DataFrame(
            columns=[
                "store_id",
                "total_images",
                "valid_images",
                "relevant_images",
                "total_people",
                "estimated_visits",
                "avg_dwell_sec",
                "bounce_rate",
                "footfall",
                "loss_of_sale_alerts",
                "top_camera_hotspot",
                "peak_time_bucket",
                "daily_walkins",
                "daily_conversions",
                "daily_conversion_rate",
            ]
        )

    return AnalysisOutput(
        stores=store_results,
        all_stores_summary=all_stores_summary,
        detector_warning=detector_warning,
        used_root_fallback_store=used_root_fallback_store,
    )


def export_analysis(
    output: AnalysisOutput,
    out_dir: Path,
    write_gzip_exports: bool = True,
    keep_plain_csv: bool = True,
) -> None:
    """Export analysis outputs with optional gzip compression for lower disk footprint."""
    out_dir.mkdir(parents=True, exist_ok=True)

    def _write(df: pd.DataFrame, path: Path) -> None:
        if keep_plain_csv:
            df.to_csv(path, index=False)
        if write_gzip_exports:
            df.to_csv(path.with_suffix(path.suffix + ".gz"), index=False, compression="gzip")

    _write(output.all_stores_summary, out_dir / "all_stores_summary.csv")
    for store_id, store_result in output.stores.items():
        image_path = out_dir / f"store_{store_id}_image_insights.csv"
        hotspot_path = out_dir / f"store_{store_id}_camera_hotspots.csv"
        location_hotspot_path = out_dir / f"store_{store_id}_location_hotspots.csv"
        sessions_path = out_dir / f"store_{store_id}_customer_sessions.csv"
        _write(
            store_result.image_insights[
                [
                    "store_id",
                    "filename",
                    "camera_id",
                    "timestamp",
                    "capture_date",
                    "source_folder",
                    "is_valid",
                    "person_count",
                    "max_person_conf",
                    "relevant",
                    "staff_count",
                    "customer_count",
                    "gender_likelihood",
                    "age_bucket_counts",
                    "age_confidence",
                    "age_gender_error",
                    "track_ids",
                    "global_visit_id",
                    "customer_ids",
                    "legacy_customer_ids",
                    "store_day_customer_ids",
                    "customer_session_ids",
                    "group_ids",
                    "floor_name",
                    "location_name",
                    "person_centroids",
                    "person_boxes",
                    "staff_flags",
                    "staff_scores",
                    "reject_reason",
                    "detection_error",
                    "relative_path",
                    "drive_link",
                    "path",
                ]
            ],
            image_path,
        )
        _write(
            store_result.camera_hotspots[
                [
                    "store_id",
                    "camera_id",
                    "relevant_images",
                    "total_people",
                    "avg_people_per_relevant_image",
                    "hotspot_rank",
                ]
            ],
            hotspot_path,
        )
        _write(
            store_result.location_hotspots[
                [
                    "store_id",
                    "floor_name",
                    "location_name",
                    "relevant_images",
                    "total_people",
                    "avg_people_per_relevant_image",
                    "avg_dwell_sec",
                    "hotspot_rank",
                ]
            ],
            location_hotspot_path,
        )
        _write(
            store_result.customer_sessions[
                [
                    "store_id",
                    "capture_date",
                    "store_day_customer_id",
                    "entry_ts",
                    "exit_ts",
                    "dwell_sec",
                    "close_reason",
                    "converted_proxy",
                    "cameras_seen",
                    "locations_seen",
                    "floors_seen",
                ]
            ],
            sessions_path,
        )
        if not store_result.daily_report.empty:
            _write(store_result.daily_report, out_dir / f"store_{store_id}_daily_report.csv")
        if not store_result.daily_proof.empty:
            _write(store_result.daily_proof, out_dir / f"store_{store_id}_daily_proof.csv")
        if not store_result.alerts.empty:
            _write(store_result.alerts, out_dir / f"store_{store_id}_alerts.csv")


def export_store_day_artifacts(
    output: AnalysisOutput,
    out_dir: Path,
    store_id: str,
    capture_date: str,
    write_gzip_exports: bool = True,
    keep_plain_csv: bool = True,
) -> list[Path]:
    sid = store_id.strip()
    cdate = capture_date.strip()
    if not sid or not cdate or sid not in output.stores:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    result = output.stores[sid]
    suffix = cdate
    created_paths: list[Path] = []

    def _write(df: pd.DataFrame, path: Path) -> None:
        if keep_plain_csv:
            df.to_csv(path, index=False)
            created_paths.append(path)
        if write_gzip_exports:
            gz_path = path.with_suffix(path.suffix + ".gz")
            df.to_csv(gz_path, index=False, compression="gzip")
            created_paths.append(gz_path)

    day_images = result.image_insights[
        result.image_insights["capture_date"].astype(str) == cdate
    ].copy()
    day_sessions = result.customer_sessions[
        result.customer_sessions["capture_date"].astype(str) == cdate
    ].copy()
    day_proof = result.daily_proof[result.daily_proof["date"].astype(str) == cdate].copy()
    day_location_hotspots = build_location_hotspots(day_images, store_id=sid)

    _write(day_images, out_dir / f"store_{sid}_{suffix}_image_insights.csv")
    _write(day_sessions, out_dir / f"store_{sid}_{suffix}_customer_sessions.csv")
    _write(day_location_hotspots, out_dir / f"store_{sid}_{suffix}_location_hotspots.csv")
    _write(day_proof, out_dir / f"store_{sid}_{suffix}_daily_proof.csv")
    return created_paths


def load_exports(out_dir: Path) -> AnalysisOutput:
    summary_path = out_dir / "all_stores_summary.csv"
    summary_gz_path = out_dir / "all_stores_summary.csv.gz"
    if not summary_path.exists() and not summary_gz_path.exists():
        return AnalysisOutput(
            stores={},
            all_stores_summary=pd.DataFrame(
                columns=[
                    "store_id",
                    "total_images",
                    "valid_images",
                    "relevant_images",
                    "total_people",
                    "estimated_visits",
                    "avg_dwell_sec",
                    "bounce_rate",
                    "footfall",
                    "loss_of_sale_alerts",
                    "top_camera_hotspot",
                    "peak_time_bucket",
                    "daily_walkins",
                    "daily_conversions",
                    "daily_conversion_rate",
                ]
            ),
            detector_warning="",
            used_root_fallback_store=False,
        )

    all_stores_summary = pd.read_csv(summary_path if summary_path.exists() else summary_gz_path)
    stores: dict[str, StoreAnalysisResult] = {}
    for store_id in all_stores_summary["store_id"].astype(str).tolist():
        image_path = out_dir / f"store_{store_id}_image_insights.csv"
        hotspot_path = out_dir / f"store_{store_id}_camera_hotspots.csv"
        location_hotspot_path = out_dir / f"store_{store_id}_location_hotspots.csv"
        sessions_path = out_dir / f"store_{store_id}_customer_sessions.csv"
        image_gz_path = image_path.with_suffix(image_path.suffix + ".gz")
        hotspot_gz_path = hotspot_path.with_suffix(hotspot_path.suffix + ".gz")
        location_hotspot_gz_path = location_hotspot_path.with_suffix(location_hotspot_path.suffix + ".gz")
        sessions_gz_path = sessions_path.with_suffix(sessions_path.suffix + ".gz")
        if not (image_path.exists() or image_gz_path.exists()) or not (hotspot_path.exists() or hotspot_gz_path.exists()):
            continue

        image_df = pd.read_csv(image_path if image_path.exists() else image_gz_path, parse_dates=["timestamp"])
        hotspot_df = pd.read_csv(hotspot_path if hotspot_path.exists() else hotspot_gz_path)
        location_hotspots_df = pd.DataFrame(
            columns=[
                "store_id",
                "floor_name",
                "location_name",
                "relevant_images",
                "total_people",
                "avg_people_per_relevant_image",
                "avg_dwell_sec",
                "hotspot_rank",
            ]
        )
        if location_hotspot_path.exists() or location_hotspot_gz_path.exists():
            location_hotspots_df = pd.read_csv(
                location_hotspot_path if location_hotspot_path.exists() else location_hotspot_gz_path
            )
        customer_sessions_df = pd.DataFrame(
            columns=[
                "store_id",
                "capture_date",
                "store_day_customer_id",
                "entry_ts",
                "exit_ts",
                "dwell_sec",
                "close_reason",
                "converted_proxy",
                "cameras_seen",
                "locations_seen",
                "floors_seen",
            ]
        )
        if sessions_path.exists() or sessions_gz_path.exists():
            customer_sessions_df = pd.read_csv(
                sessions_path if sessions_path.exists() else sessions_gz_path,
                parse_dates=["entry_ts", "exit_ts"],
            )
        summary_row = all_stores_summary[all_stores_summary["store_id"] == store_id].copy()
        alerts_path = out_dir / f"store_{store_id}_alerts.csv"
        alerts_gz_path = alerts_path.with_suffix(alerts_path.suffix + ".gz")
        alerts_df = pd.DataFrame(columns=["alert_type","camera_id","track_id","dwell_sec","risk_score","reason_codes"])
        if alerts_path.exists() or alerts_gz_path.exists():
            alerts_df = pd.read_csv(alerts_path if alerts_path.exists() else alerts_gz_path)
        daily_path = out_dir / f"store_{store_id}_daily_report.csv"
        daily_gz_path = daily_path.with_suffix(daily_path.suffix + ".gz")
        daily_df = pd.DataFrame(columns=["date","unique_individuals","unique_groups","actual_customers","converted_individuals","converted_groups","actual_conversions","conversion_rate"])
        if daily_path.exists() or daily_gz_path.exists():
            daily_df = pd.read_csv(daily_path if daily_path.exists() else daily_gz_path)
        daily_proof_path = out_dir / f"store_{store_id}_daily_proof.csv"
        daily_proof_gz_path = daily_proof_path.with_suffix(daily_proof_path.suffix + ".gz")
        daily_proof_df = pd.DataFrame(
            columns=[
                "store_id",
                "date",
                "folder_name",
                "total_images",
                "valid_images",
                "relevant_images",
                "total_detected_people",
                "individual_people",
                "group_people",
                "converted",
                "conversion_rate",
            ]
        )
        if daily_proof_path.exists() or daily_proof_gz_path.exists():
            daily_proof_df = pd.read_csv(
                daily_proof_path if daily_proof_path.exists() else daily_proof_gz_path
            )

        stores[store_id] = StoreAnalysisResult(
            image_insights=image_df,
            camera_hotspots=hotspot_df,
            location_hotspots=location_hotspots_df,
            customer_sessions=customer_sessions_df,
            summary_row=summary_row,
            alerts=alerts_df,
            daily_report=daily_df,
            daily_proof=daily_proof_df,
        )

    return AnalysisOutput(
        stores=stores,
        all_stores_summary=all_stores_summary,
        detector_warning="",
        used_root_fallback_store=False,
    )

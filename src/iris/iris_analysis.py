from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import math
import csv
import json
import os
import re
import colorsys
import pickle
import sys
from typing import Any, Protocol, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

_TORCH_PRELOAD_ERROR = ""
if (
    os.name == "nt"
    and "pytest" not in sys.modules
    and str(os.getenv("IRIS_PRELOAD_TORCH", "1")).strip() != "0"
):
    # On Windows, importing torch after numpy/pandas/opencv can fail with WinError 1114 (c10.dll init).
    # Preloading torch first stabilizes the YOLO runtime path without forcing YOLO usage.
    try:
        import torch as _torch_preload  # type: ignore  # noqa: F401
    except Exception as exc:
        _TORCH_PRELOAD_ERROR = str(exc)

import cv2
import numpy as np
import pandas as pd
from PIL import Image
from pydantic import BaseModel, Field, field_validator
import hashlib

from PIL import Image
from iris.entrance_pipeline import enrich_entrance_camera_classification


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
    person_confidences: list[float] = field(default_factory=list)
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


class CachedPersonDetector:
    """Wrapper that caches detection results to disk based on file hash and mtime."""

    def __init__(self, detector: PersonDetector, cache_dir: Path):
        self.detector = detector
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        parts = [detector.__class__.__name__]
        for attr in ("model_name", "conf_threshold", "device", "reason"):
            if hasattr(detector, attr):
                try:
                    parts.append(f"{attr}={getattr(detector, attr)}")
                except Exception:
                    continue
        self.detector_signature = "|".join(parts)

    def _get_cache_path(self, image_path: Path) -> Path:
        try:
            stats = image_path.stat()
            content = f"{self.detector_signature}_{image_path.name}_{stats.st_size}_{stats.st_mtime}".encode()
            hash_val = hashlib.md5(content).hexdigest()
            return self.cache_dir / f"{hash_val}.json"
        except Exception:
            # Fallback if stat fails
            return self.cache_dir / f"{image_path.stem}_fallback.json"

    def detect(self, image_path: Path) -> DetectionResult:
        cache_path = self._get_cache_path(image_path)
        
        # Try to load from cache
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return DetectionResult(**data)
            except Exception:
                pass
        
        # Run detection and cache
        result = self.detector.detect(image_path)
        
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                data = {
                    "person_count": result.person_count,
                    "max_person_conf": result.max_person_conf,
                    "detection_error": result.detection_error,
                    "person_centroids": result.person_centroids,
                    "person_boxes": result.person_boxes,
                    "bag_count": result.bag_count,
                }
                json.dump(data, f)
        except Exception:
            pass
        
        return result



class MockPersonDetector:
    """Deterministic detector useful for tests and local fallback."""

    def __init__(self, conf_threshold: float = 0.25) -> None:
        self.conf_threshold = conf_threshold

    def detect(self, image_path: Path) -> DetectionResult:
        seed = sum(ord(ch) for ch in image_path.name)
        person_count = seed % 4
        if person_count == 0:
            return DetectionResult(
                person_count=0,
                max_person_conf=0.0,
                detection_error="",
                person_centroids=[],
                person_boxes=[],
                person_confidences=[],
                bag_count=0,
            )
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
            person_confidences=[round(max_conf, 3)] * person_count,
            bag_count=0,
        )


class UnavailableDetector:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def detect(self, image_path: Path) -> DetectionResult:
        return DetectionResult(
            person_count=0,
            max_person_conf=0.0,
            detection_error=self.reason,
            person_centroids=[],
            person_boxes=[],
            person_confidences=[],
            bag_count=0,
        )


def _is_reasonable_person_box(box: tuple[float, float, float, float]) -> bool:
    x1, y1, x2, y2 = box
    w = max(0.0, x2 - x1)
    h = max(0.0, y2 - y1)
    area = w * h
    if w <= 0 or h <= 0:
        return False
    aspect = h / max(w, 1e-6)
    return (
        0.003 <= area <= 0.65 and
        1.0 <= aspect <= 5.5 and
        h >= 0.06
    )


class YoloPersonDetector:
    def __init__(
        self,
        model_name: str = "data/models/yolov8s.pt",
        conf_threshold: float = 0.20,
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
                return DetectionResult(
                    person_count=0,
                    max_person_conf=0.0,
                    detection_error="",
                    person_centroids=[],
                    person_boxes=[],
                    person_confidences=[],
                    bag_count=0,
                )

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
                    conf_val = float(conf_values[i]) if i < len(conf_values) else 0.0
                    centroid = None
                    box = None
                    if i < len(xywhn):
                        centroid = (float(xywhn[i][0]), float(xywhn[i][1]))
                    if i < len(xyxyn):
                        candidate_box = (
                            float(xyxyn[i][0]),
                            float(xyxyn[i][1]),
                            float(xyxyn[i][2]),
                            float(xyxyn[i][3]),
                        )
                        if _is_reasonable_person_box(candidate_box):
                            box = candidate_box
                    if box is not None:
                        person_conf.append(conf_val)
                        person_boxes.append(box)
                        if centroid is not None:
                            person_centroids.append(centroid)
                        else:
                            person_centroids.append(((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0))
                elif int(cls_id) == 26:
                    bag_count += 1

            if not person_conf:
                return DetectionResult(
                    person_count=0,
                    max_person_conf=0.0,
                    detection_error="",
                    person_centroids=[],
                    person_boxes=[],
                    person_confidences=[],
                    bag_count=bag_count,
                )

            return DetectionResult(
                person_count=len(person_conf),
                max_person_conf=float(max(person_conf)),
                detection_error="",
                person_centroids=person_centroids,
                person_boxes=person_boxes,
                person_confidences=person_conf,
                bag_count=bag_count,
            )
        except Exception as exc:
            return DetectionResult(
                person_count=0,
                max_person_conf=0.0,
                detection_error=str(exc),
                person_centroids=[],
                person_boxes=[],
                person_confidences=[],
                bag_count=0,
            )


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
                    person_confidences=[],
                    bag_count=0,
                )
            return DetectionResult(
                person_count=len(person_conf),
                max_person_conf=float(max(person_conf)),
                detection_error="",
                person_centroids=person_centroids,
                person_boxes=person_boxes,
                person_confidences=person_conf,
                bag_count=0,
            )
        except Exception as exc:
            return DetectionResult(
                person_count=0,
                max_person_conf=0.0,
                detection_error=str(exc),
                person_centroids=[],
                person_boxes=[],
                person_confidences=[],
                bag_count=0,
            )


class OpenCvHogPersonDetector:
    """CPU-safe fallback detector when YOLO/TensorFlow runtimes are unavailable."""

    def __init__(self, conf_threshold: float = 0.0) -> None:
        self.conf_threshold = conf_threshold
        self.model_name = "opencv_hog_default_people"
        self.device = "cpu"
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, image_path: Path) -> DetectionResult:
        try:
            frame = cv2.imread(str(image_path))
            if frame is None:
                return DetectionResult(
                    person_count=0,
                    max_person_conf=0.0,
                    detection_error="opencv_read_failed",
                    person_centroids=[],
                    person_boxes=[],
                    person_confidences=[],
                    bag_count=0,
                )
            h, w = frame.shape[:2]
            rects, weights = self.hog.detectMultiScale(
                frame,
                winStride=(8, 8),
                padding=(8, 8),
                scale=1.05,
            )
            person_boxes: list[tuple[float, float, float, float]] = []
            person_centroids: list[tuple[float, float]] = []
            person_conf: list[float] = []
            for i, (x, y, bw, bh) in enumerate(rects):
                x1 = max(0.0, min(1.0, float(x) / float(max(1, w))))
                y1 = max(0.0, min(1.0, float(y) / float(max(1, h))))
                x2 = max(0.0, min(1.0, float(x + bw) / float(max(1, w))))
                y2 = max(0.0, min(1.0, float(y + bh) / float(max(1, h))))
                box = (x1, y1, x2, y2)
                if not _is_reasonable_person_box(box):
                    continue
                person_boxes.append(box)
                person_centroids.append((round((x1 + x2) / 2.0, 4), round((y1 + y2) / 2.0, 4)))
                score = float(weights[i]) if i < len(weights) else 0.4
                person_conf.append(round(max(0.0, min(1.0, score)), 4))
            if not person_boxes:
                return DetectionResult(
                    person_count=0,
                    max_person_conf=0.0,
                    detection_error="",
                    person_centroids=[],
                    person_boxes=[],
                    person_confidences=[],
                    bag_count=0,
                )
            return DetectionResult(
                person_count=len(person_boxes),
                max_person_conf=float(max(person_conf)),
                detection_error="",
                person_centroids=person_centroids,
                person_boxes=person_boxes,
                person_confidences=person_conf,
                bag_count=0,
            )
        except Exception as exc:
            return DetectionResult(
                person_count=0,
                max_person_conf=0.0,
                detection_error=f"opencv_hog_error: {exc}",
                person_centroids=[],
                person_boxes=[],
                person_confidences=[],
                bag_count=0,
            )


def build_detector(detector_type: str = "yolo", conf_threshold: float = 0.20, use_cache: bool = True) -> tuple[PersonDetector, str]:
    normalized = str(detector_type).strip().lower()
    detector: PersonDetector
    warning = ""
    
    if normalized in {"tensorflow_frcnn", "tf_frcnn", "legacy_tf_frcnn"}:
        model_path = os.getenv("TF_FRCNN_MODEL_PATH", "data/models/frozen_inference_graph.pb").strip()
        try:
            detector = LegacyTfPersonDetector(model_path=model_path, conf_threshold=conf_threshold)
        except Exception as exc:
            warning = f"TF_FRCNN detector unavailable: {exc}"
            detector = UnavailableDetector(warning)
    elif normalized == "mock":
        detector = MockPersonDetector(conf_threshold=conf_threshold)
    elif normalized in {"opencv_hog", "hog"}:
        detector = OpenCvHogPersonDetector(conf_threshold=conf_threshold)
    elif normalized != "yolo":
        warning = f"Unsupported detector_type='{detector_type}', using unavailable detector fallback."
        detector = UnavailableDetector(warning)
    else:
        try:
            detector = YoloPersonDetector(
                model_name=os.getenv("YOLO_MODEL_PATH", "data/models/yolov8s.pt"),
                conf_threshold=conf_threshold,
            )
        except Exception as exc:
            yolo_warning = f"YOLO detector unavailable: {exc}"
            if _TORCH_PRELOAD_ERROR and "1114" in str(exc):
                yolo_warning += (
                    f" | torch preload diagnostic: {_TORCH_PRELOAD_ERROR}"
                )
            try:
                detector = OpenCvHogPersonDetector(conf_threshold=conf_threshold)
                warning = f"{yolo_warning}. Fallback active: OpenCV HOG."
            except Exception as hog_exc:
                warning = f"{yolo_warning}. OpenCV HOG fallback unavailable: {hog_exc}"
                detector = UnavailableDetector(warning)
            
    if use_cache and not isinstance(detector, UnavailableDetector):
        cache_dir = Path("data/cache/detections")
        detector = CachedPersonDetector(detector, cache_dir)
        
    return detector, warning


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


def _compute_color_histogram(image: Image.Image) -> np.ndarray:
    """Compute normalized HSV color histogram."""
    img_cv = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([img_cv], [0, 1], None, [16, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist

def _load_staff_reference_shirts(store_id: str, employee_assets_root: Path | None) -> list[Image.Image]:
    if employee_assets_root is None:
        return []
    store_dir = employee_assets_root / store_id
    if not store_dir.exists() or not store_dir.is_dir():
        return []
    
    refs: list[Image.Image] = []
    for path in sorted(store_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in EMPLOYEE_IMAGE_EXTENSIONS:
            try:
                img = Image.open(path)
                img.load()
                refs.append(img)
                if len(refs) >= 50:  # limit
                    break
            except Exception:
                pass
    return refs

def _classify_staff_by_shirt_color(
    image_path: Path,
    person_boxes: list[tuple[float, float, float, float]],
    store_id: str,
    reference_shirts: Optional[list[Image.Image]] = None,
    red_threshold: float = 0.22,  # kept for signature backward compat if needed
) -> tuple[list[bool], list[float]]:
    if not person_boxes:
        return [], []
    try:
        if reference_shirts is None or len(reference_shirts) == 0:
            # Fallback to simple logic if no reference images
            return _classify_staff_by_red_ratio_fallback(image_path, person_boxes, red_threshold)
            
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
                    
                shirt_crop = rgb.crop((x1, sy1, x2, sy2))
                
                # Use color histogram comparison
                hist = _compute_color_histogram(shirt_crop)
                best_match = 0.0
                for ref_shirt in reference_shirts:
                    ref_hist = _compute_color_histogram(ref_shirt)
                    similarity = cv2.compareHist(hist, ref_hist, cv2.HISTCMP_CORREL)
                    best_match = max(best_match, similarity)
                
                is_staff = best_match > 0.6  # Threshold on histogram correlation
                flags.append(is_staff)
                scores.append(round(best_match, 4))
            
            return flags, scores
    except Exception:
        return [False for _ in person_boxes], [0.0 for _ in person_boxes]


def _is_red_pixel(r: int, g: int, b: int) -> bool:
    h_val, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue_deg = h_val * 360.0
    return (
        ((hue_deg <= 20.0) or (hue_deg >= 340.0)) and
        s >= 0.35 and
        v >= 0.20
    )


def _classify_staff_by_red_ratio_fallback(
    image_path: Path,
    person_boxes: list[tuple[float, float, float, float]],
    red_threshold: float = 0.22,
) -> tuple[list[bool], list[float]]:
    """Legacy color-threshold fallback."""
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
                sy1 = y1 + int(h * 0.30)
                sy2 = y1 + int(h * 0.70)
                if sy2 <= sy1:
                    sy1 = y1
                    sy2 = y2
                crop = rgb.crop((x1, sy1, x2, y2)).resize((40, 40))
                data = list(crop.getdata())
                if not data:
                    flags.append(False)
                    scores.append(0.0)
                    continue
                red_pixels = 0
                for r, g, b in data:
                    if _is_red_pixel(r, g, b):
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
                if _is_red_pixel(r, g, b):
                    red_pixels += 1
            return float(red_pixels / len(data))
    except Exception:
        return 0.0


def _estimate_store_staff_red_threshold(
    store_id: str,
    employee_assets_root: Path | None,
) -> float:
    baseline = 0.18
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
    adaptive = avg_ratio * 0.75
    return max(0.12, min(0.30, adaptive))


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


def _matches_filename_filters(filename: str, filters: list[str] | None) -> bool:
    normalized = [str(f).strip() for f in (filters or []) if str(f).strip()]
    if not normalized:
        return True
    name = str(filename)
    for token in normalized:
        if name.startswith(token) or token in name:
            return True
    return False


def _coerce_box(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1 = float(value[0])  # type: ignore[index]
        y1 = float(value[1])  # type: ignore[index]
        x2 = float(value[2])  # type: ignore[index]
        y2 = float(value[3])  # type: ignore[index]
    except Exception:
        return None
    if not all(math.isfinite(v) for v in [x1, y1, x2, y2]):
        return None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    x2 = max(0.0, min(1.0, x2))
    y2 = max(0.0, min(1.0, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _parse_box_list(value: object) -> list[tuple[float, float, float, float]]:
    out: list[tuple[float, float, float, float]] = []
    for item in _safe_json_list(value):
        box = _coerce_box(item)
        if box is not None:
            out.append(box)
    return out


def _parse_centroid_list(value: object) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for item in _safe_json_list(value):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            x = float(item[0])  # type: ignore[index]
            y = float(item[1])  # type: ignore[index]
        except Exception:
            continue
        if math.isfinite(x) and math.isfinite(y):
            out.append((x, y))
    return out


def _parse_bool_list(value: object, expected: int) -> list[bool]:
    parsed = [bool(v) for v in _safe_json_list(value)]
    if len(parsed) < expected:
        parsed.extend([False] * (expected - len(parsed)))
    return parsed[:expected]


def _parse_float_list(value: object, expected: int) -> list[float]:
    parsed: list[float] = []
    for item in _safe_json_list(value):
        try:
            parsed.append(float(item))
        except Exception:
            parsed.append(0.0)
    if len(parsed) < expected:
        parsed.extend([0.0] * (expected - len(parsed)))
    return parsed[:expected]


def _box_centroid(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _box_area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, (box[2] - box[0]) * (box[3] - box[1]))


def _box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = _box_area(a) + _box_area(b) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _suppress_false_positives_ml(
    image_insights: pd.DataFrame,
    false_positive_model: Optional[Any] = None,
) -> pd.DataFrame:
    """
    Use a small classifier to refine non-person crops if provided.
    Placeholder integration - skip if model is not set.
    """
    if image_insights.empty or false_positive_model is None:
        return image_insights
        
    df = image_insights.copy()
    
    for idx in df[df["person_count"] > 0].index:
        path_str = str(df.at[idx, "path"]).strip()
        if not path_str:
            continue
        path = Path(path_str)
        boxes = _parse_box_list(df.at[idx, "person_boxes"])
        
        if not boxes or not path.exists():
            continue
            
        try:
            with Image.open(path) as img:
                rgb = img.convert("RGB")
                width, height = rgb.size
                
                keep_idxs = []
                for i, box in enumerate(boxes):
                    x1 = int(box[0] * width)
                    y1 = int(box[1] * height)
                    x2 = int(box[2] * width)
                    y2 = int(box[3] * height)
                    
                    if x1 >= x2 or y1 >= y2:
                        continue
                        
                    crop = rgb.crop((x1, y1, x2, y2)).resize((64, 64))
                    crop_array = np.array(crop) / 255.0
                    
                    # Assuming a scikit-learn 'predict_proba' style interface
                    if hasattr(false_positive_model, "predict_proba"):
                        proba = false_positive_model.predict_proba([crop_array])
                        is_person_prob = proba[0][1] if proba.shape[1] > 1 else proba[0][0]
                    else:
                        is_person_prob = 1.0
                        
                    if is_person_prob > 0.3:  # keep if confident it's a person
                        keep_idxs.append(i)
                
                if len(keep_idxs) < len(boxes):
                    dropped_count = len(boxes) - len(keep_idxs)
                    
                    try:
                        raw_c = str(df.at[idx, "person_centroids"]).strip()
                        centroids = json.loads(raw_c)
                        raw_f = str(df.at[idx, "staff_flags"]).strip()
                        staff_flags = [bool(v) for v in json.loads(raw_f)]
                        
                        new_boxes = [boxes[i] for i in keep_idxs]
                        new_centroids = [centroids[i] for i in keep_idxs if i < len(centroids)]
                        new_staff_flags = [staff_flags[i] for i in keep_idxs if i < len(staff_flags)]
                        
                        df.at[idx, "person_boxes"] = json.dumps(new_boxes)
                        df.at[idx, "person_centroids"] = json.dumps(new_centroids)
                        df.at[idx, "staff_flags"] = json.dumps(new_staff_flags)
                        df.at[idx, "person_count"] = max(0, int(df.at[idx, "person_count"]) - dropped_count)
                        new_staff_count = sum(1 for f in new_staff_flags if f)
                        df.at[idx, "staff_count"] = new_staff_count
                        df.at[idx, "customer_count"] = max(0, int(df.at[idx, "person_count"]) - new_staff_count)
                    except Exception:
                        pass
        except Exception:
            continue
            
    return df

def _ahash_from_crop(
    image: Image.Image,
    box: tuple[float, float, float, float],
    hash_side: int = 8,
) -> str:
    width, height = image.size
    x1 = max(0, min(width - 1, int(float(box[0]) * width)))
    y1 = max(0, min(height - 1, int(float(box[1]) * height)))
    x2 = max(x1 + 1, min(width, int(float(box[2]) * width)))
    y2 = max(y1 + 1, min(height, int(float(box[3]) * height)))
    crop = image.crop((x1, y1, x2, y2)).convert("L").resize((hash_side, hash_side))
    arr = np.array(crop, dtype=np.float32)
    if arr.size == 0:
        return ""
    avg = float(arr.mean())
    bits = ["1" if float(v) >= avg else "0" for v in arr.flatten().tolist()]
    bit_string = "".join(bits)
    if not bit_string:
        return ""
    return f"{int(bit_string, 2):0{(hash_side * hash_side + 3) // 4}x}"


def _hex_hamming_distance(a: str, b: str, bits: int = 64) -> int:
    try:
        a_int = int(str(a).strip(), 16)
        b_int = int(str(b).strip(), 16)
        xor_val = a_int ^ b_int
        return int(bin(xor_val).count("1"))
    except Exception:
        return bits


def _suppress_learned_false_positives(
    image_insights: pd.DataFrame,
    false_positive_signatures: list[dict[str, object]] | None,
) -> pd.DataFrame:
    if image_insights.empty or not false_positive_signatures:
        return image_insights
    df = image_insights.copy()
    signatures_by_camera: dict[str, list[dict[str, object]]] = {}
    for raw_sig in false_positive_signatures:
        camera_id = str(raw_sig.get("camera_id", "")).strip().upper()
        box = _coerce_box(_safe_json_list(raw_sig.get("box_json", "[]")))
        sig_hash = str(raw_sig.get("hash64", "")).strip().lower()
        try:
            ham_th = max(1, int(raw_sig.get("hamming_threshold", 10)))
        except Exception:
            ham_th = 10
        if not camera_id or box is None or not sig_hash:
            continue
        signatures_by_camera.setdefault(camera_id, []).append(
            {
                "box": box,
                "hash64": sig_hash,
                "hamming_threshold": ham_th,
            }
        )
    if not signatures_by_camera:
        return df

    for row_idx in df.index.tolist():
        camera_id = str(df.at[row_idx, "camera_id"]).strip().upper()
        signatures = signatures_by_camera.get(camera_id, [])
        if not signatures:
            continue
        is_valid = bool(df.at[row_idx, "is_valid"])
        det_err = str(df.at[row_idx, "detection_error"] or "").strip()
        if not is_valid or det_err:
            continue
        boxes = _parse_box_list(df.at[row_idx, "person_boxes"])
        if not boxes:
            continue
        path = Path(str(df.at[row_idx, "path"] or "").strip())
        if not path.exists() or not path.is_file():
            continue
        try:
            with Image.open(path) as img:
                rgb = img.convert("RGB")
                box_hashes = [_ahash_from_crop(rgb, box) for box in boxes]
        except Exception:
            continue

        remove_idxs: set[int] = set()
        for i, box in enumerate(boxes):
            crop_hash = box_hashes[i] if i < len(box_hashes) else ""
            if not crop_hash:
                continue
            for sig in signatures:
                sig_box = sig["box"]  # type: ignore[index]
                if _box_iou(box, sig_box) < 0.45:  # type: ignore[arg-type]
                    continue
                dist = _hex_hamming_distance(crop_hash, str(sig["hash64"]))  # type: ignore[index]
                if dist <= int(sig["hamming_threshold"]):  # type: ignore[index]
                    remove_idxs.add(i)
                    break

        if not remove_idxs:
            continue
        keep = [i for i in range(len(boxes)) if i not in remove_idxs]
        kept_boxes = [boxes[i] for i in keep]
        centroids = _parse_centroid_list(df.at[row_idx, "person_centroids"])
        if len(centroids) == len(boxes):
            kept_centroids = [centroids[i] for i in keep]
        else:
            kept_centroids = [_box_centroid(box) for box in kept_boxes]
        staff_flags = _parse_bool_list(df.at[row_idx, "staff_flags"], expected=len(boxes))
        staff_scores = _parse_float_list(df.at[row_idx, "staff_scores"], expected=len(boxes))
        kept_staff_flags = [staff_flags[i] for i in keep]
        kept_staff_scores = [staff_scores[i] for i in keep]
        person_count = int(len(kept_boxes))
        staff_count = int(min(person_count, sum(1 for flag in kept_staff_flags if bool(flag))))
        customer_count = int(max(0, person_count - staff_count))

        df.at[row_idx, "person_boxes"] = json.dumps(kept_boxes)
        df.at[row_idx, "person_centroids"] = json.dumps(kept_centroids)
        df.at[row_idx, "staff_flags"] = json.dumps(kept_staff_flags)
        df.at[row_idx, "staff_scores"] = json.dumps(kept_staff_scores)
        df.at[row_idx, "person_count"] = person_count
        df.at[row_idx, "staff_count"] = staff_count
        df.at[row_idx, "customer_count"] = customer_count
        if person_count <= 0:
            df.at[row_idx, "max_person_conf"] = 0.0
        df.at[row_idx, "relevant"] = bool(is_valid and person_count >= 1)
    return df


def _suppress_static_false_person_boxes(image_insights: pd.DataFrame) -> pd.DataFrame:
    if image_insights.empty:
        return image_insights
    required_cols = {
        "capture_date",
        "camera_id",
        "is_valid",
        "detection_error",
        "person_boxes",
        "person_centroids",
        "staff_flags",
        "staff_scores",
        "person_count",
        "staff_count",
        "customer_count",
        "max_person_conf",
        "relevant",
    }
    if not required_cols.issubset(set(image_insights.columns)):
        return image_insights

    df = image_insights.copy()
    valid_mask = (
        df["is_valid"].astype(bool)
        & df["detection_error"].fillna("").astype(str).str.strip().eq("")
        & df["camera_id"].fillna("").astype(str).str.strip().ne("")
        & df["capture_date"].fillna("").astype(str).str.strip().ne("")
    )
    scoped = df[valid_mask]
    if scoped.empty:
        return df

    for (_capture_date, _camera_id), indexes in scoped.groupby(["capture_date", "camera_id"]).groups.items():
        idx_list = list(indexes)
        if len(idx_list) < 6:
            continue

        clusters: list[dict[str, object]] = []
        row_boxes: dict[int, list[tuple[float, float, float, float]]] = {}
        frames_with_boxes = 0
        overlap_threshold = 0.72

        for idx in idx_list:
            boxes = _parse_box_list(df.at[idx, "person_boxes"])
            row_boxes[int(idx)] = boxes
            if not boxes:
                continue
            frames_with_boxes += 1
            for box_idx, box in enumerate(boxes):
                best_cluster: int | None = None
                best_iou = 0.0
                for c_idx, cluster in enumerate(clusters):
                    rep_box = cluster["rep_box"]  # type: ignore[index]
                    iou = _box_iou(box, rep_box)  # type: ignore[arg-type]
                    if iou >= overlap_threshold and iou > best_iou:
                        best_cluster = c_idx
                        best_iou = iou
                if best_cluster is None:
                    clusters.append(
                        {
                            "rep_box": box,
                            "occurrences": [(int(idx), int(box_idx), box)],
                        }
                    )
                else:
                    cluster = clusters[best_cluster]
                    occurrences = cluster["occurrences"]  # type: ignore[index]
                    occurrences.append((int(idx), int(box_idx), box))  # type: ignore[attr-defined]
                    coords = np.array([o[2] for o in occurrences], dtype=float)
                    cluster["rep_box"] = (
                        float(coords[:, 0].mean()),
                        float(coords[:, 1].mean()),
                        float(coords[:, 2].mean()),
                        float(coords[:, 3].mean()),
                    )

        if frames_with_boxes < 6:
            continue

        min_frames = max(6, int(math.ceil(frames_with_boxes * 0.80)))
        drop_map: dict[int, set[int]] = {}
        for cluster in clusters:
            occurrences = cluster["occurrences"]  # type: ignore[index]
            if not occurrences:
                continue
            frame_count = len({o[0] for o in occurrences})
            if frame_count < min_frames:
                continue
            coverage = frame_count / float(max(1, frames_with_boxes))
            centers = np.array([_box_centroid(o[2]) for o in occurrences], dtype=float)
            areas = np.array([_box_area(o[2]) for o in occurrences], dtype=float)
            center_std = float(max(np.std(centers[:, 0]), np.std(centers[:, 1])))
            area_mean = float(np.mean(areas))
            area_cv = float(np.std(areas) / max(1e-9, area_mean))
            if coverage >= 0.80 and center_std <= 0.015 and area_cv <= 0.08:
                for row_idx, box_idx, _ in occurrences:
                    drop_map.setdefault(int(row_idx), set()).add(int(box_idx))

        if not drop_map:
            continue

        for row_idx, remove_idxs in drop_map.items():
            boxes = row_boxes.get(int(row_idx), _parse_box_list(df.at[row_idx, "person_boxes"]))
            if not boxes:
                continue
            keep = [i for i in range(len(boxes)) if i not in remove_idxs]
            if len(keep) == len(boxes):
                continue
            kept_boxes = [boxes[i] for i in keep]
            centroids = _parse_centroid_list(df.at[row_idx, "person_centroids"])
            if len(centroids) == len(boxes):
                kept_centroids = [centroids[i] for i in keep]
            else:
                kept_centroids = [_box_centroid(box) for box in kept_boxes]
            staff_flags = _parse_bool_list(df.at[row_idx, "staff_flags"], expected=len(boxes))
            staff_scores = _parse_float_list(df.at[row_idx, "staff_scores"], expected=len(boxes))
            kept_staff_flags = [staff_flags[i] for i in keep]
            kept_staff_scores = [staff_scores[i] for i in keep]
            person_count = int(len(kept_boxes))
            staff_count = int(min(person_count, sum(1 for flag in kept_staff_flags if bool(flag))))
            customer_count = int(max(0, person_count - staff_count))

            df.at[row_idx, "person_boxes"] = json.dumps(kept_boxes)
            df.at[row_idx, "person_centroids"] = json.dumps(kept_centroids)
            df.at[row_idx, "staff_flags"] = json.dumps(kept_staff_flags)
            df.at[row_idx, "staff_scores"] = json.dumps(kept_staff_scores)
            df.at[row_idx, "person_count"] = person_count
            df.at[row_idx, "staff_count"] = staff_count
            df.at[row_idx, "customer_count"] = customer_count
            if person_count <= 0:
                df.at[row_idx, "max_person_conf"] = 0.0
            det_err = str(df.at[row_idx, "detection_error"] or "").strip()
            df.at[row_idx, "relevant"] = bool(df.at[row_idx, "is_valid"] and det_err == "" and person_count >= 1)

    return df


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

    day_cam_with_crossings: set[tuple[str, str]] = set()
    for (capture_date, camera_id, _track_id), events in track_events.items():
        ordered = sorted(events, key=lambda x: pd.Timestamp(x["ts"]))
        has_entered = False
        for a, b in zip(ordered, ordered[1:]):
            side_a = _line_side(float(a["cx"]), float(a["line_x"]))
            side_b = _line_side(float(b["cx"]), float(a["line_x"]))
            crossed_in, crossed_out = _cross_in_out(
                side_a=side_a,
                side_b=side_b,
                direction=str(a["direction"]),
            )
            ts = pd.Timestamp(b["ts"])
            if crossed_in and not has_entered:
                entry_counts.setdefault(capture_date, {})
                entry_counts[capture_date][ts] = int(entry_counts[capture_date].get(ts, 0)) + 1
                day_cam_with_crossings.add((capture_date, camera_id))
                has_entered = True
            if crossed_out and has_entered:
                exit_counts.setdefault(capture_date, {})
                exit_counts[capture_date][ts] = int(exit_counts[capture_date].get(ts, 0)) + 1
                day_cam_with_crossings.add((capture_date, camera_id))
                has_entered = False

    # Fallback: if track IDs are unstable, infer crossing via side-count deltas between gate frames.
    gate_rows = rows[rows["camera_id"].astype(str).map(lambda v: str(v).strip() in camera_configs)].copy()
    if not gate_rows.empty:
        for (capture_date, camera_id), group in gate_rows.groupby(["capture_date", "camera_id"]):
            capture_date = str(capture_date).strip() or str(pd.Timestamp(group["timestamp"].min()).date())
            camera_id = str(camera_id).strip()
            cfg = camera_configs.get(camera_id, {})
            role = str(cfg.get("camera_role", "INSIDE")).upper()
            if role not in {"ENTRANCE", "EXIT"}:
                continue
            if (capture_date, camera_id) in day_cam_with_crossings:
                continue
            line_x = float(cfg.get("entry_line_x", 0.5))
            direction = str(cfg.get("entry_direction", "OUTSIDE_TO_INSIDE")).upper()
            ordered = group[group["timestamp"].notna()].sort_values("timestamp")
            if ordered.empty:
                continue
            prev_left = None
            prev_right = None
            for _, row in ordered.iterrows():
                ts = pd.Timestamp(row["timestamp"])
                cents_raw = _safe_json_list(row.get("person_centroids", "[]"))
                left = 0
                right = 0
                for c in cents_raw:
                    try:
                        cx = float(c[0])  # type: ignore[index]
                    except Exception:
                        continue
                    if cx < line_x:
                        left += 1
                    else:
                        right += 1
                if prev_left is not None and prev_right is not None:
                    if direction == "OUTSIDE_TO_INSIDE":
                        inferred_in = max(0, right - prev_right)
                        inferred_out = max(0, left - prev_left)
                    else:
                        inferred_in = max(0, left - prev_left)
                        inferred_out = max(0, right - prev_right)
                    if inferred_in > 0:
                        entry_counts.setdefault(capture_date, {})
                        entry_counts[capture_date][ts] = int(entry_counts[capture_date].get(ts, 0)) + int(inferred_in)
                    if inferred_out > 0:
                        exit_counts.setdefault(capture_date, {})
                        exit_counts[capture_date][ts] = int(exit_counts[capture_date].get(ts, 0)) + int(inferred_out)
                prev_left = left
                prev_right = right

    # Secondary fallback for sparse/unstable tracks:
    # infer entry/exit from gate camera customer_count deltas over time.
    if not gate_rows.empty:
        for (capture_date, camera_id), group in gate_rows.groupby(["capture_date", "camera_id"]):
            capture_date = str(capture_date).strip()
            camera_id = str(camera_id).strip()
            cfg = camera_configs.get(camera_id, {})
            role = str(cfg.get("camera_role", "INSIDE")).upper()
            if role not in {"ENTRANCE", "EXIT"}:
                continue
            if entry_counts.get(capture_date) or exit_counts.get(capture_date):
                continue
            ordered = group[group["timestamp"].notna()].sort_values("timestamp")
            if ordered.empty:
                continue
            prev_count: int | None = None
            for _, row in ordered.iterrows():
                ts = pd.Timestamp(row["timestamp"])
                cur_count = int(pd.to_numeric([row.get("customer_count", 0)], errors="coerce")[0] or 0)
                if prev_count is None:
                    prev_count = cur_count
                    continue
                delta = cur_count - prev_count
                if delta > 0:
                    entry_counts.setdefault(capture_date, {})
                    entry_counts[capture_date][ts] = int(entry_counts[capture_date].get(ts, 0)) + int(delta)
                elif delta < 0:
                    exit_counts.setdefault(capture_date, {})
                    exit_counts[capture_date][ts] = int(exit_counts[capture_date].get(ts, 0)) + int(abs(delta))
                prev_count = cur_count
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


def _customer_session_columns() -> list[str]:
    return [
        "store_id",
        "capture_date",
        "session_id",
        "store_day_customer_id",
        "track_id_local",
        "entry_time",
        "last_seen_time",
        "exit_time",
        "entry_ts",
        "exit_ts",
        "dwell_seconds",
        "dwell_sec",
        "status",
        "close_reason",
        "session_class",
        "staff_flag",
        "is_staff_session",
        "is_valid_session",
        "invalid_reason",
        "converted_proxy",
        "cameras_seen",
        "locations_seen",
        "floors_seen",
        "entry_image",
        "entry_image_path",
        "entry_snapshot_path",
        "exit_image",
        "exit_image_path",
        "exit_snapshot_path",
        "frames_seen",
        "movement_score",
        "staff_ratio_max",
        "staff_score",
        "confidence",
        "gender",
        "notes",
    ]


def _dominant_gender_from_observations(observations: list[dict[str, Any]]) -> str:
    score_m = 0.0
    score_f = 0.0
    for obs in observations:
        raw = obs.get("gender_likelihood", "{}")
        payload: dict[str, Any] = {}
        if isinstance(raw, dict):
            payload = raw
        elif isinstance(raw, str):
            text = raw.strip()
            if text:
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = {}
        if not payload:
            continue
        for k, v in payload.items():
            key = str(k).strip().lower()
            try:
                fv = float(v)
            except Exception:
                fv = 0.0
            if key.startswith("m"):
                score_m += fv
            elif key.startswith("f"):
                score_f += fv
    if score_m <= 0.0 and score_f <= 0.0:
        return "unknown"
    return "male" if score_m >= score_f else "female"


def _build_track_based_strict_sessions(
    image_insights: pd.DataFrame,
    store_id: str,
    gate_camera_ids: set[str],
    camera_configs: dict[str, dict[str, object]],
    session_timeout_sec: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = image_insights.copy()
    if "store_day_customer_ids" not in df.columns:
        df["store_day_customer_ids"] = "[]"
    if "customer_session_ids" not in df.columns:
        df["customer_session_ids"] = "[]"
    if "event_label" not in df.columns:
        df["event_label"] = "INVALID"

    gate_ids_upper = {str(v).strip().upper() for v in gate_camera_ids}
    if not gate_ids_upper:
        return df, pd.DataFrame(columns=_customer_session_columns())

    rows = df[df["timestamp"].notna()].copy().sort_values("timestamp")
    track_events: dict[tuple[str, str, int], list[dict[str, Any]]] = {}

    for row_idx, row in rows.iterrows():
        camera_id = str(row.get("camera_id", "")).strip().upper()
        if camera_id not in gate_ids_upper:
            continue
        ts = pd.Timestamp(row["timestamp"])
        capture_date = str(row.get("capture_date", "")).strip()
        if not capture_date:
            capture_date = ts.date().isoformat()
        track_ids = [int(v) for v in _safe_json_list(row.get("track_ids", "[]")) if str(v).strip()]
        centroids = _parse_centroid_list(row.get("person_centroids", "[]"))
        boxes = _parse_box_list(row.get("person_boxes", "[]"))
        det_n = max(len(track_ids), len(centroids), len(boxes))
        if det_n <= 0:
            continue
        while len(centroids) < det_n:
            if len(centroids) < len(boxes):
                centroids.append(_box_centroid(boxes[len(centroids)]))
            else:
                centroids.append((0.5, 0.5))
        while len(boxes) < det_n:
            boxes.append(_fallback_box_from_centroid(centroids[len(boxes)]))
        while len(track_ids) < det_n:
            synthetic_tid = -((int(row_idx) + 1) * 1000 + len(track_ids))
            track_ids.append(synthetic_tid)
        staff_flags = _parse_bool_list(row.get("staff_flags", "[]"), expected=det_n)
        staff_scores = _parse_float_list(row.get("staff_scores", "[]"), expected=det_n)
        confs = _parse_float_list(row.get("person_confidences", "[]"), expected=det_n)
        ignore_reasons = [str(v).strip().lower() for v in _safe_json_list(row.get("ignore_reasons", "[]"))]
        if len(ignore_reasons) < det_n:
            ignore_reasons.extend([""] * (det_n - len(ignore_reasons)))
        box_labels = [str(v).strip().lower() for v in _safe_json_list(row.get("box_labels", "[]"))]
        if len(box_labels) < det_n:
            box_labels.extend([""] * (det_n - len(box_labels)))
        location_name = str(row.get("location_name", "")).strip() or camera_id
        floor_name = str(row.get("floor_name", "")).strip() or "Ground"
        image_name = str(row.get("filename", "")).strip()
        image_path = str(row.get("path", "")).strip()
        for det_i in range(det_n):
            tid = int(track_ids[det_i])
            cx, cy = centroids[det_i]
            event_key = (capture_date, camera_id, tid)
            track_events.setdefault(event_key, []).append(
                {
                    "row_idx": int(row_idx),
                    "timestamp": ts,
                    "camera_id": camera_id,
                    "cx": float(cx),
                    "cy": float(cy),
                    "bbox": boxes[det_i],
                    "staff_flag": bool(staff_flags[det_i]),
                    "staff_score": float(staff_scores[det_i]),
                    "confidence": float(confs[det_i]),
                    "ignore_reason": str(ignore_reasons[det_i]),
                    "box_label": str(box_labels[det_i]),
                    "image_name": image_name,
                    "image_path": image_path,
                    "location_name": location_name,
                    "floor_name": floor_name,
                    "gender_likelihood": row.get("gender_likelihood", "{}"),
                }
            )

    if not track_events:
        df["store_day_customer_ids"] = "[]"
        df["customer_session_ids"] = "[]"
        return df, pd.DataFrame(columns=_customer_session_columns())

    staff_threshold = float(os.getenv("IRIS_STAFF_SCORE_THRESHOLD", "0.92") or 0.92)
    staff_threshold = max(0.4, min(1.4, staff_threshold))

    track_customer_windows: dict[tuple[str, str, int], tuple[str, pd.Timestamp, pd.Timestamp]] = {}
    track_to_status: dict[tuple[str, str, int], str] = {}
    sessions_out: list[dict[str, Any]] = []

    day_keys: dict[str, list[tuple[str, str, int]]] = {}
    for key in track_events:
        day_keys.setdefault(key[0], []).append(key)

    for capture_date in sorted(day_keys.keys()):
        seq = 1
        ordered_keys = sorted(
            day_keys[capture_date],
            key=lambda key: (pd.Timestamp(track_events[key][0]["timestamp"]), key[1], key[2]),
        )
        for key in ordered_keys:
            day, camera_id, track_id = key
            obs = sorted(track_events[key], key=lambda x: pd.Timestamp(x["timestamp"]))
            cfg = camera_configs.get(camera_id, {})
            line_x = float(cfg.get("entry_line_x", 0.5))
            direction = str(cfg.get("entry_direction", "OUTSIDE_TO_INSIDE")).upper()
            first_ts = pd.Timestamp(obs[0]["timestamp"])
            last_ts = pd.Timestamp(obs[-1]["timestamp"])
            duration_sec = max(1.0, float((last_ts - first_ts).total_seconds()) + 1.0)

            crossed_in_ts: pd.Timestamp | None = None
            crossed_out_ts: pd.Timestamp | None = None
            entered = False
            for a, b in zip(obs, obs[1:]):
                side_a = _line_side(float(a["cx"]), line_x)
                side_b = _line_side(float(b["cx"]), line_x)
                crossed_in, crossed_out = _cross_in_out(side_a=side_a, side_b=side_b, direction=direction)
                if crossed_in and crossed_in_ts is None:
                    crossed_in_ts = pd.Timestamp(b["timestamp"])
                    entered = True
                elif crossed_out and entered and crossed_out_ts is None:
                    crossed_out_ts = pd.Timestamp(b["timestamp"])
                    entered = False
                    break

            point_std_x = float(np.std([float(v["cx"]) for v in obs])) if len(obs) > 1 else 0.0
            point_std_y = float(np.std([float(v["cy"]) for v in obs])) if len(obs) > 1 else 0.0
            areas = np.array([_box_area(v["bbox"]) for v in obs], dtype=float)
            area_mean = float(np.mean(areas)) if len(areas) else 0.0
            area_cv = float(np.std(areas) / max(1e-9, area_mean)) if len(areas) > 1 else 0.0
            movement = 0.0
            for a, b in zip(obs, obs[1:]):
                movement += math.dist((float(a["cx"]), float(a["cy"])), (float(b["cx"]), float(b["cy"])))

            poster_votes = sum(
                1
                for item in obs
                if str(item.get("ignore_reason", "")).strip().lower() == "poster_or_flat_static"
                or str(item.get("box_label", "")).strip().lower() in {"ignore", "static_object"}
            )
            static_like = bool(
                (len(obs) >= 5 and movement <= 0.09 and point_std_x <= 0.015 and point_std_y <= 0.015 and area_cv <= 0.10)
                or (poster_votes >= max(2, int(len(obs) * 0.6)))
            )

            color_score = float(max(float(item.get("staff_score", 0.0) or 0.0) for item in obs))
            repeat_presence_score = min(1.0, (duration_sec / 5400.0) + (len(obs) / 90.0))
            zone_score = float(sum(1 for item in obs if abs(float(item["cx"]) - line_x) <= 0.18) / max(1, len(obs)))
            staff_score = round(0.60 * color_score + 0.25 * repeat_presence_score + 0.15 * zone_score, 4)
            staff_vote_ratio = float(sum(1 for item in obs if bool(item.get("staff_flag", False))) / max(1, len(obs)))
            is_staff = bool(
                staff_score >= staff_threshold
                or (staff_vote_ratio >= 0.70 and duration_sec >= 300.0)
            )

            near_entry_no_cross = bool(crossed_in_ts is None and any(abs(float(v["cx"]) - line_x) <= 0.05 for v in obs))
            is_outside_passer = bool(crossed_in_ts is None and not is_staff and not static_like and not near_entry_no_cross)

            entry_valid = bool(crossed_in_ts is not None and not is_staff and not static_like and not is_outside_passer)
            if entry_valid:
                session_id = _new_store_day_customer_id(store_id=store_id, capture_date=day, seq=seq)
                seq += 1
            else:
                session_id = f"REJ_{store_id}_{day.replace('-', '')}_{camera_id}_{abs(int(track_id))}"

            if is_staff:
                status = "STAFF"
                session_class = "STAFF"
                invalid_reason = "staff_like"
            elif static_like:
                status = "INVALID_STATIC_OBJECT"
                session_class = "STATIC_OBJECT"
                invalid_reason = "static_object"
            elif is_outside_passer:
                status = "OUTSIDE_PASSER"
                session_class = "OUTSIDE_PASSER"
                invalid_reason = "no_valid_entry"
            elif crossed_in_ts is None:
                status = "ENTRY_CANDIDATE"
                session_class = "INVALID"
                invalid_reason = "entry_not_confirmed"
            elif crossed_out_ts is None:
                status = "ACTIVE_CUSTOMER"
                session_class = "CUSTOMER"
                invalid_reason = ""
            else:
                status = "EXITED"
                session_class = "CUSTOMER"
                invalid_reason = ""

            track_to_status[key] = status
            close_reason = "exit_crossing" if crossed_out_ts is not None else "timeout"
            entry_time = crossed_in_ts if crossed_in_ts is not None else first_ts
            if crossed_out_ts is not None:
                exit_time = crossed_out_ts
            elif crossed_in_ts is not None:
                exit_time = last_ts
            else:
                exit_time = last_ts
            dwell_seconds = max(1.0, float((pd.Timestamp(exit_time) - pd.Timestamp(entry_time)).total_seconds()) + 1.0)
            confidence = round(float(np.mean([float(v.get("confidence", 0.0) or 0.0) for v in obs])), 4)
            gender = _dominant_gender_from_observations(obs)
            entry_obs = next((v for v in obs if pd.Timestamp(v["timestamp"]) >= pd.Timestamp(entry_time)), obs[0])
            exit_obs = next((v for v in reversed(obs) if pd.Timestamp(v["timestamp"]) <= pd.Timestamp(exit_time)), obs[-1])
            cameras_seen = sorted({str(v["camera_id"]).strip() for v in obs if str(v.get("camera_id", "")).strip()})
            locations_seen = sorted({str(v["location_name"]).strip() for v in obs if str(v.get("location_name", "")).strip()})
            floors_seen = sorted({str(v["floor_name"]).strip() for v in obs if str(v.get("floor_name", "")).strip()})
            notes = (
                f"tracker_track={camera_id}:{track_id};"
                f"staff_score={staff_score:.3f};"
                f"movement={movement:.4f};"
                f"cross_in={bool(crossed_in_ts)};"
                f"cross_out={bool(crossed_out_ts)}"
            )
            sessions_out.append(
                {
                    "store_id": store_id,
                    "capture_date": day,
                    "session_id": session_id,
                    "store_day_customer_id": session_id if entry_valid else "",
                    "track_id_local": f"{camera_id}:{int(track_id)}",
                    "entry_time": pd.Timestamp(entry_time),
                    "last_seen_time": pd.Timestamp(last_ts),
                    "exit_time": pd.Timestamp(exit_time),
                    "entry_ts": pd.Timestamp(entry_time),
                    "exit_ts": pd.Timestamp(exit_time),
                    "dwell_seconds": round(float(dwell_seconds), 2),
                    "dwell_sec": round(float(dwell_seconds), 2),
                    "status": status,
                    "close_reason": close_reason,
                    "session_class": session_class,
                    "staff_flag": int(is_staff),
                    "is_staff_session": int(is_staff),
                    "is_valid_session": int(bool(entry_valid)),
                    "invalid_reason": invalid_reason,
                    "converted_proxy": 0,
                    "cameras_seen": ",".join(cameras_seen),
                    "locations_seen": ",".join(locations_seen),
                    "floors_seen": ",".join(floors_seen),
                    "entry_image": str(entry_obs.get("image_name", "")),
                    "entry_image_path": str(entry_obs.get("image_path", "")),
                    "entry_snapshot_path": str(entry_obs.get("image_path", "")),
                    "exit_image": str(exit_obs.get("image_name", "")),
                    "exit_image_path": str(exit_obs.get("image_path", "")),
                    "exit_snapshot_path": str(exit_obs.get("image_path", "")),
                    "frames_seen": int(len(obs)),
                    "movement_score": int(round(movement * 1000)),
                    "staff_ratio_max": round(float(staff_vote_ratio), 4),
                    "staff_score": float(staff_score),
                    "confidence": float(confidence),
                    "gender": gender,
                    "notes": notes,
                }
            )
            if entry_valid:
                track_customer_windows[key] = (session_id, pd.Timestamp(entry_time), pd.Timestamp(exit_time))

    # Re-attach session ids to frame rows using track ids.
    for idx, row in df.iterrows():
        if pd.isna(row.get("timestamp", pd.NaT)):
            df.at[idx, "store_day_customer_ids"] = "[]"
            df.at[idx, "customer_session_ids"] = "[]"
            df.at[idx, "event_label"] = "INVALID"
            continue
        ts = pd.Timestamp(row["timestamp"])
        day = str(row.get("capture_date", "")).strip() or ts.date().isoformat()
        camera_id = str(row.get("camera_id", "")).strip().upper()
        track_ids = [int(v) for v in _safe_json_list(row.get("track_ids", "[]")) if str(v).strip()]
        row_statuses: list[str] = []
        row_session_ids: list[str] = []
        for tid in track_ids:
            key = (day, camera_id, int(tid))
            status = track_to_status.get(key, "")
            if status:
                row_statuses.append(status)
            sid_payload = track_customer_windows.get(key)
            if sid_payload is not None:
                sid, sid_entry_ts, sid_exit_ts = sid_payload
                if pd.Timestamp(ts) >= pd.Timestamp(sid_entry_ts) and pd.Timestamp(ts) <= pd.Timestamp(sid_exit_ts):
                    row_session_ids.append(str(sid))
        row_session_ids = sorted({sid for sid in row_session_ids if sid})
        df.at[idx, "store_day_customer_ids"] = json.dumps(row_session_ids)
        df.at[idx, "customer_session_ids"] = json.dumps(row_session_ids)

        is_valid = bool(row.get("is_valid", False))
        det_err = str(row.get("detection_error", "") or "").strip()
        reject_reason = str(row.get("reject_reason", "") or "").strip()
        if (not is_valid) or det_err or reject_reason:
            label = "INVALID"
        elif row_session_ids:
            label = "CUSTOMER"
        elif any(s == "STAFF" for s in row_statuses):
            label = "STAFF"
        elif any(s == "INVALID_STATIC_OBJECT" for s in row_statuses):
            label = "STATIC_OBJECT"
        elif any(s == "OUTSIDE_PASSER" for s in row_statuses):
            label = "OUTSIDE_PASSER"
        elif any(s == "ENTRY_CANDIDATE" for s in row_statuses):
            label = "ENTRY_CANDIDATE"
        else:
            label = "INVALID"
        df.at[idx, "event_label"] = label

    sessions_df = pd.DataFrame(sessions_out)
    if sessions_df.empty:
        sessions_df = pd.DataFrame(columns=_customer_session_columns())
    else:
        for col in _customer_session_columns():
            if col not in sessions_df.columns:
                sessions_df[col] = ""
        sessions_df = sessions_df[_customer_session_columns()].sort_values(
            ["capture_date", "entry_time", "track_id_local"],
            na_position="last",
        ).reset_index(drop=True)
    return df, sessions_df


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
    df["event_label"] = "INVALID"
    if df.empty or "timestamp" not in df.columns:
        return df, pd.DataFrame(columns=_customer_session_columns())

    # Build crossing events from ENTRANCE/EXIT cameras.
    entry_counts, exit_counts = _compute_entry_exit_event_counts(
        image_insights=df,
        camera_configs=camera_configs,
    )
    gate_camera_ids = {
        str(cid).strip().upper()
        for cid, cfg in (camera_configs or {}).items()
        if str((cfg or {}).get("camera_role", "INSIDE")).upper() in {"ENTRANCE", "EXIT"}
    }
    if not gate_camera_ids:
        # Store-default gate fallback for deployments that use D07 as door camera.
        has_d07 = bool((df["camera_id"].astype(str).str.upper() == "D07").any())
        if has_d07:
            gate_camera_ids = {"D07"}
            camera_configs.setdefault(
                "D07",
                {
                    "camera_role": "ENTRANCE",
                    "entry_line_x": 0.5,
                    "entry_direction": "OUTSIDE_TO_INSIDE",
                },
            )
            entry_counts, exit_counts = _compute_entry_exit_event_counts(
                image_insights=df,
                camera_configs=camera_configs,
            )
    strict_gate_mode = bool(entry_counts or exit_counts or gate_camera_ids)
    if strict_gate_mode:
        return _build_track_based_strict_sessions(
            image_insights=df,
            store_id=store_id,
            gate_camera_ids=gate_camera_ids,
            camera_configs=camera_configs,
            session_timeout_sec=session_timeout_sec,
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
        duration_sec = max(1.0, float((close_ts - entry_ts).total_seconds()) + 1.0)
        cameras_seen = sorted(state.get("cameras_seen", set()))
        floors_seen = sorted(state.get("floors_seen", set()))
        locations_seen = sorted(state.get("locations_seen", set()))
        frames_seen = int(state.get("frames_seen", 0) or 0)
        movement_score = int(state.get("movement_score", 0) or 0)
        is_staff_session = bool(
            duration_sec >= 7200.0
            and (
                str(reason).strip().lower() != "exit_crossing"
                or float(state.get("staff_ratio_max", 0.0) or 0.0) >= 0.5
            )
        )
        invalid_reason = ""
        is_valid_session = True
        session_class = "CUSTOMER"
        if strict_gate_mode:
            if reason != "exit_crossing":
                is_valid_session = False
                invalid_reason = "no_exit_crossing"
            elif duration_sec < 2.0:
                is_valid_session = False
                invalid_reason = "duration_lt_2s"
            elif movement_score <= 0 and frames_seen <= 1 and len(cameras_seen) <= 1:
                is_valid_session = False
                invalid_reason = "no_movement"
        if is_staff_session:
            is_valid_session = False
            invalid_reason = "staff_like"
            session_class = "STAFF"
        elif not is_valid_session:
            gate_only = bool(cameras_seen) and all(str(c).upper() in gate_camera_ids for c in cameras_seen)
            if gate_only and invalid_reason in {"no_exit_crossing", "no_movement"}:
                session_class = "OUTSIDE_PASSER"
            else:
                session_class = "INVALID"

        sessions_out.append(
            {
                "store_id": store_id,
                "capture_date": str(state["capture_date"]),
                "store_day_customer_id": sid,
                "entry_ts": entry_ts,
                "exit_ts": close_ts,
                "dwell_sec": round(duration_sec, 2),
                "close_reason": reason,
                "converted_proxy": int(bool(state.get("converted_proxy", False))),
                "cameras_seen": ",".join(cameras_seen),
                "locations_seen": ",".join(locations_seen),
                "floors_seen": ",".join(floors_seen),
                "entry_image": str(state.get("entry_image", "")),
                "entry_image_path": str(state.get("entry_image_path", "")),
                "exit_image": str(state.get("exit_image", "")),
                "exit_image_path": str(state.get("exit_image_path", "")),
                "frames_seen": frames_seen,
                "movement_score": movement_score,
                "staff_ratio_max": round(float(state.get("staff_ratio_max", 0.0) or 0.0), 4),
                "is_staff_session": int(is_staff_session),
                "is_valid_session": int(bool(is_valid_session)),
                "invalid_reason": invalid_reason,
                "session_class": session_class,
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
                    "entry_image": "",
                    "entry_image_path": "",
                    "exit_image": "",
                    "exit_image_path": "",
                    "last_image": "",
                    "last_image_path": "",
                    "closed": False,
                    "close_reason": "",
                    "converted_proxy": False,
                    "cameras_seen": set(),
                    "locations_seen": set(),
                    "floors_seen": set(),
                    "frames_seen": 0,
                    "movement_score": 0,
                    "staff_ratio_max": 0.0,
                }
                active_ids.append(sid)

            ts_idx = day_df[day_df["timestamp"] == ts].index.tolist()
            observed_count = 0
            if ts_idx:
                observed_count = int(
                    max(pd.to_numeric(df.loc[ts_idx, "customer_count"], errors="coerce").fillna(0).astype(int).tolist())
                )
            open_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]
            if not strict_gate_mode:
                while len(open_ids) < observed_count:
                    sid = _new_store_day_customer_id(store_id=store_id, capture_date=day, seq=seq)
                    seq += 1
                    session_state[sid] = {
                        "capture_date": day,
                        "entry_ts": ts,
                        "last_seen": ts,
                        "exit_ts": ts,
                        "entry_image": "",
                        "entry_image_path": "",
                        "exit_image": "",
                        "exit_image_path": "",
                        "last_image": "",
                        "last_image_path": "",
                        "closed": False,
                        "close_reason": "",
                        "converted_proxy": False,
                        "cameras_seen": set(),
                        "locations_seen": set(),
                        "floors_seen": set(),
                        "frames_seen": 0,
                        "movement_score": 0,
                        "staff_ratio_max": 0.0,
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
                file_name = str(df.at[idx, "filename"]) if "filename" in df.columns else ""
                file_path = str(df.at[idx, "path"]) if "path" in df.columns else ""
                location_name = str(df.at[idx, "location_name"]) if "location_name" in df.columns else camera_id
                floor_name = str(df.at[idx, "floor_name"]) if "floor_name" in df.columns else "Ground"
                row_staff = int(pd.to_numeric([df.at[idx, "staff_count"]], errors="coerce")[0] or 0)
                row_people = int(pd.to_numeric([df.at[idx, "person_count"]], errors="coerce")[0] or 0)
                row_staff_ratio = (float(row_staff) / float(max(1, row_people))) if row_people > 0 else 0.0
                for sid in row_ids:
                    state = session_state[sid]
                    state["last_seen"] = ts
                    if not str(state.get("entry_image", "")).strip():
                        state["entry_image"] = file_name
                        state["entry_image_path"] = file_path
                    state["last_image"] = file_name
                    state["last_image_path"] = file_path
                    state["cameras_seen"].add(camera_id)
                    state["locations_seen"].add(location_name if location_name.strip() else camera_id)
                    state["floors_seen"].add(floor_name if floor_name.strip() else "Ground")
                    state["frames_seen"] = int(state.get("frames_seen", 0) or 0) + 1
                    if len(state["cameras_seen"]) > 1:
                        state["movement_score"] = int(state.get("movement_score", 0) or 0) + 1
                    state["staff_ratio_max"] = max(float(state.get("staff_ratio_max", 0.0) or 0.0), row_staff_ratio)
                    if camera_id in billing_cameras:
                        state["converted_proxy"] = True

            n_exit = int(exit_counts.get(day, {}).get(ts, 0))
            if n_exit > 0:
                closable = sorted(
                    [sid for sid in active_ids if not bool(session_state[sid].get("closed"))],
                    key=lambda sid: pd.Timestamp(session_state[sid]["entry_ts"]),
                )
                for sid in closable[:n_exit]:
                    state = session_state.get(sid, {})
                    state["exit_image"] = str(state.get("last_image", ""))
                    state["exit_image_path"] = str(state.get("last_image_path", ""))
                    _close_session(sid=sid, close_ts=ts, reason="exit_crossing")
            active_ids = [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]

        for sid in [sid for sid in active_ids if not bool(session_state[sid].get("closed"))]:
            state = session_state.get(sid, {})
            state["exit_image"] = str(state.get("last_image", ""))
            state["exit_image_path"] = str(state.get("last_image_path", ""))
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
                "entry_image",
                "entry_image_path",
                "exit_image",
                "exit_image_path",
                "frames_seen",
                "movement_score",
                "staff_ratio_max",
                "is_staff_session",
                "is_valid_session",
                "invalid_reason",
                "session_class",
            ]
        )
    else:
        sessions_df = sessions_df.sort_values(["capture_date", "entry_ts"]).reset_index(drop=True)

    # Frame-level class label for QA/dashboard:
    # CUSTOMER, STAFF, OUTSIDE_PASSER, INVALID
    if "event_label" not in df.columns:
        df["event_label"] = "INVALID"
    gate_ids_upper = {str(x).upper() for x in gate_camera_ids}
    for idx, row in df.iterrows():
        is_valid = bool(row.get("is_valid", False))
        det_err = str(row.get("detection_error", "") or "").strip()
        reject_reason = str(row.get("reject_reason", "") or "").strip()
        if (not is_valid) or det_err or reject_reason:
            df.at[idx, "event_label"] = "INVALID"
            continue
        staff_count = int(pd.to_numeric([row.get("staff_count", 0)], errors="coerce")[0] or 0)
        customer_count = int(pd.to_numeric([row.get("customer_count", 0)], errors="coerce")[0] or 0)
        has_session = bool([x for x in _safe_json_list(row.get("store_day_customer_ids", "[]")) if str(x).strip()])
        camera_id = str(row.get("camera_id", "")).strip().upper()
        if has_session and customer_count > 0:
            df.at[idx, "event_label"] = "CUSTOMER"
        elif staff_count > 0 and customer_count <= 0:
            df.at[idx, "event_label"] = "STAFF"
        elif strict_gate_mode and camera_id in gate_ids_upper and customer_count > 0:
            df.at[idx, "event_label"] = "OUTSIDE_PASSER"
        else:
            df.at[idx, "event_label"] = "INVALID"
    return df, sessions_df


def _valid_closed_customer_sessions(customer_sessions: pd.DataFrame) -> pd.DataFrame:
    if customer_sessions.empty:
        return customer_sessions
    out = customer_sessions.copy()
    if "exit_ts" in out.columns:
        out = out[out["exit_ts"].fillna("").astype(str).str.strip().ne("")]
    if "is_valid_session" in out.columns:
        out = out[pd.to_numeric(out["is_valid_session"], errors="coerce").fillna(0).astype(int) > 0]
    elif "close_reason" in out.columns:
        out = out[out["close_reason"].fillna("").astype(str).str.strip().eq("exit_crossing")]
    return out


def _apply_session_metrics_to_summary(
    summary_row: pd.DataFrame,
    customer_sessions: pd.DataFrame,
    bounce_threshold_sec: int,
) -> pd.DataFrame:
    if summary_row.empty:
        return summary_row
    summary_row = summary_row.copy()
    if customer_sessions.empty:
        summary_row["daily_walkins"] = 0
        summary_row["daily_conversions"] = 0
        summary_row["daily_bounced"] = 0
        summary_row["daily_conversion_rate"] = np.nan
        summary_row["bounce_rate"] = np.nan
        return summary_row

    # Track-based strict D07 engine adds richer identifiers and lifecycle fields.
    strict_gate_contract_detected = bool(
        ("status" in customer_sessions.columns)
        or ("session_id" in customer_sessions.columns)
        or ("track_id_local" in customer_sessions.columns)
    )
    validated_session_contract_detected = bool(
        ("store_day_customer_id" in customer_sessions.columns)
        or ("is_valid_session" in customer_sessions.columns)
        or ("session_class" in customer_sessions.columns)
    )
    generic_validated_contract = bool(
        validated_session_contract_detected and ("close_reason" not in customer_sessions.columns)
    )
    if not strict_gate_contract_detected and not generic_validated_contract:
        legacy_walkins = int(len(customer_sessions))
        legacy_conversions = int(
            pd.to_numeric(customer_sessions.get("converted_proxy", pd.Series([], dtype=float)), errors="coerce").fillna(0).sum()
        )
        legacy_bounced = int(max(0, legacy_walkins - legacy_conversions))
        summary_row["daily_walkins"] = legacy_walkins
        summary_row["daily_conversions"] = legacy_conversions
        summary_row["daily_bounced"] = legacy_bounced
        summary_row["daily_conversion_rate"] = (
            round(float(legacy_conversions) / float(max(1, legacy_walkins)), 4) if legacy_walkins > 0 else 0.0
        )
        return summary_row

    valid_entries = customer_sessions.copy()
    if "session_class" in valid_entries.columns:
        valid_entries = valid_entries[
            valid_entries["session_class"].fillna("").astype(str).str.upper().eq("CUSTOMER")
        ].copy()
    if "store_day_customer_id" in valid_entries.columns:
        valid_entries = valid_entries[
            valid_entries["store_day_customer_id"].fillna("").astype(str).str.strip().ne("")
        ].copy()
    if "is_valid_session" in valid_entries.columns:
        valid_entries = valid_entries[
            pd.to_numeric(valid_entries["is_valid_session"], errors="coerce").fillna(0).astype(int) > 0
        ].copy()

    total_entries = int(len(valid_entries))
    conversions = int(
        pd.to_numeric(
            valid_entries.get("converted_proxy", pd.Series([], dtype=float)),
            errors="coerce",
        ).fillna(0).sum()
    )
    conversions = max(0, min(total_entries, conversions))
    bounced = int(max(0, total_entries - conversions))
    dwell_series = pd.to_numeric(
        valid_entries.get("dwell_sec", pd.Series([], dtype=float)),
        errors="coerce",
    ).fillna(0.0)
    avg_dwell = round(float(dwell_series.mean()), 2) if total_entries > 0 else 0.0
    bounce_rate = round(float(bounced) / float(total_entries), 4) if total_entries > 0 else np.nan
    conversion_rate = round(float(conversions) / float(total_entries), 4) if total_entries > 0 else np.nan

    if strict_gate_contract_detected:
        # Strict gate-mode keeps footfall/estimated-visits tied to explicit exit crossing closures.
        closed_visits = int(
            valid_entries.get("close_reason", pd.Series([], dtype=str))
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("exit_crossing")
            .sum()
        )
        summary_row["footfall"] = closed_visits
        summary_row["estimated_visits"] = closed_visits
    elif generic_validated_contract:
        summary_row["estimated_visits"] = total_entries

    summary_row["avg_dwell_sec"] = avg_dwell
    summary_row["bounce_rate"] = bounce_rate
    summary_row["daily_walkins"] = total_entries
    summary_row["daily_conversions"] = conversions
    summary_row["daily_bounced"] = bounced
    summary_row["daily_conversion_rate"] = conversion_rate
    return summary_row


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


def _cosine_distance(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 1.0
    a_norm = float(np.linalg.norm(a))
    b_norm = float(np.linalg.norm(b))
    if a_norm <= 1e-9 or b_norm <= 1e-9:
        return 1.0
    sim = float(np.dot(a, b) / (a_norm * b_norm))
    sim = max(-1.0, min(1.0, sim))
    return float(1.0 - sim)


def _clip_box_to_image(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(box[0] * width)))
    y1 = max(0, min(height - 1, int(box[1] * height)))
    x2 = max(x1 + 1, min(width, int(box[2] * width)))
    y2 = max(y1 + 1, min(height, int(box[3] * height)))
    return x1, y1, x2, y2


def _appearance_embedding_from_rgb(
    image_rgb: np.ndarray | None,
    box: tuple[float, float, float, float] | None,
) -> np.ndarray | None:
    if image_rgb is None or box is None:
        return None
    if image_rgb.ndim != 3 or image_rgb.shape[2] < 3:
        return None
    h, w = image_rgb.shape[:2]
    if h <= 1 or w <= 1:
        return None
    try:
        x1, y1, x2, y2 = _clip_box_to_image(box, width=w, height=h)
        crop = image_rgb[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        rgb = crop.astype(np.float32) / 255.0
        r = rgb[..., 0]
        g = rgb[..., 1]
        b = rgb[..., 2]
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        delta = max_c - min_c
        hue = np.zeros_like(max_c)
        mask = delta > 1e-6
        ridx = (max_c == r) & mask
        gidx = (max_c == g) & mask
        bidx = (max_c == b) & mask
        hue[ridx] = (60.0 * ((g[ridx] - b[ridx]) / delta[ridx]) + 360.0) % 360.0
        hue[gidx] = 60.0 * ((b[gidx] - r[gidx]) / delta[gidx]) + 120.0
        hue[bidx] = 60.0 * ((r[bidx] - g[bidx]) / delta[bidx]) + 240.0
        sat = np.where(max_c <= 1e-6, 0.0, delta / np.maximum(max_c, 1e-6))
        val = max_c
        h_hist, _ = np.histogram(hue, bins=8, range=(0.0, 360.0), density=True)
        s_hist, _ = np.histogram(sat, bins=4, range=(0.0, 1.0), density=True)
        v_hist, _ = np.histogram(val, bins=4, range=(0.0, 1.0), density=True)
        embed = np.concatenate([h_hist, s_hist, v_hist]).astype(np.float32)
        norm = float(np.linalg.norm(embed))
        if norm <= 1e-9:
            return None
        return embed / norm
    except Exception:
        return None


def _fallback_box_from_centroid(centroid: tuple[float, float], half_size: float = 0.05) -> tuple[float, float, float, float]:
    cx = float(max(0.0, min(1.0, centroid[0])))
    cy = float(max(0.0, min(1.0, centroid[1])))
    x1 = max(0.0, cx - half_size)
    y1 = max(0.0, cy - half_size)
    x2 = min(1.0, cx + half_size)
    y2 = min(1.0, cy + half_size)
    if x2 <= x1:
        x2 = min(1.0, x1 + 0.01)
    if y2 <= y1:
        y2 = min(1.0, y1 + 0.01)
    return (x1, y1, x2, y2)




def assign_single_camera_tracks(
    image_insights: pd.DataFrame,
    session_gap_sec: int = 30,
    distance_threshold: float = 0.18,
    tracker_type: str | None = None,
) -> pd.DataFrame:
    df = image_insights.copy()
    df["track_ids"] = "[]"
    if "tracker_backend" not in df.columns:
        df["tracker_backend"] = ""
    next_id = 1
    tracker_mode = str(
        tracker_type
        or os.getenv("IRIS_TRACKER_TYPE", "botsort")
    ).strip().lower()
    if tracker_mode not in {"botsort", "bytetrack", "centroid"}:
        tracker_mode = "botsort"
    use_reid = tracker_mode == "botsort"
    image_cache: dict[str, np.ndarray | None] = {}
    reid_weight = float(os.getenv("IRIS_REID_WEIGHT", "0.42") or 0.42)
    reid_weight = max(0.0, min(0.8, reid_weight))
    reid_threshold = float(os.getenv("IRIS_REID_DISTANCE_THRESHOLD", "0.48") or 0.48)
    reid_threshold = max(0.1, min(1.0, reid_threshold))
    motion_cost_limit = float(os.getenv("IRIS_TRACK_MATCH_COST", "0.85") or 0.85)
    motion_cost_limit = max(0.2, min(2.0, motion_cost_limit))

    for camera_id, cam_df in df[df["timestamp"].notna()].groupby("camera_id"):
        active: dict[int, dict[str, Any]] = {}
        for idx in cam_df.sort_values("timestamp").index.tolist():
            ts = pd.Timestamp(df.at[idx, "timestamp"])
            centroids = _parse_centroid_list(df.at[idx, "person_centroids"])
            boxes = _parse_box_list(df.at[idx, "person_boxes"])
            n_det = max(len(centroids), len(boxes))
            if n_det <= 0:
                df.at[idx, "track_ids"] = "[]"
                df.at[idx, "tracker_backend"] = tracker_mode
                for tid in list(active.keys()):
                    if (ts - pd.Timestamp(active[tid]["timestamp"])).total_seconds() > session_gap_sec:
                        del active[tid]
                continue

            if len(centroids) < n_det:
                for det_i in range(len(centroids), n_det):
                    if det_i < len(boxes):
                        centroids.append(_box_centroid(boxes[det_i]))
                    else:
                        centroids.append((0.5, 0.5))
            if len(boxes) < n_det:
                for det_i in range(len(boxes), n_det):
                    boxes.append(_fallback_box_from_centroid(centroids[det_i]))

            embeddings: list[np.ndarray | None] = [None for _ in range(n_det)]
            if use_reid and n_det > 0:
                path = str(df.at[idx, "path"] if "path" in df.columns else "").strip()
                image_rgb = image_cache.get(path)
                if path and path not in image_cache:
                    try:
                        with Image.open(Path(path)) as img:
                            image_rgb = np.array(img.convert("RGB"))
                    except Exception:
                        image_rgb = None
                    image_cache[path] = image_rgb
                if path:
                    image_rgb = image_cache.get(path)
                for det_i in range(n_det):
                    embeddings[det_i] = _appearance_embedding_from_rgb(image_rgb=image_rgb, box=boxes[det_i])

            for tid in list(active.keys()):
                if (ts - pd.Timestamp(active[tid]["timestamp"])).total_seconds() > session_gap_sec:
                    del active[tid]

            pair_candidates: list[tuple[float, int, int]] = []
            for det_i in range(n_det):
                c = centroids[det_i]
                b = boxes[det_i]
                for tid, state in active.items():
                    gap_sec = (ts - pd.Timestamp(state["timestamp"])).total_seconds()
                    if gap_sec > session_gap_sec:
                        continue
                    prev_c = state.get("centroid", (0.5, 0.5))
                    prev_b = state.get("box")
                    motion_dist = math.dist((float(c[0]), float(c[1])), (float(prev_c[0]), float(prev_c[1])))
                    iou = _box_iou(b, prev_b) if isinstance(prev_b, tuple) else 0.0
                    if motion_dist > (distance_threshold * 1.8) and iou < 0.02:
                        continue
                    motion_cost = float(motion_dist + (1.0 - iou) * 0.20)
                    if tracker_mode == "centroid":
                        match_cost = motion_dist
                    elif tracker_mode == "bytetrack":
                        match_cost = motion_cost
                    else:
                        app_dist = _cosine_distance(embeddings[det_i], state.get("embedding"))
                        if app_dist > reid_threshold and motion_dist > distance_threshold:
                            continue
                        match_cost = (1.0 - reid_weight) * motion_cost + reid_weight * app_dist
                    if match_cost <= motion_cost_limit:
                        pair_candidates.append((float(match_cost), det_i, int(tid)))

            pair_candidates.sort(key=lambda x: x[0])
            matched_tracks: set[int] = set()
            matched_dets: set[int] = set()
            current_ids: list[int] = [0 for _ in range(n_det)]
            for _, det_i, tid in pair_candidates:
                if det_i in matched_dets or tid in matched_tracks:
                    continue
                matched_dets.add(det_i)
                matched_tracks.add(tid)
                current_ids[det_i] = int(tid)

            for det_i in range(n_det):
                if current_ids[det_i] <= 0:
                    current_ids[det_i] = next_id
                    next_id += 1
                tid = int(current_ids[det_i])
                active[tid] = {
                    "timestamp": ts,
                    "centroid": (float(centroids[det_i][0]), float(centroids[det_i][1])),
                    "box": boxes[det_i],
                    "embedding": embeddings[det_i] if use_reid else None,
                }

            df.at[idx, "track_ids"] = json.dumps(current_ids)
            df.at[idx, "tracker_backend"] = tracker_mode
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

def _analyze_single_image(
    image_path: Path,
    store_dir: Path,
    store_id: str,
    detector: PersonDetector,
    reference_day: date | None,
    camera_configs: dict[str, dict[str, object]],
    staff_red_threshold: float,
    enable_age_gender: bool,
    drive_link_map: dict[str, str],
) -> dict[str, Any] | None:
    """Worker function for single image processing, picklable for multiprocessing."""
    rel_path = _relative_image_path(image_path=image_path, store_dir=store_dir)
    drive_link = drive_link_map.get(rel_path, "")
    image_day, capture_date, source_folder = _infer_image_context(
        image_path=image_path,
        store_dir=store_dir,
        fallback_day=reference_day,
    )
    
    parsed = parse_filename(image_path.name, reference_day=image_day)
    if parsed is None:
        return {
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
            "person_confidences": "[]",
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
            "upper_colors": "[]",
            "lower_colors": "[]",
            "clothing_types": "[]",
            "ignore_reasons": "[]",
            "box_labels": "[]",
            "track_audit_json": "[]",
            "reject_reason": "bad_filename",
            "detection_error": "",
            "relative_path": rel_path,
            "drive_link": drive_link,
            "path": str(image_path),
        }

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
        person_confidences=[],
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
            store_id=store_id,
            red_threshold=staff_red_threshold,
        )
        
    staff_count = min(
        int(detection.person_count),
        int(sum(1 for flag in staff_flags if bool(flag))),
    )
    customer_count = max(0, int(detection.person_count) - int(staff_count))
    
    camera_role = str(cfg.get("camera_role", "")).strip().upper()
    age_gender_camera = (
        parsed.camera_id.strip().upper() == "D07"
        or camera_role in {"ENTRY", "EXIT", "ENTRY_EXIT", "ENTRANCE", "GATE"}
    )

    gender_likelihood = "{}"
    age_bucket_counts = "{}"
    age_confidence = 0.0
    age_gender_error = ""
    if enable_age_gender and age_gender_camera and is_valid and detection.person_boxes:
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

    return {
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
        "person_confidences": json.dumps(detection.person_confidences),
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
        "upper_colors": "[]",
        "lower_colors": "[]",
        "clothing_types": "[]",
        "ignore_reasons": "[]",
        "box_labels": "[]",
        "track_audit_json": "[]",
        "reject_reason": reject_reason,
        "detection_error": detection.detection_error,
        "relative_path": rel_path,
        "drive_link": drive_link,
        "path": str(image_path),
    }

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
    false_positive_signatures: list[dict[str, object]] | None = None,
    use_parallel: bool = True,
    use_streaming: bool = True,
    false_positive_model: Optional[Any] = None,
    filename_prefixes: list[str] | None = None,
) -> StoreAnalysisResult:
    if use_parallel and use_streaming:
        # Fallback detectors like OpenCV HOG are not picklable under multiprocessing.
        # Downgrade to linear execution instead of failing.
        try:
            pickle.dumps(detector)
        except Exception:
            use_parallel = False
            use_streaming = False
    if enable_age_gender:
        # DeepFace model loading/downloading is not process-safe in this pipeline.
        # Force single-process execution for stable runs.
        use_parallel = False
        use_streaming = False
    normalized_prefixes = [
        str(p).strip() for p in (filename_prefixes or []) if str(p).strip()
    ]
    if use_parallel and use_streaming:
        return analyze_store_streaming(
            store_id=store_id, store_dir=store_dir, detector=detector,
            reference_day=reference_day, time_bucket_minutes=time_bucket_minutes,
            bounce_threshold_sec=bounce_threshold_sec, session_gap_sec=session_gap_sec,
            camera_configs=camera_configs, engaged_dwell_threshold_sec=engaged_dwell_threshold_sec,
            max_images_per_store=max_images_per_store, employee_assets_root=employee_assets_root,
            capture_date_filter=capture_date_filter, session_timeout_sec=session_timeout_sec,
            enable_age_gender=enable_age_gender, false_positive_signatures=false_positive_signatures,
            false_positive_model=false_positive_model,
            filename_prefixes=normalized_prefixes,
        )
    
    # Original linear processing
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
        if not _matches_filename_filters(image_path.name, normalized_prefixes):
            continue
        if capture_date_filter is not None:
             image_day, _, _ = _infer_image_context(
                image_path=image_path,
                store_dir=store_dir,
                fallback_day=reference_day,
            )
             if image_day != capture_date_filter:
                continue
                
        if max_images_per_store is not None and max_images_per_store > 0 and processed_images >= max_images_per_store:
            break
            
        res = _analyze_single_image(
            image_path=image_path,
            store_dir=store_dir,
            store_id=store_id,
            detector=detector,
            reference_day=reference_day,
            camera_configs=camera_configs,
            staff_red_threshold=staff_red_threshold,
            enable_age_gender=enable_age_gender,
            drive_link_map=drive_link_map
        )
        if res:
            rows.append(res)
            processed_images += 1

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
            "person_confidences",
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
                "person_confidences",
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
                "upper_colors",
                "lower_colors",
                "clothing_types",
                "ignore_reasons",
                "box_labels",
                "track_audit_json",
                "reject_reason",
                "detection_error",
                "relative_path",
                "drive_link",
                "path",
            ]
        )
    else:
        if false_positive_model is not None:
             image_insights = _suppress_false_positives_ml(
                image_insights=image_insights,
                false_positive_model=false_positive_model
             )
        image_insights = image_insights.sort_values(
            by=["timestamp", "camera_id", "filename"], na_position="last"
        ).reset_index(drop=True)
        image_insights = _suppress_learned_false_positives(
            image_insights=image_insights,
            false_positive_signatures=false_positive_signatures,
        )
        image_insights = _suppress_static_false_person_boxes(image_insights)

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
    image_insights = enrich_entrance_camera_classification(
        image_insights=image_insights,
        camera_configs=camera_configs,
    )
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
        "upper_colors": "[]",
        "lower_colors": "[]",
        "clothing_types": "[]",
        "ignore_reasons": "[]",
        "box_labels": "[]",
        "track_audit_json": "[]",
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
    summary_row = _apply_session_metrics_to_summary(
        summary_row=summary_row,
        customer_sessions=customer_sessions,
        bounce_threshold_sec=bounce_threshold_sec,
    )

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


def analyze_store_streaming(
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
    false_positive_signatures: list[dict[str, object]] | None = None,
    false_positive_model: Optional[Any] = None,
    chunk_size: int = 500,
    filename_prefixes: list[str] | None = None,
) -> StoreAnalysisResult:
    """Implement memory optimization using chunks + parquet storage + multiprocessing."""
    image_paths = _iter_store_images(store_dir)
    drive_link_map = _load_drive_link_map(store_dir)
    
    if camera_configs is None:
        camera_configs = {}
        
    staff_red_threshold = _estimate_store_staff_red_threshold(
        store_id=store_id,
        employee_assets_root=employee_assets_root,
    )
    
    # Filter targets
    targets = []
    for ip in image_paths:
        if not _matches_filename_filters(ip.name, filename_prefixes):
            continue
        if capture_date_filter is not None:
             image_day, _, _ = _infer_image_context(
                image_path=ip,
                store_dir=store_dir,
                fallback_day=reference_day,
            )
             if image_day != capture_date_filter:
                continue
        targets.append(ip)
        if max_images_per_store and len(targets) >= max_images_per_store:
            break
            
    # Process chunks in parallel
    parquet_files: list[Path] = []
    temp_dir = Path("data/cache/temp_chunks")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Simple chunking
    target_chunks = [targets[i:i + chunk_size] for i in range(0, len(targets), chunk_size)]
    
    # Run chunks (sequentially saving to disk) using multiprocessing for frames
    num_workers = max(1, multiprocessing.cpu_count() - 1)
    
    for chunk_idx, chunk in enumerate(target_chunks):
        rows = []
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(
                    _analyze_single_image,
                    ip,
                    store_dir,
                    store_id,
                    detector,
                    reference_day,
                    camera_configs,
                    staff_red_threshold,
                    enable_age_gender,
                    drive_link_map
                ) for ip in chunk
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    rows.append(res)
                    
        # Write to temporary parquet
        if rows:
            df = pd.DataFrame(rows)
            chunk_file = temp_dir / f"{store_id}_{chunk_idx}.parquet"
            df.to_parquet(chunk_file)
            parquet_files.append(chunk_file)
            
    # Concatenate all parquet chunks
    if not parquet_files:
        image_insights = pd.DataFrame(
            columns=[
                "store_id", "filename", "camera_id", "timestamp", "capture_date",
                "source_folder", "is_valid", "person_count", "max_person_conf",
                "relevant", "person_centroids", "person_boxes", "person_confidences", "staff_flags",
                "staff_scores", "staff_count", "customer_count", "bag_count",
                "gender_likelihood", "age_bucket_counts", "age_confidence",
                "age_gender_error", "floor_name", "location_name", "upper_colors",
                "lower_colors", "clothing_types", "ignore_reasons", "box_labels",
                "track_audit_json", "reject_reason",
                "detection_error", "relative_path", "drive_link", "path",
            ]
        )
    else:
        dfs = [pd.read_parquet(pf) for pf in parquet_files]
        image_insights = pd.concat(dfs, ignore_index=True)
        # Cleanup temp chunks
        for pf in parquet_files:
            try:
                pf.unlink()
            except Exception:
                pass
                
        if false_positive_model is not None:
             image_insights = _suppress_false_positives_ml(
                image_insights=image_insights,
                false_positive_model=false_positive_model
             )
             
        if not image_insights.empty:
            image_insights = image_insights.sort_values(
                by=["timestamp", "camera_id", "filename"], na_position="last"
            ).reset_index(drop=True)
            image_insights = _suppress_learned_false_positives(
                image_insights=image_insights,
                false_positive_signatures=false_positive_signatures,
            )
            image_insights = _suppress_static_false_person_boxes(image_insights)

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
    image_insights = enrich_entrance_camera_classification(
        image_insights=image_insights,
        camera_configs=camera_configs,
    )
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
        "person_confidences": "[]",
        "upper_colors": "[]",
        "lower_colors": "[]",
        "clothing_types": "[]",
        "ignore_reasons": "[]",
        "box_labels": "[]",
        "track_audit_json": "[]",
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
    summary_row = _apply_session_metrics_to_summary(
        summary_row=summary_row,
        customer_sessions=customer_sessions,
        bounce_threshold_sec=bounce_threshold_sec,
    )

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
    conf_threshold: float = 0.18,
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
    false_positive_signatures_by_store: dict[str, list[dict[str, object]]] | None = None,
    use_parallel: bool = True,
    use_streaming: bool = True,
    false_positive_model: Optional[Any] = None,
    filename_prefixes: list[str] | None = None,
) -> AnalysisOutput:
    root_dir = root_dir.resolve()
    detector, detector_warning = build_detector(
        detector_type=detector_type, conf_threshold=conf_threshold
    )

    store_dirs, used_root_fallback_store = _list_store_dirs(root_dir)
    store_results: dict[str, StoreAnalysisResult] = {}
    if camera_configs_by_store is None:
        camera_configs_by_store = {}
    if false_positive_signatures_by_store is None:
        false_positive_signatures_by_store = {}
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
            false_positive_signatures=false_positive_signatures_by_store.get(store_id, []),
            use_parallel=use_parallel,
            use_streaming=use_streaming,
            false_positive_model=false_positive_model,
            filename_prefixes=filename_prefixes,
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

    summary_export = output.all_stores_summary.copy()
    summary_columns = [
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
    for col in summary_columns:
        if col not in summary_export.columns:
            summary_export[col] = "" if col in {"store_id", "top_camera_hotspot", "peak_time_bucket"} else np.nan
    _write(summary_export[summary_columns], out_dir / "all_stores_summary.csv")
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
                    "event_label",
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
                    "person_confidences",
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
        session_export_cols = [
            "store_id",
            "capture_date",
            "session_id",
            "store_day_customer_id",
            "track_id_local",
            "entry_time",
            "last_seen_time",
            "exit_time",
            "entry_ts",
            "exit_ts",
            "dwell_seconds",
            "dwell_sec",
            "status",
            "close_reason",
            "session_class",
            "staff_flag",
            "is_staff_session",
            "is_valid_session",
            "invalid_reason",
            "converted_proxy",
            "cameras_seen",
            "locations_seen",
            "floors_seen",
            "entry_image",
            "entry_image_path",
            "entry_snapshot_path",
            "exit_image",
            "exit_image_path",
            "exit_snapshot_path",
            "frames_seen",
            "movement_score",
            "staff_ratio_max",
            "staff_score",
            "confidence",
            "gender",
            "notes",
        ]
        available_session_cols = [c for c in session_export_cols if c in store_result.customer_sessions.columns]
        if not available_session_cols:
            available_session_cols = list(store_result.customer_sessions.columns)
        _write(
            store_result.customer_sessions[available_session_cols],
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
        customer_sessions_df = pd.DataFrame(columns=_customer_session_columns())
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

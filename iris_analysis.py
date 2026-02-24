from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Protocol

import pandas as pd
from PIL import Image


FILE_PATTERN = re.compile(
    r"(?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


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


@dataclass(frozen=True)
class StoreAnalysisResult:
    image_insights: pd.DataFrame
    camera_hotspots: pd.DataFrame
    summary_row: pd.DataFrame


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
            return DetectionResult(person_count=0, max_person_conf=0.0, detection_error="")
        max_conf = max(self.conf_threshold, min(0.95, 0.55 + (seed % 30) / 100))
        return DetectionResult(
            person_count=person_count,
            max_person_conf=round(max_conf, 3),
            detection_error="",
        )


class UnavailableDetector:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def detect(self, image_path: Path) -> DetectionResult:
        return DetectionResult(person_count=0, max_person_conf=0.0, detection_error=self.reason)


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
                classes=[0],
                conf=self.conf_threshold,
                device=self.device,
                verbose=False,
            )
            boxes = results[0].boxes if results else None
            if boxes is None or len(boxes) == 0:
                return DetectionResult(person_count=0, max_person_conf=0.0, detection_error="")
            conf_values = boxes.conf.tolist()
            return DetectionResult(
                person_count=len(conf_values),
                max_person_conf=float(max(conf_values)),
                detection_error="",
            )
        except Exception as exc:
            return DetectionResult(person_count=0, max_person_conf=0.0, detection_error=str(exc))


def build_detector(detector_type: str = "yolo", conf_threshold: float = 0.25) -> tuple[PersonDetector, str]:
    if detector_type == "mock":
        return MockPersonDetector(conf_threshold=conf_threshold), ""
    if detector_type != "yolo":
        return (
            UnavailableDetector(f"Unsupported detector_type='{detector_type}'"),
            f"Unsupported detector_type='{detector_type}', using unavailable detector fallback.",
        )

    try:
        return YoloPersonDetector(conf_threshold=conf_threshold), ""
    except Exception as exc:
        reason = f"Detector unavailable: {exc}"
        return UnavailableDetector(reason), reason


def parse_filename(filename: str, reference_day: date | None = None) -> ParsedFilename | None:
    match = FILE_PATTERN.match(filename)
    if not match:
        return None
    hh, mm, ss = [int(part) for part in match.group("time").split("-")]
    if reference_day is None:
        reference_day = date.today()
    ts = datetime.combine(reference_day, datetime.min.time()).replace(
        hour=hh, minute=mm, second=ss
    )
    return ParsedFilename(
        timestamp=ts,
        camera_id=match.group("camera"),
        frame_no=int(match.group("frame")),
    )


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
        files = [child for child in path.iterdir() if child.is_file()]
        has_images = any(child.suffix.lower() in IMAGE_EXTENSIONS for child in files)
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
            for path in store_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
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


def build_store_summary(
    store_id: str, image_insights: pd.DataFrame, camera_hotspots: pd.DataFrame, time_bucket_minutes: int
) -> pd.DataFrame:
    total_images = int(len(image_insights))
    valid_images = int(image_insights["is_valid"].sum()) if total_images else 0
    relevant_images = int(image_insights["relevant"].sum()) if total_images else 0
    total_people = int(image_insights["person_count"].sum()) if total_images else 0

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
                "top_camera_hotspot": top_camera,
                "peak_time_bucket": peak_bucket,
            }
        ]
    )


def analyze_store(
    store_id: str,
    store_dir: Path,
    detector: PersonDetector,
    reference_day: date | None = None,
    time_bucket_minutes: int = 1,
) -> StoreAnalysisResult:
    rows: list[dict[str, object]] = []
    for image_path in _iter_store_images(store_dir):
        parsed = parse_filename(image_path.name, reference_day=reference_day)
        if parsed is None:
            rows.append(
                {
                    "store_id": store_id,
                    "filename": image_path.name,
                    "camera_id": "",
                    "timestamp": pd.NaT,
                    "is_valid": False,
                    "person_count": 0,
                    "max_person_conf": 0.0,
                    "relevant": False,
                    "reject_reason": "bad_filename",
                    "detection_error": "",
                    "path": str(image_path),
                }
            )
            continue

        is_valid, reject_reason = validate_image(image_path)
        detection = DetectionResult(person_count=0, max_person_conf=0.0, detection_error="")
        if is_valid:
            detection = detector.detect(image_path)
        relevant = bool(
            is_valid and detection.detection_error == "" and detection.person_count >= 1
        )

        rows.append(
            {
                "store_id": store_id,
                "filename": image_path.name,
                "camera_id": parsed.camera_id,
                "timestamp": parsed.timestamp,
                "is_valid": is_valid,
                "person_count": int(detection.person_count),
                "max_person_conf": float(detection.max_person_conf),
                "relevant": relevant,
                "reject_reason": reject_reason,
                "detection_error": detection.detection_error,
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
            "is_valid",
            "person_count",
            "max_person_conf",
            "relevant",
            "reject_reason",
            "detection_error",
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
                "is_valid",
                "person_count",
                "max_person_conf",
                "relevant",
                "reject_reason",
                "detection_error",
                "path",
            ]
        )
    else:
        image_insights = image_insights.sort_values(
            by=["timestamp", "camera_id", "filename"], na_position="last"
        ).reset_index(drop=True)

    camera_hotspots = build_camera_hotspots(image_insights, store_id=store_id)
    summary_row = build_store_summary(
        store_id=store_id,
        image_insights=image_insights,
        camera_hotspots=camera_hotspots,
        time_bucket_minutes=time_bucket_minutes,
    )
    return StoreAnalysisResult(
        image_insights=image_insights,
        camera_hotspots=camera_hotspots,
        summary_row=summary_row,
    )


def analyze_root(
    root_dir: Path,
    conf_threshold: float = 0.25,
    detector_type: str = "yolo",
    time_bucket_minutes: int = 1,
    reference_day: date | None = None,
) -> AnalysisOutput:
    root_dir = root_dir.resolve()
    detector, detector_warning = build_detector(
        detector_type=detector_type, conf_threshold=conf_threshold
    )

    store_dirs, used_root_fallback_store = _list_store_dirs(root_dir)
    store_results: dict[str, StoreAnalysisResult] = {}
    summary_frames: list[pd.DataFrame] = []
    for store_dir in store_dirs:
        store_id = store_dir.name
        result = analyze_store(
            store_id=store_id,
            store_dir=store_dir,
            detector=detector,
            reference_day=reference_day,
            time_bucket_minutes=time_bucket_minutes,
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
                "top_camera_hotspot",
                "peak_time_bucket",
            ]
        )

    return AnalysisOutput(
        stores=store_results,
        all_stores_summary=all_stores_summary,
        detector_warning=detector_warning,
        used_root_fallback_store=used_root_fallback_store,
    )


def export_analysis(output: AnalysisOutput, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    output.all_stores_summary.to_csv(out_dir / "all_stores_summary.csv", index=False)
    for store_id, store_result in output.stores.items():
        image_path = out_dir / f"store_{store_id}_image_insights.csv"
        hotspot_path = out_dir / f"store_{store_id}_camera_hotspots.csv"
        store_result.image_insights[
            [
                "store_id",
                "filename",
                "camera_id",
                "timestamp",
                "is_valid",
                "person_count",
                "max_person_conf",
                "relevant",
                "reject_reason",
                "detection_error",
                "path",
            ]
        ].to_csv(image_path, index=False)
        store_result.camera_hotspots[
            [
                "store_id",
                "camera_id",
                "relevant_images",
                "total_people",
                "avg_people_per_relevant_image",
                "hotspot_rank",
            ]
        ].to_csv(hotspot_path, index=False)


def load_exports(out_dir: Path) -> AnalysisOutput:
    summary_path = out_dir / "all_stores_summary.csv"
    if not summary_path.exists():
        return AnalysisOutput(
            stores={},
            all_stores_summary=pd.DataFrame(
                columns=[
                    "store_id",
                    "total_images",
                    "valid_images",
                    "relevant_images",
                    "total_people",
                    "top_camera_hotspot",
                    "peak_time_bucket",
                ]
            ),
            detector_warning="",
            used_root_fallback_store=False,
        )

    all_stores_summary = pd.read_csv(summary_path)
    stores: dict[str, StoreAnalysisResult] = {}
    for store_id in all_stores_summary["store_id"].astype(str).tolist():
        image_path = out_dir / f"store_{store_id}_image_insights.csv"
        hotspot_path = out_dir / f"store_{store_id}_camera_hotspots.csv"
        if not image_path.exists() or not hotspot_path.exists():
            continue

        image_df = pd.read_csv(image_path, parse_dates=["timestamp"])
        hotspot_df = pd.read_csv(hotspot_path)
        summary_row = all_stores_summary[all_stores_summary["store_id"] == store_id].copy()
        stores[store_id] = StoreAnalysisResult(
            image_insights=image_df,
            camera_hotspots=hotspot_df,
            summary_row=summary_row,
        )

    return AnalysisOutput(
        stores=stores,
        all_stores_summary=all_stores_summary,
        detector_warning="",
        used_root_fallback_store=False,
    )

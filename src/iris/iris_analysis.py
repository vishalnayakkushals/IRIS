from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
import math
import csv
import json
import re
from typing import Protocol

import pandas as pd
from PIL import Image


FILE_PATTERN = re.compile(
    r"(?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
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
) -> StoreAnalysisResult:
    rows: list[dict[str, object]] = []
    image_paths = _iter_store_images(store_dir)
    drive_link_map = _load_drive_link_map(store_dir)
    staff_red_threshold = _estimate_store_staff_red_threshold(
        store_id=store_id,
        employee_assets_root=employee_assets_root,
    )
    if max_images_per_store is not None and max_images_per_store > 0:
        image_paths = image_paths[:max_images_per_store]

    for image_path in image_paths:
        rel_path = _relative_image_path(image_path=image_path, store_dir=store_dir)
        drive_link = drive_link_map.get(rel_path, "")
        image_day, capture_date, source_folder = _infer_image_context(
            image_path=image_path,
            store_dir=store_dir,
            fallback_day=reference_day,
        )
        parsed = parse_filename(image_path.name, reference_day=image_day)
        if parsed is None:
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
                    "reject_reason": "bad_filename",
                    "detection_error": "",
                    "relative_path": rel_path,
                    "drive_link": drive_link,
                    "path": str(image_path),
                }
            )
            continue

        is_valid, reject_reason = validate_image(image_path)
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
        relevant = bool(
            is_valid and detection.detection_error == "" and detection.person_count >= 1
        )

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
    role_map = {cid: (cfg.get("camera_role", "INSIDE") if isinstance(cfg, dict) else "INSIDE") for cid, cfg in (camera_configs or {}).items()}
    if "camera_id" in image_insights.columns:
        mask = image_insights["camera_id"].map(lambda c: str(role_map.get(str(c), "INSIDE")).upper() in {"BILLING", "BACKROOM"})
        image_insights.loc[mask, "relevant"] = False
    image_insights = assign_single_camera_tracks(image_insights=image_insights, session_gap_sec=session_gap_sec)
    image_insights = stitch_multi_camera_visits(image_insights=image_insights, max_delta_sec=max(1, int(session_gap_sec // 2)))
    image_insights, daily_report = build_daily_customer_report(
        image_insights=image_insights,
        camera_configs=camera_configs,
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
    if not daily_report.empty:
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
) -> AnalysisOutput:
    root_dir = root_dir.resolve()
    detector, detector_warning = build_detector(
        detector_type=detector_type, conf_threshold=conf_threshold
    )

    store_dirs, used_root_fallback_store = _list_store_dirs(root_dir)
    store_results: dict[str, StoreAnalysisResult] = {}
    if camera_configs_by_store is None:
        camera_configs_by_store = {}
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
                    "track_ids",
                    "global_visit_id",
                    "customer_ids",
                    "group_ids",
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
        if not store_result.daily_report.empty:
            _write(store_result.daily_report, out_dir / f"store_{store_id}_daily_report.csv")
        if not store_result.daily_proof.empty:
            _write(store_result.daily_proof, out_dir / f"store_{store_id}_daily_proof.csv")
        if not store_result.alerts.empty:
            _write(store_result.alerts, out_dir / f"store_{store_id}_alerts.csv")


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
        image_gz_path = image_path.with_suffix(image_path.suffix + ".gz")
        hotspot_gz_path = hotspot_path.with_suffix(hotspot_path.suffix + ".gz")
        if not (image_path.exists() or image_gz_path.exists()) or not (hotspot_path.exists() or hotspot_gz_path.exists()):
            continue

        image_df = pd.read_csv(image_path if image_path.exists() else image_gz_path, parse_dates=["timestamp"])
        hotspot_df = pd.read_csv(hotspot_path if hotspot_path.exists() else hotspot_gz_path)
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

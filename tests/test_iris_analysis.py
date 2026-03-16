from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from PIL import Image
import pandas as pd

from iris.iris_analysis import (
    AnalysisOutput,
    DetectionResult,
    PersonDetector,
    _ahash_from_crop,
    analyze_root,
    analyze_store,
    build_detector,
    build_camera_hotspots,
    export_analysis,
    export_store_day_artifacts,
    load_exports,
    parse_filename,
    validate_image,
)


class FixedDetector(PersonDetector):
    def __init__(self, mapping: dict[str, int]) -> None:
        self.mapping = mapping

    def detect(self, image_path: Path) -> DetectionResult:
        count = self.mapping.get(image_path.name, 0)
        conf = 0.8 if count > 0 else 0.0
        return DetectionResult(person_count=count, max_person_conf=conf, detection_error="")


class BoxDetector(PersonDetector):
    def __init__(self, mapping: dict[str, list[tuple[float, float, float, float]]]) -> None:
        self.mapping = mapping

    def detect(self, image_path: Path) -> DetectionResult:
        boxes = self.mapping.get(image_path.name, [])
        centroids = [((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0) for b in boxes]
        return DetectionResult(
            person_count=len(boxes),
            max_person_conf=0.9 if boxes else 0.0,
            detection_error="",
            person_centroids=centroids,
            person_boxes=boxes,
            bag_count=0,
        )


def _write_image(path: Path, color: tuple[int, int, int] = (120, 90, 60)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 12), color=color).save(path)


def test_parse_filename_extracts_time_camera_frame() -> None:
    parsed = parse_filename("09-57-27_D02-1.jpg", reference_day=date(2026, 2, 24))
    assert parsed is not None
    assert parsed.camera_id == "D02"
    assert parsed.frame_no == 1
    assert parsed.timestamp.hour == 9
    assert parsed.timestamp.minute == 57
    assert parsed.timestamp.second == 27


def test_validate_image_flags_zero_byte_and_unreadable(tmp_path: Path) -> None:
    zero = tmp_path / "09-57-27_D02-1.jpg"
    zero.write_bytes(b"")
    assert validate_image(zero) == (False, "zero_byte")

    broken = tmp_path / "09-57-27_D03-1.jpg"
    broken.write_text("not an image", encoding="utf-8")
    assert validate_image(broken) == (False, "unreadable")


def test_relevant_rule_requires_valid_and_person_detected(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    img_person = store / "09-57-27_D02-1.jpg"
    img_empty = store / "09-57-27_D03-1.jpg"
    img_zero = store / "09-57-27_D04-1.jpg"
    _write_image(img_person)
    _write_image(img_empty)
    img_zero.write_bytes(b"")

    detector = FixedDetector({img_person.name: 2, img_empty.name: 0})
    result = analyze_store(store_id="store_a", store_dir=store, detector=detector)
    rows = result.image_insights.set_index("filename")

    assert bool(rows.loc[img_person.name, "relevant"]) is True
    assert bool(rows.loc[img_empty.name, "relevant"]) is False
    assert bool(rows.loc[img_zero.name, "relevant"]) is False


def test_static_banner_false_positive_is_suppressed(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    mapping: dict[str, list[tuple[float, float, float, float]]] = {}
    static_box = (0.08, 0.10, 0.28, 0.62)
    for i in range(8):
        name = f"09-57-{i:02d}_D03-1.jpg"
        _write_image(store / name)
        boxes = [static_box]
        if i in {2, 5}:
            boxes.append((0.45 + (i * 0.02), 0.20, 0.62 + (i * 0.02), 0.82))
        mapping[name] = boxes
    detector = BoxDetector(mapping)
    result = analyze_store(store_id="store_a", store_dir=store, detector=detector)
    rows = result.image_insights.set_index("filename")
    assert int(rows["person_count"].sum()) == 2
    assert int(rows.loc["09-57-02_D03-1.jpg", "person_count"]) == 1
    assert int(rows.loc["09-57-05_D03-1.jpg", "person_count"]) == 1
    assert int(rows.loc["09-57-00_D03-1.jpg", "person_count"]) == 0
    assert bool(rows.loc["09-57-00_D03-1.jpg", "relevant"]) is False


def test_staff_is_counted_separately_from_customer(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    img = store / "09-57-27_D02-1.jpg"
    _write_image(img, color=(240, 30, 30))
    detector = BoxDetector({img.name: [(0.10, 0.05, 0.90, 0.95)]})
    result = analyze_store(store_id="store_a", store_dir=store, detector=detector)
    row = result.image_insights.iloc[0]
    assert int(row["person_count"]) == 1
    assert int(row["staff_count"]) == 1
    assert int(row["customer_count"]) == 0


def test_feedback_signature_suppresses_learned_banner_false_positive(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    img = store / "09-57-27_D03-1.jpg"
    _write_image(img, color=(160, 160, 160))
    box = (0.08, 0.10, 0.28, 0.62)
    detector = BoxDetector({img.name: [box]})
    baseline = analyze_store(store_id="store_a", store_dir=store, detector=detector)
    assert int(baseline.image_insights.iloc[0]["person_count"]) == 1

    with Image.open(img) as raw:
        sig_hash = _ahash_from_crop(raw.convert("RGB"), box)
    with_signature = analyze_store(
        store_id="store_a",
        store_dir=store,
        detector=detector,
        false_positive_signatures=[
            {
                "camera_id": "D03",
                "box_json": json.dumps(list(box)),
                "hash64": sig_hash,
                "hamming_threshold": 10,
            }
        ],
    )
    row = with_signature.image_insights.iloc[0]
    assert int(row["person_count"]) == 0
    assert bool(row["relevant"]) is False


def test_hotspot_ranking_tie_breaks_by_total_people_then_camera() -> None:
    df = pd.DataFrame(
        [
            {"store_id": "s1", "filename": "f1", "camera_id": "D02", "relevant": True, "person_count": 2},
            {"store_id": "s1", "filename": "f2", "camera_id": "D02", "relevant": True, "person_count": 2},
            {"store_id": "s1", "filename": "f3", "camera_id": "D03", "relevant": True, "person_count": 2},
            {"store_id": "s1", "filename": "f4", "camera_id": "D03", "relevant": True, "person_count": 2},
            {"store_id": "s1", "filename": "f5", "camera_id": "D04", "relevant": True, "person_count": 1},
            {"store_id": "s1", "filename": "f6", "camera_id": "D04", "relevant": True, "person_count": 3},
        ]
    )
    hotspots = build_camera_hotspots(df, store_id="s1")
    ordered = hotspots.sort_values("hotspot_rank")["camera_id"].tolist()
    assert ordered == ["D02", "D03", "D04"]


def test_export_csv_schema_for_multi_store(tmp_path: Path) -> None:
    root = tmp_path / "root"
    s1 = root / "store_1"
    s2 = root / "store_2"
    _write_image(s1 / "09-57-27_D02-1.jpg")
    _write_image(s1 / "09-57-44_D03-1.jpg")
    _write_image(s2 / "09-58-00_D02-1.jpg")
    (s2 / "bad_name.jpg").write_text("bad", encoding="utf-8")

    output = analyze_root(root_dir=root, detector_type="mock", conf_threshold=0.25)
    out = tmp_path / "exports"
    export_analysis(output, out_dir=out)

    summary = pd.read_csv(out / "all_stores_summary.csv")
    assert set(summary.columns) == {
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
    }
    assert sorted(summary["store_id"].tolist()) == ["store_1", "store_2"]

    image_csv = pd.read_csv(out / "store_store_1_image_insights.csv")
    assert {
        "store_id",
        "filename",
        "camera_id",
        "timestamp",
        "is_valid",
        "person_count",
        "max_person_conf",
        "relevant",
    }.issubset(set(image_csv.columns))


def test_build_detector_accepts_tf_frcnn_option() -> None:
    detector, warning = build_detector(detector_type="tf_frcnn", conf_threshold=0.25)
    assert detector is not None
    assert "Unsupported detector_type" not in warning


def test_empty_store_folder_is_in_summary(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "store_empty").mkdir(parents=True)
    output: AnalysisOutput = analyze_root(root_dir=root, detector_type="mock")
    assert "store_empty" in output.stores
    summary = output.all_stores_summary.set_index("store_id")
    assert int(summary.loc["store_empty", "total_images"]) == 0
    assert int(summary.loc["store_empty", "relevant_images"]) == 0


def test_non_image_technical_folders_are_not_treated_as_stores(tmp_path: Path) -> None:
    root = tmp_path / "root"
    tech = root / "tests"
    tech.mkdir(parents=True)
    (tech / "a.txt").write_text("ignore", encoding="utf-8")
    store = root / "store_1"
    _write_image(store / "09-57-27_D02-1.jpg")

    output = analyze_root(root_dir=root, detector_type="mock")
    assert sorted(output.stores.keys()) == ["store_1"]


def test_export_and_load_with_gzip_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = root / "store_1"
    _write_image(store / "09-57-27_D02-1.jpg")

    output = analyze_root(root_dir=root, detector_type="mock", conf_threshold=0.25)
    out = tmp_path / "exports"
    export_analysis(output, out_dir=out, write_gzip_exports=True, keep_plain_csv=False)

    assert (out / "all_stores_summary.csv.gz").exists()
    assert not (out / "all_stores_summary.csv").exists()

    loaded = load_exports(out)
    assert not loaded.all_stores_summary.empty
    assert "store_1" in loaded.stores


def test_estimated_visits_dwell_and_bounce_metrics(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    # Same camera with a large gap to create 2 sessions.
    _write_image(store / "09-00-00_D02-1.jpg")
    _write_image(store / "09-00-10_D02-2.jpg")
    _write_image(store / "09-02-00_D02-3.jpg")

    detector = FixedDetector(
        {
            "09-00-00_D02-1.jpg": 1,
            "09-00-10_D02-2.jpg": 1,
            "09-02-00_D02-3.jpg": 1,
        }
    )
    result = analyze_store(
        store_id="store_a",
        store_dir=store,
        detector=detector,
        bounce_threshold_sec=20,
        session_gap_sec=30,
    )
    row = result.summary_row.iloc[0]
    assert int(row["estimated_visits"]) == 2
    assert float(row["avg_dwell_sec"]) > 0
    assert 0.0 <= float(row["bounce_rate"]) <= 1.0


class CrossingDetector(PersonDetector):
    def __init__(self, mapping):
        self.mapping = mapping

    def detect(self, image_path: Path) -> DetectionResult:
        centroids = self.mapping.get(image_path.name, [])
        return DetectionResult(
            person_count=len(centroids),
            max_person_conf=0.9 if centroids else 0.0,
            detection_error="",
            person_centroids=centroids,
            bag_count=0,
        )


def test_footfall_and_loss_of_sale_alert_from_entrance_line(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    _write_image(store / "09-00-00_D01-1.jpg")
    _write_image(store / "09-03-30_D01-2.jpg")

    detector = CrossingDetector(
        {
            "09-00-00_D01-1.jpg": [(0.45, 0.5)],
            "09-03-30_D01-2.jpg": [(0.55, 0.5)],
        }
    )

    result = analyze_store(
        store_id="store_a",
        store_dir=store,
        detector=detector,
        camera_configs={
            "D01": {
                "camera_role": "ENTRANCE",
                "entry_line_x": 0.5,
                "entry_direction": "OUTSIDE_TO_INSIDE",
            }
        },
        engaged_dwell_threshold_sec=30,
        session_gap_sec=400,
    )
    row = result.summary_row.iloc[0]
    assert int(row["footfall"]) >= 1
    assert int(row["loss_of_sale_alerts"]) >= 0


def test_date_is_inferred_from_folder_name_for_timestamp_and_proof(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    date_folder = store / "2026-03-12"
    _write_image(date_folder / "09-00-00_D01-1.jpg")
    _write_image(date_folder / "09-00-10_D01-2.jpg")
    detector = FixedDetector(
        {
            "09-00-00_D01-1.jpg": 1,
            "09-00-10_D01-2.jpg": 2,
        }
    )
    result = analyze_store(store_id="store_a", store_dir=store, detector=detector)
    assert not result.image_insights.empty
    assert str(result.image_insights.iloc[0]["capture_date"]) == "2026-03-12"
    assert int(result.image_insights.iloc[0]["timestamp"].year) == 2026
    assert not result.daily_proof.empty
    proof_row = result.daily_proof.iloc[0]
    assert str(proof_row["date"]) == "2026-03-12"
    assert int(proof_row["total_images"]) == 2


def test_daily_proof_csv_is_exported_and_loaded(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = root / "store_1" / "2026-03-12"
    _write_image(store / "09-57-27_D02-1.jpg")
    output = analyze_root(root_dir=root.parent / "root", detector_type="mock", conf_threshold=0.25)
    out = tmp_path / "exports"
    export_analysis(output, out_dir=out)
    assert (out / "store_store_1_daily_proof.csv").exists()
    loaded = load_exports(out)
    assert "store_1" in loaded.stores
    assert not loaded.stores["store_1"].daily_proof.empty


def test_store_day_customer_ids_are_date_scoped(tmp_path: Path) -> None:
    store = tmp_path / "store_a"
    d1 = store / "2025-03-12"
    d2 = store / "2025-03-13"
    _write_image(d1 / "09-00-00_D02-1.jpg")
    _write_image(d1 / "09-00-10_D02-2.jpg")
    _write_image(d2 / "09-01-00_D02-1.jpg")
    detector = FixedDetector(
        {
            "09-00-00_D02-1.jpg": 1,
            "09-00-10_D02-2.jpg": 1,
            "09-01-00_D02-1.jpg": 1,
        }
    )
    result = analyze_store(
        store_id="BLRJAY",
        store_dir=store,
        detector=detector,
        camera_configs={"D02": {"camera_role": "ENTRANCE", "entry_line_x": 0.5, "entry_direction": "OUTSIDE_TO_INSIDE"}},
        capture_date_filter=date(2025, 3, 12),
    )
    assert not result.image_insights.empty
    assert set(result.image_insights["capture_date"].astype(str).tolist()) == {"2025-03-12"}
    ids = []
    for value in result.image_insights["store_day_customer_ids"].tolist():
        if isinstance(value, str) and value.strip():
            ids.extend([str(x) for x in json.loads(value)])
    assert all(cid.startswith("C_BLRJAY_20250312_") for cid in ids if cid)
    assert not result.customer_sessions.empty
    assert set(result.customer_sessions["capture_date"].astype(str).tolist()) == {"2025-03-12"}


def test_export_store_day_artifacts_creates_required_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    store = root / "BLRJAY" / "2025-03-12"
    _write_image(store / "09-57-27_D02-1.jpg")
    output = analyze_root(
        root_dir=root,
        detector_type="mock",
        store_filter="BLRJAY",
        capture_date_filter=date(2025, 3, 12),
        max_images_per_store=None,
    )
    out = tmp_path / "exports"
    created = export_store_day_artifacts(
        output=output,
        out_dir=out,
        store_id="BLRJAY",
        capture_date="2025-03-12",
        write_gzip_exports=False,
        keep_plain_csv=True,
    )
    names = sorted([p.name for p in created])
    assert "store_BLRJAY_2025-03-12_image_insights.csv" in names
    assert "store_BLRJAY_2025-03-12_customer_sessions.csv" in names
    assert "store_BLRJAY_2025-03-12_location_hotspots.csv" in names
    assert "store_BLRJAY_2025-03-12_daily_proof.csv" in names

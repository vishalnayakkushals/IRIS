from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image
import pandas as pd

from iris_analysis import (
    AnalysisOutput,
    DetectionResult,
    PersonDetector,
    analyze_root,
    analyze_store,
    build_camera_hotspots,
    export_analysis,
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
        "top_camera_hotspot",
        "peak_time_bucket",
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

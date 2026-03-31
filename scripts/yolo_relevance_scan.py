from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.iris_analysis import build_detector, parse_filename  # noqa: E402


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DATE_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_FOLDER_COMPACT_PATTERN = re.compile(r"^\d{8}$")


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Stage-1 YOLO relevance scan (human presence filter).")
    parser.add_argument("--root", type=Path, default=app_dir / "data" / "test_stores")
    parser.add_argument("--out-dir", type=Path, default=app_dir / "data" / "exports" / "current" / "stage1_relevance")
    parser.add_argument("--store-id", default="", help="Optional store filter.")
    parser.add_argument("--conf", type=float, default=0.18)
    parser.add_argument("--detector", choices=["yolo", "mock"], default="yolo")
    parser.add_argument("--allow-detector-fallback", action="store_true", help="Allow non-YOLO fallback if YOLO is unavailable.")
    parser.add_argument("--max-images", type=int, default=0, help="Optional cap; 0 means full scan.")
    parser.add_argument("--gzip-exports", action="store_true", help="Also write .csv.gz outputs.")
    parser.add_argument("--drop-plain-csv", action="store_true", help="Skip plain CSV and keep only gzip output.")
    parser.add_argument(
        "--store-report",
        type=Path,
        default=app_dir / "data" / "exports" / "current" / "vision_eval" / "store_report.csv",
        help="Store+date aggregated Stage-1 report path.",
    )
    parser.add_argument("--skip-store-report", action="store_true", help="Skip store-level report generation.")
    return parser.parse_args()


def _discover_store_dirs(root_dir: Path, store_filter: str) -> list[tuple[str, Path]]:
    if not root_dir.exists():
        return []
    wanted = store_filter.strip()
    store_dirs: list[tuple[str, Path]] = []
    subdirs = [p for p in sorted(root_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    for sub in subdirs:
        has_images = any(path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS for path in sub.rglob("*"))
        if not has_images:
            continue
        sid = sub.name
        if wanted and sid != wanted:
            continue
        store_dirs.append((sid, sub))
    if store_dirs:
        return store_dirs

    root_has_images = any(path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS for path in root_dir.rglob("*"))
    if not root_has_images:
        return []
    sid = wanted or root_dir.name
    return [(sid, root_dir)]


def _iter_images(store_dir: Path) -> list[Path]:
    return sorted(
        [p for p in store_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: str(p.relative_to(store_dir)).lower(),
    )


def _capture_date_from_relpath(rel_path: Path) -> date | None:
    for part in rel_path.parts:
        text = str(part).strip()
        if DATE_FOLDER_PATTERN.fullmatch(text):
            try:
                return date.fromisoformat(text)
            except ValueError:
                continue
        if DATE_FOLDER_COMPACT_PATTERN.fullmatch(text):
            try:
                return date.fromisoformat(f"{text[0:4]}-{text[4:6]}-{text[6:8]}")
            except ValueError:
                continue
    return None


def _to_str_ts(value: Any) -> str:
    if value is None:
        return ""
    try:
        return pd.Timestamp(value).isoformat()
    except Exception:
        return ""


def _write_csv(df: pd.DataFrame, path: Path, write_gzip: bool, keep_plain: bool) -> None:
    if keep_plain:
        df.to_csv(path, index=False)
    if write_gzip:
        df.to_csv(path.with_suffix(path.suffix + ".gz"), index=False, compression="gzip")


def _preferred_output_path(path: Path, write_gzip: bool, keep_plain: bool) -> str:
    if keep_plain:
        return str(path.resolve())
    if write_gzip:
        return str(path.with_suffix(path.suffix + ".gz").resolve())
    return str(path.resolve())


def _normalized_date(value: Any) -> str:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return ""
        return ts.date().isoformat()
    except Exception:
        return ""


def _build_store_date_report(stage1_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["store_name", "date", "raw_image_count", "relevant_image_count"]
    if stage1_df.empty:
        return pd.DataFrame(columns=columns)
    df = stage1_df.copy()
    df["store_name"] = df.get("store_id", "").fillna("").astype(str).str.strip()
    date_col = df.get("capture_date", "").map(_normalized_date)
    ts_col = df.get("timestamp", "").map(_normalized_date)
    df["date"] = date_col.mask(date_col == "", ts_col)
    df["is_relevant"] = pd.to_numeric(df.get("is_relevant", 0), errors="coerce").fillna(0).astype(int).clip(lower=0, upper=1)
    scoped = df[df["store_name"].ne("") & df["date"].ne("")].copy()
    if scoped.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        scoped.groupby(["store_name", "date"], as_index=False)
        .agg(
            raw_image_count=("image_name", "count"),
            relevant_image_count=("is_relevant", "sum"),
        )
        .sort_values(["date", "store_name"], ascending=[False, True])
        .reset_index(drop=True)
    )
    grouped["raw_image_count"] = grouped["raw_image_count"].astype(int)
    grouped["relevant_image_count"] = grouped["relevant_image_count"].astype(int)
    return grouped[columns]


def _upsert_store_report(report_df: pd.DataFrame, report_path: Path) -> tuple[pd.DataFrame, Path, Path]:
    cols = ["store_name", "date", "raw_image_count", "relevant_image_count"]
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = report_path.with_suffix(".json")
    if report_df.empty:
        if report_path.exists():
            try:
                existing = pd.read_csv(report_path)
                existing = existing[[c for c in cols if c in existing.columns]].copy()
                for c in cols:
                    if c not in existing.columns:
                        existing[c] = 0 if c.endswith("_count") else ""
                existing = existing[cols]
                existing.to_csv(report_path, index=False)
                existing.to_json(json_path, orient="records", indent=2)
                return existing, report_path, json_path
            except Exception:
                pass
        empty = pd.DataFrame(columns=cols)
        empty.to_csv(report_path, index=False)
        empty.to_json(json_path, orient="records", indent=2)
        return empty, report_path, json_path

    incoming = report_df[cols].copy()
    incoming["raw_image_count"] = pd.to_numeric(incoming["raw_image_count"], errors="coerce").fillna(0).astype(int)
    incoming["relevant_image_count"] = pd.to_numeric(incoming["relevant_image_count"], errors="coerce").fillna(0).astype(int)
    if report_path.exists():
        try:
            existing = pd.read_csv(report_path)
            for c in cols:
                if c not in existing.columns:
                    existing[c] = 0 if c.endswith("_count") else ""
            existing = existing[cols].copy()
            existing["store_name"] = existing["store_name"].fillna("").astype(str).str.strip()
            existing["date"] = existing["date"].map(_normalized_date)
            existing["raw_image_count"] = pd.to_numeric(existing["raw_image_count"], errors="coerce").fillna(0).astype(int)
            existing["relevant_image_count"] = pd.to_numeric(existing["relevant_image_count"], errors="coerce").fillna(0).astype(int)
        except Exception:
            existing = pd.DataFrame(columns=cols)
    else:
        existing = pd.DataFrame(columns=cols)

    overwrite_keys = set((str(r["store_name"]).strip(), str(r["date"]).strip()) for _, r in incoming.iterrows())
    if not existing.empty:
        existing = existing[
            ~existing.apply(lambda r: (str(r.get("store_name", "")).strip(), str(r.get("date", "")).strip()) in overwrite_keys, axis=1)
        ].copy()
    merged = pd.concat([existing, incoming], ignore_index=True)
    merged = merged.sort_values(["date", "store_name"], ascending=[False, True]).reset_index(drop=True)
    merged.to_csv(report_path, index=False)
    merged.to_json(json_path, orient="records", indent=2)
    return merged, report_path, json_path


def run_stage1_scan(args: argparse.Namespace) -> dict[str, Any]:
    root_dir = args.root.resolve()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    detector, detector_warning = build_detector(
        detector_type=str(args.detector),
        conf_threshold=float(args.conf),
        use_cache=True,
    )
    if str(args.detector).strip().lower() == "yolo":
        fallback_active = bool(detector_warning and "fallback active" in str(detector_warning).lower())
        if fallback_active and not bool(args.allow_detector_fallback):
            raise RuntimeError(
                "YOLO detector unavailable and fallback would be used. "
                "Fix YOLO runtime or pass --allow-detector-fallback to continue."
            )

    store_dirs = _discover_store_dirs(root_dir=root_dir, store_filter=str(args.store_id or ""))
    if not store_dirs:
        summary = {
            "root_dir": str(root_dir),
            "out_dir": str(out_dir),
            "detector": str(args.detector),
            "conf_threshold": float(args.conf),
            "detector_warning": str(detector_warning or ""),
            "stores_scanned": 0,
            "total_images_discovered": 0,
            "total_images_processed": 0,
            "relevant_images": 0,
            "irrelevant_images": 0,
            "relevant_percent": 0.0,
            "irrelevant_percent": 0.0,
            "store_summaries": [],
        }
        (out_dir / "stage1_relevance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    keep_plain = not bool(args.drop_plain_csv)
    write_gzip = bool(args.gzip_exports)
    max_images = max(0, int(args.max_images))

    all_rows: list[dict[str, Any]] = []
    store_summaries: list[dict[str, Any]] = []
    total_discovered = 0
    total_processed = 0

    for store_id, store_dir in store_dirs:
        images = _iter_images(store_dir=store_dir)
        discovered = len(images)
        total_discovered += discovered
        if max_images > 0:
            images = images[:max_images]
        processed = len(images)
        total_processed += processed
        store_rows: list[dict[str, Any]] = []

        for image_path in images:
            rel_path = image_path.relative_to(store_dir)
            capture_day = _capture_date_from_relpath(rel_path=rel_path)
            parsed = parse_filename(image_path.name, reference_day=capture_day)
            camera_id = parsed.camera_id if parsed is not None else ""
            timestamp_text = _to_str_ts(parsed.timestamp if parsed is not None else None)
            capture_date = (
                parsed.timestamp.date().isoformat()
                if parsed is not None
                else (capture_day.isoformat() if capture_day is not None else "")
            )

            detection = detector.detect(image_path)
            person_count = max(0, int(detection.person_count or 0))
            det_error = str(detection.detection_error or "").strip()
            person_detected = bool(person_count >= 1 and det_error == "")
            row = {
                "store_id": store_id,
                "image_name": image_path.name,
                "image_path": str(image_path.resolve()),
                "relative_path": str(rel_path).replace("\\", "/"),
                "source_folder": str(rel_path.parent).replace("\\", "/"),
                "camera_id": camera_id,
                "timestamp": timestamp_text,
                "capture_date": capture_date,
                "person_detected": int(person_detected),
                "person_count": int(person_count),
                "max_person_conf": float(detection.max_person_conf or 0.0),
                "detection_error": det_error,
                "is_relevant": int(person_detected),
            }
            store_rows.append(row)
            all_rows.append(row)

        store_df = pd.DataFrame(store_rows)
        if store_df.empty:
            relevant_df = pd.DataFrame(columns=["store_id", "image_name", "image_path", "relative_path", "source_folder", "camera_id", "timestamp", "capture_date", "person_detected", "person_count", "max_person_conf", "detection_error", "is_relevant"])
            irrelevant_df = relevant_df.copy()
        else:
            relevant_df = store_df[store_df["is_relevant"] == 1].copy()
            irrelevant_df = store_df[store_df["is_relevant"] == 0].copy()

        camera_summary = {}
        if not relevant_df.empty and "camera_id" in relevant_df.columns:
            counts = relevant_df["camera_id"].fillna("").astype(str).value_counts().to_dict()
            camera_summary = {str(k): int(v) for k, v in counts.items() if str(k).strip()}

        store_summary = {
            "store_id": store_id,
            "store_path": str(store_dir.resolve()),
            "images_discovered": int(discovered),
            "images_processed": int(processed),
            "relevant_images": int(len(relevant_df)),
            "irrelevant_images": int(len(irrelevant_df)),
            "relevant_percent": round((float(len(relevant_df)) / float(processed) * 100.0), 2) if processed > 0 else 0.0,
            "per_camera_relevant_count": camera_summary,
        }
        store_summaries.append(store_summary)

        store_out = out_dir / store_id
        store_out.mkdir(parents=True, exist_ok=True)
        _write_csv(store_df, store_out / "stage1_relevance_all.csv", write_gzip=write_gzip, keep_plain=keep_plain)
        _write_csv(relevant_df, store_out / "stage1_relevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain)
        _write_csv(irrelevant_df, store_out / "stage1_irrelevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain)
        (store_out / "stage1_relevance_summary.json").write_text(json.dumps(store_summary, indent=2), encoding="utf-8")

    all_df = pd.DataFrame(all_rows)
    if all_df.empty:
        relevant_all = pd.DataFrame(columns=["store_id", "image_name", "image_path", "relative_path", "source_folder", "camera_id", "timestamp", "capture_date", "person_detected", "person_count", "max_person_conf", "detection_error", "is_relevant"])
        irrelevant_all = relevant_all.copy()
    else:
        relevant_all = all_df[all_df["is_relevant"] == 1].copy()
        irrelevant_all = all_df[all_df["is_relevant"] == 0].copy()

    _write_csv(all_df, out_dir / "stage1_relevance_all.csv", write_gzip=write_gzip, keep_plain=keep_plain)
    _write_csv(relevant_all, out_dir / "stage1_relevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain)
    _write_csv(irrelevant_all, out_dir / "stage1_irrelevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain)

    summary = {
        "root_dir": str(root_dir),
        "out_dir": str(out_dir),
        "detector": str(args.detector),
        "conf_threshold": float(args.conf),
        "detector_warning": str(detector_warning or ""),
        "stores_scanned": int(len(store_dirs)),
        "total_images_discovered": int(total_discovered),
        "total_images_processed": int(total_processed),
        "relevant_images": int(len(relevant_all)),
        "irrelevant_images": int(len(irrelevant_all)),
        "relevant_percent": round((float(len(relevant_all)) / float(total_processed) * 100.0), 2) if total_processed > 0 else 0.0,
        "irrelevant_percent": round((float(len(irrelevant_all)) / float(total_processed) * 100.0), 2) if total_processed > 0 else 0.0,
        "store_summaries": store_summaries,
        "outputs": {
            "all": _preferred_output_path(out_dir / "stage1_relevance_all.csv", write_gzip=write_gzip, keep_plain=keep_plain),
            "relevant": _preferred_output_path(out_dir / "stage1_relevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain),
            "irrelevant": _preferred_output_path(out_dir / "stage1_irrelevant_images.csv", write_gzip=write_gzip, keep_plain=keep_plain),
            "summary": str((out_dir / "stage1_relevance_summary.json").resolve()),
        },
    }
    if not bool(args.skip_store_report):
        stage1_report = _build_store_date_report(stage1_df=all_df)
        merged_report, report_path, json_path = _upsert_store_report(
            report_df=stage1_report,
            report_path=args.store_report,
        )
        summary["outputs"]["store_report_csv"] = str(report_path)
        summary["outputs"]["store_report_json"] = str(json_path)
        summary["store_report_rows"] = int(len(merged_report))
    (out_dir / "stage1_relevance_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    args = parse_args()
    summary = run_stage1_scan(args)
    print("Stage 1 YOLO relevance scan completed.")
    print(
        "Totals: "
        f"discovered={summary.get('total_images_discovered', 0)}, "
        f"processed={summary.get('total_images_processed', 0)}, "
        f"relevant={summary.get('relevant_images', 0)}, "
        f"irrelevant={summary.get('irrelevant_images', 0)}, "
        f"relevant_pct={summary.get('relevant_percent', 0.0)}%"
    )
    print(f"Summary JSON: {summary.get('outputs', {}).get('summary', '')}")
    if summary.get("detector_warning"):
        print(f"WARNING: {summary['detector_warning']}")


if __name__ == "__main__":
    main()

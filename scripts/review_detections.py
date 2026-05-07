"""
Visual detection review tool — draws bounding boxes on camera frames.

Usage:
    # Review a single image
    python scripts/review_detections.py --image data/stores/BLRJAY/10-35-12_D03-1.jpg

    # Review latest N frames from all stores
    python scripts/review_detections.py --frames 20

    # Review latest N frames from one store
    python scripts/review_detections.py --frames 20 --store BLRJAY

    # Side-by-side ONNX vs YOLO comparison
    python scripts/review_detections.py --frames 10 --compare

Output saved to: data/review/  (opens folder when done)
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

OUTPUT_DIR = pathlib.Path("data/review")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Box colours by confidence band (BGR)
HIGH_CONF  = (0, 200, 0)    # green  > 0.60
MED_CONF   = (0, 180, 255)  # orange 0.30–0.60
LOW_CONF   = (0, 0, 220)    # red    < 0.30


def _conf_color(conf: float) -> tuple[int, int, int]:
    if conf >= 0.60:
        return HIGH_CONF
    if conf >= 0.30:
        return MED_CONF
    return LOW_CONF


def draw_boxes(bgr: np.ndarray, result, title: str = "") -> np.ndarray:
    out = bgr.copy()
    h, w = out.shape[:2]

    for box, conf in zip(result.person_boxes, result.person_confidences):
        x1 = int(box[0] * w)
        y1 = int(box[1] * h)
        x2 = int(box[2] * w)
        y2 = int(box[3] * h)
        color = _conf_color(conf)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        label = f"{conf:.2f}"
        cv2.putText(out, label, (x1 + 4, y1 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    count = result.person_count
    banner = f"{title}  persons={count}" if title else f"persons={count}"
    cv2.rectangle(out, (0, 0), (w, 28), (30, 30, 30), -1)
    cv2.putText(out, banner, (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return out


def process_single(image_path: pathlib.Path, onnx_det, yolo_det=None) -> pathlib.Path:
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        print(f"  SKIP  cannot read {image_path}")
        return None

    r_onnx = onnx_det.detect(image_path)

    if yolo_det:
        r_yolo = yolo_det.detect(image_path)
        ann_onnx = draw_boxes(bgr, r_onnx, "ONNX")
        ann_yolo  = draw_boxes(bgr, r_yolo,  "YOLO")
        # Resize both to same height before hstack
        if ann_onnx.shape[0] != ann_yolo.shape[0]:
            ann_yolo = cv2.resize(ann_yolo, (ann_onnx.shape[1], ann_onnx.shape[0]))
        combined = np.hstack([ann_onnx, ann_yolo])
        out_img = combined
    else:
        out_img = draw_boxes(bgr, r_onnx, "ONNX")

    stem = image_path.stem
    out_path = OUTPUT_DIR / f"{stem}_reviewed.jpg"
    cv2.imwrite(str(out_path), out_img)
    match = ""
    if yolo_det:
        r_yolo_count = r_yolo.person_count
        match = f"  ONNX={r_onnx.person_count} YOLO={r_yolo_count} {'OK' if r_onnx.person_count == r_yolo_count else 'DIFF'}"
    print(f"  {image_path.name:<40} persons={r_onnx.person_count}  conf_max={r_onnx.max_person_conf:.3f}{match}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual detection review")
    parser.add_argument("--image",   type=str, default="", help="Single image path to review")
    parser.add_argument("--frames",  type=int, default=20, help="Number of frames to review from data/stores")
    parser.add_argument("--store",   type=str, default="", help="Limit to specific store_id folder")
    parser.add_argument("--conf",    type=float, default=0.20, help="Confidence threshold")
    parser.add_argument("--compare", action="store_true", help="Side-by-side ONNX vs YOLO")
    args = parser.parse_args()

    from iris.iris_analysis import OnnxPersonDetector

    onnx_det = OnnxPersonDetector("data/models/yolov8s.onnx", conf_threshold=args.conf)
    yolo_det = None

    if args.compare:
        try:
            from iris.iris_analysis import YoloPersonDetector
            yolo_det = YoloPersonDetector("data/models/yolov8s.pt", conf_threshold=args.conf)
            print("Compare mode: ONNX vs YOLO side-by-side\n")
        except Exception as e:
            print(f"YOLO unavailable ({e}) — running ONNX only\n")

    if args.image:
        images = [pathlib.Path(args.image)]
    else:
        root = pathlib.Path("data/stores")
        if args.store:
            root = root / args.store
        images = sorted(
            (p for p in root.rglob("*.jpg") if "-" in p.stem),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[: args.frames]
        if not images:
            print(f"No frames found under {root}")
            sys.exit(1)

    print(f"Reviewing {len(images)} frame(s)  (conf={args.conf})\n")
    t0 = time.perf_counter()
    saved: list[pathlib.Path] = []
    for img in images:
        out = process_single(img, onnx_det, yolo_det)
        if out:
            saved.append(out)

    elapsed = time.perf_counter() - t0
    print(f"\nSaved {len(saved)} annotated image(s) -> {OUTPUT_DIR.resolve()}")
    print(f"Elapsed: {elapsed:.1f}s  ({1000*elapsed/max(len(saved),1):.0f} ms/image)")

    # Open output folder in Explorer
    if saved:
        subprocess.Popen(f'explorer "{OUTPUT_DIR.resolve()}"')


if __name__ == "__main__":
    main()

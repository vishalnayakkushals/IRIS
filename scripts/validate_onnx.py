"""
Validate OnnxPersonDetector accuracy vs YoloPersonDetector on real camera frames.

Usage:
    python scripts/validate_onnx.py [--frames N] [--conf FLOAT]

Compares detection counts frame-by-frame and reports exact match rate,
speedup, and any remaining differences with confidence values.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="ONNX vs YOLO accuracy validation")
    parser.add_argument("--frames", type=int, default=50, help="Number of frames to test")
    parser.add_argument("--conf", type=float, default=0.30, help="Confidence threshold")
    parser.add_argument("--store", type=str, default="", help="Limit to a specific store_id folder")
    args = parser.parse_args()

    from iris.iris_analysis import OnnxPersonDetector, YoloPersonDetector

    root = pathlib.Path("data/stores")
    if args.store:
        root = root / args.store

    frames = [
        p for p in root.rglob("*.jpg")
        if "-" in p.stem and "_D" in p.stem.upper()
    ][: args.frames]

    if not frames:
        print(f"No camera frames found under {root}")
        sys.exit(1)

    print(f"Validating {len(frames)} frames  (conf={args.conf})\n")

    onnx = OnnxPersonDetector("data/models/yolov8s.onnx", conf_threshold=args.conf)
    yolo = YoloPersonDetector("data/models/yolov8s.pt",   conf_threshold=args.conf)

    exact = onnx_more = yolo_more = 0
    t_onnx = t_yolo = 0.0
    diffs: list[tuple] = []

    for img in frames:
        t0 = time.perf_counter()
        ro = onnx.detect(img)
        t_onnx += time.perf_counter() - t0

        t0 = time.perf_counter()
        ry = yolo.detect(img)
        t_yolo += time.perf_counter() - t0

        if ro.person_count == ry.person_count:
            exact += 1
        elif ro.person_count > ry.person_count:
            onnx_more += 1
            diffs.append((img.name, ro.person_count, ry.person_count,
                          ro.max_person_conf, ry.max_person_conf))
        else:
            yolo_more += 1
            diffs.append((img.name, ro.person_count, ry.person_count,
                          ro.max_person_conf, ry.max_person_conf))

    n = len(frames)
    print(f"Exact match       : {exact}/{n} ({100 * exact / n:.0f}%)")
    print(f"ONNX detected more: {onnx_more}  |  YOLO detected more: {yolo_more}")
    print(f"Avg ONNX          : {1000 * t_onnx / n:.0f} ms/image")
    print(f"Avg YOLO          : {1000 * t_yolo / n:.0f} ms/image")
    print(f"Speedup           : {t_yolo / t_onnx:.1f}x faster")

    if diffs:
        print(f"\nRemaining differences ({len(diffs)} frames):")
        print(f"  {'Image':<38} ONNX  YOLO  ONNX_conf  YOLO_conf  Note")
        for name, op, yp, oc, yc in diffs:
            gap = abs(oc - yc)
            note = "borderline" if gap < 0.15 else "preprocessing gap"
            print(f"  {name:<38} {op:>4}  {yp:>4}  {oc:.3f}     {yc:.3f}     {note}")
    else:
        print("\nPerfect match — no differences.")


if __name__ == "__main__":
    main()

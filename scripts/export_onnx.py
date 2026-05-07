"""
One-time helper: export yolov8s.pt → yolov8s.onnx

Run on a dev machine that has ultralytics + torch installed (NOT on the server):
    pip install ultralytics
    python scripts/export_onnx.py

The resulting data/models/yolov8s.onnx is committed to the repo and used
by OnnxPersonDetector on the server (no torch or ultralytics required there).
"""
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError:
        print("ERROR: ultralytics is not installed. Run: pip install ultralytics")
        sys.exit(1)

    root = pathlib.Path(__file__).resolve().parents[1]
    pt_path = root / "data" / "models" / "yolov8s.pt"
    onnx_path = root / "data" / "models" / "yolov8s.onnx"

    if not pt_path.exists():
        print(f"ERROR: {pt_path} not found. Download it first.")
        sys.exit(1)

    print(f"Exporting {pt_path.name} ({pt_path.stat().st_size / 1e6:.1f} MB)...")
    model = YOLO(str(pt_path))
    model.export(format="onnx", imgsz=640, simplify=True, opset=11)

    if onnx_path.exists():
        print(f"Done: {onnx_path} ({onnx_path.stat().st_size / 1e6:.1f} MB)")
    else:
        print("ERROR: export completed but .onnx file not found at expected path.")
        sys.exit(1)


if __name__ == "__main__":
    main()

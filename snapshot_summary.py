from __future__ import annotations

from pathlib import Path
import re

from PIL import Image


FILE_PATTERN = re.compile(
    r"(?P<time>\d{2}-\d{2}-\d{2})_(?P<camera>D\d{2})-(?P<frame>\d+)\.jpg$"
)


def is_readable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def main() -> None:
    root = Path(__file__).resolve().parent
    files = sorted([f for f in root.glob("*.jpg") if FILE_PATTERN.match(f.name)])
    if not files:
        print("No matching snapshot files found.")
        return

    zero_byte = 0
    unreadable = 0
    per_camera: dict[str, int] = {}
    for file in files:
        if file.stat().st_size == 0:
            zero_byte += 1
        if not is_readable(file):
            unreadable += 1
        camera = FILE_PATTERN.match(file.name).group("camera")  # type: ignore[union-attr]
        per_camera[camera] = per_camera.get(camera, 0) + 1

    print(f"Total snapshots: {len(files)}")
    print(f"Cameras: {len(per_camera)}")
    print(f"Zero-byte files: {zero_byte}")
    print(f"Unreadable files: {unreadable}")
    print("Per-camera counts:")
    for camera in sorted(per_camera):
        print(f"  {camera}: {per_camera[camera]}")


if __name__ == "__main__":
    main()

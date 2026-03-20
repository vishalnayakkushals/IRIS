from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.secret_store import save_google_api_key


def parse_args() -> argparse.Namespace:
    app_dir = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description="Encrypt and store Google API key for IRIS sync jobs")
    p.add_argument(
        "--key",
        default="",
        help="Google API key. If omitted, reads GOOGLE_API_KEY from environment.",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=app_dir / "data" / "stores",
        help="Data root used to infer secrets directory location.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    key = str(args.key or os.getenv("GOOGLE_API_KEY", "")).strip()
    if not key:
        raise SystemExit("ERROR: Provide --key or set GOOGLE_API_KEY")
    secret_path = save_google_api_key(key, data_dir=args.data_root.parent)
    print(f"Saved encrypted key: {secret_path}")


if __name__ == "__main__":
    main()

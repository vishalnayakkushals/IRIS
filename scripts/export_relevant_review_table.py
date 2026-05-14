from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from iris.relevant_review_table import export_relevant_review_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a local CSV review table for YOLO-relevant images")
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--date", default="", help="Optional date filter. Accepts display date like 10-05-2026 or folder date like 2026-05-10")
    parser.add_argument("--db", type=Path, default=Path("data/store_registry.db"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/exports/current/onfly"))
    parser.add_argument("--limit", type=int, default=0, help="Optional row cap for quick review samples")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = export_relevant_review_table(
        db_path=args.db,
        out_dir=args.out_dir,
        store_id=str(args.store_id).strip(),
        date_filter=str(args.date).strip(),
        limit=max(0, int(args.limit)),
    )
    print(f"rows={result['rows']}")
    print(f"output={result['output_path']}")
    print(f"generated_at={result['generated_at']}")


if __name__ == "__main__":
    main()

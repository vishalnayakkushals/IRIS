from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def _normalize_folder_from_relative(relative_path: str) -> str:
    txt = str(relative_path or "").strip().replace("\\", "/")
    if not txt:
        return ""
    first = txt.split("/", 1)[0].strip()
    if len(first) == 10 and first[4] == "-" and first[7] == "-":
        try:
            yyyy, mm, dd = first.split("-")
            return f"{dd}-{mm}-{yyyy}"
        except Exception:
            return first
    return first


def run(store_dir: Path, run_id: str = "") -> None:
    if run_id:
        image_csv = store_dir / f"onfly_image_results_{run_id}.csv"
        walk_csv = store_dir / f"onfly_walkin_sessions_{run_id}.csv"
    else:
        image_csv = store_dir / "onfly_image_results.csv"
        walk_csv = store_dir / "onfly_walkin_sessions.csv"

    if not image_csv.exists():
        raise FileNotFoundError(f"Missing file: {image_csv}")
    if not walk_csv.exists():
        raise FileNotFoundError(f"Missing file: {walk_csv}")

    image_df = pd.read_csv(image_csv)
    if "relative_path" in image_df.columns:
        image_df["folder_name"] = image_df["relative_path"].map(_normalize_folder_from_relative)
    elif "Date" in image_df.columns:
        image_df["folder_name"] = image_df["Date"].astype(str)
    else:
        image_df["folder_name"] = ""

    if "date_source" in image_df.columns:
        image_df = image_df.drop(columns=["date_source"])

    folder_series = image_df["folder_name"] if "folder_name" in image_df.columns else pd.Series([""] * len(image_df))
    image_name_series = image_df["image_name"] if "image_name" in image_df.columns else pd.Series([""] * len(image_df))
    lookup = pd.DataFrame({"image_id": image_df["image_id"], "folder_name": folder_series, "image_name": image_name_series}).drop_duplicates(
        subset=["image_id"], keep="last"
    )

    walk_df = pd.read_csv(walk_csv)
    walk_df = walk_df.merge(lookup, on="image_id", how="left")
    if "folder_name_x" in walk_df.columns:
        walk_df["folder_name"] = walk_df["folder_name_x"].fillna(walk_df.get("folder_name_y"))
        walk_df = walk_df.drop(columns=[c for c in ["folder_name_x", "folder_name_y"] if c in walk_df.columns])
    if "image_name_x" in walk_df.columns:
        walk_df["image_name"] = walk_df["image_name_x"].fillna(walk_df.get("image_name_y"))
        walk_df = walk_df.drop(columns=[c for c in ["image_name_x", "image_name_y"] if c in walk_df.columns])
    if "folder_name" in walk_df.columns:
        walk_df["folder_name"] = walk_df["folder_name"].fillna("").astype(str)
        if "date" in walk_df.columns:
            walk_df["date"] = walk_df["folder_name"]

    preferred_image_cols = ["store_id", "image_id", "relative_path", "folder_name", "Date", "image_name"]
    image_df = image_df[[c for c in preferred_image_cols if c in image_df.columns] + [c for c in image_df.columns if c not in preferred_image_cols]]
    preferred_walk_cols = ["id", "store_id", "run_id", "image_id", "folder_name", "image_name", "date"]
    walk_df = walk_df[[c for c in preferred_walk_cols if c in walk_df.columns] + [c for c in walk_df.columns if c not in preferred_walk_cols]]

    image_out = image_csv
    walk_out = walk_csv
    try:
        image_df.to_csv(image_csv, index=False)
    except PermissionError:
        image_out = image_csv.with_name("onfly_image_results_fixed.csv")
        image_df.to_csv(image_out, index=False)
    try:
        walk_df.to_csv(walk_csv, index=False)
    except PermissionError:
        walk_out = walk_csv.with_name("onfly_walkin_sessions_fixed.csv")
        walk_df.to_csv(walk_out, index=False)

    print("Updated exports:")
    print(f"- {image_out}")
    print(f"- {walk_out}")
    print(f"Rows image={len(image_df)} walkin={len(walk_df)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch onfly export CSVs with Folder/Image name columns and hide date_source.")
    parser.add_argument("--store-dir", required=True, help="Path to data/exports/current/onfly/<STORE_ID>")
    parser.add_argument("--run-id", default="", help="Optional run_id to patch run-scoped files (without file prefix)")
    args = parser.parse_args()
    run(Path(args.store_dir).expanduser().resolve(), run_id=str(args.run_id or "").strip())


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from iris_analysis import AnalysisOutput, analyze_root, export_analysis, load_exports
from store_registry import (
    add_employee_image,
    get_store_by_email,
    init_db,
    list_employees,
    list_stores,
    sync_store_from_drive,
    upsert_store,
)


def _ensure_session_state() -> None:
    if "analysis_output" not in st.session_state:
        st.session_state["analysis_output"] = None


def _run_analysis(
    root_dir: Path, out_dir: Path, conf_threshold: float, detector_type: str, time_bucket_minutes: int
) -> AnalysisOutput:
    output = analyze_root(
        root_dir=root_dir,
        conf_threshold=conf_threshold,
        detector_type=detector_type,
        time_bucket_minutes=time_bucket_minutes,
    )
    export_analysis(output, out_dir=out_dir)
    return output


def _filter_output_to_store(output: AnalysisOutput, store_id: str) -> AnalysisOutput:
    if store_id not in output.stores:
        return AnalysisOutput(
            stores={},
            all_stores_summary=output.all_stores_summary.iloc[0:0].copy(),
            detector_warning=output.detector_warning,
            used_root_fallback_store=output.used_root_fallback_store,
        )
    return AnalysisOutput(
        stores={store_id: output.stores[store_id]},
        all_stores_summary=output.all_stores_summary[
            output.all_stores_summary["store_id"] == store_id
        ].copy(),
        detector_warning=output.detector_warning,
        used_root_fallback_store=output.used_root_fallback_store,
    )


def _load_or_run_default(root_dir: Path, out_dir: Path) -> AnalysisOutput:
    output = load_exports(out_dir=out_dir)
    if not output.all_stores_summary.empty:
        return output
    output = _run_analysis(
        root_dir=root_dir,
        out_dir=out_dir,
        conf_threshold=0.25,
        detector_type="yolo",
        time_bucket_minutes=1,
    )
    return output


def _render_overview(output: AnalysisOutput) -> None:
    st.subheader("All Stores Summary")
    if output.all_stores_summary.empty:
        st.warning("No stores found for analysis.")
        return

    df = output.all_stores_summary.copy()
    st.dataframe(df, use_container_width=True)

    leaderboard = df.sort_values(by="total_people", ascending=False)
    chart = px.bar(
        leaderboard,
        x="store_id",
        y="total_people",
        color="store_id",
        labels={"store_id": "Store", "total_people": "Total Detected People"},
        title="Store Leaderboard by Customer Count",
    )
    chart.update_layout(showlegend=False)
    st.plotly_chart(chart, use_container_width=True)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Stores", f"{len(df)}")
    metric_cols[1].metric("Total Images", f"{int(df['total_images'].sum())}")
    metric_cols[2].metric("Relevant Images", f"{int(df['relevant_images'].sum())}")
    metric_cols[3].metric("Detected People", f"{int(df['total_people'].sum())}")


def _render_store_detail(output: AnalysisOutput, time_bucket_minutes: int) -> None:
    st.subheader("Store Drill-down")
    store_ids = sorted(output.stores.keys())
    if not store_ids:
        st.info("No per-store analysis available.")
        return

    selected_store = st.selectbox("Store", options=store_ids)
    store_result = output.stores[selected_store]
    image_df = store_result.image_insights.copy()
    hotspot_df = store_result.camera_hotspots.copy()

    row = output.all_stores_summary[
        output.all_stores_summary["store_id"] == selected_store
    ].iloc[0]
    cols = st.columns(5)
    cols[0].metric("Total Images", int(row["total_images"]))
    cols[1].metric("Valid Images", int(row["valid_images"]))
    cols[2].metric("Relevant Images", int(row["relevant_images"]))
    cols[3].metric("Total People", int(row["total_people"]))
    cols[4].metric("Top Hotspot Camera", row["top_camera_hotspot"] or "-")

    if not hotspot_df.empty:
        st.markdown("**Camera Hotspots**")
        hotspot_chart = px.bar(
            hotspot_df.sort_values(by="hotspot_rank"),
            x="camera_id",
            y="avg_people_per_relevant_image",
            color="total_people",
            labels={
                "camera_id": "Camera",
                "avg_people_per_relevant_image": "Avg People / Relevant Image",
                "total_people": "Total People",
            },
        )
        st.plotly_chart(hotspot_chart, use_container_width=True)
        st.dataframe(hotspot_df, use_container_width=True)

    relevant_df = image_df[image_df["relevant"]].copy()
    if not relevant_df.empty:
        relevant_df["bucket"] = relevant_df["timestamp"].dt.floor(f"{time_bucket_minutes}min")
        trend_df = (
            relevant_df.groupby(["bucket", "camera_id"], as_index=False)
            .agg(total_people=("person_count", "sum"))
            .sort_values(by="bucket")
        )
        st.markdown("**Customer Trend by Time**")
        trend_chart = px.line(
            trend_df,
            x="bucket",
            y="total_people",
            color="camera_id",
            markers=True,
            labels={"bucket": "Time Bucket", "total_people": "Detected People"},
        )
        st.plotly_chart(trend_chart, use_container_width=True)

    st.markdown("**Data Quality Issues**")
    quality_df = image_df[
        (image_df["reject_reason"].fillna("") != "")
        | (image_df["detection_error"].fillna("") != "")
        | (~image_df["is_valid"])
    ].copy()
    if quality_df.empty:
        st.success("No quality issues detected.")
    else:
        st.dataframe(
            quality_df[
                [
                    "filename",
                    "camera_id",
                    "timestamp",
                    "is_valid",
                    "reject_reason",
                    "detection_error",
                ]
            ],
            use_container_width=True,
        )

    st.markdown("**Relevant Image Gallery**")
    camera_options = sorted([camera for camera in image_df["camera_id"].dropna().unique() if camera])
    selected_cameras = st.multiselect(
        "Cameras",
        options=camera_options,
        default=camera_options,
        key=f"camera_filter_{selected_store}",
    )
    max_images = st.slider(
        "Max gallery images",
        min_value=6,
        max_value=60,
        value=24,
        step=6,
        key=f"gallery_limit_{selected_store}",
    )
    gallery_df = relevant_df[relevant_df["camera_id"].isin(selected_cameras)].head(max_images)
    if gallery_df.empty:
        st.info("No relevant images for the selected camera filter.")
        return

    cols = st.columns(3)
    for idx, row_image in gallery_df.iterrows():
        col = cols[idx % 3]
        caption = (
            f"{row_image['timestamp'].strftime('%H:%M:%S')} "
            f"{row_image['camera_id']} "
            f"people={row_image['person_count']}"
        )
        with col:
            st.image(row_image["path"], caption=caption, use_container_width=True)


def _render_quality_summary(output: AnalysisOutput) -> None:
    st.subheader("Quality Summary")
    if not output.stores:
        st.info("No store analysis loaded.")
        return

    quality_rows: list[dict[str, object]] = []
    for store_id, result in output.stores.items():
        image_df = result.image_insights
        total = len(image_df)
        invalid = int((~image_df["is_valid"]).sum()) if total else 0
        bad_filename = int((image_df["reject_reason"] == "bad_filename").sum()) if total else 0
        detection_errors = (
            int((image_df["detection_error"].fillna("") != "").sum()) if total else 0
        )
        quality_rows.append(
            {
                "store_id": store_id,
                "total_images": total,
                "invalid_images": invalid,
                "bad_filename": bad_filename,
                "detection_errors": detection_errors,
            }
        )

    quality_df = pd.DataFrame(quality_rows).sort_values(by="store_id")
    st.dataframe(quality_df, use_container_width=True)


def _render_store_admin(
    db_path: Path, data_root: Path, employee_assets_root: Path, auto_sync_after_save: bool
) -> None:
    st.subheader("Store Registry")
    stores = list_stores(db_path)
    if stores:
        store_df = pd.DataFrame([store.__dict__ for store in stores])
        st.dataframe(store_df, use_container_width=True)
    else:
        st.info("No stores registered yet.")

    with st.form("store_create_update_form", clear_on_submit=False):
        st.markdown("**Add / Update Store Mapping**")
        store_id = st.text_input("Store ID (unique)", value="")
        store_name = st.text_input("Store Name", value="")
        email = st.text_input("Store Email", value="")
        drive_folder_url = st.text_input("Google Drive Folder URL", value="")
        submitted = st.form_submit_button("Save Store")

    if submitted:
        if not store_id.strip() or not store_name.strip() or not email.strip():
            st.error("Store ID, Store Name, and Store Email are required.")
        else:
            try:
                upsert_store(
                    db_path=db_path,
                    store_id=store_id.strip(),
                    store_name=store_name.strip(),
                    email=email.strip(),
                    drive_folder_url=drive_folder_url.strip(),
                )
                (data_root / store_id.strip()).mkdir(parents=True, exist_ok=True)
                st.success(f"Saved store mapping for '{store_id.strip()}'.")
                if auto_sync_after_save and drive_folder_url.strip():
                    matched = [s for s in list_stores(db_path) if s.store_id == store_id.strip()]
                    if matched:
                        ok, message = sync_store_from_drive(matched[0], data_root=data_root)
                        if ok:
                            st.info(message)
                        else:
                            st.warning(message)
            except Exception as exc:
                st.error(str(exc))

    st.markdown("**Sync Store Snapshots From Drive**")
    stores = list_stores(db_path)
    if stores:
        sync_store_id = st.selectbox(
            "Select store to sync",
            options=[s.store_id for s in stores],
            key="sync_store_selector",
        )
        if st.button("Sync Selected Store", key="sync_selected_store_button"):
            store_record = [s for s in stores if s.store_id == sync_store_id][0]
            ok, message = sync_store_from_drive(store_record, data_root=data_root)
            if ok:
                st.success(message)
            else:
                st.warning(message)
    else:
        st.caption("Create a store first to sync from Google Drive.")

    st.subheader("Employee Image Upload")
    stores = list_stores(db_path)
    if not stores:
        st.caption("Create a store before uploading employees.")
        return

    upload_store = st.selectbox(
        "Employee Store",
        options=[s.store_id for s in stores],
        key="employee_store_selector",
    )
    employee_name = st.text_input("Employee Name", value="", key="employee_name_input")
    upload_files = st.file_uploader(
        "Employee Image Files",
        type=["jpg", "jpeg", "png", "webp", "bmp"],
        accept_multiple_files=True,
        key="employee_uploader",
    )
    if st.button("Upload Employee Images", key="upload_employee_button"):
        if not employee_name.strip():
            st.error("Employee name is required for upload.")
        elif not upload_files:
            st.error("Select at least one image.")
        else:
            uploaded = 0
            for file in upload_files:
                add_employee_image(
                    db_path=db_path,
                    employee_assets_root=employee_assets_root,
                    store_id=upload_store,
                    employee_name=employee_name.strip(),
                    original_filename=file.name,
                    content=file.getvalue(),
                )
                uploaded += 1
            st.success(f"Uploaded {uploaded} image(s) for {employee_name.strip()} in {upload_store}.")

    employees = pd.DataFrame(list_employees(db_path=db_path, store_id=upload_store))
    if employees.empty:
        st.caption("No employee images uploaded for this store yet.")
    else:
        st.dataframe(employees, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="IRIS Store Analysis Dashboard", layout="wide")
    st.title("IRIS Store Analysis Dashboard")
    _ensure_session_state()

    app_dir = Path(__file__).resolve().parent
    data_dir = app_dir / "data"
    default_stores_root = data_dir / "stores"
    default_exports_dir = data_dir / "exports" / "current"
    db_path = app_dir / "data" / "store_registry.db"
    data_root = default_stores_root
    employee_assets_root = data_dir / "employee_assets"
    data_root.mkdir(parents=True, exist_ok=True)
    default_exports_dir.mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    with st.sidebar:
        st.header("Analysis Controls")
        root_str = st.text_input("Root Directory", value=str(data_root))
        out_str = st.text_input("Export Directory", value=str(default_exports_dir))
        access_email = st.text_input("Access Email (optional)", value="")
        conf_threshold = st.slider(
            "Detection Confidence",
            min_value=0.05,
            max_value=0.9,
            value=0.25,
            step=0.05,
        )
        time_bucket_minutes = st.selectbox("Time Bucket (minutes)", options=[1, 5, 15], index=0)
        detector_type = st.selectbox("Detector", options=["yolo", "mock"], index=0)
        auto_sync_linked_drives = st.checkbox("Auto-sync linked drives before analysis", value=True)
        auto_sync_on_save = st.checkbox("Auto-sync when saving store mapping", value=False)
        rerun_clicked = st.button("Regenerate Analysis + CSV", type="primary")

    root_dir = Path(root_str).expanduser().resolve()
    out_dir = Path(out_str).expanduser().resolve()

    if rerun_clicked:
        with st.spinner("Running analysis..."):
            if auto_sync_linked_drives:
                sync_messages: list[str] = []
                for store in list_stores(db_path):
                    ok, message = sync_store_from_drive(store, data_root=root_dir)
                    sync_messages.append(("OK: " if ok else "WARN: ") + message)
                if sync_messages:
                    st.caption("Drive sync status:")
                    for message in sync_messages:
                        st.write(f"- {message}")
            output = _run_analysis(
                root_dir=root_dir,
                out_dir=out_dir,
                conf_threshold=conf_threshold,
                detector_type=detector_type,
                time_bucket_minutes=time_bucket_minutes,
            )
            st.session_state["analysis_output"] = output
            st.success("Analysis completed and CSV exports updated.")

    output: AnalysisOutput | None = st.session_state.get("analysis_output")
    if output is None:
        output = _load_or_run_default(root_dir=root_dir, out_dir=out_dir)
        st.session_state["analysis_output"] = output

    view_output = output
    if access_email.strip():
        mapped = get_store_by_email(db_path=db_path, email=access_email.strip())
        if mapped is None:
            st.error(f"No store mapping found for email '{access_email.strip()}'.")
            view_output = AnalysisOutput(
                stores={},
                all_stores_summary=output.all_stores_summary.iloc[0:0].copy(),
                detector_warning=output.detector_warning,
                used_root_fallback_store=output.used_root_fallback_store,
            )
        else:
            st.info(f"Access mapped to store `{mapped.store_id}` ({mapped.store_name}).")
            view_output = _filter_output_to_store(output, mapped.store_id)

    if output.detector_warning:
        st.warning(output.detector_warning)
    if output.used_root_fallback_store:
        st.info(
            "No store subfolders found in root; root folder was treated as a single store."
        )

    tabs = st.tabs(["Overview", "Store Detail", "Quality", "Store Admin"])
    with tabs[0]:
        _render_overview(view_output)
    with tabs[1]:
        _render_store_detail(view_output, time_bucket_minutes=time_bucket_minutes)
    with tabs[2]:
        _render_quality_summary(view_output)
    with tabs[3]:
        _render_store_admin(
            db_path=db_path,
            data_root=root_dir,
            employee_assets_root=employee_assets_root,
            auto_sync_after_save=auto_sync_on_save,
        )

    st.caption(f"Exports folder: `{out_dir}`")


if __name__ == "__main__":
    main()

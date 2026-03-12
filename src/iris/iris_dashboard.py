from __future__ import annotations

import html
from pathlib import Path
import re
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

from iris.iris_analysis import AnalysisOutput, analyze_root, export_analysis, load_exports
from iris.store_registry import (
    add_employee_image,
    bulk_upsert_store_access_rows,
    camera_config_map,
    create_user_session,
    create_license,
    delete_role,
    create_role,
    create_user,
    delete_employee,
    delete_store,
    ensure_default_admins,
    ensure_store_login,
    get_app_settings,
    get_store_master_by_id,
    get_user_by_session_token,
    get_store_by_email,
    init_db,
    list_alert_routes,
    list_user_activity,
    log_user_activity,
    list_camera_configs,
    list_employees,
    list_license_audit,
    list_licenses,
    list_permission_codes,
    list_roles,
    list_store_master,
    list_stores,
    list_users,
    revoke_user_session,
    route_alert,
    authenticate_user,
    set_employee_active,
    set_role_permissions,
    set_user_password,
    sync_store_from_drive,
    transition_license,
    upsert_alert_route,
    upsert_camera_config,
    upsert_manager_access,
    upsert_store,
    upsert_app_settings,
    upsert_store_master_rows,
    upsert_user_account,
    replace_user_store_access,
    list_user_store_access,
    user_store_scope,
    user_permissions,
    user_role_names,
)

NAV_TREE: dict[str, dict[str, list[str]]] = {
    "Reports": {
        "Business Health": ["Overview", "Store Detail", "Quality", "QA Timeline"],
    },
    "Access": {
        "Administration": [
            "Organisation",
            "Users",
            "Password Manager",
            "Role Permissions",
            "Store Access Mapping",
            "Bulk Access Upload",
            "Setup Help",
            "Licenses",
            "Alert Routes",
            "Activity Logs",
        ],
    },
    "Operations": {
        "Store Setup": ["Store Mapping", "Camera Zones", "Store Master"],
        "Workforce": ["Employee Management"],
    },
}

DEFAULT_ORG_SETTINGS: dict[str, str] = {
    "app_name": "IRIS",
    "font_family": "Segoe UI",
    "background_color": "#f4f6f8",
    "surface_color": "#ffffff",
    "nav_color": "#1f3044",
    "accent_color": "#2a7fd9",
    "default_user_password": "ChangeMe123!",
}

LEGACY_PAGE_ALIAS = {
    "Store Admin": "Store Mapping",
    "Auth/RBAC": "Role Permissions",
}

PAGE_TO_PATH: dict[str, tuple[str, str]] = {
    page: (module, section)
    for module, sections in NAV_TREE.items()
    for section, pages in sections.items()
    for page in pages
}


def _is_yolo_available() -> bool:
    try:
        import ultralytics  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def _ensure_session_state() -> None:
    if "analysis_output" not in st.session_state:
        st.session_state["analysis_output"] = None
    if "login_email" not in st.session_state:
        st.session_state["login_email"] = ""
    if "login_full_name" not in st.session_state:
        st.session_state["login_full_name"] = ""
    if "is_authenticated" not in st.session_state:
        st.session_state["is_authenticated"] = False
    if "session_token" not in st.session_state:
        st.session_state["session_token"] = ""
    if "ctrl_scope_email" not in st.session_state:
        st.session_state["ctrl_scope_email"] = ""


def _query_value(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value)


def _resolve_menu_from_query() -> tuple[str, str, str]:
    module_names = list(NAV_TREE.keys())
    raw_page_param = _query_value("page", "")
    page_param = LEGACY_PAGE_ALIAS.get(raw_page_param, raw_page_param)
    if page_param in PAGE_TO_PATH:
        module, section = PAGE_TO_PATH[page_param]
        return module, section, page_param

    module = _query_value("module", module_names[0])
    if module not in NAV_TREE:
        module = module_names[0]

    sections = NAV_TREE[module]
    section_names = list(sections.keys())
    section = _query_value("section", section_names[0])
    if section not in sections:
        section = section_names[0]

    return module, section, sections[section][0]


def _safe_hex_color(value: str, fallback: str) -> str:
    color = str(value or "").strip()
    if re.match(r"^#[0-9a-fA-F]{6}$", color):
        return color
    return fallback


def _font_stack(font_label: str) -> str:
    options = {
        "Segoe UI": '"Segoe UI","Helvetica Neue",Arial,sans-serif',
        "Calibri": 'Calibri,"Segoe UI",Arial,sans-serif',
        "Arial": 'Arial,"Helvetica Neue",sans-serif',
    }
    return options.get(font_label, options["Segoe UI"])


def _effective_org_settings(raw: dict[str, str]) -> dict[str, str]:
    merged = dict(DEFAULT_ORG_SETTINGS)
    merged.update({str(k): str(v) for k, v in raw.items()})
    font_label = merged.get("font_family", "Segoe UI")
    if font_label not in {"Segoe UI", "Calibri", "Arial"}:
        font_label = "Segoe UI"
    merged["font_family"] = font_label
    merged["background_color"] = _safe_hex_color(merged.get("background_color", ""), DEFAULT_ORG_SETTINGS["background_color"])
    merged["surface_color"] = _safe_hex_color(merged.get("surface_color", ""), DEFAULT_ORG_SETTINGS["surface_color"])
    merged["nav_color"] = _safe_hex_color(merged.get("nav_color", ""), DEFAULT_ORG_SETTINGS["nav_color"])
    merged["accent_color"] = _safe_hex_color(merged.get("accent_color", ""), DEFAULT_ORG_SETTINGS["accent_color"])
    merged["app_name"] = (merged.get("app_name", "") or "IRIS").strip()[:60]
    if not merged["app_name"]:
        merged["app_name"] = "IRIS"
    merged["default_user_password"] = (merged.get("default_user_password", "") or "ChangeMe123!").strip()[:128]
    if not merged["default_user_password"]:
        merged["default_user_password"] = "ChangeMe123!"
    return merged


def _inject_clean_ui_css(org_settings: dict[str, str]) -> None:
    font_stack = _font_stack(org_settings.get("font_family", "Segoe UI"))
    bg = org_settings.get("background_color", DEFAULT_ORG_SETTINGS["background_color"])
    surface = org_settings.get("surface_color", DEFAULT_ORG_SETTINGS["surface_color"])
    nav = org_settings.get("nav_color", DEFAULT_ORG_SETTINGS["nav_color"])
    accent = org_settings.get("accent_color", DEFAULT_ORG_SETTINGS["accent_color"])
    st.markdown(
        f"""
<style>
body, .stApp {{
    background: {bg};
    font-family: {font_stack};
}}
.block-container {{padding-top: 0.2rem; padding-bottom: 0.8rem;}}
div[data-testid="stToolbar"] {{visibility: hidden; height: 0; position: fixed;}}
header[data-testid="stHeader"] {{height: 0.1rem;}}
.iris-header {{
    background: {surface};
    border: 1px solid #d7dee8;
    border-radius: 8px;
    padding: 0.4rem 0.65rem;
    margin: 0 0 0.3rem 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}}
.iris-brand-fallback {{
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: {nav};
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.86rem;
    font-weight: 700;
}}
.iris-app-name {{
    font-size: 1.12rem;
    font-weight: 800;
    letter-spacing: 0.02rem;
    color: #1d2d3f;
}}
.iris-nav .iris-menu {{background: {nav};}}
.iris-nav .iris-module.active .iris-module-label, .iris-nav .iris-module:hover .iris-module-label {{background: {accent};}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _render_header_bar(
    app_name: str,
    logo_path: str,
    active_email: str,
    active_full_name: str,
    active_roles: list[str],
    db_path: Path,
    auth_token: str,
) -> str:
    header_cols = st.columns([4, 2], gap="small")
    with header_cols[0]:
        inner = st.columns([1, 8], gap="small")
        logo_file = Path(logo_path).expanduser() if logo_path.strip() else None
        if logo_file and logo_file.exists():
            inner[0].image(str(logo_file), width=40)
        else:
            inner[0].markdown('<div class="iris-brand-fallback">IR</div>', unsafe_allow_html=True)
        inner[1].markdown(
            f'<div class="iris-app-name">{html.escape(app_name)}</div>',
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        with st.expander("👤 Profile", expanded=False):
            display_name = active_full_name.strip() or active_email.strip() or "User"
            st.caption(f"Name: {display_name}")
            st.caption(f"Email: {active_email}")
            st.caption(f"Roles: {', '.join(active_roles) if active_roles else '-'}")
            st.text_input(
                "View As Store Email (optional)",
                key="ctrl_scope_email",
                placeholder="store-user@company.com",
                help="Optional filter: only show mapped store data for this store email.",
            )
            if st.button("Logout", key="logout_button_profile"):
                revoke_user_session(db_path=db_path, token=auth_token)
                st.session_state["is_authenticated"] = False
                st.session_state["login_email"] = ""
                st.session_state["login_full_name"] = ""
                st.session_state["session_token"] = ""
                st.query_params["auth"] = ""
                st.rerun()
    return str(st.session_state.get("ctrl_scope_email", "")).strip()


def _render_hover_nav(
    current_module: str,
    current_section: str,
    current_page: str,
    auth_token: str,
) -> None:
    extra_bits: list[str] = []
    if auth_token:
        extra_bits.append(f"auth={quote(auth_token)}")
    extra_query = ""
    if extra_bits:
        extra_query = "&" + "&".join(extra_bits)
    module_nodes: list[str] = []
    for module, sections in NAV_TREE.items():
        section_nodes: list[str] = []
        for section, pages in sections.items():
            page_nodes: list[str] = []
            for page in pages:
                href = (
                    f"?module={quote(module)}&section={quote(section)}"
                    f"&page={quote(page)}{extra_query}"
                )
                active_class = " active" if page == current_page else ""
                page_nodes.append(
                    f'<li><a class="iris-page{active_class}" href="{href}" target="_self">{html.escape(page)}</a></li>'
                )
            section_active_class = " active" if section == current_section and module == current_module else ""
            section_nodes.append(
                f'<div class="iris-section{section_active_class}">'
                f'<div class="iris-section-title">{html.escape(section)}</div>'
                f'<ul>{"".join(page_nodes)}</ul>'
                f"</div>"
            )

        module_active_class = " active" if module == current_module else ""
        module_nodes.append(
            f'<li class="iris-module{module_active_class}">'
            f'<span class="iris-module-label">{html.escape(module)}</span>'
            f'<div class="iris-dropdown">{"".join(section_nodes)}</div>'
            f"</li>"
        )

    st.markdown(
        """
<style>
.iris-nav {margin: 0 0 0.2rem 0;}
.iris-nav ul {list-style: none; margin: 0; padding: 0;}
.iris-nav .iris-menu {display: flex; gap: 0.25rem; border-radius: 8px; padding: 0.25rem 0.35rem;}
.iris-nav .iris-module {position: relative;}
.iris-nav .iris-module .iris-module-label {display: block; padding: 0.44rem 0.72rem; color: #f4f7fb; border-radius: 7px; font-weight: 600; font-size: 0.9rem; cursor: default; user-select: none;}
.iris-nav .iris-dropdown {display: none; position: absolute; top: 2rem; left: 0; min-width: 520px; background: #f7fbff; border: 1px solid #d8e3f0; border-radius: 10px; box-shadow: 0 12px 24px rgba(9, 30, 66, 0.18); padding: 0.6rem; z-index: 999;}
.iris-nav .iris-module:hover .iris-dropdown {display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.6rem;}
.iris-nav .iris-section {border: 1px solid #e3edf8; border-radius: 8px; background: #ffffff; padding: 0.45rem 0.55rem;}
.iris-nav .iris-section.active {border-color: #70a9eb; background: #eef6ff;}
.iris-nav .iris-section-title {font-size: 0.85rem; color: #35506b; font-weight: 700; margin-bottom: 0.35rem;}
.iris-nav .iris-section ul {display: grid; gap: 0.2rem;}
.iris-nav .iris-page {display: block; padding: 0.35rem 0.45rem; border-radius: 6px; text-decoration: none; color: #233142; font-size: 0.92rem;}
.iris-nav .iris-page:hover {background: #e8f2ff;}
.iris-nav .iris-page.active {background: #d7e9ff; color: #0f4fa8; font-weight: 700;}
.iris-breadcrumb {margin: 0.32rem 0 0.52rem 0; color: #5a6777; font-size: 0.85rem;}
</style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<nav class="iris-nav"><ul class="iris-menu">{"".join(module_nodes)}</ul></nav>',
        unsafe_allow_html=True,
    )
    st.markdown(
        (
            f'<div class="iris-breadcrumb"><strong>Path:</strong> '
            f'{html.escape(current_module)} &gt; {html.escape(current_section)} &gt; {html.escape(current_page)}</div>'
        ),
        unsafe_allow_html=True,
    )


def _permissions_frame(perms: dict[str, dict[str, bool]]) -> pd.DataFrame:
    if not perms:
        return pd.DataFrame(columns=["Module", "Read", "Write", "Access"])
    rows: list[dict[str, object]] = []
    for module, rights in sorted(perms.items(), key=lambda kv: kv[0]):
        read_value = bool(rights.get("read"))
        write_value = bool(rights.get("write"))
        if read_value and write_value:
            access = "Read + Write"
        elif read_value:
            access = "Read Only"
        elif write_value:
            access = "Write Only"
        else:
            access = "No Access"
        rows.append(
            {
                "Module": module.replace("_", " ").title(),
                "Read": "Yes" if read_value else "No",
                "Write": "Yes" if write_value else "No",
                "Access": access,
            }
        )
    return pd.DataFrame(rows)


def _parse_permission_blob(blob: str) -> dict[str, tuple[bool, bool]]:
    parsed: dict[str, tuple[bool, bool]] = {}
    if not blob:
        return parsed
    for token in str(blob).split("|"):
        parts = [x.strip() for x in token.split(":")]
        if len(parts) != 3:
            continue
        code = parts[0].lower()
        read_ok = parts[1] == "1"
        write_ok = parts[2] == "1"
        parsed[code] = (read_ok, write_ok)
    return parsed


def _render_login_gate(db_path: Path) -> None:
    org_settings = _effective_org_settings(get_app_settings(db_path))
    _inject_clean_ui_css(org_settings)
    st.markdown(
        f'<div class="iris-header"><div class="iris-brand-fallback">IR</div><div class="iris-app-name">{html.escape(org_settings.get("app_name", "IRIS"))}</div></div>',
        unsafe_allow_html=True,
    )
    st.subheader("Login")
    st.caption("Sign in once. Session stays active across menu navigation.")
    _left, center, _right = st.columns([1, 1.2, 1])
    with center:
        with st.form("login_gate_form", clear_on_submit=False):
            email = st.text_input("Email", value="", placeholder="name@company.com")
            password = st.text_input("Password", value="", type="password")
            submitted = st.form_submit_button("Login", type="primary")

        if submitted:
            normalized_email = email.strip().lower()
            user = authenticate_user(db_path=db_path, email=normalized_email, password=password)
            perms = user_permissions(db_path=db_path, email=normalized_email) if user else {}
            if user is None or not perms:
                st.error("Invalid login or no role assigned.")
            else:
                st.session_state["login_email"] = normalized_email
                st.session_state["login_full_name"] = user.full_name
                st.session_state["is_authenticated"] = True
                token = create_user_session(db_path=db_path, email=normalized_email, ttl_days=14)
                st.session_state["session_token"] = token
                st.query_params["auth"] = token
                log_user_activity(
                    db_path=db_path,
                    actor_email=normalized_email,
                    action_code="LOGIN_SUCCESS",
                )
                st.rerun()

    st.stop()


def _run_analysis(
    root_dir: Path,
    out_dir: Path,
    conf_threshold: float,
    detector_type: str,
    time_bucket_minutes: int,
    bounce_threshold_sec: int,
    session_gap_sec: int,
    write_gzip_exports: bool,
    keep_plain_csv: bool,
    camera_configs_by_store: dict[str, dict[str, dict[str, object]]],
    max_images_per_store: int,
) -> AnalysisOutput:
    output = analyze_root(
        root_dir=root_dir,
        conf_threshold=conf_threshold,
        detector_type=detector_type,
        time_bucket_minutes=time_bucket_minutes,
        bounce_threshold_sec=bounce_threshold_sec,
        session_gap_sec=session_gap_sec,
        camera_configs_by_store=camera_configs_by_store,
        max_images_per_store=max_images_per_store,
    )
    export_analysis(output, out_dir=out_dir, write_gzip_exports=write_gzip_exports, keep_plain_csv=keep_plain_csv)
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


def _filter_output_to_stores(output: AnalysisOutput, store_ids: list[str]) -> AnalysisOutput:
    allowed = {sid.strip() for sid in store_ids if sid and sid.strip()}
    if not allowed:
        return AnalysisOutput(
            stores={},
            all_stores_summary=output.all_stores_summary.iloc[0:0].copy(),
            detector_warning=output.detector_warning,
            used_root_fallback_store=output.used_root_fallback_store,
        )
    filtered_stores = {sid: result for sid, result in output.stores.items() if sid in allowed}
    filtered_summary = output.all_stores_summary[
        output.all_stores_summary["store_id"].isin(sorted(allowed))
    ].copy()
    return AnalysisOutput(
        stores=filtered_stores,
        all_stores_summary=filtered_summary,
        detector_warning=output.detector_warning,
        used_root_fallback_store=output.used_root_fallback_store,
    )


def _load_or_run_default(root_dir: Path, out_dir: Path) -> AnalysisOutput:
    return load_exports(out_dir=out_dir)


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
    if "estimated_visits" in df.columns:
        st.caption(
            f"Estimated Visits: {int(df['estimated_visits'].sum())} | "
            f"Avg Bounce Rate: {df['bounce_rate'].mean():.2%}"
        )


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

    # Defensive normalization: some stores can have empty/partial frames after sync,
    # so keep dashboard rendering stable even if columns are missing.
    if "camera_id" not in image_df.columns:
        image_df["camera_id"] = "UNKNOWN"
    if "relevant" not in image_df.columns:
        image_df["relevant"] = False
    if "is_valid" not in image_df.columns:
        image_df["is_valid"] = False
    if "person_count" not in image_df.columns:
        image_df["person_count"] = 0
    if "timestamp" not in image_df.columns:
        image_df["timestamp"] = pd.NaT
    if "filename" not in image_df.columns:
        image_df["filename"] = ""
    if "path" not in image_df.columns:
        image_df["path"] = ""
    if "reject_reason" not in image_df.columns:
        image_df["reject_reason"] = ""
    if "detection_error" not in image_df.columns:
        image_df["detection_error"] = ""

    row = output.all_stores_summary[
        output.all_stores_summary["store_id"] == selected_store
    ].iloc[0]
    cols = st.columns(9)
    cols[0].metric("Total Images", int(row["total_images"]))
    cols[1].metric("Valid Images", int(row["valid_images"]))
    cols[2].metric("Relevant Images", int(row["relevant_images"]))
    cols[3].metric("Total People", int(row["total_people"]))
    cols[4].metric("Estimated Visits", int(row.get("estimated_visits", 0)))
    cols[5].metric("Avg Dwell (sec)", float(row.get("avg_dwell_sec", 0.0)))
    cols[6].metric("Bounce Rate", f"{float(row.get('bounce_rate', 0.0)):.2%}")
    cols[7].metric("Footfall", int(row.get("footfall", 0)))
    cols[8].metric("LOS Alerts", int(row.get("loss_of_sale_alerts", 0)))
    cols2 = st.columns(3)
    cols2[0].metric("Daily Walk-ins (Actual)", int(row.get("daily_walkins", 0)))
    cols2[1].metric("Daily Conversions", int(row.get("daily_conversions", 0)))
    cols2[2].metric("Daily Conversion Rate", f"{float(row.get('daily_conversion_rate', 0.0)):.2%}")

    if hasattr(store_result, "daily_report") and not store_result.daily_report.empty:
        st.markdown("**Daily Walk-in & Conversion Report**")
        st.dataframe(store_result.daily_report, use_container_width=True)

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
    if "camera_id" not in relevant_df.columns:
        relevant_df["camera_id"] = "UNKNOWN"
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
    if "camera_id" in relevant_df.columns and selected_cameras:
        gallery_df = relevant_df[relevant_df["camera_id"].isin(selected_cameras)].head(max_images)
    else:
        gallery_df = relevant_df.head(0)
    if gallery_df.empty:
        st.info("No relevant images for the selected camera filter.")
        return

    cols = st.columns(3)
    for idx, row_image in gallery_df.iterrows():
        col = cols[idx % 3]
        ts_value = row_image.get("timestamp")
        if pd.isna(ts_value):
            ts_text = "NA"
        else:
            ts_text = ts_value.strftime('%H:%M:%S')
        caption = (
            f"{ts_text} "
            f"{row_image.get('camera_id', 'UNKNOWN')} "
            f"people={row_image.get('person_count', 0)}"
        )
        with col:
            image_path = row_image.get("path", "")
            if image_path:
                st.image(image_path, caption=caption, use_container_width=True)
            else:
                st.caption(caption)


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
    st.markdown("---")
    st.markdown("**Camera Onboarding + Calibration (Entrance Line)**")
    if stores:
        cfg_store_id = st.selectbox("Config Store", options=[s.store_id for s in stores], key="cfg_store")
        cfg_camera_id = st.text_input("Camera ID (e.g., D02)", value="", key="cfg_camera_id")
        cfg_role = st.selectbox("Camera Role", options=["ENTRANCE", "INSIDE"], index=0, key="cfg_role")
        cfg_line_x = st.slider("Entry Line X (0=left,1=right)", min_value=0.0, max_value=1.0, value=0.5, step=0.01, key="cfg_line")
        cfg_dir = st.selectbox("Entry Direction", options=["OUTSIDE_TO_INSIDE", "INSIDE_TO_OUTSIDE"], index=0, key="cfg_dir")
        if st.button("Save Camera Calibration", key="save_camera_cfg"):
            if not cfg_camera_id.strip():
                st.error("Camera ID is required")
            else:
                upsert_camera_config(
                    db_path=db_path,
                    store_id=cfg_store_id,
                    camera_id=cfg_camera_id.strip().upper(),
                    camera_role=cfg_role,
                    entry_line_x=float(cfg_line_x),
                    entry_direction=cfg_dir,
                )
                st.success("Camera calibration saved.")

        cfg_df = pd.DataFrame([c.__dict__ for c in list_camera_configs(db_path=db_path, store_id=cfg_store_id)])
        if not cfg_df.empty:
            st.dataframe(cfg_df, use_container_width=True)

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


def _prefill_store_mapping_fields(db_path: Path, store_id: str) -> None:
    sid = store_id.strip()
    if not sid:
        return
    existing = {s.store_id: s for s in list_stores(db_path)}
    rec = existing.get(sid)
    master = get_store_master_by_id(db_path=db_path, store_id=sid)
    if rec is not None:
        st.session_state["map_store_name"] = rec.store_name
        st.session_state["map_store_email"] = rec.email
        st.session_state["map_drive_url"] = rec.drive_folder_url
        st.session_state["map_existing_drive_url"] = rec.drive_folder_url
    elif master is not None:
        st.session_state["map_store_name"] = str(master.get("gofrugal_name", "")).strip()
        st.session_state["map_store_email"] = str(master.get("store_email", "")).strip().lower()
        st.session_state["map_drive_url"] = ""
        st.session_state["map_existing_drive_url"] = ""
    else:
        st.session_state["map_store_name"] = ""
        st.session_state["map_store_email"] = ""
        st.session_state["map_drive_url"] = ""
        st.session_state["map_existing_drive_url"] = ""
    st.session_state["map_replace_drive_url"] = False
    st.session_state["map_last_store_id"] = sid


def _render_store_mapping(
    db_path: Path,
    data_root: Path,
    auto_sync_after_save: bool,
    default_user_password: str,
    active_email: str,
) -> None:
    st.subheader("Store Mapping")
    st.caption("On save, store login is auto-created using Store Email + default password from Organisation settings.")
    stores = list_stores(db_path)
    if "map_store_id" not in st.session_state:
        st.session_state["map_store_id"] = ""
    if "map_store_name" not in st.session_state:
        st.session_state["map_store_name"] = ""
    if "map_store_email" not in st.session_state:
        st.session_state["map_store_email"] = ""
    if "map_drive_url" not in st.session_state:
        st.session_state["map_drive_url"] = ""
    if "map_existing_drive_url" not in st.session_state:
        st.session_state["map_existing_drive_url"] = ""
    if "map_replace_drive_url" not in st.session_state:
        st.session_state["map_replace_drive_url"] = False
    if "map_last_store_id" not in st.session_state:
        st.session_state["map_last_store_id"] = ""
    if "map_edit_store_select" not in st.session_state:
        st.session_state["map_edit_store_select"] = ""

    edit_ids = [""] + [s.store_id for s in stores]
    selected_edit = st.selectbox(
        "Edit Existing Store (optional)",
        options=edit_ids,
        key="map_edit_store_select",
        help="Select a store to auto-fill Store Name, Store Email, and current Drive link.",
    )
    if selected_edit and selected_edit != st.session_state.get("map_store_id", ""):
        st.session_state["map_store_id"] = selected_edit

    st.text_input("Store ID (unique)", key="map_store_id")
    current_sid = st.session_state["map_store_id"].strip()
    if current_sid and current_sid != st.session_state.get("map_last_store_id", ""):
        _prefill_store_mapping_fields(db_path=db_path, store_id=current_sid)

    st.text_input("Store Name", key="map_store_name")
    st.text_input("Store Email", key="map_store_email")
    st.text_input("Google Drive Folder URL", key="map_drive_url")

    existing_drive = st.session_state.get("map_existing_drive_url", "").strip()
    new_drive = st.session_state.get("map_drive_url", "").strip()
    drive_changed = bool(existing_drive and new_drive and existing_drive != new_drive)
    if existing_drive:
        st.caption(f"Current Drive URL: {existing_drive}")
    if drive_changed:
        st.checkbox(
            "Replace existing Drive link for this store",
            key="map_replace_drive_url",
            help="Required when updating an existing store to a different Drive link.",
        )

    save_cols = st.columns([1, 1, 2])
    if save_cols[0].button("Save / Update Store", type="primary"):
        sid = st.session_state["map_store_id"].strip()
        sname = st.session_state["map_store_name"].strip()
        semail = st.session_state["map_store_email"].strip()
        sdrive = st.session_state["map_drive_url"].strip()
        if not sid or not sname or not semail:
            st.error("Store ID, Store Name, and Store Email are required.")
        elif drive_changed and not bool(st.session_state.get("map_replace_drive_url", False)):
            st.warning("Confirm drive replacement first, then save.")
        else:
            upsert_store(
                db_path=db_path,
                store_id=sid,
                store_name=sname,
                email=semail,
                drive_folder_url=sdrive,
            )
            login_result = ensure_store_login(
                db_path=db_path,
                store_id=sid,
                store_email=semail,
                store_name=sname,
                default_password=default_user_password,
            )
            (data_root / sid).mkdir(parents=True, exist_ok=True)
            st.success(f"Saved store mapping for {sid}.")
            if bool(login_result.get("created")):
                st.info(
                    f"Store login created: {semail.lower()} | temp password: {default_user_password}"
                )
            else:
                st.info("Store login already existed and store mapping was refreshed.")
            if active_email:
                log_user_activity(
                    db_path=db_path,
                    actor_email=active_email,
                    action_code="STORE_SAVED_WITH_AUTO_LOGIN",
                    store_id=sid,
                )
            _prefill_store_mapping_fields(db_path=db_path, store_id=sid)
            if auto_sync_after_save and sdrive:
                matched = [s for s in list_stores(db_path) if s.store_id == sid]
                if matched:
                    ok, message = sync_store_from_drive(matched[0], data_root=data_root)
                    if ok:
                        st.info(message)
                    else:
                        st.warning(message)

    if save_cols[1].button("Sync Selected Store"):
        sid = st.session_state["map_store_id"].strip()
        matched = [s for s in list_stores(db_path) if s.store_id == sid]
        if not sid or not matched:
            st.warning("Select a valid store first.")
        else:
            ok, message = sync_store_from_drive(matched[0], data_root=data_root)
            if ok:
                st.success(message)
            else:
                st.warning(message)

    if stores:
        st.markdown("**Registered Stores**")
        st.dataframe(pd.DataFrame([s.__dict__ for s in stores]), use_container_width=True)
    else:
        st.info("No stores registered yet.")


def _render_camera_zones(db_path: Path) -> None:
    st.subheader("Camera Zones")
    stores = list_stores(db_path)
    if not stores:
        st.info("Create at least one store before camera setup.")
        return
    store_ids = [s.store_id for s in stores]
    with st.form("camera_zone_form", clear_on_submit=False):
        cfg_store_id = st.selectbox("Store", options=store_ids)
        cfg_camera_id = st.text_input("Camera ID (e.g., D01)")
        cfg_location = st.text_input("Location Name (e.g., Zone1, Zone2)")
        cfg_role = st.selectbox(
            "Camera Role",
            options=["ENTRANCE", "INSIDE", "BILLING", "BACKROOM", "EXIT", "ZONE"],
            index=1,
        )
        cfg_line_x = st.slider("Entry Line X (0=left,1=right)", min_value=0.0, max_value=1.0, value=0.5, step=0.01)
        cfg_dir = st.selectbox("Entry Direction", options=["OUTSIDE_TO_INSIDE", "INSIDE_TO_OUTSIDE"], index=0)
        save_camera = st.form_submit_button("Save Camera")
    if save_camera:
        if not cfg_camera_id.strip():
            st.error("Camera ID is required.")
        else:
            upsert_camera_config(
                db_path=db_path,
                store_id=cfg_store_id,
                camera_id=cfg_camera_id.strip().upper(),
                camera_role=cfg_role,
                location_name=cfg_location.strip(),
                entry_line_x=float(cfg_line_x),
                entry_direction=cfg_dir,
            )
            st.success("Camera zone saved.")

    selected_store = st.selectbox("View Store Cameras", options=store_ids, key="camera_view_store")
    cfg_df = pd.DataFrame([c.__dict__ for c in list_camera_configs(db_path=db_path, store_id=selected_store)])
    if cfg_df.empty:
        st.caption("No camera configuration found for this store.")
    else:
        st.dataframe(cfg_df, use_container_width=True)


def _render_employee_management(db_path: Path, employee_assets_root: Path) -> None:
    st.subheader("Employee Management")
    stores = list_stores(db_path)
    if not stores:
        st.info("Create at least one store before employee onboarding.")
        return
    store_ids = [s.store_id for s in stores]

    st.markdown("**Add Employee Images**")
    with st.form("employee_upload_form", clear_on_submit=True):
        upload_store = st.selectbox("Store", options=store_ids)
        employee_name = st.text_input("Employee Name")
        upload_files = st.file_uploader(
            "Employee Image Files",
            type=["jpg", "jpeg", "png", "webp", "bmp"],
            accept_multiple_files=True,
        )
        upload_clicked = st.form_submit_button("Upload")
    if upload_clicked:
        if not employee_name.strip():
            st.error("Employee name is required.")
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
            st.success(f"Uploaded {uploaded} image(s).")

    st.markdown("**Employee Directory**")
    view_scope = st.selectbox("View Scope", options=["ALL"] + store_ids, key="employee_view_scope")
    if view_scope == "ALL":
        employees = list_employees(db_path=db_path, store_id=None)
    else:
        employees = list_employees(db_path=db_path, store_id=view_scope)
    emp_df = pd.DataFrame(employees)
    if emp_df.empty:
        st.caption("No employee records found.")
        return
    st.dataframe(emp_df, use_container_width=True, hide_index=True)

    selected_id = st.selectbox("Employee ID", options=emp_df["id"].astype(int).tolist(), key="employee_selected_id")
    selected_row = emp_df[emp_df["id"] == selected_id].iloc[0]
    action_cols = st.columns([1, 1, 1])
    if action_cols[0].button("Enable", key="employee_enable_button"):
        set_employee_active(db_path=db_path, employee_id=int(selected_id), is_active=True)
        st.success("Employee enabled.")
    if action_cols[1].button("Disable", key="employee_disable_button"):
        set_employee_active(db_path=db_path, employee_id=int(selected_id), is_active=False)
        st.success("Employee disabled.")
    confirm_delete = action_cols[2].checkbox("Confirm delete", key="employee_confirm_delete")
    if action_cols[2].button("Delete", key="employee_delete_button"):
        if not confirm_delete:
            st.warning("Tick confirm delete first.")
        else:
            deleted = delete_employee(db_path=db_path, employee_id=int(selected_id), delete_file=True)
            if deleted:
                st.success("Employee deleted.")
            else:
                st.warning("Employee not found.")
    st.caption(
        f"Selected employee: {selected_row['employee_name']} | "
        f"Store: {selected_row['store_id']} | Active: {bool(selected_row['is_active'])}"
    )


def _render_organisation(db_path: Path, data_dir: Path) -> None:
    st.subheader("Organisation")
    st.caption("Manage company logo, app name, and standard UI theme controls.")
    settings = _effective_org_settings(get_app_settings(db_path))

    branding_dir = data_dir / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    current_logo_path = settings.get("logo_path", "").strip()
    logo_file = Path(current_logo_path).expanduser() if current_logo_path else None
    if logo_file and logo_file.exists():
        st.markdown("**Current logo**")
        st.image(str(logo_file), width=120)
    else:
        st.caption("No company logo uploaded yet.")

    logo_upload = st.file_uploader(
        "Upload company logo",
        type=["png", "jpg", "jpeg", "webp"],
        key="org_logo_uploader",
        help="Recommended: transparent PNG, square ratio.",
    )
    remove_logo = st.checkbox("Remove current logo", key="org_remove_logo")

    font_options = ["Segoe UI", "Calibri", "Arial"]
    editor_rows = pd.DataFrame(
        [
            {"Setting": "app_name", "Value": settings.get("app_name", "IRIS")},
            {"Setting": "font_family", "Value": settings.get("font_family", "Segoe UI")},
            {"Setting": "background_color", "Value": settings.get("background_color", "#f4f6f8")},
            {"Setting": "surface_color", "Value": settings.get("surface_color", "#ffffff")},
            {"Setting": "nav_color", "Value": settings.get("nav_color", "#1f3044")},
            {"Setting": "accent_color", "Value": settings.get("accent_color", "#2a7fd9")},
            {"Setting": "default_user_password", "Value": settings.get("default_user_password", "ChangeMe123!")},
        ]
    )
    st.markdown("**Style editor (excel-like)**")
    edited_rows = st.data_editor(
        editor_rows,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="org_settings_editor",
    )
    st.caption(
        "Use HEX colors like `#1f3044`. Font values allowed: Segoe UI, Calibri, Arial. "
        "Default user password is used for auto-created Store/CM/AM logins."
    )

    quick_cols = st.columns([2, 2, 3])
    selected_font = quick_cols[0].selectbox(
        "Font quick select",
        options=font_options,
        index=font_options.index(settings.get("font_family", "Segoe UI")),
        key="org_font_select",
    )
    quick_cols[1].color_picker(
        "Background quick select",
        value=settings.get("background_color", "#f4f6f8"),
        key="org_bg_picker",
    )
    quick_cols[2].color_picker(
        "Accent quick select",
        value=settings.get("accent_color", "#2a7fd9"),
        key="org_accent_picker",
    )

    if st.button("Save organisation settings", type="primary", key="save_org_settings_button"):
        edited_map: dict[str, str] = {}
        for _, row in edited_rows.iterrows():
            setting_key = str(row.get("Setting", "")).strip()
            setting_value = str(row.get("Value", "")).strip()
            if setting_key:
                edited_map[setting_key] = setting_value

        # Quick selectors override matching fields for easier usage.
        edited_map["font_family"] = selected_font
        edited_map["background_color"] = str(st.session_state.get("org_bg_picker", "#f4f6f8"))
        edited_map["accent_color"] = str(st.session_state.get("org_accent_picker", "#2a7fd9"))

        app_name = edited_map.get("app_name", "IRIS").strip() or "IRIS"
        font_name = edited_map.get("font_family", "Segoe UI").strip()
        if font_name not in set(font_options):
            st.error("Font must be one of: Segoe UI, Calibri, Arial.")
            return
        for color_key in ["background_color", "surface_color", "nav_color", "accent_color"]:
            color_value = edited_map.get(color_key, "").strip()
            if not re.match(r"^#[0-9a-fA-F]{6}$", color_value):
                st.error(f"Invalid color for {color_key}. Use HEX format like #1f3044.")
                return
        edited_map["app_name"] = app_name

        if remove_logo:
            if logo_file and logo_file.exists():
                try:
                    logo_file.unlink()
                except Exception:
                    pass
            edited_map["logo_path"] = ""
        elif logo_upload is not None:
            ext = Path(logo_upload.name).suffix.lower() or ".png"
            target = branding_dir / f"company_logo{ext}"
            target.write_bytes(logo_upload.getvalue())
            edited_map["logo_path"] = str(target)
        else:
            edited_map["logo_path"] = current_logo_path

        upsert_app_settings(db_path=db_path, settings=edited_map)
        st.success("Organisation settings saved.")
        st.rerun()


def _render_users_page(db_path: Path, active_email: str) -> None:
    st.subheader("Users")
    st.caption("Create or update user accounts. This page is best for individual user operations.")
    roles = [str(r.get("role_name", "")).strip() for r in list_roles(db_path) if str(r.get("role_name", "")).strip()]
    store_ids = [s.store_id for s in list_stores(db_path)]
    with st.form("users_create_update_form", clear_on_submit=False):
        u_email = st.text_input("User email")
        u_name = st.text_input("Full name")
        u_pwd = st.text_input("Password", type="password", value="ChangeMe123!")
        default_roles = ["store_user"] if "store_user" in roles else roles[:1]
        u_roles = st.multiselect("Roles", options=roles, default=default_roles)
        u_store_ids = st.multiselect(
            "Store access",
            options=store_ids,
            help="If selected, these stores become visible in dashboard for this user.",
        )
        u_force_reset = st.checkbox("Reset password if user already exists", value=False)
        save_user = st.form_submit_button("Create / Update User", type="primary")
    if save_user:
        if not u_email.strip() or not u_name.strip() or not u_roles:
            st.error("Email, full name, and at least one role are required.")
        else:
            try:
                user_id, created = upsert_user_account(
                    db_path=db_path,
                    email=u_email.strip(),
                    full_name=u_name.strip(),
                    role_names=u_roles,
                    password=u_pwd.strip() or "ChangeMe123!",
                    force_password_reset=bool(u_force_reset),
                    is_active=True,
                )
                replace_user_store_access(db_path=db_path, email=u_email.strip(), store_ids=u_store_ids)
                if active_email:
                    log_user_activity(
                        db_path=db_path,
                        actor_email=active_email,
                        action_code="UPSERT_USER",
                        payload_json=f'{{"target":"{u_email.strip().lower()}","created":{str(created).lower()}}}',
                    )
                st.success(f"User {'created' if created else 'updated'} (id={user_id}).")
            except Exception as exc:
                st.error(str(exc))
    users_df = pd.DataFrame(list_users(db_path))
    access_rows = list_user_store_access(db_path)
    if not users_df.empty:
        st.markdown("**User Directory**")
        if access_rows:
            access_df = pd.DataFrame(access_rows)
            grouped = (
                access_df.groupby("email", as_index=False)["store_id"]
                .agg(lambda x: "|".join(sorted(set(str(v) for v in x if str(v).strip()))))
                .rename(columns={"store_id": "accessible_stores"})
            )
            users_df = users_df.merge(grouped, on="email", how="left")
        users_df["accessible_stores"] = users_df.get("accessible_stores", "").fillna("")
        st.dataframe(users_df, use_container_width=True, hide_index=True)
    else:
        st.info("No users found.")


def _render_password_manager(db_path: Path, active_email: str) -> None:
    st.subheader("Password Manager")
    st.caption("Reset passwords quickly. Use this for Store / CM / AM login changes.")
    users_df = pd.DataFrame(list_users(db_path))
    if users_df.empty:
        st.info("No users available for password update.")
        return
    target_email = st.selectbox("User email", options=users_df["email"].tolist(), key="pwd_user_email")
    new_pwd = st.text_input("New password", type="password", key="pwd_new_password")
    confirm_pwd = st.text_input("Confirm new password", type="password", key="pwd_confirm_password")
    if st.button("Update password", key="pwd_update_button"):
        if not new_pwd.strip() or not confirm_pwd.strip():
            st.error("Both password fields are required.")
        elif new_pwd != confirm_pwd:
            st.error("Password and confirm password do not match.")
        else:
            set_user_password(db_path=db_path, email=target_email, new_password=new_pwd)
            if active_email:
                log_user_activity(
                    db_path=db_path,
                    actor_email=active_email,
                    action_code="SET_PASSWORD",
                    payload_json=f'{{"target":"{target_email}"}}',
                )
            st.success("Password updated.")


def _render_role_permissions_page(db_path: Path, active_email: str, active_perms: dict[str, dict[str, bool]]) -> None:
    st.subheader("Role Permissions")
    st.caption(f"Active login: {active_email or '-'}")
    perms_df = _permissions_frame(active_perms)
    role_rows = list_roles(db_path)
    role_names = [str(row.get("role_name", "")).strip() for row in role_rows if str(row.get("role_name", "")).strip()]
    permission_codes = list_permission_codes(db_path)
    role_lookup = {str(row.get("role_name", "")).strip(): row for row in role_rows}
    if perms_df.empty:
        st.warning("No permissions mapped for this user.")
    else:
        st.markdown("**Permission Matrix**")
        st.dataframe(perms_df, use_container_width=True, hide_index=True)
    with st.expander("Create role", expanded=False):
        r_name = st.text_input("Role name (new)", key="role_new_name")
        r_desc = st.text_input("Role description", key="role_new_desc")
        if st.button("Create role", key="role_create_btn"):
            if not r_name.strip():
                st.error("Role name is required.")
            else:
                create_role(db_path, r_name, r_desc)
                st.success("Role created")
                st.rerun()
    with st.expander("Set role permissions", expanded=True):
        if not role_names:
            st.caption("No roles found.")
        else:
            selected_perm_role = st.selectbox(
                "Role",
                options=role_names,
                key="rbac_permission_role_select",
            )
            selected_blob = str(role_lookup[selected_perm_role].get("permissions", ""))
            selected_map = _parse_permission_blob(selected_blob)
            for code in permission_codes:
                read_default, write_default = selected_map.get(code, (False, False))
                role_key = "".join(ch if ch.isalnum() else "_" for ch in selected_perm_role)
                read_key = f"rbac_{role_key}_{code}_read"
                write_key = f"rbac_{role_key}_{code}_write"
                cols_perm = st.columns([1.6, 0.7, 0.7])
                cols_perm[0].markdown(f"`{code}`")
                cols_perm[1].checkbox("Read", key=read_key, value=read_default)
                cols_perm[2].checkbox("Write", key=write_key, value=write_default)
            if st.button("Save role permissions", key="save_role_permission_btn"):
                rows: list[tuple[str, int, int]] = []
                role_key = "".join(ch if ch.isalnum() else "_" for ch in selected_perm_role)
                for code in permission_codes:
                    read_key = f"rbac_{role_key}_{code}_read"
                    write_key = f"rbac_{role_key}_{code}_write"
                    read_flag = 1 if st.session_state.get(read_key, False) else 0
                    write_flag = 1 if st.session_state.get(write_key, False) else 0
                    rows.append((code, read_flag, write_flag))
                set_role_permissions(db_path, selected_perm_role, rows)
                if active_email:
                    log_user_activity(
                        db_path=db_path,
                        actor_email=active_email,
                        action_code="SET_ROLE_PERMISSIONS",
                    )
                st.success("Role permissions saved")
                st.rerun()
    with st.expander("Delete role", expanded=False):
        delete_role_name = st.selectbox(
            "Role to delete",
            options=role_names,
            key="rbac_delete_role_select",
        )
        confirm_role_delete = st.checkbox(
            "Confirm role deletion",
            key="rbac_confirm_role_delete",
        )
        if st.button("Delete selected role", key="rbac_delete_role_btn"):
            if not confirm_role_delete:
                st.warning("Tick confirm role deletion first.")
            else:
                ok, message = delete_role(db_path=db_path, role_name=delete_role_name)
                if ok:
                    if active_email:
                        log_user_activity(
                            db_path=db_path,
                            actor_email=active_email,
                            action_code="DELETE_ROLE",
                        )
                    st.success(message)
                    st.rerun()
                else:
                    st.warning(message)
    st.markdown("**Current roles**")
    st.dataframe(pd.DataFrame(list_roles(db_path)), use_container_width=True, hide_index=True)


def _render_store_access_mapping(db_path: Path, default_user_password: str, active_email: str) -> None:
    st.subheader("Store Access Mapping")
    st.caption(
        "Easy way: map one Store/CM/AM at a time. Saving mapping replaces previous store mapping for that user."
    )
    stores = list_stores(db_path)
    store_ids = [s.store_id for s in stores]
    store_lookup = {s.store_id: s for s in stores}

    st.markdown("**Auto-create Store login**")
    auto_cols = st.columns([2, 1])
    selected_store_id = auto_cols[0].selectbox(
        "Store for auto-login",
        options=store_ids,
        key="access_auto_store_selector",
    ) if store_ids else ""
    if auto_cols[1].button("Create / Sync Store Login", key="access_auto_store_btn"):
        if not selected_store_id:
            st.warning("No stores available.")
        else:
            rec = store_lookup[selected_store_id]
            result = ensure_store_login(
                db_path=db_path,
                store_id=rec.store_id,
                store_email=rec.email,
                store_name=rec.store_name,
                default_password=default_user_password,
            )
            if active_email:
                log_user_activity(
                    db_path=db_path,
                    actor_email=active_email,
                    action_code="AUTO_STORE_LOGIN_SYNC",
                    store_id=rec.store_id,
                )
            if bool(result.get("created")):
                st.success(
                    f"Store login created: {rec.email} | temp password: {default_user_password}"
                )
            else:
                st.success(f"Store login already existed and access mapping was updated: {rec.email}")

    st.markdown("**Manual CM/AM mapping**")
    with st.form("manual_manager_mapping_form", clear_on_submit=False):
        manager_type = st.selectbox(
            "Manager type",
            options=["cluster_manager", "area_manager"],
            format_func=lambda v: "Cluster Manager" if v == "cluster_manager" else "Area Manager",
        )
        manager_email = st.text_input("Manager email")
        manager_name = st.text_input("Manager full name")
        manager_stores = st.multiselect("Stores", options=store_ids)
        reset_pwd = st.checkbox("Reset password to default while saving", value=False)
        save_mapping = st.form_submit_button("Save manager mapping", type="primary")
    if save_mapping:
        if not manager_email.strip():
            st.error("Manager email is required.")
        elif not manager_stores:
            st.error("Select at least one store.")
        else:
            try:
                result = upsert_manager_access(
                    db_path=db_path,
                    manager_type=manager_type,
                    email=manager_email.strip(),
                    full_name=manager_name.strip(),
                    store_ids=manager_stores,
                    default_password=default_user_password,
                    force_password_reset=bool(reset_pwd),
                )
                if active_email:
                    log_user_activity(
                        db_path=db_path,
                        actor_email=active_email,
                        action_code="UPSERT_MANAGER_MAPPING",
                    )
                if bool(result.get("created")):
                    st.success(
                        f"{manager_type} login created: {result['email']} | temp password: {default_user_password}"
                    )
                else:
                    st.success(f"Mapping updated for {result['email']}.")
            except Exception as exc:
                st.error(str(exc))

    st.markdown("**Current Access Mapping**")
    access_rows = list_user_store_access(db_path=db_path)
    if not access_rows:
        st.caption("No access mappings found yet.")
    else:
        access_df = pd.DataFrame(access_rows)
        users_rows = list_users(db_path)
        users_df = pd.DataFrame(users_rows)[["email", "roles"]] if users_rows else pd.DataFrame(columns=["email", "roles"])
        if not users_df.empty:
            access_df = access_df.merge(users_df, on="email", how="left")
        st.dataframe(access_df, use_container_width=True, hide_index=True)


def _render_bulk_access_upload(db_path: Path, default_user_password: str, active_email: str) -> None:
    st.subheader("Bulk Access Upload")
    st.caption(
        "Bulk way: upload CSV or edit rows directly. Supports `store_user`, `cluster_manager`, `area_manager`."
    )
    st.markdown("Template columns: `manager_type,email,full_name,store_id,store_ids`")
    template_df = pd.DataFrame(
        [
            {
                "manager_type": "store_user",
                "email": "store1@example.com",
                "full_name": "Store One User",
                "store_id": "STORE_001",
                "store_ids": "",
            },
            {
                "manager_type": "cluster_manager",
                "email": "cm.north@example.com",
                "full_name": "CM North",
                "store_id": "",
                "store_ids": "STORE_001|STORE_002",
            },
        ]
    )
    edited_df = st.data_editor(
        template_df,
        use_container_width=True,
        num_rows="dynamic",
        key="bulk_access_editor",
    )
    if st.button("Apply editor rows", key="bulk_access_apply_editor"):
        rows = edited_df.fillna("").to_dict(orient="records")
        summary = bulk_upsert_store_access_rows(
            db_path=db_path,
            rows=rows,
            default_password=default_user_password,
        )
        if active_email:
            log_user_activity(db_path=db_path, actor_email=active_email, action_code="BULK_ACCESS_EDITOR_APPLY")
        st.success(
            f"Processed={summary['processed']} | Created={summary['created_users']} | "
            f"Updated={summary['updated_users']} | Failed={summary['failed']}"
        )

    upload = st.file_uploader("Upload CSV", type=["csv"], key="bulk_access_csv_uploader")
    if upload is not None:
        try:
            upload_df = pd.read_csv(upload).fillna("")
            st.dataframe(upload_df, use_container_width=True, hide_index=True)
            if st.button("Apply uploaded CSV", key="bulk_access_apply_csv"):
                rows = upload_df.to_dict(orient="records")
                summary = bulk_upsert_store_access_rows(
                    db_path=db_path,
                    rows=rows,
                    default_password=default_user_password,
                )
                if active_email:
                    log_user_activity(
                        db_path=db_path,
                        actor_email=active_email,
                        action_code="BULK_ACCESS_CSV_APPLY",
                    )
                st.success(
                    f"Processed={summary['processed']} | Created={summary['created_users']} | "
                    f"Updated={summary['updated_users']} | Failed={summary['failed']}"
                )
        except Exception as exc:
            st.error(f"Invalid CSV: {exc}")


def _render_setup_help() -> None:
    st.subheader("Setup Help")
    st.markdown(
        """
### Recommended Access Setup
1. `Operations > Store Mapping`: create store, email, drive link.
2. Store login is auto-created using Organisation default password.
3. `Access > Store Access Mapping`: map CM/AM emails to stores.
4. `Access > Password Manager`: set final passwords.
5. `Access > Bulk Access Upload`: use CSV for large updates.

### Quick Hints
- `manager_type=store_user` uses `store_id` or first value from `store_ids`.
- `manager_type=cluster_manager/area_manager` should use `store_ids` with `|` separator.
- Mapping save replaces previous store mapping for that user, so maintenance stays simple.
- Use `Organisation` page to change default auto-created password anytime.
        """
    )

def main() -> None:
    st.set_page_config(
        page_title="IRIS Store Analysis Dashboard",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _ensure_session_state()

    app_dir = Path(__file__).resolve().parents[2]
    data_dir = app_dir / "data"
    default_stores_root = data_dir / "stores"
    default_exports_dir = data_dir / "exports" / "current"
    db_path = app_dir / "data" / "store_registry.db"
    data_root = default_stores_root
    employee_assets_root = data_dir / "employee_assets"
    data_root.mkdir(parents=True, exist_ok=True)
    default_exports_dir.mkdir(parents=True, exist_ok=True)
    init_db(db_path)
    ensure_default_admins(db_path, ["vishal.nayak@kushals.com", "mayur.pathak@kushals.com"])
    org_settings = _effective_org_settings(get_app_settings(db_path))
    _inject_clean_ui_css(org_settings)
    auth_token_from_query = _query_value("auth", "").strip()
    if not st.session_state.get("is_authenticated", False) and auth_token_from_query:
        session_user = get_user_by_session_token(db_path=db_path, token=auth_token_from_query)
        if session_user is not None:
            st.session_state["login_email"] = session_user.email
            st.session_state["login_full_name"] = session_user.full_name
            st.session_state["is_authenticated"] = True
            st.session_state["session_token"] = auth_token_from_query
    if not st.session_state.get("is_authenticated", False):
        _render_login_gate(db_path)

    if "ctrl_root_str" not in st.session_state:
        st.session_state["ctrl_root_str"] = str(data_root)
    if "ctrl_out_str" not in st.session_state:
        st.session_state["ctrl_out_str"] = str(default_exports_dir)
    if "ctrl_conf_threshold" not in st.session_state:
        st.session_state["ctrl_conf_threshold"] = 0.25
    if "ctrl_time_bucket_minutes" not in st.session_state:
        st.session_state["ctrl_time_bucket_minutes"] = 1
    if "ctrl_bounce_threshold_sec" not in st.session_state:
        st.session_state["ctrl_bounce_threshold_sec"] = 120
    if "ctrl_session_gap_sec" not in st.session_state:
        st.session_state["ctrl_session_gap_sec"] = 30
    if "ctrl_max_images_per_store" not in st.session_state:
        st.session_state["ctrl_max_images_per_store"] = 20
    if "ctrl_detector_type" not in st.session_state:
        st.session_state["ctrl_detector_type"] = "mock"
    if "ctrl_write_gzip_exports" not in st.session_state:
        st.session_state["ctrl_write_gzip_exports"] = True
    if "ctrl_keep_plain_csv" not in st.session_state:
        st.session_state["ctrl_keep_plain_csv"] = True
    if "ctrl_auto_sync_linked_drives" not in st.session_state:
        st.session_state["ctrl_auto_sync_linked_drives"] = True
    if "ctrl_auto_sync_on_save" not in st.session_state:
        st.session_state["ctrl_auto_sync_on_save"] = False

    active_email = st.session_state.get("login_email", "")
    active_full_name = st.session_state.get("login_full_name", "")
    auth_token = st.session_state.get("session_token", "")
    default_user_password = org_settings.get("default_user_password", "ChangeMe123!")
    active_perms = user_permissions(db_path=db_path, email=active_email) if active_email else {}
    active_roles = user_role_names(db_path=db_path, email=active_email) if active_email else []
    current_module, current_section, current_page = _resolve_menu_from_query()

    access_email = _render_header_bar(
        app_name=org_settings.get("app_name", "IRIS"),
        logo_path=org_settings.get("logo_path", ""),
        active_email=active_email,
        active_full_name=active_full_name,
        active_roles=active_roles,
        db_path=db_path,
        auth_token=auth_token,
    )

    _render_hover_nav(
        current_module=current_module,
        current_section=current_section,
        current_page=current_page,
        auth_token=auth_token,
    )

    st.query_params["module"] = current_module
    st.query_params["section"] = current_section
    st.query_params["page"] = current_page
    if auth_token:
        st.query_params["auth"] = auth_token

    with st.expander("Analysis Controls", expanded=False):
        with st.form("analysis_controls_form", clear_on_submit=False):
            ctrl_cols_1 = st.columns(2)
            ctrl_cols_1[0].text_input("Root Directory", key="ctrl_root_str")
            ctrl_cols_1[1].text_input("Export Directory", key="ctrl_out_str")

            ctrl_cols_2 = st.columns(5)
            ctrl_cols_2[0].slider(
                "Detection Confidence",
                min_value=0.05,
                max_value=0.9,
                step=0.05,
                key="ctrl_conf_threshold",
            )
            ctrl_cols_2[1].selectbox(
                "Time Bucket (minutes)",
                options=[1, 5, 15],
                key="ctrl_time_bucket_minutes",
            )
            ctrl_cols_2[2].number_input(
                "Bounce Threshold (sec)",
                min_value=10,
                max_value=3600,
                step=10,
                key="ctrl_bounce_threshold_sec",
            )
            ctrl_cols_2[3].number_input(
                "Session Gap (sec)",
                min_value=5,
                max_value=600,
                step=5,
                key="ctrl_session_gap_sec",
            )
            ctrl_cols_2[4].selectbox(
                "Images / Store",
                options=[10, 20, 50, 100, 0],
                help="Use 0 to process all images.",
                key="ctrl_max_images_per_store",
            )

            ctrl_cols_3 = st.columns(5)
            yolo_available = _is_yolo_available()
            detector_options = ["yolo", "mock"] if yolo_available else ["mock", "yolo"]
            if st.session_state["ctrl_detector_type"] not in detector_options:
                st.session_state["ctrl_detector_type"] = detector_options[0]
            ctrl_cols_3[0].selectbox("Detector", options=detector_options, key="ctrl_detector_type")
            ctrl_cols_3[1].checkbox("Write .csv.gz", key="ctrl_write_gzip_exports")
            ctrl_cols_3[2].checkbox("Keep plain CSV", key="ctrl_keep_plain_csv")
            ctrl_cols_3[3].checkbox("Auto-sync drives", key="ctrl_auto_sync_linked_drives")
            ctrl_cols_3[4].checkbox("Auto-sync on save", key="ctrl_auto_sync_on_save")
            rerun_clicked = st.form_submit_button("Regenerate Analysis + CSV", type="primary")

            if not yolo_available:
                st.caption("YOLO not installed in this runtime. Using `mock` is recommended.")

    root_dir = Path(st.session_state["ctrl_root_str"]).expanduser().resolve()
    out_dir = Path(st.session_state["ctrl_out_str"]).expanduser().resolve()
    conf_threshold = float(st.session_state["ctrl_conf_threshold"])
    time_bucket_minutes = int(st.session_state["ctrl_time_bucket_minutes"])
    bounce_threshold_sec = int(st.session_state["ctrl_bounce_threshold_sec"])
    session_gap_sec = int(st.session_state["ctrl_session_gap_sec"])
    max_images_per_store = int(st.session_state["ctrl_max_images_per_store"])
    detector_type = str(st.session_state["ctrl_detector_type"])
    write_gzip_exports = bool(st.session_state["ctrl_write_gzip_exports"])
    keep_plain_csv = bool(st.session_state["ctrl_keep_plain_csv"])
    auto_sync_linked_drives = bool(st.session_state["ctrl_auto_sync_linked_drives"])
    auto_sync_on_save = bool(st.session_state["ctrl_auto_sync_on_save"])

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
            cfg_map_obj = camera_config_map(db_path=db_path)
            cfg_map = {
                sid: {
                    cid: {
                        "camera_role": cfg.camera_role,
                        "entry_line_x": cfg.entry_line_x,
                        "entry_direction": cfg.entry_direction,
                    }
                    for cid, cfg in cams.items()
                }
                for sid, cams in cfg_map_obj.items()
            }
            output = _run_analysis(
                root_dir=root_dir,
                out_dir=out_dir,
                conf_threshold=conf_threshold,
                detector_type=detector_type,
                time_bucket_minutes=time_bucket_minutes,
                bounce_threshold_sec=int(bounce_threshold_sec),
                session_gap_sec=int(session_gap_sec),
                write_gzip_exports=write_gzip_exports,
                keep_plain_csv=keep_plain_csv,
                camera_configs_by_store=cfg_map,
                max_images_per_store=int(max_images_per_store),
            )
            st.session_state["analysis_output"] = output
            if st.session_state.get("login_email"):
                log_user_activity(db_path=db_path, actor_email=st.session_state.get("login_email",""), action_code="ANALYSIS_RUN")
            st.success("Analysis completed and CSV exports updated.")

    output: AnalysisOutput | None = st.session_state.get("analysis_output")
    if output is None:
        output = _load_or_run_default(root_dir=root_dir, out_dir=out_dir)
        st.session_state["analysis_output"] = output

    view_output = output
    user_scope = user_store_scope(db_path=db_path, email=active_email) if active_email else {"restricted": True, "store_ids": []}
    if bool(user_scope.get("restricted", True)):
        scoped_store_ids = list(user_scope.get("store_ids", []))
        if not scoped_store_ids:
            st.warning("No store access mapped for this login.")
            view_output = AnalysisOutput(
                stores={},
                all_stores_summary=output.all_stores_summary.iloc[0:0].copy(),
                detector_warning=output.detector_warning,
                used_root_fallback_store=output.used_root_fallback_store,
            )
        else:
            view_output = _filter_output_to_stores(output, scoped_store_ids)

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
            if bool(user_scope.get("restricted", True)) and mapped.store_id not in set(user_scope.get("store_ids", [])):
                st.warning(f"'{access_email.strip()}' maps to store `{mapped.store_id}` which is outside your access scope.")
                view_output = AnalysisOutput(
                    stores={},
                    all_stores_summary=output.all_stores_summary.iloc[0:0].copy(),
                    detector_warning=output.detector_warning,
                    used_root_fallback_store=output.used_root_fallback_store,
                )
            else:
                st.info(f"Access mapped to store `{mapped.store_id}` ({mapped.store_name}).")
                view_output = _filter_output_to_store(view_output, mapped.store_id)

    if output.detector_warning:
        st.warning(output.detector_warning)
    if output.used_root_fallback_store:
        st.info(
            "No store subfolders found in root; root folder was treated as a single store."
        )

    if current_page == "Overview":
        _render_overview(view_output)
    elif current_page == "Organisation":
        _render_organisation(db_path=db_path, data_dir=data_dir)
    elif current_page == "Users":
        _render_users_page(db_path=db_path, active_email=active_email)
    elif current_page == "Password Manager":
        _render_password_manager(db_path=db_path, active_email=active_email)
    elif current_page == "Role Permissions":
        _render_role_permissions_page(db_path=db_path, active_email=active_email, active_perms=active_perms)
    elif current_page == "Store Access Mapping":
        _render_store_access_mapping(
            db_path=db_path,
            default_user_password=default_user_password,
            active_email=active_email,
        )
    elif current_page == "Bulk Access Upload":
        _render_bulk_access_upload(
            db_path=db_path,
            default_user_password=default_user_password,
            active_email=active_email,
        )
    elif current_page == "Setup Help":
        _render_setup_help()
    elif current_page == "Store Detail":
        _render_store_detail(view_output, time_bucket_minutes=time_bucket_minutes)
    elif current_page == "Quality":
        _render_quality_summary(view_output)
    elif current_page == "Store Mapping":
        _render_store_mapping(
            db_path=db_path,
            data_root=root_dir,
            auto_sync_after_save=auto_sync_on_save,
            default_user_password=default_user_password,
            active_email=active_email,
        )
    elif current_page == "Camera Zones":
        _render_camera_zones(db_path=db_path)
    elif current_page == "Employee Management":
        _render_employee_management(
            db_path=db_path,
            employee_assets_root=employee_assets_root,
        )

    elif current_page == "Licenses":
        st.subheader("Trade/Display License Workflow")
        lic_store = st.selectbox("License store", options=[s.store_id for s in list_stores(db_path)] or [""], key="lic_store")
        lic_type = st.text_input("License type", value="trade_display")
        if st.button("Create license") and lic_store:
            lid = create_license(db_path, lic_store, lic_type, actor_email=active_email or "system@local")
            st.success(f"Created {lid}")
        licenses = pd.DataFrame(list_licenses(db_path))
        st.dataframe(licenses, use_container_width=True)
        if not licenses.empty:
            sel = st.selectbox("License ID", options=licenses["license_id"].tolist())
            new_status = st.selectbox("Transition to", options=["review", "approved", "rejected", "expired"])
            note = st.text_input("Audit note")
            if st.button("Apply transition"):
                transition_license(db_path, sel, new_status, actor_email=active_email or "system@local", note=note)
            st.dataframe(pd.DataFrame(list_license_audit(db_path, sel)), use_container_width=True)

    elif current_page == "Alert Routes":
        st.subheader("Alert Routing")
        ar_store = st.selectbox("Route store", options=[s.store_id for s in list_stores(db_path)] or [""], key="route_store")
        ch = st.selectbox("Channel", options=["email", "webhook", "slack", "whatsapp"])
        tgt = st.text_input("Target")
        if st.button("Add route") and ar_store and tgt:
            upsert_alert_route(db_path, ar_store, ch, tgt, enabled=True)
            st.success("Route saved")
        if st.button("Test route") and ar_store:
            delivered = route_alert(db_path, ar_store, "TEST_ALERT", '{"message":"test"}')
            st.info("Delivered: " + ", ".join(delivered))
        st.dataframe(pd.DataFrame(list_alert_routes(db_path, ar_store)) if ar_store else pd.DataFrame(), use_container_width=True)

    elif current_page == "QA Timeline":
        st.subheader("Operator QA Timeline")
        if view_output.stores:
            sid = st.selectbox("QA store", options=sorted(view_output.stores.keys()), key="qa_store")
            idf = view_output.stores[sid].image_insights.copy()
            if "timestamp" in idf.columns:
                cols = [c for c in ["timestamp","camera_id","person_count","relevant","filename","track_ids","detection_error"] if c in idf.columns]
                st.dataframe(idf.sort_values("timestamp")[cols].tail(500), use_container_width=True)

    elif current_page == "Store Master":
        st.subheader("Store Master")
        st.caption("Paste TSV with headers: Short code, GoFrugal Name, Outlet id, City, State, Zone, Country, Mobile no., Store Email, Cluster Manager, Area Manager")
        raw = st.text_area("Store master TSV paste", height=200)
        if st.button("Import store master") and raw.strip():
            lines=[x for x in raw.splitlines() if x.strip()]
            hdr=[h.strip() for h in lines[0].split('	')]
            rows=[]
            for ln in lines[1:]:
                vals=[v.strip() for v in ln.split('	')]
                rows.append({hdr[i]: vals[i] if i < len(vals) else "" for i in range(len(hdr))})
            n=upsert_store_master_rows(db_path, rows)
            st.success(f"Imported {n} store-master rows")
            for r in rows[:5]:
                if r.get("Short code") and r.get("GoFrugal Name") and r.get("Store Email"):
                    try:
                        upsert_store(db_path, r.get("Short code",""), r.get("GoFrugal Name",""), r.get("Store Email",""), "")
                    except Exception:
                        pass
        sm = pd.DataFrame(list_store_master(db_path))
        st.dataframe(sm, use_container_width=True)


    elif current_page == "Activity Logs":
        st.subheader("User Activity Logs")
        filter_email = st.text_input("Filter by email (optional)", value=active_email or "")
        logs_df = pd.DataFrame(list_user_activity(db_path=db_path, actor_email=filter_email.strip() or None, limit=1000))
        st.dataframe(logs_df, use_container_width=True)

    st.caption(f"Exports folder: `{out_dir}`")


if __name__ == "__main__":
    main()

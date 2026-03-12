from __future__ import annotations

import html
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image, ImageDraw

from iris.iris_analysis import AnalysisOutput, analyze_root, export_analysis, load_exports
from iris.store_registry import (
    add_qa_feedback,
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
    list_synced_stores,
    list_qa_feedback,
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
    detect_source_provider,
    set_employee_active,
    set_role_permissions,
    set_user_password,
    sync_store_from_drive,
    transition_license,
    update_qa_feedback_review,
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
        "Business Health": ["Overview", "Store Detail", "Quality", "QA Timeline", "Customer Journeys"],
    },
    "Access": {
        "Administration": [
            "Organisation",
            "Pipeline Configuration",
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
    "default_admin_password": "AdminChangeMe123!",
}

COLOR_PRESETS: dict[str, str] = {
    "Slate Blue": "#1f3044",
    "Ocean Blue": "#2a7fd9",
    "Charcoal": "#2d3748",
    "Forest Green": "#2f855a",
    "Warm Gray": "#f4f6f8",
    "Pure White": "#ffffff",
    "Soft Navy": "#243b53",
    "Steel Blue": "#486581",
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


def _is_tf_frcnn_available() -> bool:
    model_path = os.getenv("TF_FRCNN_MODEL_PATH", "data/models/frozen_inference_graph.pb").strip()
    if not Path(model_path).exists():
        return False
    try:
        import tensorflow.compat.v1 as tf  # type: ignore  # noqa: F401

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
    merged["default_admin_password"] = (merged.get("default_admin_password", "") or "AdminChangeMe123!").strip()[:128]
    if not merged["default_admin_password"]:
        merged["default_admin_password"] = "AdminChangeMe123!"
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
div[data-testid="stWidgetLabel"] p {{
    font-weight: 700;
}}
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
</style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<nav class="iris-nav"><ul class="iris-menu">{"".join(module_nodes)}</ul></nav>',
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
    employee_assets_root: Path,
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
        employee_assets_root=employee_assets_root,
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


def _safe_json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        return []
    return []


def _normalize_image_df(image_df: pd.DataFrame) -> pd.DataFrame:
    out = image_df.copy()
    defaults: dict[str, object] = {
        "camera_id": "UNKNOWN",
        "relevant": False,
        "is_valid": False,
        "person_count": 0,
        "staff_count": 0,
        "customer_count": 0,
        "timestamp": pd.NaT,
        "filename": "",
        "path": "",
        "capture_date": "",
        "source_folder": "",
        "track_ids": "[]",
        "customer_ids": "[]",
        "group_ids": "[]",
        "person_boxes": "[]",
        "staff_flags": "[]",
        "staff_scores": "[]",
        "drive_link": "",
        "relative_path": "",
        "reject_reason": "",
        "detection_error": "",
    }
    for col, val in defaults.items():
        if col not in out.columns:
            out[col] = val
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["person_count"] = pd.to_numeric(out["person_count"], errors="coerce").fillna(0).astype(int)
    out["staff_count"] = pd.to_numeric(out["staff_count"], errors="coerce").fillna(0).astype(int)
    out["customer_count"] = pd.to_numeric(out["customer_count"], errors="coerce").fillna(
        out["person_count"] - out["staff_count"]
    ).astype(int)
    out["customer_count"] = out["customer_count"].clip(lower=0)
    out["capture_date"] = out["capture_date"].fillna("").astype(str)
    missing_date = out["capture_date"].str.strip() == ""
    out.loc[missing_date, "capture_date"] = out.loc[missing_date, "timestamp"].dt.date.astype(str)
    return out


def _predicted_label(row: pd.Series) -> str:
    person_count = int(row.get("person_count", 0) or 0)
    staff_count = int(row.get("staff_count", 0) or 0)
    if person_count <= 0:
        return "no_person"
    if staff_count <= 0:
        return "customer"
    if staff_count >= person_count:
        return "staff"
    return "mixed"


def _render_overlay_image(row: pd.Series):
    image_path = str(row.get("path", "")).strip()
    if not image_path:
        return None
    path_obj = Path(image_path)
    if not path_obj.exists():
        return None
    person_boxes = _safe_json_list(row.get("person_boxes", "[]"))
    staff_flags = [bool(x) for x in _safe_json_list(row.get("staff_flags", "[]"))]
    track_ids = [str(x) for x in _safe_json_list(row.get("track_ids", "[]"))]
    if not person_boxes:
        return None
    try:
        with Image.open(path_obj) as raw:
            canvas = raw.convert("RGB")
        draw = ImageDraw.Draw(canvas)
        width, height = canvas.size
        stroke = max(2, int(round(min(width, height) * 0.004)))
        for idx, box in enumerate(person_boxes):
            if not isinstance(box, list | tuple) or len(box) != 4:
                continue
            try:
                x1 = max(0, min(width - 1, int(float(box[0]) * width)))
                y1 = max(0, min(height - 1, int(float(box[1]) * height)))
                x2 = max(x1 + 1, min(width, int(float(box[2]) * width)))
                y2 = max(y1 + 1, min(height, int(float(box[3]) * height)))
            except Exception:
                continue
            is_staff = bool(staff_flags[idx]) if idx < len(staff_flags) else False
            color = "#e63946" if is_staff else "#2a7fd9"
            label = "STAFF" if is_staff else "CUSTOMER"
            if idx < len(track_ids) and str(track_ids[idx]).strip():
                label += f" T{track_ids[idx]}"
            draw.rectangle((x1, y1, x2, y2), outline=color, width=stroke)
            tag_h = min(22, max(14, int(height * 0.03)))
            tag_y1 = max(0, y1 - tag_h)
            tag_y2 = min(height, y1)
            tag_x2 = min(width, x1 + max(100, len(label) * 8))
            draw.rectangle((x1, tag_y1, tag_x2, tag_y2), fill=color)
            draw.text((x1 + 4, tag_y1 + 2), label, fill="#ffffff")
        return canvas
    except Exception:
        return None


def _build_customer_journey_summary(
    image_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, list[dict[str, object]]]]:
    if image_df.empty:
        return pd.DataFrame(), {}
    events: dict[str, list[dict[str, object]]] = {}
    for _, row in image_df[image_df["timestamp"].notna()].sort_values("timestamp").iterrows():
        customer_ids = [str(x) for x in _safe_json_list(row.get("customer_ids", "[]")) if str(x).strip()]
        for cid in customer_ids:
            events.setdefault(cid, []).append(
                {
                    "timestamp": row.get("timestamp"),
                    "camera_id": str(row.get("camera_id", "")),
                    "filename": str(row.get("filename", "")),
                    "path": str(row.get("path", "")),
                    "drive_link": str(row.get("drive_link", "")),
                    "track_ids": row.get("track_ids", "[]"),
                    "staff_count": int(row.get("staff_count", 0) or 0),
                    "customer_count": int(row.get("customer_count", 0) or 0),
                }
            )

    rows: list[dict[str, object]] = []
    for cid, cid_events in events.items():
        if not cid_events:
            continue
        first_seen = cid_events[0]["timestamp"]
        last_seen = cid_events[-1]["timestamp"]
        duration = 0.0
        if pd.notna(first_seen) and pd.notna(last_seen):
            duration = max(
                0.0,
                float((pd.Timestamp(last_seen) - pd.Timestamp(first_seen)).total_seconds()),
            )
        cameras = sorted({str(evt["camera_id"]) for evt in cid_events if str(evt["camera_id"]).strip()})
        rows.append(
            {
                "customer_id": cid,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "duration_sec": round(duration, 1),
                "frames": len(cid_events),
                "cameras": ",".join(cameras),
                "sample_filename": str(cid_events[0]["filename"]),
            }
        )
    if not rows:
        return pd.DataFrame(), events
    summary = pd.DataFrame(rows).sort_values(["first_seen", "customer_id"]).reset_index(drop=True)
    return summary, events


def _sync_confirmed_feedback_export(db_path: Path) -> Path:
    out_path = db_path.parent / "training" / "qa_feedback_confirmed.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    confirmed = pd.DataFrame(
        list_qa_feedback(db_path=db_path, store_id=None, review_status="confirmed", limit=100000)
    )
    if confirmed.empty:
        confirmed = pd.DataFrame(
            columns=[
                "id",
                "store_id",
                "capture_date",
                "filename",
                "camera_id",
                "track_id",
                "predicted_label",
                "corrected_label",
                "confidence",
                "needs_review",
                "review_status",
                "comment",
                "actor_email",
                "reviewer_email",
                "created_at",
                "reviewed_at",
            ]
        )
    confirmed.to_csv(out_path, index=False)
    return out_path


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
    image_df = _normalize_image_df(store_result.image_insights)
    hotspot_df = store_result.camera_hotspots.copy()

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
    auth_token = str(st.session_state.get("session_token", "")).strip()
    query_extra = f"&auth={quote(auth_token)}" if auth_token else ""
    st.markdown(
        f'<a href="?module=Reports&section=Business%20Health&page=Customer%20Journeys&store={quote(selected_store)}{query_extra}" target="_blank">Open Unique Customer IDs for verification</a>',
        unsafe_allow_html=True,
    )
    cols2 = st.columns(3)
    cols2[0].metric("Daily Walk-ins (Actual)", int(row.get("daily_walkins", 0)))
    cols2[1].metric("Daily Conversions", int(row.get("daily_conversions", 0)))
    cols2[2].metric("Daily Conversion Rate", f"{float(row.get('daily_conversion_rate', 0.0)):.2%}")

    if hasattr(store_result, "daily_report") and not store_result.daily_report.empty:
        st.markdown("**Daily Walk-in & Conversion Report**")
        st.dataframe(store_result.daily_report, use_container_width=True)

    daily_proof_df = (
        store_result.daily_proof.copy()
        if hasattr(store_result, "daily_proof") and not store_result.daily_proof.empty
        else pd.DataFrame()
    )
    if daily_proof_df.empty:
        # Fallback proof view from frame-level data if proof export is not present.
        fallback = (
            image_df.groupby("capture_date", as_index=False)
            .agg(
                total_images=("filename", "count"),
                valid_images=("is_valid", "sum"),
                relevant_images=("relevant", "sum"),
                total_detected_people=("person_count", "sum"),
            )
            .rename(columns={"capture_date": "date"})
            .sort_values("date", ascending=False)
        )
        if not fallback.empty:
            fallback["store_id"] = selected_store
            fallback["folder_name"] = fallback["date"]
            fallback["individual_people"] = 0
            fallback["group_people"] = 0
            fallback["converted"] = 0
            fallback["conversion_rate"] = 0.0
            daily_proof_df = fallback[
                [
                    "store_id",
                    "date",
                    "folder_name",
                    "total_images",
                    "valid_images",
                    "relevant_images",
                    "total_detected_people",
                    "individual_people",
                    "group_people",
                    "converted",
                    "conversion_rate",
                ]
            ]

    if not daily_proof_df.empty:
        st.markdown("**Daily Calculation Proof (Folder Date Based)**")
        date_options = daily_proof_df["date"].astype(str).tolist()
        selected_date = st.selectbox(
            "Proof Date",
            options=date_options,
            index=0,
            key=f"proof_date_{selected_store}",
        )
        proof_row = daily_proof_df[daily_proof_df["date"].astype(str) == str(selected_date)].iloc[0]
        proof_cols = st.columns(4)
        proof_cols[0].metric("Images", int(proof_row.get("total_images", 0)))
        proof_cols[1].metric("Individual People", int(proof_row.get("individual_people", 0)))
        proof_cols[2].metric("Group People", int(proof_row.get("group_people", 0)))
        proof_cols[3].metric("Converted", int(proof_row.get("converted", 0)))
        st.caption(
            f"Folder: {proof_row.get('folder_name', selected_date)} | "
            f"Detected People: {int(proof_row.get('total_detected_people', 0))} | "
            f"Conversion Rate: {float(proof_row.get('conversion_rate', 0.0)):.2%}"
        )
        st.dataframe(daily_proof_df, use_container_width=True, hide_index=True)
        proof_frames = image_df[image_df["capture_date"].astype(str) == str(selected_date)].copy()
        if not proof_frames.empty:
            st.markdown("**Frame-Level Proof for Selected Date**")
            proof_columns = [
                "capture_date",
                "source_folder",
                "timestamp",
                "filename",
                "camera_id",
                "person_count",
                "relevant",
                "track_ids",
                "group_ids",
                "customer_ids",
                "detection_error",
            ]
            st.dataframe(proof_frames[proof_columns].sort_values("timestamp"), use_container_width=True, hide_index=True)

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


def _render_qa_timeline(output: AnalysisOutput, db_path: Path, active_email: str) -> None:
    st.subheader("Operator QA Timeline")
    if not output.stores:
        st.info("No store analysis loaded.")
        return

    store_ids = sorted(output.stores.keys())
    preselected_store = _query_value("store", "").strip()
    default_index = store_ids.index(preselected_store) if preselected_store in store_ids else 0
    sid = st.selectbox("QA store", options=store_ids, index=default_index, key="qa_store")
    image_df = _normalize_image_df(output.stores[sid].image_insights)
    if image_df.empty:
        st.info("No image rows available for this store.")
        return

    image_df = image_df.sort_values("timestamp", ascending=False).reset_index(drop=True)
    image_df["predicted_label"] = image_df.apply(_predicted_label, axis=1)
    image_df["track_count"] = image_df["track_ids"].map(lambda x: len(_safe_json_list(x)))
    unique_ids = sorted(
        {
            str(cid)
            for ids in image_df["customer_ids"].tolist()
            for cid in _safe_json_list(ids)
            if str(cid).strip()
        }
    )

    top_cols = st.columns(4)
    top_cols[0].metric("Frames", int(len(image_df)))
    top_cols[1].metric("Detected People", int(image_df["person_count"].sum()))
    top_cols[2].metric("Unique Customer IDs", int(len(unique_ids)))
    top_cols[3].metric("Frames With Drive Link", int((image_df["drive_link"].fillna("") != "").sum()))

    auth_token = str(st.session_state.get("session_token", "")).strip()
    extra_auth = f"&auth={quote(auth_token)}" if auth_token else ""
    st.markdown(
        f'<a href="?module=Reports&section=Business%20Health&page=Customer%20Journeys&store={quote(sid)}{extra_auth}" target="_blank">Open unique customer verification page</a>',
        unsafe_allow_html=True,
    )

    table_cols = [
        "timestamp",
        "capture_date",
        "camera_id",
        "filename",
        "person_count",
        "staff_count",
        "customer_count",
        "predicted_label",
        "track_ids",
        "drive_link",
        "detection_error",
    ]
    preview_df = image_df[table_cols].head(500).copy()
    preview_df["timestamp"] = preview_df["timestamp"].astype(str)
    try:
        st.dataframe(
            preview_df,
            use_container_width=True,
            height=360,
            hide_index=True,
            column_config={
                "drive_link": st.column_config.LinkColumn("Drive Image", display_text="Open")
            },
        )
    except Exception:
        st.dataframe(preview_df, use_container_width=True, height=360, hide_index=True)
    quick_links = preview_df[preview_df["drive_link"].fillna("").astype(str).str.strip() != ""].head(20)
    if not quick_links.empty:
        st.markdown("**Quick Image Links**")
        for _, row in quick_links.iterrows():
            st.markdown(f"- [{row['filename']}]({row['drive_link']})")

    selector = image_df.head(500).copy()
    selector["row_label"] = selector.apply(
        lambda r: f"{str(r.get('timestamp', 'NA'))} | {str(r.get('camera_id', ''))} | {str(r.get('filename', ''))}",
        axis=1,
    )
    selected_label = st.selectbox(
        "Frame for proof and QA correction",
        options=selector["row_label"].tolist(),
        key=f"qa_frame_selector_{sid}",
    )
    selected_row = selector[selector["row_label"] == selected_label].iloc[0]

    proof_cols = st.columns(2)
    with proof_cols[0]:
        drive_link = str(selected_row.get("drive_link", "")).strip()
        if drive_link:
            if hasattr(st, "link_button"):
                st.link_button("Open Source Image in Google Drive", drive_link)
            else:
                st.markdown(f"[Open Source Image in Google Drive]({drive_link})")
        st.caption(f"File: {selected_row.get('filename', '')}")
        st.caption(f"Camera: {selected_row.get('camera_id', '')}")
        st.caption(f"Predicted: {_predicted_label(selected_row)}")
        st.caption(
            f"People={int(selected_row.get('person_count', 0))}, "
            f"Staff={int(selected_row.get('staff_count', 0))}, "
            f"Customers={int(selected_row.get('customer_count', 0))}"
        )
    with proof_cols[1]:
        overlay_image = _render_overlay_image(selected_row)
        if overlay_image is not None:
            st.image(overlay_image, caption="Overlay: red=staff, blue=customer", use_container_width=True)
        else:
            raw_path = str(selected_row.get("path", "")).strip()
            if raw_path and Path(raw_path).exists():
                st.image(raw_path, caption="Source frame", use_container_width=True)
            else:
                st.caption("Source image not available locally.")

    st.markdown("**Mark Prediction Wrong**")
    st.caption(
        "Corrections are stored first as pending review. Confirmed rows are exported for retraining, so accidental labels can be rejected safely."
    )
    with st.form(f"qa_feedback_form_{sid}", clear_on_submit=False):
        track_ids = [str(x) for x in _safe_json_list(selected_row.get("track_ids", "[]")) if str(x).strip()]
        track_option = st.selectbox(
            "Track ID scope",
            options=["frame"] + track_ids,
            help="Use a specific track ID if only one person in the frame is wrong.",
        )
        predicted_label = st.selectbox(
            "Predicted label",
            options=["customer", "staff", "mixed", "no_person"],
            index=["customer", "staff", "mixed", "no_person"].index(_predicted_label(selected_row)),
        )
        corrected_label = st.selectbox(
            "Corrected label",
            options=["customer", "staff", "mixed", "no_person"],
            index=0,
        )
        confidence = st.slider("Correction confidence", min_value=0.0, max_value=1.0, value=0.7, step=0.05)
        needs_review = st.checkbox("Require reviewer approval", value=True)
        comment = st.text_input("Comment", value="")
        submit_feedback = st.form_submit_button("Save QA correction")
    if submit_feedback:
        feedback_id = add_qa_feedback(
            db_path=db_path,
            store_id=sid,
            capture_date=str(selected_row.get("capture_date", "")),
            filename=str(selected_row.get("filename", "")),
            camera_id=str(selected_row.get("camera_id", "")),
            track_id="" if track_option == "frame" else str(track_option),
            predicted_label=predicted_label,
            corrected_label=corrected_label,
            confidence=float(confidence),
            needs_review=bool(needs_review),
            actor_email=(active_email or "system@local"),
            comment=comment,
        )
        st.success(f"Saved QA correction #{feedback_id}.")

    st.markdown("**Feedback Review Queue**")
    status_filter = st.selectbox(
        "Feedback status",
        options=["all", "pending", "confirmed", "rejected"],
        index=0,
        key=f"qa_feedback_filter_{sid}",
    )
    feedback_rows = list_qa_feedback(
        db_path=db_path,
        store_id=sid,
        review_status=None if status_filter == "all" else status_filter,
        limit=500,
    )
    if not feedback_rows:
        st.caption("No feedback records yet.")
        return
    feedback_df = pd.DataFrame(feedback_rows)
    st.dataframe(feedback_df, use_container_width=True, hide_index=True)
    pending_df = feedback_df[feedback_df["review_status"].astype(str).str.lower() == "pending"].copy()
    if pending_df.empty:
        export_path = _sync_confirmed_feedback_export(db_path=db_path)
        st.caption(f"Confirmed feedback export: {export_path}")
        return

    review_cols = st.columns(3)
    with review_cols[0]:
        selected_feedback_id = st.selectbox(
            "Pending feedback ID",
            options=pending_df["id"].astype(int).tolist(),
            key=f"qa_feedback_id_{sid}",
        )
    with review_cols[1]:
        if st.button("Confirm selected", key=f"qa_confirm_{sid}"):
            update_qa_feedback_review(
                db_path=db_path,
                feedback_id=int(selected_feedback_id),
                review_status="confirmed",
                reviewer_email=(active_email or "system@local"),
            )
            _sync_confirmed_feedback_export(db_path=db_path)
            st.success(f"Feedback #{selected_feedback_id} confirmed.")
            st.rerun()
    with review_cols[2]:
        if st.button("Reject selected", key=f"qa_reject_{sid}"):
            update_qa_feedback_review(
                db_path=db_path,
                feedback_id=int(selected_feedback_id),
                review_status="rejected",
                reviewer_email=(active_email or "system@local"),
            )
            st.warning(f"Feedback #{selected_feedback_id} rejected.")
            st.rerun()


def _render_customer_journeys(output: AnalysisOutput) -> None:
    st.subheader("Customer Journey Verification")
    if not output.stores:
        st.info("No store analysis loaded.")
        return
    store_ids = sorted(output.stores.keys())
    preselected_store = _query_value("store", "").strip()
    default_index = store_ids.index(preselected_store) if preselected_store in store_ids else 0
    sid = st.selectbox("Store", options=store_ids, index=default_index, key="journey_store")
    image_df = _normalize_image_df(output.stores[sid].image_insights)
    summary_df, events = _build_customer_journey_summary(image_df=image_df)
    if summary_df.empty:
        st.info("No unique customer IDs available yet. Run analysis and ensure relevant frames exist.")
        return

    st.caption("Unique IDs are derived from tracked detections across camera frames.")
    limit = st.selectbox("Customer IDs to display", options=[20, 50, 100, 200], index=0)
    show_df = summary_df.head(int(limit)).copy()
    show_df["first_seen"] = show_df["first_seen"].astype(str)
    show_df["last_seen"] = show_df["last_seen"].astype(str)
    st.dataframe(show_df, use_container_width=True, hide_index=True)

    selected_customer = st.selectbox(
        "Customer ID for frame-by-frame proof",
        options=summary_df["customer_id"].tolist(),
        index=0,
        key=f"journey_customer_{sid}",
    )
    customer_events = events.get(str(selected_customer), [])
    if not customer_events:
        st.caption("No timeline events available for this customer.")
        return
    events_df = pd.DataFrame(customer_events)
    events_df["timestamp"] = pd.to_datetime(events_df["timestamp"], errors="coerce")
    events_df["timestamp"] = events_df["timestamp"].astype(str)
    try:
        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
            column_config={"drive_link": st.column_config.LinkColumn("Drive Image", display_text="Open")},
        )
    except Exception:
        st.dataframe(events_df, use_container_width=True, hide_index=True)

    st.markdown("**Visual Verification**")
    gallery_cols = st.columns(4)
    for idx, evt in enumerate(customer_events[:20]):
        caption = f"{evt.get('timestamp')} | {evt.get('camera_id')} | {evt.get('filename')}"
        with gallery_cols[idx % 4]:
            path = str(evt.get("path", "")).strip()
            if path and Path(path).exists():
                st.image(path, caption=caption, use_container_width=True)
            else:
                link = str(evt.get("drive_link", "")).strip()
                if link:
                    st.markdown(f"[{evt.get('filename', 'Open frame')}]({link})")
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
    synced_gdrive = list_synced_stores(db_path=db_path, provider_filter="gdrive")
    stores = list_stores(db_path)
    if synced_gdrive:
        st.markdown("**Registered Stores (Synced to Google Drive)**")
        st.dataframe(pd.DataFrame(synced_gdrive), use_container_width=True)
        with st.expander("Show all mapped stores"):
            all_df = pd.DataFrame([store.__dict__ for store in stores])
            all_df["source_provider"] = all_df["drive_folder_url"].map(detect_source_provider)
            st.dataframe(all_df, use_container_width=True)
    elif stores:
        st.info("No Google Drive store has completed sync yet.")
        all_df = pd.DataFrame([store.__dict__ for store in stores])
        all_df["source_provider"] = all_df["drive_folder_url"].map(detect_source_provider)
        st.dataframe(all_df, use_container_width=True)
    else:
        st.info("No stores registered yet.")

    with st.form("store_create_update_form", clear_on_submit=False):
        st.markdown("**Add / Update Store Mapping**")
        store_id = st.text_input("Store ID (unique)", value="")
        store_name = st.text_input("Store Name", value="")
        email = st.text_input("Store Email", value="")
        drive_folder_url = st.text_input(
            "Source URL",
            value="",
            help=(
                "Supported: Google Drive folder URL, s3://bucket/prefix, "
                "S3 HTTPS URL, or local folder path."
            ),
        )
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
                        ok, message = sync_store_from_drive(matched[0], data_root=data_root, db_path=db_path)
                        if ok:
                            st.info(message)
                        else:
                            st.warning(message)
            except Exception as exc:
                st.error(str(exc))

    st.markdown("**Sync Store Snapshots From Source**")
    stores = list_stores(db_path)
    if stores:
        sync_store_id = st.selectbox(
            "Select store to sync",
            options=[s.store_id for s in stores],
            key="sync_store_selector",
        )
        if st.button("Sync Selected Store", key="sync_selected_store_button"):
            store_record = [s for s in stores if s.store_id == sync_store_id][0]
            ok, message = sync_store_from_drive(store_record, data_root=data_root, db_path=db_path)
            if ok:
                st.success(message)
            else:
                st.warning(message)
    else:
        st.caption("Create a store first to sync from source.")

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
    st.caption(
        "On save, store login is auto-created using Store Email + default password from Organisation settings."
    )
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
        help="Select a store to auto-fill Store Name, Store Email, and current source URL.",
    )
    if selected_edit and selected_edit != st.session_state.get("map_store_id", ""):
        st.session_state["map_store_id"] = selected_edit

    st.text_input("Store ID (unique)", key="map_store_id")
    current_sid = st.session_state["map_store_id"].strip()
    if current_sid and current_sid != st.session_state.get("map_last_store_id", ""):
        _prefill_store_mapping_fields(db_path=db_path, store_id=current_sid)

    st.text_input("Store Name", key="map_store_name")
    st.text_input("Store Email", key="map_store_email")
    st.text_input(
        "Source URL",
        key="map_drive_url",
        help=(
            "Supported: Google Drive folder URL, s3://bucket/prefix, "
            "S3 HTTPS URL, or local folder path."
        ),
    )

    existing_drive = st.session_state.get("map_existing_drive_url", "").strip()
    new_drive = st.session_state.get("map_drive_url", "").strip()
    drive_changed = bool(existing_drive and new_drive and existing_drive != new_drive)
    if existing_drive:
        st.caption(f"Current Source URL: {existing_drive}")
    if drive_changed:
        st.checkbox(
            "Replace existing source URL for this store",
            key="map_replace_drive_url",
            help="Required when updating an existing store to a different source URL.",
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
                    ok, message = sync_store_from_drive(matched[0], data_root=data_root, db_path=db_path)
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
            ok, message = sync_store_from_drive(matched[0], data_root=data_root, db_path=db_path)
            if ok:
                st.success(message)
            else:
                st.warning(message)

    if stores:
        synced_gdrive = list_synced_stores(db_path=db_path, provider_filter="gdrive")
        if synced_gdrive:
            st.markdown("**Registered Stores (Synced to Google Drive)**")
            st.dataframe(pd.DataFrame(synced_gdrive), use_container_width=True)
        else:
            st.info("No Google Drive store has completed sync yet.")
        with st.expander("Show all mapped stores"):
            all_df = pd.DataFrame([s.__dict__ for s in stores])
            all_df["source_provider"] = all_df["drive_folder_url"].map(detect_source_provider)
            st.dataframe(all_df, use_container_width=True)
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
    st.caption("Manage company logo, app name, theme, and default account passwords.")
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

    def _preset_label_from_color(value: str) -> str:
        normalized = str(value or "").strip().lower()
        for label, hex_value in COLOR_PRESETS.items():
            if hex_value.lower() == normalized:
                return label
        return "Custom"

    color_choices = list(COLOR_PRESETS.keys()) + ["Custom"]
    app_name_default = settings.get("app_name", "IRIS")
    app_name_options = ["IRIS", "IRIS HQ", "Custom"]
    app_mode_default = app_name_default if app_name_default in {"IRIS", "IRIS HQ"} else "Custom"

    with st.form("org_settings_form", clear_on_submit=False):
        app_mode = st.selectbox(
            "App Name",
            options=app_name_options,
            index=app_name_options.index(app_mode_default),
            help="Displayed in top header beside company logo.",
        )
        app_custom = st.text_input(
            "Custom App Name",
            value=app_name_default if app_mode_default == "Custom" else "",
            disabled=app_mode != "Custom",
            help="Enter a custom app name only when App Name is set to Custom.",
        )
        selected_font = st.selectbox(
            "Font Family",
            options=font_options,
            index=font_options.index(settings.get("font_family", "Segoe UI")),
            help="Controls overall application font family.",
        )
        bg_label = st.selectbox(
            "Background Color",
            options=color_choices,
            index=color_choices.index(_preset_label_from_color(settings.get("background_color", "#f4f6f8"))),
            help="Main app background color.",
        )
        bg_custom = st.color_picker(
            "Background Color (Custom)",
            value=settings.get("background_color", "#f4f6f8"),
            disabled=bg_label != "Custom",
            help="Used only when Background Color is set to Custom.",
        )
        surface_label = st.selectbox(
            "Surface Color",
            options=color_choices,
            index=color_choices.index(_preset_label_from_color(settings.get("surface_color", "#ffffff"))),
            help="Card and panel background color.",
        )
        surface_custom = st.color_picker(
            "Surface Color (Custom)",
            value=settings.get("surface_color", "#ffffff"),
            disabled=surface_label != "Custom",
            help="Used only when Surface Color is set to Custom.",
        )
        nav_label = st.selectbox(
            "Navigation Color",
            options=color_choices,
            index=color_choices.index(_preset_label_from_color(settings.get("nav_color", "#1f3044"))),
            help="Top navigation bar background color.",
        )
        nav_custom = st.color_picker(
            "Navigation Color (Custom)",
            value=settings.get("nav_color", "#1f3044"),
            disabled=nav_label != "Custom",
            help="Used only when Navigation Color is set to Custom.",
        )
        accent_label = st.selectbox(
            "Accent Color",
            options=color_choices,
            index=color_choices.index(_preset_label_from_color(settings.get("accent_color", "#2a7fd9"))),
            help="Active tab, hover and highlight color.",
        )
        accent_custom = st.color_picker(
            "Accent Color (Custom)",
            value=settings.get("accent_color", "#2a7fd9"),
            disabled=accent_label != "Custom",
            help="Used only when Accent Color is set to Custom.",
        )
        default_user_password = st.text_input(
            "Default User Password",
            type="password",
            value=settings.get("default_user_password", "ChangeMe123!"),
            help="Default password for auto-created Store/CM/AM users.",
        )
        default_admin_password = st.text_input(
            "Default Admin Password",
            type="password",
            value=settings.get("default_admin_password", "AdminChangeMe123!"),
            help="Default password for auto-created Admin accounts.",
        )
        save_org = st.form_submit_button("Save Organisation Settings", type="primary")

    if save_org:
        app_name = app_custom.strip() if app_mode == "Custom" else app_mode
        if not app_name:
            st.error("App Name cannot be empty.")
            return
        if not default_user_password.strip() or not default_admin_password.strip():
            st.error("Default passwords cannot be empty.")
            return
        if default_user_password.strip() == default_admin_password.strip():
            st.error("Default Admin Password and Default User Password must be different.")
            return
        edited_map: dict[str, str] = {
            "app_name": app_name,
            "font_family": selected_font,
            "background_color": bg_custom if bg_label == "Custom" else COLOR_PRESETS[bg_label],
            "surface_color": surface_custom if surface_label == "Custom" else COLOR_PRESETS[surface_label],
            "nav_color": nav_custom if nav_label == "Custom" else COLOR_PRESETS[nav_label],
            "accent_color": accent_custom if accent_label == "Custom" else COLOR_PRESETS[accent_label],
            "default_user_password": default_user_password.strip(),
            "default_admin_password": default_admin_password.strip(),
        }
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
1. `Operations > Store Mapping`: create store, email, source URL (Google Drive/S3/local).
2. Store login is auto-created using Organisation Default User Password.
3. `Access > Store Access Mapping`: map CM/AM emails to stores.
4. `Access > Password Manager`: set final passwords.
5. `Access > Bulk Access Upload`: use CSV for large updates.
6. `Access > Pipeline Configuration`: run analysis and export updates.

### Quick Hints
- `manager_type=store_user` uses `store_id` or first value from `store_ids`.
- `manager_type=cluster_manager/area_manager` should use `store_ids` with `|` separator.
- Mapping save replaces previous store mapping for that user, so maintenance stays simple.
- Keep Admin and User default passwords different for security.
        """
    )


def _render_pipeline_configuration_controls() -> bool:
    st.subheader("Pipeline Configuration")
    st.caption("Run analysis from this page only. These settings persist across pages.")
    bounce_options = [30, 60, 90, 120, 180, 240, 300]
    session_options = [10, 20, 30, 45, 60, 90, 120]
    image_options = [10, 20, 50, 100, 0]
    if st.session_state.get("ctrl_bounce_threshold_sec") not in bounce_options:
        st.session_state["ctrl_bounce_threshold_sec"] = 120
    if st.session_state.get("ctrl_session_gap_sec") not in session_options:
        st.session_state["ctrl_session_gap_sec"] = 30
    if st.session_state.get("ctrl_max_images_per_store") not in image_options:
        st.session_state["ctrl_max_images_per_store"] = 20
    with st.form("analysis_controls_form", clear_on_submit=False):
        ctrl_cols_1 = st.columns(2)
        ctrl_cols_1[0].text_input(
            "Root Directory",
            key="ctrl_root_str",
            help="Folder containing store folders and date subfolders.",
        )
        ctrl_cols_1[1].text_input(
            "Export Directory",
            key="ctrl_out_str",
            help="Location where analysis CSV exports are written.",
        )

        ctrl_cols_2 = st.columns(5)
        ctrl_cols_2[0].slider(
            "Detection Confidence",
            min_value=0.05,
            max_value=0.9,
            step=0.05,
            key="ctrl_conf_threshold",
            help="Minimum confidence for counting detections.",
        )
        ctrl_cols_2[1].selectbox(
            "Time Bucket (Minutes)",
            options=[1, 5, 15],
            key="ctrl_time_bucket_minutes",
            help="Bucket size used in time-trend charts.",
        )
        ctrl_cols_2[2].selectbox(
            "Bounce Threshold (Seconds)",
            options=bounce_options,
            key="ctrl_bounce_threshold_sec",
            help="Visits below this dwell threshold are treated as bounce.",
        )
        ctrl_cols_2[3].selectbox(
            "Session Gap (Seconds)",
            options=session_options,
            key="ctrl_session_gap_sec",
            help="Gap threshold to split sessions.",
        )
        ctrl_cols_2[4].selectbox(
            "Images Per Store",
            options=image_options,
            key="ctrl_max_images_per_store",
            help="Use 0 to process all images.",
        )

        ctrl_cols_3 = st.columns(5)
        yolo_available = _is_yolo_available()
        tf_frcnn_available = _is_tf_frcnn_available()
        detector_options = ["yolo", "tf_frcnn", "mock"] if yolo_available else ["mock", "tf_frcnn", "yolo"]
        if st.session_state["ctrl_detector_type"] not in detector_options:
            st.session_state["ctrl_detector_type"] = detector_options[0]
        ctrl_cols_3[0].selectbox(
            "Detector",
            options=detector_options,
            key="ctrl_detector_type",
            help="YOLO (recommended), TF_FRCNN (legacy TensorFlow), MOCK (testing).",
        )
        ctrl_cols_3[1].selectbox(
            "Write Gzip CSV",
            options=["Yes", "No"],
            index=0 if bool(st.session_state.get("ctrl_write_gzip_exports", True)) else 1,
            key="cfg_write_gzip_select",
            help="Write compressed `.csv.gz` exports.",
        )
        ctrl_cols_3[2].selectbox(
            "Keep Plain CSV",
            options=["Yes", "No"],
            index=0 if bool(st.session_state.get("ctrl_keep_plain_csv", True)) else 1,
            key="cfg_keep_plain_select",
            help="Keep normal `.csv` files along with gzip exports.",
        )
        ctrl_cols_3[3].selectbox(
            "Auto-Sync Sources",
            options=["Yes", "No"],
            index=0 if bool(st.session_state.get("ctrl_auto_sync_linked_drives", True)) else 1,
            key="cfg_auto_sync_drives_select",
            help="Sync mapped source URLs (Drive/S3/local) before analysis.",
        )
        ctrl_cols_3[4].selectbox(
            "Auto-Sync On Save",
            options=["Yes", "No"],
            index=0 if bool(st.session_state.get("ctrl_auto_sync_on_save", False)) else 1,
            key="cfg_auto_sync_on_save_select",
            help="Sync a store right after saving store mapping.",
        )
        rerun_clicked = st.form_submit_button("Regenerate Analysis + CSV", type="primary")
        if not yolo_available:
            st.caption("YOLO not installed in this runtime. Using `mock` is recommended.")
        if not tf_frcnn_available:
            st.caption(
                "TF_FRCNN not ready. Requires TensorFlow and a frozen graph at "
                "`data/models/frozen_inference_graph.pb` (or `TF_FRCNN_MODEL_PATH`)."
            )

    st.session_state["ctrl_write_gzip_exports"] = st.session_state.get("cfg_write_gzip_select", "Yes") == "Yes"
    st.session_state["ctrl_keep_plain_csv"] = st.session_state.get("cfg_keep_plain_select", "Yes") == "Yes"
    st.session_state["ctrl_auto_sync_linked_drives"] = st.session_state.get("cfg_auto_sync_drives_select", "Yes") == "Yes"
    st.session_state["ctrl_auto_sync_on_save"] = st.session_state.get("cfg_auto_sync_on_save_select", "No") == "Yes"
    return bool(rerun_clicked)

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
    org_settings = _effective_org_settings(get_app_settings(db_path))
    ensure_default_admins(
        db_path,
        ["vishal.nayak@kushals.com", "mayur.pathak@kushals.com"],
        default_password=org_settings.get("default_admin_password", "AdminChangeMe123!"),
    )
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

    rerun_clicked = False
    if current_page == "Pipeline Configuration":
        rerun_clicked = _render_pipeline_configuration_controls()

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
                    ok, message = sync_store_from_drive(store, data_root=root_dir, db_path=db_path)
                    sync_messages.append(("OK: " if ok else "WARN: ") + message)
                if sync_messages:
                    st.caption("Source sync status:")
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
                employee_assets_root=employee_assets_root,
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

    if current_page == "Pipeline Configuration":
        st.caption("Use the configuration form above to run analysis.")
    elif current_page == "Overview":
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
    elif current_page == "Customer Journeys":
        _render_customer_journeys(view_output)
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
        _render_qa_timeline(output=view_output, db_path=db_path, active_email=active_email)

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

if __name__ == "__main__":
    main()

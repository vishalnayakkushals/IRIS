from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote, unquote_plus

import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from iris.iris_analysis import (
    AnalysisOutput,
    IMAGE_EXTENSIONS,
    analyze_root,
    export_analysis,
    export_store_day_artifacts,
    load_exports,
    parse_filename,
)
from iris.onfly_pipeline import OnFlyConfig, run_onfly_pipeline
from iris.store_registry import (
    add_qa_feedback,
    add_false_positive_signature,
    add_employee_image,
    bulk_upsert_store_access_rows,
    camera_config_map,
    create_user_session,
    delete_location_master,
    delete_role,
    create_role,
    create_user,
    delete_employee,
    delete_store,
    ensure_default_admins,
    ensure_store_login,
    get_app_settings,
    get_onfly_report_index,
    get_store_master_by_id,
    get_user_by_session_token,
    get_store_by_email,
    init_db,
    list_synced_stores,
    list_qa_feedback,
    list_false_positive_signatures,
    list_user_activity,
    log_user_activity,
    list_camera_configs,
    list_employees,
    list_location_master,
    list_onfly_pipeline_run_events,
    list_onfly_pipeline_runs,
    list_permission_codes,
    list_roles,
    list_model_versions,
    list_store_master,
    list_stores,
    list_users,
    revoke_user_session,
    authenticate_user,
    detect_source_provider,
    set_employee_active,
    set_role_permissions,
    set_user_password,
    sync_store_from_drive,
    register_model_version,
    promote_model_version,
    parse_drive_folder_id,
    update_qa_feedback_review,
    update_qa_feedback_entry,
    upsert_camera_config,
    upsert_location_master,
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
        "Business Health": ["Overview", "Model Accuracy", "Store Detail", "Report Module", "Frame Review", "Customer Journeys"],
    },
    "Access": {
        "Administration": [
            "Organisation",
            "Config",
            "Users",
            "Password Manager",
            "Role Permissions",
            "Store Access Mapping",
            "Setup Help",
            "Activity Logs",
        ],
    },
    "Operations": {
        "Store Setup": ["Store Mapping", "Store Camera Mapping", "Store Master"],
        "Workforce": ["Employee Management"],
        "Pipeline": ["Manual data sync of IRIS"],
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
    "Pipeline Configuration": "Config",
    "Pipeline Journey": "Manual data sync of IRIS",
    "Store Admin": "Store Mapping",
    "Auth/RBAC": "Role Permissions",
    "Camera Zones": "Store Camera Mapping",
    "Licenses": "Organisation",
    "Alert Routes": "Organisation",
    "Quality": "Report Module",
    "QA Timeline": "Frame Review",
    "Model QA": "Model Accuracy",
}

PIPELINE_PRESET_DEFAULT = "Full Scan (Dev)"
PIPELINE_PRESETS: dict[str, dict[str, object]] = {
    "Full Scan (Dev)": {
        "ctrl_max_images_per_store": 0,
        "ctrl_enable_age_gender": False,
        "ctrl_auto_sync_linked_drives": True,
        "ctrl_auto_sync_on_save": False,
        "ctrl_detector_type": "yolo",
        "ctrl_conf_threshold": 0.25,
        "ctrl_bounce_threshold_sec": 120,
        "ctrl_session_gap_sec": 30,
        "ctrl_session_timeout_sec": 180,
        "ctrl_time_bucket_minutes": 1,
    },
    "Test": {
        "ctrl_max_images_per_store": 0,
        "ctrl_enable_age_gender": False,
        "ctrl_auto_sync_linked_drives": False,
        "ctrl_auto_sync_on_save": False,
        "ctrl_detector_type": "yolo",
        "ctrl_conf_threshold": 0.25,
        "ctrl_bounce_threshold_sec": 120,
        "ctrl_session_gap_sec": 30,
        "ctrl_session_timeout_sec": 180,
        "ctrl_time_bucket_minutes": 5,
    },
    "Custom": {},
}

CONFIG_DEFAULTS: dict[str, str] = {
    "cfg_feedback_auto_confirm": "1",
    "cfg_feedback_batch_confidence": "0.90",
    "cfg_feedback_fast_edit_mode": "1",
    "cfg_feedback_hide_reviewed": "1",
    "cfg_feedback_rerun_after_save": "0",
    "cfg_retrain_min_rows": "10",
    "cfg_scheduler_enabled": "1",
    "cfg_scheduler_interval_minutes": "30",
    "cfg_scheduler_buffer_minutes": "5",
    "cfg_scheduler_task_sync_enabled": "1",
    "cfg_scheduler_task_feedback_enabled": "1",
    "cfg_scheduler_task_retrain_enabled": "1",
    "cfg_scheduler_task_predict_enabled": "1",
    "cfg_scheduler_task_refresh_enabled": "1",
    "cfg_scheduler_est_sync_minutes": "3",
    "cfg_scheduler_est_feedback_minutes": "2",
    "cfg_scheduler_est_retrain_minutes": "4",
    "cfg_scheduler_est_predict_minutes": "4",
    "cfg_scheduler_est_refresh_minutes": "2",
    "cfg_scheduler_next_run_at": "",
    "cfg_scheduler_last_run_at": "",
    "cfg_scheduler_last_summary_json": "",
}


def _setting_bool(settings: dict[str, str], key: str, default: bool) -> bool:
    raw = str(settings.get(key, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _setting_int(settings: dict[str, str], key: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(float(str(settings.get(key, default) or default).strip()))
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(int(minimum), value)
    if maximum is not None:
        value = min(int(maximum), value)
    return value


def _setting_float(settings: dict[str, str], key: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(str(settings.get(key, default) or default).strip())
    except Exception:
        value = float(default)
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _scheduler_min_interval_minutes(settings: dict[str, str]) -> int:
    task_pairs = [
        ("cfg_scheduler_task_sync_enabled", "cfg_scheduler_est_sync_minutes"),
        ("cfg_scheduler_task_feedback_enabled", "cfg_scheduler_est_feedback_minutes"),
        ("cfg_scheduler_task_retrain_enabled", "cfg_scheduler_est_retrain_minutes"),
        ("cfg_scheduler_task_predict_enabled", "cfg_scheduler_est_predict_minutes"),
        ("cfg_scheduler_task_refresh_enabled", "cfg_scheduler_est_refresh_minutes"),
    ]
    total = 0
    for enabled_key, estimate_key in task_pairs:
        if _setting_bool(settings, enabled_key, True):
            total += _setting_int(settings, estimate_key, 1, minimum=1, maximum=180)
    buffer_minutes = _setting_int(settings, "cfg_scheduler_buffer_minutes", 5, minimum=0, maximum=120)
    return int(total + buffer_minutes)


def _parse_iso_utc(raw: object) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _ensure_config_defaults(db_path: Path) -> dict[str, str]:
    settings = get_app_settings(db_path)
    missing = {k: v for k, v in CONFIG_DEFAULTS.items() if str(settings.get(k, "")).strip() == ""}
    if missing:
        upsert_app_settings(db_path=db_path, settings=missing)
        settings = get_app_settings(db_path)
    return settings

PAGE_TO_PATH: dict[str, tuple[str, str]] = {
    page: (module, section)
    for module, sections in NAV_TREE.items()
    for section, pages in sections.items()
    for page in pages
}


def _is_yolo_available() -> bool:
    return importlib.util.find_spec("ultralytics") is not None


def _is_tf_frcnn_available() -> bool:
    model_path = os.getenv("TF_FRCNN_MODEL_PATH", "data/models/frozen_inference_graph.pb").strip()
    if not Path(model_path).exists():
        return False
    return importlib.util.find_spec("tensorflow") is not None


def _is_deepface_available() -> bool:
    # Avoid importing DeepFace during UI render; import can trigger heavy TF initialization.
    return importlib.util.find_spec("deepface") is not None


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


def _query_value(name: str, default: str = "", decode_plus: bool = False) -> str:
    value = st.query_params.get(name, default)
    text = ""
    if isinstance(value, list):
        text = str(value[0]) if value else default
    else:
        text = str(value)
    if decode_plus:
        try:
            return unquote_plus(text)
        except Exception:
            return text
    return text


def _resolve_menu_from_query() -> tuple[str, str, str]:
    module_names = list(NAV_TREE.keys())
    raw_page_param = _query_value("page", "", decode_plus=True).strip()
    page_param = LEGACY_PAGE_ALIAS.get(raw_page_param, raw_page_param)
    if page_param in PAGE_TO_PATH:
        module, section = PAGE_TO_PATH[page_param]
        return module, section, page_param

    module = _query_value("module", module_names[0], decode_plus=True).strip()
    if module not in NAV_TREE:
        module = module_names[0]

    sections = NAV_TREE[module]
    section_names = list(sections.keys())
    section = _query_value("section", section_names[0], decode_plus=True).strip()
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
    padding: 0.35rem 0.55rem;
    margin: 0 0 0.3rem 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    min-height: 56px;
}}
.iris-brand-fallback {{
    width: 42px;
    height: 42px;
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
.iris-header-logo {{
    width: 42px;
    height: 42px;
    object-fit: contain;
    border-radius: 6px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    padding: 2px;
}}
.iris-nav .iris-menu {{background: {nav};}}
.iris-nav .iris-module.active .iris-module-label, .iris-nav .iris-module:hover .iris-module-label {{background: {accent};}}
div[data-testid="stWidgetLabel"] p {{
    font-weight: 700;
}}
.iris-hover-list {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 0.55rem;
}}
.iris-hover-item {{
    position: relative;
    background: #ffffff;
    border: 1px solid #d7dee8;
    border-radius: 8px;
    padding: 0.45rem 0.55rem;
}}
.iris-hover-item a {{
    text-decoration: none;
}}
.iris-hover-card {{
    display: none;
    position: absolute;
    left: 0;
    top: calc(100% + 4px);
    width: 220px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    box-shadow: 0 12px 24px rgba(15, 23, 42, 0.25);
    padding: 0.4rem;
    z-index: 1200;
}}
.iris-hover-card img {{
    width: 100%;
    border-radius: 6px;
}}
.iris-hover-item:hover .iris-hover-card {{
    display: block;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _resolve_logo_file(logo_path: str) -> Path | None:
    raw = str(logo_path or "").strip()
    if not raw:
        return None
    app_root = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []
    p = Path(raw).expanduser()
    candidates.append(p)
    if not p.is_absolute():
        candidates.append((app_root / p).resolve())
    # If absolute path is stale (e.g., moved local->docker), recover by basename from branding dir.
    candidates.append(app_root / "data" / "branding" / Path(raw).name)
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _render_brand_identity(app_name: str, logo_path: str) -> None:
    app_label = (str(app_name or "").strip() or "IRIS")[:60]
    logo_file = _resolve_logo_file(logo_path=logo_path)
    brand_cols = st.columns([1, 7], gap="small")
    with brand_cols[0]:
        if logo_file:
            try:
                st.image(str(logo_file), width=54)
            except Exception:
                st.markdown('<div class="iris-brand-fallback">IR</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="iris-brand-fallback">IR</div>', unsafe_allow_html=True)
    with brand_cols[1]:
        st.markdown(f"### {app_label}")


def _frame_review_link(store_id: str, frame_idx: int, auth_token: str) -> str:
    params = [
        f"module={quote('Reports')}",
        f"section={quote('Business Health')}",
        f"page={quote('Frame Review')}",
        f"store={quote(str(store_id).strip())}",
        f"frame_idx={int(frame_idx)}",
    ]
    token = str(auth_token or "").strip()
    if token:
        params.append(f"auth={quote(token)}")
    return "?" + "&".join(params)


def _frame_review_identity_link(store_id: str, filename: str, timestamp: str, auth_token: str) -> str:
    params = [
        f"module={quote('Reports')}",
        f"section={quote('Business Health')}",
        f"page={quote('Frame Review')}",
        f"store={quote(str(store_id).strip())}",
    ]
    file_name = str(filename or "").strip()
    ts_text = str(timestamp or "").strip()
    if file_name:
        params.append(f"frame_file={quote(file_name)}")
    if ts_text and ts_text.lower() != "nat":
        params.append(f"frame_ts={quote(ts_text)}")
    token = str(auth_token or "").strip()
    if token:
        params.append(f"auth={quote(token)}")
    return "?" + "&".join(params)


def _hover_preview_data_uri(image_path: Path, max_size: int = 260) -> str:
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=72, optimize=True)
            encoded = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def _pil_image_data_uri(image: Image.Image, max_size: int = 260) -> str:
    try:
        canvas = image.convert("RGB")
        canvas.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=72, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return ""


def _overlay_or_source_preview_uri(row: pd.Series, store_id: str, root_dir: Path, max_size: int = 260) -> str:
    row_for_overlay = row.copy()
    raw_path = str(row_for_overlay.get("path", "") or "").strip()
    if not raw_path:
        resolved = _resolve_row_image_path(row=row_for_overlay, store_id=store_id, root_dir=root_dir)
        if resolved is not None:
            row_for_overlay["path"] = str(resolved)
    overlay = _render_overlay_image(row_for_overlay)
    if overlay is not None:
        return _pil_image_data_uri(overlay, max_size=max_size)
    resolved = _resolve_row_image_path(row=row_for_overlay, store_id=store_id, root_dir=root_dir)
    if resolved is not None:
        return _hover_preview_data_uri(resolved, max_size=max_size)
    return ""


def _render_header_bar(
    app_name: str,
    logo_path: str,
    active_email: str,
    active_full_name: str,
    active_roles: list[str],
    db_path: Path,
    auth_token: str,
) -> str:
    header_cols = st.columns([5, 2], gap="small")
    with header_cols[0]:
        _render_brand_identity(app_name=app_name, logo_path=logo_path)
    with header_cols[1]:
        with st.expander("Profile", expanded=False):
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
    _render_brand_identity(
        app_name=org_settings.get("app_name", "IRIS"),
        logo_path=org_settings.get("logo_path", ""),
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
    db_path: Path,
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
    store_filter: str,
    capture_date_filter: date | None,
    session_timeout_sec: int,
    enable_age_gender: bool,
    export_pilot_store_id: str,
    export_pilot_date: str,
    false_positive_signatures_by_store: dict[str, list[dict[str, object]]] | None = None,
    use_parallel: bool = True,
    use_streaming: bool = True,
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
        store_filter=(store_filter.strip() or None),
        capture_date_filter=capture_date_filter,
        session_timeout_sec=int(session_timeout_sec),
        enable_age_gender=bool(enable_age_gender),
        false_positive_signatures_by_store=false_positive_signatures_by_store,
        use_parallel=bool(use_parallel),
        use_streaming=bool(use_streaming),
    )
    export_analysis(output, out_dir=out_dir, write_gzip_exports=write_gzip_exports, keep_plain_csv=keep_plain_csv)
    sid = export_pilot_store_id.strip()
    cdate = export_pilot_date.strip()
    if sid and cdate:
        export_store_day_artifacts(
            output=output,
            out_dir=out_dir,
            store_id=sid,
            capture_date=cdate,
            write_gzip_exports=write_gzip_exports,
            keep_plain_csv=keep_plain_csv,
        )
    _persist_model_accuracy_snapshot(db_path=db_path, out_dir=out_dir, output=output, source="analysis_run")
    return output


def _model_accuracy_history_path(out_dir: Path) -> Path:
    return out_dir / "model_accuracy_history.csv"


def _pending_retrain_rows_for_store(db_path: Path, store_id: str, settings: dict[str, str]) -> int:
    retrain_key = f"qa_last_retrain_feedback_id__{store_id}"
    try:
        last_retrain_feedback_id = int(str(settings.get(retrain_key, "0") or "0"))
    except Exception:
        last_retrain_feedback_id = 0
    confirmed_rows = list_qa_feedback(db_path=db_path, store_id=store_id, review_status="confirmed", limit=200000)
    return int(len([r for r in confirmed_rows if int(r.get("id", 0) or 0) > last_retrain_feedback_id]))


def _persist_model_accuracy_snapshot(
    *,
    db_path: Path,
    out_dir: Path,
    output: AnalysisOutput,
    source: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    history_path = _model_accuracy_history_path(out_dir=out_dir)
    settings = get_app_settings(db_path)
    now_utc = datetime.now(tz=timezone.utc)
    snapshot_date = now_utc.date().isoformat()
    rows: list[dict[str, object]] = []
    for store_id, result in output.stores.items():
        feedback_rows = list_qa_feedback(db_path=db_path, store_id=store_id, review_status=None, limit=200000)
        image_df = _normalize_image_df(result.image_insights)
        summary, _trend = _build_feedback_accuracy_report(
            feedback_rows=feedback_rows,
            image_df=image_df,
            db_path=db_path,
            store_id=store_id,
        )
        model_key = f"qa_active_model_id__{store_id}"
        active_model_id = str(settings.get(model_key, "baseline_rules_v1") or "baseline_rules_v1")
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "snapshot_ts_utc": now_utc.isoformat(),
                "store_id": store_id,
                "model_id": active_model_id,
                "accuracy_pct": float(summary.get("accuracy_pct", 0.0)),
                "scored_rows": int(summary.get("scored_rows", 0.0)),
                "matched_rows": int(summary.get("matched_rows", 0.0)),
                "mismatch_rows": int(summary.get("mismatch_rows", 0.0)),
                "considered_rows": int(summary.get("considered_rows", 0.0)),
                "pending_retrain_rows": int(_pending_retrain_rows_for_store(db_path=db_path, store_id=store_id, settings=settings)),
                "source": str(source or "unknown"),
            }
        )
    if not rows:
        return history_path

    new_df = pd.DataFrame(rows)
    if history_path.exists():
        try:
            old_df = pd.read_csv(history_path)
        except Exception:
            old_df = pd.DataFrame()
    else:
        old_df = pd.DataFrame()
    merged = pd.concat([old_df, new_df], ignore_index=True)
    key_cols = ["snapshot_date", "store_id", "model_id"]
    merged = merged.drop_duplicates(subset=key_cols, keep="last")
    merged = merged.sort_values(by=["snapshot_date", "store_id", "snapshot_ts_utc"], ascending=[True, True, True]).reset_index(drop=True)
    merged.to_csv(history_path, index=False)
    return history_path


def _load_model_accuracy_history(out_dir: Path) -> pd.DataFrame:
    history_path = _model_accuracy_history_path(out_dir=out_dir)
    if not history_path.exists():
        return pd.DataFrame(
            columns=[
                "snapshot_date",
                "snapshot_ts_utc",
                "store_id",
                "model_id",
                "accuracy_pct",
                "scored_rows",
                "matched_rows",
                "mismatch_rows",
                "considered_rows",
                "pending_retrain_rows",
                "source",
            ]
        )
    try:
        df = pd.read_csv(history_path)
    except Exception:
        return pd.DataFrame()
    if "snapshot_date" in df.columns:
        df["snapshot_date"] = df["snapshot_date"].astype(str)
    for col in ["accuracy_pct", "scored_rows", "matched_rows", "mismatch_rows", "considered_rows", "pending_retrain_rows"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


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


def _export_summary_mtime(out_dir: Path) -> float:
    summary_csv = out_dir / "all_stores_summary.csv"
    summary_gz = out_dir / "all_stores_summary.csv.gz"
    candidate = summary_csv if summary_csv.exists() else summary_gz
    if not candidate.exists():
        return 0.0
    try:
        return float(candidate.stat().st_mtime)
    except Exception:
        return 0.0


def _summary_total_images(output: AnalysisOutput) -> int:
    summary = output.all_stores_summary
    if summary is None or summary.empty or "total_images" not in summary.columns:
        return 0
    return int(pd.to_numeric(summary["total_images"], errors="coerce").fillna(0).sum())


def _count_source_images(root_dir: Path, store_filter: str = "", sample_limit: int = 500000) -> int:
    if not root_dir.exists():
        return 0
    base = root_dir
    if store_filter.strip():
        candidate = root_dir / store_filter.strip()
        if candidate.exists():
            base = candidate
    count = 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            count += 1
            if count >= sample_limit:
                break
    return count


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


def _safe_json_dict(value: object) -> dict[str, float]:
    if isinstance(value, dict):
        out: dict[str, float] = {}
        for key, val in value.items():
            try:
                out[str(key)] = float(val)
            except Exception:
                continue
        return out
    if value is None:
        return {}
    if isinstance(value, float) and pd.isna(value):
        return {}
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, float] = {}
    for key, val in parsed.items():
        try:
            out[str(key)] = float(val)
        except Exception:
            continue
    return out


def _coerce_box(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1 = float(value[0])  # type: ignore[index]
        y1 = float(value[1])  # type: ignore[index]
        x2 = float(value[2])  # type: ignore[index]
        y2 = float(value[3])  # type: ignore[index]
    except Exception:
        return None
    x1, x2 = sorted((max(0.0, min(1.0, x1)), max(0.0, min(1.0, x2))))
    y1, y2 = sorted((max(0.0, min(1.0, y1)), max(0.0, min(1.0, y2))))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _ahash_from_crop(image: Image.Image, box: tuple[float, float, float, float], hash_side: int = 8) -> str:
    width, height = image.size
    x1 = max(0, min(width - 1, int(float(box[0]) * width)))
    y1 = max(0, min(height - 1, int(float(box[1]) * height)))
    x2 = max(x1 + 1, min(width, int(float(box[2]) * width)))
    y2 = max(y1 + 1, min(height, int(float(box[3]) * height)))
    crop = image.crop((x1, y1, x2, y2)).convert("L").resize((hash_side, hash_side))
    arr = pd.Series(list(crop.getdata()), dtype="float64")
    if arr.empty:
        return ""
    avg = float(arr.mean())
    bits = ["1" if float(v) >= avg else "0" for v in arr.tolist()]
    bit_string = "".join(bits)
    if not bit_string:
        return ""
    return f"{int(bit_string, 2):0{(hash_side * hash_side + 3) // 4}x}"


def _learn_false_positive_signatures_from_row(
    db_path: Path,
    store_id: str,
    row: pd.Series,
    root_dir: Path,
    feedback_id: int,
) -> int:
    resolved = _resolve_row_image_path(row=row, store_id=store_id, root_dir=root_dir)
    if resolved is None:
        return 0
    camera_id = str(row.get("camera_id", "") or "").strip()
    person_boxes = [_coerce_box(v) for v in _safe_json_list(row.get("person_boxes", "[]"))]
    boxes = [b for b in person_boxes if b is not None]
    if not boxes:
        return 0
    learned = 0
    try:
        with Image.open(resolved) as img:
            rgb = img.convert("RGB")
            for box in boxes:
                crop_hash = _ahash_from_crop(rgb, box)
                if not crop_hash:
                    continue
                add_false_positive_signature(
                    db_path=db_path,
                    store_id=store_id,
                    camera_id=camera_id,
                    box_json=json.dumps(list(box)),
                    hash64=crop_hash,
                    source_feedback_id=int(feedback_id),
                    hamming_threshold=10,
                )
                learned += 1
    except Exception:
        return 0
    return learned


def _false_positive_signature_map(db_path: Path) -> dict[str, list[dict[str, object]]]:
    rows = list_false_positive_signatures(db_path=db_path, store_id=None, active_only=True, limit=200000)
    by_store: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        sid = str(row.get("store_id", "")).strip()
        if not sid:
            continue
        by_store.setdefault(sid, []).append(
            {
                "camera_id": str(row.get("camera_id", "")).strip(),
                "box_json": str(row.get("box_json", "[]")),
                "hash64": str(row.get("hash64", "")).strip(),
                "hamming_threshold": int(row.get("hamming_threshold", 10) or 10),
            }
        )
    return by_store


def _business_kpi_summary(image_df: pd.DataFrame, customer_sessions_df: pd.DataFrame) -> dict[str, object]:
    scoped_sessions = customer_sessions_df.copy() if not customer_sessions_df.empty else customer_sessions_df
    if scoped_sessions is not None and not scoped_sessions.empty and "session_class" in scoped_sessions.columns:
        scoped_sessions = scoped_sessions[
            scoped_sessions["session_class"].fillna("").astype(str).str.upper().eq("CUSTOMER")
        ].copy()
    if not customer_sessions_df.empty and "is_valid_session" in customer_sessions_df.columns:
        scoped_sessions = scoped_sessions[
            pd.to_numeric(scoped_sessions["is_valid_session"], errors="coerce").fillna(0).astype(int) > 0
        ].copy()
    entries = int(len(scoped_sessions)) if scoped_sessions is not None and not scoped_sessions.empty else 0
    closed_exits = 0
    converted = 0
    bounced = 0
    if scoped_sessions is not None and not scoped_sessions.empty:
        if "close_reason" in scoped_sessions.columns:
            closed_exits = int(
                scoped_sessions["close_reason"].fillna("").astype(str).str.strip().str.lower().eq("exit_crossing").sum()
            )
        elif "status" in scoped_sessions.columns:
            closed_exits = int(
                scoped_sessions["status"].fillna("").astype(str).str.strip().str.upper().eq("EXITED").sum()
            )
        elif "exit_ts" in scoped_sessions.columns:
            closed_exits = int(scoped_sessions["exit_ts"].fillna("").astype(str).str.strip().ne("").sum())
        if "converted_proxy" in scoped_sessions.columns:
            converted = int(pd.to_numeric(scoped_sessions["converted_proxy"], errors="coerce").fillna(0).sum())
        converted = max(0, min(entries, converted))
        bounced = max(0, entries - converted)

    per_customer_gender: dict[str, str] = {}
    per_customer_age: dict[str, str] = {}
    if not image_df.empty:
        relevant_df = image_df[image_df["relevant"] == True].copy()  # noqa: E712
        relevant_df = relevant_df.sort_values("timestamp")
        for _, row in relevant_df.iterrows():
            customer_ids = [str(x) for x in _safe_json_list(row.get("store_day_customer_ids", "[]")) if str(x).strip()]
            if not customer_ids:
                customer_ids = [str(x) for x in _safe_json_list(row.get("customer_ids", "[]")) if str(x).strip()]
            if not customer_ids:
                continue
            gender_scores = _safe_json_dict(row.get("gender_likelihood", "{}"))
            age_scores = _safe_json_dict(row.get("age_bucket_counts", "{}"))
            top_gender = max(gender_scores, key=gender_scores.get) if gender_scores else ""
            top_age = max(age_scores, key=age_scores.get) if age_scores else ""
            for cid in customer_ids:
                if cid not in per_customer_gender and top_gender:
                    per_customer_gender[cid] = str(top_gender).lower()
                if cid not in per_customer_age and top_age:
                    per_customer_age[cid] = str(top_age)

    male = sum(1 for g in per_customer_gender.values() if g.startswith("m"))
    female = sum(1 for g in per_customer_gender.values() if g.startswith("f"))
    known_gender = male + female
    unknown = max(entries - known_gender, 0)

    age_counts: dict[str, int] = {}
    for bucket in per_customer_age.values():
        age_counts[bucket] = age_counts.get(bucket, 0) + 1

    return {
        "entries": entries,
        "closed_exits": closed_exits,
        "converted": converted,
        "bounced": bounced,
        "conversion_rate": (float(converted) / float(entries)) if entries > 0 else None,
        "bounce_rate": (float(bounced) / float(entries)) if entries > 0 else None,
        "gender_counts": {"male": male, "female": female, "unknown": unknown},
        "age_bucket_counts": age_counts,
    }


def _normalize_image_df(image_df: pd.DataFrame) -> pd.DataFrame:
    out = image_df.copy()
    defaults: dict[str, object] = {
        "camera_id": "UNKNOWN",
        "relevant": False,
        "is_valid": False,
        "person_count": 0,
        "staff_count": 0,
        "customer_count": 0,
        "event_label": "",
        "timestamp": pd.NaT,
        "filename": "",
        "path": "",
        "capture_date": "",
        "source_folder": "",
        "track_ids": "[]",
        "customer_ids": "[]",
        "legacy_customer_ids": "[]",
        "store_day_customer_ids": "[]",
        "customer_session_ids": "[]",
        "group_ids": "[]",
        "floor_name": "Ground",
        "location_name": "",
        "person_boxes": "[]",
        "staff_flags": "[]",
        "staff_scores": "[]",
        "gender_likelihood": "{}",
        "age_bucket_counts": "{}",
        "age_confidence": 0.0,
        "age_gender_error": "",
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
    out["floor_name"] = out["floor_name"].fillna("Ground").astype(str)
    out["location_name"] = out["location_name"].fillna("").astype(str)
    out.loc[out["location_name"].str.strip() == "", "location_name"] = out["camera_id"].astype(str)
    return out


def _top_gender_label(gender_payload: object) -> str:
    scores = _safe_json_dict(gender_payload)
    if not scores:
        return "unknown"
    key = str(max(scores, key=scores.get)).strip().lower()
    if key.startswith("m"):
        return "male"
    if key.startswith("f"):
        return "female"
    return "unknown"


def _normalize_validation_role(raw: object) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        return "UNKNOWN"
    if "STAFF" in text:
        return "STAFF"
    if "OUTSIDE" in text:
        return "PEDESTRIANS"
    if "STATIC" in text:
        return "BANNER"
    if "ENTRY_CANDIDATE" in text:
        return "ENTRY_CANDIDATE"
    if "ACTIVE" in text or "EXITED" in text or "CUSTOMER" in text:
        return "CUSTOMER"
    if "INVALID" in text:
        return "INVALID"
    return text


def _validation_preferred_link(
    row: pd.Series,
    store_id: str,
    root_dir: Path,
    auth_token: str,
) -> str:
    drive_link = str(row.get("drive_link", "") or "").strip()
    if drive_link.startswith("http://") or drive_link.startswith("https://"):
        return drive_link
    return _row_image_hyperlink(row=row, store_id=store_id, root_dir=root_dir, auth_token=auth_token)


def _render_validation_console(
    *,
    image_df: pd.DataFrame,
    customer_sessions_df: pd.DataFrame,
    selected_store: str,
    root_dir: Path,
    auth_token: str,
) -> None:
    st.markdown("**Validation Console (D07)**")
    st.caption("Table-first validation for manual verification. Use filters first, then verify proof links.")

    frame_rows = image_df.copy()
    if frame_rows.empty:
        st.info("No image rows available for validation yet. Run analysis to generate frame-level outputs.")
        return

    frame_rows["capture_date"] = frame_rows["capture_date"].fillna("").astype(str)
    frame_rows["camera_id"] = frame_rows["camera_id"].fillna("UNKNOWN").astype(str)
    frame_rows["event_label"] = frame_rows["event_label"].fillna("").astype(str)

    session_rows = customer_sessions_df.copy() if customer_sessions_df is not None else pd.DataFrame()
    if not session_rows.empty:
        for col in ["entry_time", "entry_ts", "last_seen_time", "exit_time", "exit_ts"]:
            if col in session_rows.columns:
                session_rows[col] = pd.to_datetime(session_rows[col], errors="coerce")
        session_rows["capture_date"] = session_rows.get("capture_date", "").fillna("").astype(str)
    else:
        session_rows = pd.DataFrame()

    track_to_person: dict[tuple[str, str, int], str] = {}
    unique_records: dict[str, dict[str, object]] = {}

    if not session_rows.empty:
        for _, srow in session_rows.iterrows():
            capture_date = str(srow.get("capture_date", "")).strip()
            person_id = (
                str(srow.get("session_id", "")).strip()
                or str(srow.get("store_day_customer_id", "")).strip()
                or str(srow.get("track_id_local", "")).strip()
            )
            if not person_id:
                person_id = f"SESSION_{len(unique_records) + 1:06d}"
            role = _normalize_validation_role(
                str(srow.get("session_class", "")).strip() or str(srow.get("status", "")).strip()
            )
            gender = str(srow.get("gender", "")).strip().lower() or "unknown"
            entry_time = pd.to_datetime(
                srow.get("entry_time", srow.get("entry_ts", pd.NaT)),
                errors="coerce",
            )
            exit_time = pd.to_datetime(
                srow.get("exit_time", srow.get("exit_ts", pd.NaT)),
                errors="coerce",
            )
            dwell_seconds = float(pd.to_numeric([srow.get("dwell_seconds", srow.get("dwell_sec", 0.0))], errors="coerce")[0] or 0.0)
            invalid_reason = str(srow.get("invalid_reason", "")).strip()
            converted_proxy = int(pd.to_numeric([srow.get("converted_proxy", 0)], errors="coerce")[0] or 0)
            close_reason = str(srow.get("close_reason", "")).strip().lower()
            bounced = int(role == "CUSTOMER" and (close_reason != "exit_crossing" or invalid_reason != ""))
            cameras_seen = str(srow.get("cameras_seen", "")).strip()
            best_path = (
                str(srow.get("entry_snapshot_path", "")).strip()
                or str(srow.get("entry_image_path", "")).strip()
                or str(srow.get("exit_snapshot_path", "")).strip()
                or str(srow.get("exit_image_path", "")).strip()
            )
            unique_records[person_id] = {
                "Person ID": person_id,
                "Role": role,
                "Gender": gender,
                "Entry Time": entry_time,
                "Exit Time": exit_time,
                "Dwell Time (sec)": round(max(0.0, dwell_seconds), 2),
                "Best Proof Link": "",
                "All Proof Links": "",
                "Best Proof Path": best_path,
                "All Proof Paths": best_path,
                "Capture Date": capture_date,
                "Cameras": cameras_seen,
                "Converted": converted_proxy,
                "Bounced": bounced,
                "Rejection Reason": invalid_reason,
            }

            track_local = str(srow.get("track_id_local", "")).strip()
            if ":" in track_local and capture_date:
                cam, tid_str = track_local.split(":", 1)
                try:
                    tid_val = int(float(tid_str))
                except Exception:
                    tid_val = None
                if tid_val is not None:
                    track_to_person[(capture_date, str(cam).strip().upper(), int(tid_val))] = person_id

    appearance_rows: list[dict[str, object]] = []
    for _, row in frame_rows[frame_rows["timestamp"].notna()].iterrows():
        ts = pd.Timestamp(row["timestamp"])
        day = str(row.get("capture_date", "")).strip() or ts.date().isoformat()
        cam = str(row.get("camera_id", "")).strip().upper()
        role_fallback = _normalize_validation_role(row.get("event_label", ""))
        gender_fallback = _top_gender_label(row.get("gender_likelihood", "{}"))
        proof_link = _validation_preferred_link(
            row=row,
            store_id=selected_store,
            root_dir=root_dir,
            auth_token=auth_token,
        )
        resolved = _resolve_row_image_path(row=row, store_id=selected_store, root_dir=root_dir)
        proof_path = str(resolved) if resolved is not None else str(row.get("path", "")).strip()

        track_ids: list[int] = []
        for item in _safe_json_list(row.get("track_ids", "[]")):
            try:
                track_ids.append(int(item))
            except Exception:
                continue

        if track_ids:
            for tid in track_ids:
                person_id = track_to_person.get((day, cam, int(tid)), "")
                if not person_id:
                    person_id = f"T_{day.replace('-', '')}_{cam}_{int(tid)}"
                unique = unique_records.get(person_id)
                if unique is None:
                    unique = {
                        "Person ID": person_id,
                        "Role": role_fallback,
                        "Gender": gender_fallback,
                        "Entry Time": ts,
                        "Exit Time": ts,
                        "Dwell Time (sec)": 1.0,
                        "Best Proof Link": "",
                        "All Proof Links": "",
                        "Best Proof Path": proof_path,
                        "All Proof Paths": proof_path,
                        "Capture Date": day,
                        "Cameras": cam,
                        "Converted": 0,
                        "Bounced": 0,
                        "Rejection Reason": "",
                    }
                    unique_records[person_id] = unique
                else:
                    role_existing = str(unique.get("Role", "UNKNOWN"))
                    if role_existing in {"UNKNOWN", "ENTRY_CANDIDATE", "INVALID"} and role_fallback not in {"UNKNOWN"}:
                        unique["Role"] = role_fallback
                    if str(unique.get("Gender", "unknown")).strip().lower() in {"", "unknown"} and gender_fallback != "unknown":
                        unique["Gender"] = gender_fallback
                    et = pd.to_datetime(unique.get("Entry Time", pd.NaT), errors="coerce")
                    xt = pd.to_datetime(unique.get("Exit Time", pd.NaT), errors="coerce")
                    unique["Entry Time"] = ts if pd.isna(et) else min(et, ts)
                    unique["Exit Time"] = ts if pd.isna(xt) else max(xt, ts)
                    unique["Capture Date"] = str(unique.get("Capture Date", "")).strip() or day
                    cams = {c.strip() for c in str(unique.get("Cameras", "")).split(",") if c.strip()}
                    cams.add(cam)
                    unique["Cameras"] = ",".join(sorted(cams))

                appearance_rows.append(
                    {
                        "Person ID": person_id,
                        "Date": day,
                        "Camera": cam,
                        "Timestamp": ts,
                        "Role": str(unique_records[person_id].get("Role", role_fallback)),
                        "Gender": str(unique_records[person_id].get("Gender", gender_fallback)),
                        "Proof Link": proof_link,
                        "Proof Path": proof_path,
                    }
                )
        else:
            person_ids = [str(v).strip() for v in _safe_json_list(row.get("store_day_customer_ids", "[]")) if str(v).strip()]
            for person_id in person_ids:
                appearance_rows.append(
                    {
                        "Person ID": person_id,
                        "Date": day,
                        "Camera": cam,
                        "Timestamp": ts,
                        "Role": role_fallback,
                        "Gender": gender_fallback,
                        "Proof Link": proof_link,
                        "Proof Path": proof_path,
                    }
                )

    appearances_df = pd.DataFrame(appearance_rows)
    if appearances_df.empty:
        st.info(
            "Validation data is empty after current run. "
            "Check detector output and rerun analysis for this store/date."
        )
        return

    # Merge proof links and seen counts back into unique records.
    for person_id, grp in appearances_df.groupby("Person ID"):
        links = [str(v).strip() for v in grp["Proof Link"].dropna().astype(str).tolist() if str(v).strip()]
        paths = [str(v).strip() for v in grp["Proof Path"].dropna().astype(str).tolist() if str(v).strip()]
        unique = unique_records.get(person_id)
        if unique is None:
            first_ts = pd.Timestamp(grp["Timestamp"].min())
            last_ts = pd.Timestamp(grp["Timestamp"].max())
            unique = {
                "Person ID": person_id,
                "Role": str(grp["Role"].iloc[0]),
                "Gender": str(grp["Gender"].iloc[0]),
                "Entry Time": first_ts,
                "Exit Time": last_ts,
                "Dwell Time (sec)": max(1.0, float((last_ts - first_ts).total_seconds()) + 1.0),
                "Best Proof Link": links[0] if links else "",
                "All Proof Links": " | ".join(sorted(set(links))[:8]),
                "Best Proof Path": paths[0] if paths else "",
                "All Proof Paths": " | ".join(sorted(set(paths))[:8]),
                "Capture Date": str(grp["Date"].iloc[0]),
                "Cameras": ",".join(sorted(set(grp["Camera"].astype(str).tolist()))),
                "Converted": 0,
                "Bounced": 0,
                "Rejection Reason": "",
            }
            unique_records[person_id] = unique
        else:
            if links and not str(unique.get("Best Proof Link", "")).strip():
                unique["Best Proof Link"] = links[0]
            if paths and not str(unique.get("Best Proof Path", "")).strip():
                unique["Best Proof Path"] = paths[0]
            existing_links = [x.strip() for x in str(unique.get("All Proof Links", "")).split("|") if x.strip()]
            existing_paths = [x.strip() for x in str(unique.get("All Proof Paths", "")).split("|") if x.strip()]
            merged_links = sorted(set(existing_links + links))
            merged_paths = sorted(set(existing_paths + paths))
            unique["All Proof Links"] = " | ".join(merged_links[:8])
            unique["All Proof Paths"] = " | ".join(merged_paths[:8])

    unique_df = pd.DataFrame(unique_records.values())
    if unique_df.empty:
        st.info("No unique person/session records available after filter preparation.")
        return
    unique_df["Entry Time"] = pd.to_datetime(unique_df["Entry Time"], errors="coerce")
    unique_df["Exit Time"] = pd.to_datetime(unique_df["Exit Time"], errors="coerce")
    missing_dwell = pd.to_numeric(unique_df["Dwell Time (sec)"], errors="coerce").fillna(0.0) <= 0.0
    unique_df.loc[missing_dwell, "Dwell Time (sec)"] = (
        unique_df.loc[missing_dwell, "Exit Time"] - unique_df.loc[missing_dwell, "Entry Time"]
    ).dt.total_seconds().fillna(0.0).clip(lower=1.0)

    # Filters
    filter_cols = st.columns(5)
    filter_cols[0].selectbox(
        "Store",
        options=[selected_store],
        index=0,
        key=f"val_store_{selected_store}",
        disabled=True,
    )
    date_options = ["(All)"] + sorted([d for d in appearances_df["Date"].dropna().astype(str).unique().tolist() if d.strip()])
    selected_date = filter_cols[1].selectbox(
        "Date",
        options=date_options,
        index=0,
        key=f"val_date_{selected_store}",
    )
    camera_options = sorted([c for c in appearances_df["Camera"].dropna().astype(str).unique().tolist() if c.strip()])
    selected_cameras = filter_cols[2].multiselect(
        "Camera",
        options=camera_options,
        default=camera_options,
        key=f"val_cam_{selected_store}",
    )
    role_options = sorted(
        {
            str(v).strip()
            for v in pd.concat([appearances_df["Role"], unique_df["Role"]], ignore_index=True).astype(str).tolist()
            if str(v).strip()
        }
    )
    selected_roles = filter_cols[3].multiselect(
        "Role",
        options=role_options,
        default=role_options,
        key=f"val_role_{selected_store}",
    )
    person_query = filter_cols[4].text_input(
        "Person ID search",
        value="",
        key=f"val_person_{selected_store}",
        placeholder="type id fragment",
    ).strip().lower()

    appearances_filtered = appearances_df.copy()
    if selected_date != "(All)":
        appearances_filtered = appearances_filtered[appearances_filtered["Date"] == selected_date]
    if selected_cameras:
        appearances_filtered = appearances_filtered[appearances_filtered["Camera"].isin(selected_cameras)]
    if selected_roles:
        appearances_filtered = appearances_filtered[appearances_filtered["Role"].isin(selected_roles)]
    if person_query:
        appearances_filtered = appearances_filtered[
            appearances_filtered["Person ID"].astype(str).str.lower().str.contains(person_query, na=False)
        ]

    unique_filtered = unique_df.copy()
    if selected_date != "(All)":
        unique_filtered = unique_filtered[
            unique_filtered["Capture Date"].astype(str).str.strip().eq(selected_date)
            | unique_filtered["Entry Time"].dt.date.astype(str).eq(selected_date)
        ]
    if selected_cameras:
        unique_filtered = unique_filtered[
            unique_filtered["Cameras"].astype(str).map(
                lambda text: bool({c.strip() for c in str(text).split(",") if c.strip()} & set(selected_cameras))
            )
        ]
    if selected_roles:
        unique_filtered = unique_filtered[unique_filtered["Role"].isin(selected_roles)]
    if person_query:
        unique_filtered = unique_filtered[
            unique_filtered["Person ID"].astype(str).str.lower().str.contains(person_query, na=False)
        ]

    # Top summary
    summary_df = pd.DataFrame(
        [
            {
                "Store Name": selected_store,
                "Total Person Appearances": int(len(appearances_filtered)),
                "Count of Unique Persons": int(unique_filtered["Person ID"].nunique()),
                "Staff": int(unique_filtered["Role"].astype(str).str.upper().eq("STAFF").sum()),
                "Converted": int(pd.to_numeric(unique_filtered["Converted"], errors="coerce").fillna(0).astype(int).sum()),
                "Bounced": int(pd.to_numeric(unique_filtered["Bounced"], errors="coerce").fillna(0).astype(int).sum()),
            }
        ]
    )
    st.markdown("**Top Summary**")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    tab_overview, tab_all, tab_unique, tab_rejected = st.tabs(
        ["Overview", "All Appearances", "Unique Persons", "Rejected Cases"]
    )
    with tab_overview:
        st.caption("Validation-first view. Tables below are filtered by Store/Date/Camera/Role/Person ID.")
        if appearances_filtered.empty or unique_filtered.empty:
            st.info("No rows match current filters. Widen filters to view validation records.")
        else:
            st.write(
                f"Showing `{len(appearances_filtered)}` appearances across "
                f"`{int(unique_filtered['Person ID'].nunique())}` unique persons."
            )

    with tab_all:
        if appearances_filtered.empty:
            st.info("No appearance rows for selected filters.")
        else:
            all_agg = (
                appearances_filtered.groupby("Person ID", as_index=False)
                .agg(
                    seen_count=("Timestamp", "count"),
                    role=("Role", lambda s: str(s.mode().iloc[0]) if not s.mode().empty else str(s.iloc[0])),
                    gender=("Gender", lambda s: str(s.mode().iloc[0]) if not s.mode().empty else str(s.iloc[0])),
                    first_seen=("Timestamp", "min"),
                    last_seen=("Timestamp", "max"),
                    proof_links=("Proof Link", lambda s: next((x for x in s.astype(str).tolist() if str(x).strip()), "")),
                )
                .sort_values(["seen_count", "first_seen"], ascending=[False, True])
            )
            all_view = all_agg.rename(
                columns={
                    "Person ID": "Person ID",
                    "seen_count": "Seen Count",
                    "role": "Role",
                    "gender": "Gender",
                    "first_seen": "First Seen",
                    "last_seen": "Last Seen",
                    "proof_links": "Proof Links",
                }
            )
            st.dataframe(
                all_view[["Person ID", "Seen Count", "Role", "Gender", "First Seen", "Last Seen", "Proof Links"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Proof Links": st.column_config.LinkColumn(
                        "Proof Links",
                        help="Open proof image (Google Drive when available) in a new tab.",
                        display_text="Open",
                    ),
                },
            )

    with tab_unique:
        if unique_filtered.empty:
            st.info("No unique person/session rows for selected filters.")
        else:
            uniq_view = unique_filtered.copy()
            uniq_view = uniq_view.sort_values("Entry Time", na_position="last")
            st.dataframe(
                uniq_view[
                    [
                        "Person ID",
                        "Role",
                        "Gender",
                        "Entry Time",
                        "Exit Time",
                        "Dwell Time (sec)",
                        "Best Proof Link",
                        "All Proof Links",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Best Proof Link": st.column_config.LinkColumn(
                        "Best Proof Link",
                        help="Open best available Google Drive proof link in new tab.",
                        display_text="Open",
                    ),
                },
            )
            st.caption("Hover thumbnail preview in tables is limited in Streamlit; use preview selector below.")

            preview_candidates = uniq_view[
                uniq_view["Best Proof Path"].astype(str).str.strip().ne("")
            ]["Person ID"].astype(str).tolist()
            if preview_candidates:
                preview_pid = st.selectbox(
                    "Proof Preview Person ID",
                    options=preview_candidates,
                    index=0,
                    key=f"val_preview_{selected_store}",
                )
                prow = uniq_view[uniq_view["Person ID"].astype(str) == str(preview_pid)].iloc[0]
                preview_path = str(prow.get("Best Proof Path", "") or "").strip()
                if preview_path and Path(preview_path).exists():
                    st.image(preview_path, caption=f"Preview: {preview_pid}", use_container_width=True)
                else:
                    st.info("Preview image path is unavailable for selected person.")

    with tab_rejected:
        rejected_roles = {"STAFF", "PEDESTRIANS", "BANNER", "INVALID", "ENTRY_CANDIDATE"}
        rejected_people = unique_filtered[unique_filtered["Role"].astype(str).str.upper().isin(rejected_roles)].copy()
        if rejected_people.empty:
            st.info("No rejected-person rows for selected filters.")
        else:
            rejected_people["rejection_category"] = rejected_people["Role"].astype(str).str.upper()
            st.dataframe(
                rejected_people[
                    [
                        "Person ID",
                        "rejection_category",
                        "Role",
                        "Entry Time",
                        "Exit Time",
                        "Rejection Reason",
                        "Best Proof Link",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Best Proof Link": st.column_config.LinkColumn(
                        "Best Proof Link",
                        help="Open rejection proof in new tab.",
                        display_text="Open",
                    ),
                },
            )

        invalid_frames = frame_rows[
            (frame_rows["reject_reason"].fillna("").astype(str).str.strip().ne(""))
            | (frame_rows["detection_error"].fillna("").astype(str).str.strip().ne(""))
            | (~frame_rows["is_valid"])
        ].copy()
        if selected_date != "(All)":
            invalid_frames = invalid_frames[invalid_frames["capture_date"].astype(str).eq(selected_date)]
        if selected_cameras:
            invalid_frames = invalid_frames[invalid_frames["camera_id"].astype(str).isin(selected_cameras)]
        if not invalid_frames.empty:
            invalid_frames["Proof Link"] = invalid_frames.apply(
                lambda r: _validation_preferred_link(
                    row=r,
                    store_id=selected_store,
                    root_dir=root_dir,
                    auth_token=auth_token,
                ),
                axis=1,
            )
            invalid_frames["rejection reason"] = invalid_frames.apply(
                lambda r: str(r.get("reject_reason", "") or "").strip()
                or str(r.get("detection_error", "") or "").strip()
                or "invalid_frame",
                axis=1,
            )
            st.markdown("**Invalid Frames**")
            st.dataframe(
                invalid_frames[
                    ["filename", "camera_id", "timestamp", "rejection reason", "Proof Link"]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Proof Link": st.column_config.LinkColumn(
                        "Proof Link",
                        help="Open invalid frame proof in new tab.",
                        display_text="Open",
                    ),
                },
            )
        else:
            st.info("No invalid-frame rows for selected filters.")


def _resolve_row_image_path(row: pd.Series, store_id: str, root_dir: Path) -> Path | None:
    # 1) Try stored absolute path first.
    raw_path = str(row.get("path", "") or "").strip()
    if raw_path:
        p = Path(raw_path)
        if p.exists() and p.is_file():
            return p
    # 2) Use exported relative path if present.
    rel = str(row.get("relative_path", "") or "").strip().replace("\\", "/")
    if rel:
        p = (root_dir / store_id / rel).resolve()
        if p.exists() and p.is_file():
            return p
    # 3) Reconstruct from source_folder + filename.
    source_folder = str(row.get("source_folder", "") or "").strip().replace("\\", "/")
    filename = str(row.get("filename", "") or "").strip()
    if filename:
        if source_folder:
            p = (root_dir / store_id / source_folder / filename).resolve()
        else:
            p = (root_dir / store_id / filename).resolve()
        if p.exists() and p.is_file():
            return p
    return None


def _row_image_hyperlink(row: pd.Series, store_id: str, root_dir: Path, auth_token: str = "") -> str:
    # Use authenticated in-app link first so users are not forced into external Drive login.
    file_name = str(row.get("filename", "") or "").strip()
    ts_value = str(row.get("timestamp", "") or "").strip()
    if file_name:
        return _frame_review_identity_link(
            store_id=store_id,
            filename=file_name,
            timestamp=ts_value,
            auth_token=auth_token,
        )

    drive_link = str(row.get("drive_link", "") or "").strip()
    if drive_link and drive_link.lower() != "nan":
        return drive_link

    # Final fallback: local file URI only when local file exists.
    resolved = _resolve_row_image_path(row=row, store_id=store_id, root_dir=root_dir)
    if resolved is None:
        return ""
    return resolved.as_uri()


def _valid_link_or_empty(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.lower() in {"nan", "none", "null", "nat"}:
        return ""
    return text


def _safe_text(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null", "nat"}:
        return ""
    return text


def _event_verification_link(evt: dict[str, object], store_id: str, auth_token: str) -> str:
    filename = _safe_text(evt.get("filename", ""))
    timestamp = _safe_text(evt.get("timestamp", ""))
    if filename:
        return _frame_review_identity_link(
            store_id=store_id,
            filename=filename,
            timestamp=timestamp,
            auth_token=auth_token,
        )
    drive_link = _valid_link_or_empty(evt.get("drive_link", ""))
    if drive_link:
        return drive_link
    raw_path = _safe_text(evt.get("path", ""))
    if raw_path:
        p = Path(raw_path)
        if p.exists() and p.is_file():
            return p.as_uri()
    return ""


def _resolve_event_image_path(evt: dict[str, object], store_id: str, root_dir: Path) -> Path | None:
    raw_path = _safe_text(evt.get("path", ""))
    if raw_path:
        p = Path(raw_path)
        if p.exists() and p.is_file():
            return p
    rel = _safe_text(evt.get("relative_path", "")).replace("\\", "/")
    if rel:
        p = (root_dir / store_id / rel).resolve()
        if p.exists() and p.is_file():
            return p
    source_folder = _safe_text(evt.get("source_folder", "")).replace("\\", "/")
    filename = _safe_text(evt.get("filename", ""))
    if filename:
        if source_folder:
            p = (root_dir / store_id / source_folder / filename).resolve()
            if p.exists() and p.is_file():
                return p
        p = (root_dir / store_id / filename).resolve()
        if p.exists() and p.is_file():
            return p
    return None


def _predicted_label(row: pd.Series) -> str:
    explicit = str(row.get("event_label", "") or "").strip().upper()
    if explicit in {"CUSTOMER", "STAFF", "OUTSIDE_PASSER", "INVALID"}:
        return explicit.lower()
    person_count = int(row.get("person_count", 0) or 0)
    staff_count = int(row.get("staff_count", 0) or 0)
    if person_count <= 0:
        return "no_person"
    if staff_count <= 0:
        return "customer"
    if staff_count >= person_count:
        return "staff"
    return "mixed"


LABEL_CANONICAL_ALIASES: dict[str, str] = {
    "CUSTOMER": "customer",
    "STAFF": "staff",
    "BANNER": "poster_banner",
    "POSTER_BANNER": "poster_banner",
    "PRODUCT": "product",
    "PEDESTRIANS": "outside_passer",
    "OUTSIDE_PASSER": "outside_passer",
    "INVALID": "invalid",
    "NOT_SURE": "not_sure",
    "MIXED": "mixed",
    "NO_PERSON": "no_person",
    "NO_CUSTOMER": "no_person",
    "STATIC_OBJECT": "poster_banner",
}

LABEL_DISPLAY_BY_CANONICAL: dict[str, str] = {
    "customer": "CUSTOMER",
    "staff": "STAFF",
    "poster_banner": "BANNER",
    "product": "PRODUCT",
    "outside_passer": "PEDESTRIANS",
    "invalid": "INVALID",
    "not_sure": "NOT_SURE",
    "mixed": "MIXED",
    "no_person": "NO_CUSTOMER",
}


def _label_to_canonical(raw: object) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    return LABEL_CANONICAL_ALIASES.get(text, text.lower())


def _label_to_display(raw: object) -> str:
    canonical = _label_to_canonical(raw)
    if not canonical:
        return ""
    return LABEL_DISPLAY_BY_CANONICAL.get(canonical, canonical.upper())


FEEDBACK_LABEL_OPTIONS = [
    "CUSTOMER",
    "STAFF",
    "BANNER",
    "PRODUCT",
    "PEDESTRIANS",
    "NO_CUSTOMER",
    "INVALID",
    "NOT_SURE",
]
TRACK_FEEDBACK_OPTIONS = [""] + FEEDBACK_LABEL_OPTIONS


def _normalize_capture_date_key(raw: object) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.notna(parsed):
        return str(parsed.date())
    parsed_dayfirst = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.notna(parsed_dayfirst):
        return str(parsed_dayfirst.date())
    return text


def _feedback_label_default(row: pd.Series) -> str:
    predicted = str(_predicted_label(row)).strip().lower()
    event_label = str(row.get("event_label", "") or "").strip().upper()
    bag_count = int(pd.to_numeric([row.get("bag_count", 0)], errors="coerce")[0] or 0)
    person_count = int(pd.to_numeric([row.get("person_count", 0)], errors="coerce")[0] or 0)
    if person_count <= 0 or predicted == "no_person":
        return "NO_CUSTOMER"
    if event_label == "STAFF" or predicted == "staff":
        return "STAFF"
    if event_label == "CUSTOMER" or predicted == "customer":
        return "CUSTOMER"
    if bag_count > 0:
        return "PRODUCT"
    if event_label in {"STATIC_OBJECT"}:
        return "BANNER"
    if event_label == "OUTSIDE_PASSER" or predicted == "outside_passer":
        return "PEDESTRIANS"
    if event_label == "INVALID":
        return "INVALID"
    return "NOT_SURE"


def _resolve_track_prediction_from_source_row(source_row: pd.Series, track_id: str) -> str:
    track_ids = [str(x) for x in _safe_json_list(source_row.get("track_ids", "[]")) if str(x).strip()]
    if not track_ids:
        return ""
    try:
        idx = track_ids.index(str(track_id).strip())
    except ValueError:
        return ""
    staff_flags = [bool(x) for x in _safe_json_list(source_row.get("staff_flags", "[]"))]
    if idx < len(staff_flags):
        return "staff" if bool(staff_flags[idx]) else "customer"
    return "customer"


def _build_feedback_accuracy_report(
    *,
    feedback_rows: list[dict[str, object]],
    image_df: pd.DataFrame,
    db_path: Path,
    store_id: str,
) -> tuple[dict[str, float], pd.DataFrame]:
    summary = {
        "considered_rows": 0.0,
        "scored_rows": 0.0,
        "matched_rows": 0.0,
        "mismatch_rows": 0.0,
        "accuracy_pct": 0.0,
        "no_customer_rows": 0.0,
    }
    if not feedback_rows:
        return summary, pd.DataFrame(
            columns=[
                "model_version",
                "total_rows",
                "matched_rows",
                "mismatch_rows",
                "accuracy_pct",
                "last_feedback_at",
            ]
        )
    feedback_df = pd.DataFrame(feedback_rows).copy()
    if feedback_df.empty:
        return summary, pd.DataFrame()
    feedback_df["review_status"] = feedback_df.get("review_status", "").astype(str).str.lower()
    image_lookup = {
        (
            _normalize_capture_date_key(r.get("capture_date", "")),
            str(r.get("camera_id", "") or "").strip(),
            str(r.get("filename", "") or "").strip(),
        ): r
        for _, r in image_df.iterrows()
    }

    def _resolved_predicted_label(row: pd.Series) -> str:
        key = (
            _normalize_capture_date_key(row.get("capture_date", "")),
            str(row.get("camera_id", "") or "").strip(),
            str(row.get("filename", "") or "").strip(),
        )
        track_id = str(row.get("track_id", "") or "").strip()
        source_row = image_lookup.get(key)
        if source_row is not None:
            if track_id:
                track_pred = _resolve_track_prediction_from_source_row(source_row, track_id=track_id)
                if track_pred:
                    return track_pred
            return str(_predicted_label(source_row))
        return str(row.get("predicted_label", "") or "")

    feedback_df["predicted_resolved"] = feedback_df.apply(_resolved_predicted_label, axis=1)
    feedback_df["predicted_canonical"] = feedback_df["predicted_resolved"].map(_label_to_canonical)
    feedback_df["corrected_canonical"] = feedback_df.get("corrected_label", "").map(_label_to_canonical)
    considered_df = feedback_df[feedback_df["review_status"].isin(["confirmed", "pending"])].copy()
    if considered_df.empty:
        return summary, pd.DataFrame()
    scored_df = considered_df[
        (considered_df["predicted_canonical"].astype(str) != "")
        & (considered_df["corrected_canonical"].astype(str) != "")
        & (considered_df["corrected_canonical"].astype(str) != "not_sure")
    ].copy()
    if scored_df.empty:
        summary["considered_rows"] = float(len(considered_df))
        summary["no_customer_rows"] = float((considered_df["corrected_canonical"] == "no_person").sum())
        return summary, pd.DataFrame()

    scored_df["is_match"] = (
        scored_df["predicted_canonical"].astype(str) == scored_df["corrected_canonical"].astype(str)
    ).astype(int)
    matched_rows = int(scored_df["is_match"].sum())
    total_rows = int(len(scored_df))
    mismatch_rows = int(max(0, total_rows - matched_rows))
    summary.update(
        {
            "considered_rows": float(len(considered_df)),
            "scored_rows": float(total_rows),
            "matched_rows": float(matched_rows),
            "mismatch_rows": float(mismatch_rows),
            "accuracy_pct": float((matched_rows * 100.0 / total_rows) if total_rows > 0 else 0.0),
            "no_customer_rows": float((considered_df["corrected_canonical"] == "no_person").sum()),
        }
    )

    scored_df["model_version"] = scored_df.get("model_version", "").astype(str).str.strip()
    scored_df.loc[scored_df["model_version"] == "", "model_version"] = "(unknown)"
    scored_df["created_at_dt"] = pd.to_datetime(scored_df.get("created_at"), errors="coerce")
    trend_df = (
        scored_df.groupby("model_version", dropna=False)
        .agg(
            total_rows=("id", "count"),
            matched_rows=("is_match", "sum"),
            last_feedback_at=("created_at_dt", "max"),
        )
        .reset_index()
    )
    trend_df["mismatch_rows"] = (trend_df["total_rows"] - trend_df["matched_rows"]).clip(lower=0).astype(int)
    trend_df["accuracy_pct"] = (
        pd.to_numeric(trend_df["matched_rows"], errors="coerce")
        .fillna(0)
        .astype(float)
        .mul(100.0)
        .div(pd.to_numeric(trend_df["total_rows"], errors="coerce").replace({0: np.nan}))
        .fillna(0.0)
        .round(2)
    )
    trend_df["last_feedback_at"] = pd.to_datetime(trend_df["last_feedback_at"], errors="coerce")

    model_order: dict[str, int] = {}
    try:
        model_rows = list_model_versions(db_path=db_path, model_name=f"iris_feedback_rules_{store_id}")
        ordered = sorted(
            model_rows,
            key=lambda row: str(row.get("created_at", "") or ""),
        )
        for idx, row in enumerate(ordered):
            key = str(row.get("model_id", "") or "").strip()
            if key:
                model_order[key] = idx + 1
    except Exception:
        model_order = {}

    trend_df["_order"] = trend_df["model_version"].map(lambda x: model_order.get(str(x), 10_000))
    trend_df = trend_df.sort_values(by=["_order", "last_feedback_at", "model_version"]).reset_index(drop=True)
    trend_df["run_index"] = np.arange(1, len(trend_df) + 1, dtype=int)
    trend_df["last_feedback_at"] = trend_df["last_feedback_at"].astype(str).replace({"NaT": ""})
    return summary, trend_df[
        [
            "run_index",
            "model_version",
            "total_rows",
            "matched_rows",
            "mismatch_rows",
            "accuracy_pct",
            "last_feedback_at",
        ]
    ].copy()


def _feedback_retrain_cycle(
    db_path: Path,
    store_id: str,
    actor_email: str,
    min_new_rows: int = 10,
    force_retrain: bool = False,
) -> tuple[bool, str, int]:
    settings = get_app_settings(db_path)
    key_last = f"qa_last_retrain_feedback_id__{store_id}"
    key_model = f"qa_active_model_id__{store_id}"
    try:
        last_retrain_id = int(str(settings.get(key_last, "0") or "0"))
    except Exception:
        last_retrain_id = 0
    confirmed_rows = list_qa_feedback(
        db_path=db_path,
        store_id=store_id,
        review_status="confirmed",
        limit=200000,
    )
    new_rows = [row for row in confirmed_rows if int(row.get("id", 0) or 0) > last_retrain_id]
    eligible_rows = confirmed_rows if bool(force_retrain) else new_rows
    if len(eligible_rows) < int(max(1, min_new_rows)):
        return (
            False,
            (
                f"Need at least {int(min_new_rows)} eligible rows. "
                f"confirmed_total={len(confirmed_rows)}, "
                f"new_confirmed_rows={len(new_rows)}, "
                f"last_retrain_feedback_id={last_retrain_id}, "
                f"mode={'force_all_confirmed' if force_retrain else 'incremental_new_only'}"
            ),
            len(eligible_rows),
        )

    label_counts: dict[str, int] = {}
    for row in eligible_rows:
        label = _label_to_canonical(row.get("corrected_label", "")) or "unknown"
        label_counts[label] = int(label_counts.get(label, 0)) + 1
    version_tag = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    artifact_path = db_path.parent / "models" / f"qa_feedback_rules_{store_id}_{version_tag}.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "store_id": store_id,
        "version_tag": version_tag,
        "retrain_mode": "force_all_confirmed" if bool(force_retrain) else "incremental_new_only",
        "last_retrain_feedback_id": int(last_retrain_id),
        "confirmed_total": len(confirmed_rows),
        "new_confirmed_rows": len(new_rows),
        "eligible_feedback_rows": len(eligible_rows),
        "label_counts": label_counts,
        "updated_by": actor_email,
        "updated_at": pd.Timestamp.utcnow().isoformat(),
    }
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    model_name = f"iris_feedback_rules_{store_id}"
    model_id = register_model_version(
        db_path=db_path,
        model_name=model_name,
        version_tag=version_tag,
        metrics_json=json.dumps(payload),
        status="candidate",
        artifact_path=str(artifact_path),
    )
    promote_model_version(db_path=db_path, model_name=model_name, model_id=model_id)
    max_feedback_id = max(int(row.get("id", 0) or 0) for row in eligible_rows)
    upsert_app_settings(
        db_path=db_path,
        settings={
            key_last: str(max_feedback_id),
            key_model: str(model_id),
        },
    )
    return (
        True,
        (
            f"Retrained feedback rules as {model_id}. "
            f"confirmed_total={len(confirmed_rows)}, "
            f"new_confirmed_rows={len(new_rows)}, "
            f"eligible_feedback_rows={len(eligible_rows)}, "
            f"last_retrain_feedback_id={last_retrain_id}, "
            f"new_watermark_feedback_id={max_feedback_id}, "
            f"mode={'force_all_confirmed' if force_retrain else 'incremental_new_only'}"
        ),
        len(eligible_rows),
    )


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
        font = ImageFont.load_default()
        width, height = canvas.size
        stroke = max(2, int(round(min(width, height) * 0.004)))
        label_boxes: list[tuple[int, int, int, int]] = []

        def _overlaps(rect: tuple[int, int, int, int]) -> bool:
            rx1, ry1, rx2, ry2 = rect
            for ox1, oy1, ox2, oy2 in label_boxes:
                if not (rx2 < ox1 or ox2 < rx1 or ry2 < oy1 or oy2 < ry1):
                    return True
            return False

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
            text_bbox = draw.textbbox((0, 0), label, font=font, stroke_width=1)
            text_w = int(text_bbox[2] - text_bbox[0])
            text_h = int(text_bbox[3] - text_bbox[1])
            tag_w = min(width, max(96, text_w + 14))
            tag_h = min(max(18, text_h + 8), max(20, int(height * 0.09)))

            candidates = [
                (x1, max(0, y1 - tag_h - 2)),  # above box
                (x1, min(height - tag_h, y2 + 2)),  # below box
                (x1, min(height - tag_h, max(0, y1 + 2))),  # inside near top
            ]
            tag_x, tag_y = candidates[0]
            for cand_x, cand_y in candidates:
                cx = max(0, min(width - tag_w, cand_x))
                cy = max(0, min(height - tag_h, cand_y))
                rect = (cx, cy, cx + tag_w, cy + tag_h)
                if not _overlaps(rect):
                    tag_x, tag_y = cx, cy
                    break
                tag_x, tag_y = cx, cy
            # Last fallback: shift down until free or image end.
            rect = (tag_x, tag_y, tag_x + tag_w, tag_y + tag_h)
            while _overlaps(rect) and tag_y + tag_h + 2 < height:
                tag_y += tag_h + 2
                tag_y = min(height - tag_h, tag_y)
                rect = (tag_x, tag_y, tag_x + tag_w, tag_y + tag_h)
            label_boxes.append(rect)
            draw.rectangle((tag_x, tag_y, tag_x + tag_w, tag_y + tag_h), fill=color)
            draw.text(
                (tag_x + 6, tag_y + 4),
                label,
                fill="#ffffff",
                font=font,
                stroke_width=1,
                stroke_fill="#000000",
            )
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
        customer_ids = [str(x) for x in _safe_json_list(row.get("store_day_customer_ids", "[]")) if str(x).strip()]
        if not customer_ids:
            customer_ids = [str(x) for x in _safe_json_list(row.get("customer_ids", "[]")) if str(x).strip()]
        for cid in customer_ids:
            events.setdefault(cid, []).append(
                {
                    "timestamp": row.get("timestamp"),
                    "camera_id": str(row.get("camera_id", "")),
                    "filename": _safe_text(row.get("filename", "")),
                    "path": _safe_text(row.get("path", "")),
                    "source_folder": _safe_text(row.get("source_folder", "")),
                    "relative_path": _safe_text(row.get("relative_path", "")),
                    "drive_link": _safe_text(row.get("drive_link", "")),
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
                "model_version",
                "drive_link",
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


def _parse_dashboard_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _time_to_seconds(text: object) -> int | None:
    raw = str(text or "").strip()
    if not raw or raw.upper() == "NA":
        return None
    try:
        hh, mm, ss = [int(x) for x in raw.split(":")]
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return None


def _duration_minutes(row: pd.Series) -> float | None:
    raw = pd.to_numeric([row.get("time_spent_mins", np.nan)], errors="coerce")[0]
    if not pd.isna(raw) and float(raw) >= 0:
        return float(raw)
    entry_sec = _time_to_seconds(row.get("entry_time", ""))
    exit_sec = _time_to_seconds(row.get("exit_time", ""))
    if entry_sec is None or exit_sec is None:
        return None
    diff = exit_sec - entry_sec
    if diff < 0:
        return None
    return round(diff / 60.0, 2)


def _load_onfly_walkin_business_df(root_dir: Path, db_path: Path) -> pd.DataFrame:
    base = root_dir / "exports" / "current" / "onfly"
    if not base.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for csv_path in sorted(base.glob("*/onfly_walkin_sessions.csv")):
        try:
            part = pd.read_csv(csv_path)
        except Exception:
            continue
        if part.empty:
            continue
        part = part.copy()
        store_from_path = csv_path.parent.name
        if "store_id" not in part.columns:
            part["store_id"] = store_from_path
        part["store_id"] = part["store_id"].fillna(store_from_path).astype(str).str.strip()
        part["store_id"] = part["store_id"].replace("", store_from_path)
        frames.append(part)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    for col in [
        "role",
        "included_in_analytics",
        "group_id",
        "walkin_id",
        "gender",
        "age_band",
        "purchase_signal_bag",
        "entry_type",
        "session_status",
        "camera_id",
    ]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    if "business_date" in df.columns:
        date_series = df["business_date"]
    elif "date" in df.columns:
        date_series = df["date"]
    elif "folder_name" in df.columns:
        date_series = df["folder_name"]
    else:
        date_series = ""
    df["date_raw"] = date_series
    df["date_dt"] = df["date_raw"].map(_parse_dashboard_date)
    df["date_label"] = df["date_dt"].map(lambda d: d.strftime("%Y-%m-%d") if isinstance(d, datetime) else "")
    df.loc[df["date_label"] == "", "date_label"] = df.loc[df["date_label"] == "", "date_raw"].astype(str)

    df["role_norm"] = df["role"].str.upper()
    df["included_norm"] = df["included_in_analytics"].str.lower()
    df["is_customer"] = (df["role_norm"] == "CUSTOMER") & (df["included_norm"].isin({"yes", "true", "1"}))
    df["is_conversion"] = (
        df["purchase_signal_bag"].str.lower().isin({"yes", "true", "1"})
        | df.get("event_type", pd.Series([""] * len(df))).astype(str).str.upper().eq("INSIDE_PURCHASING")
    ) & df["is_customer"]

    df["duration_mins"] = df.apply(_duration_minutes, axis=1)
    valid_duration = pd.to_numeric(df["duration_mins"], errors="coerce")
    df["duration_mins"] = np.where(valid_duration >= 0, valid_duration, np.nan)

    # Customer-group correction at dashboard layer to avoid frame-wide grouping artifacts.
    walkin_key = df["walkin_id"].where(df["walkin_id"] != "", df.get("image_id", pd.Series([""] * len(df))).astype(str))
    df["walkin_key"] = walkin_key.astype(str)
    group_key = df["group_id"].where(df["group_id"] != "", df["walkin_key"])
    group_key = np.where(df["is_customer"], df["walkin_key"], group_key)
    df["group_key"] = pd.Series(group_key).astype(str)

    store_master = pd.DataFrame(list_store_master(db_path))
    if not store_master.empty:
        store_master["store_id"] = store_master["store_id"].astype(str).str.strip()
        store_master["zone"] = store_master.get("zone", "").fillna("").astype(str).str.strip()
        df = df.merge(store_master[["store_id", "zone"]], on="store_id", how="left")
        df["region"] = df["zone"].fillna("").astype(str).str.strip()
    else:
        df["region"] = ""
    df.loc[df["region"] == "", "region"] = "Unknown"
    return df


def _summarize_walkin_metrics(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"groups": 0, "walkins": 0, "avg_time_spent": 0.0, "conversion_rate": np.nan}
    customer_df = df[df["is_customer"]].copy()
    if customer_df.empty:
        return {"groups": 0, "walkins": 0, "avg_time_spent": 0.0, "conversion_rate": np.nan}
    walkins = int(customer_df["walkin_key"].nunique())
    groups = int(customer_df["group_key"].nunique())
    avg_time = float(pd.to_numeric(customer_df["duration_mins"], errors="coerce").dropna().mean() or 0.0)
    conversions = int(customer_df["is_conversion"].sum())
    conversion_rate = (float(conversions) / float(walkins)) if walkins > 0 else np.nan
    return {
        "groups": groups,
        "walkins": walkins,
        "avg_time_spent": round(avg_time, 2),
        "conversion_rate": conversion_rate,
    }


def _render_overview(output: AnalysisOutput) -> None:
    st.subheader("Overview")
    root_dir = Path(str(st.session_state.get("ctrl_root_str", "data"))).resolve()
    db_path = Path(str(st.session_state.get("db_path", root_dir / "store_registry.db"))).resolve()
    walkin_df = _load_onfly_walkin_business_df(root_dir=root_dir, db_path=db_path)
    if walkin_df.empty:
        st.warning("No walk-in session data found yet. Run on-fly pipeline for at least one store.")
        return

    customer_df = walkin_df[walkin_df["is_customer"]].copy()
    overall = _summarize_walkin_metrics(walkin_df)
    kcols = st.columns(4)
    kcols[0].metric("Total Groups", int(overall["groups"]))
    kcols[1].metric("Total Walk-ins", int(overall["walkins"]))
    kcols[2].metric("Avg Time Spent (mins)", f"{float(overall['avg_time_spent']):.2f}")
    kcols[3].metric("Conversion Rate", "N/A" if pd.isna(overall["conversion_rate"]) else f"{float(overall['conversion_rate']):.2%}")

    if customer_df.empty:
        st.info("Walk-in files exist, but no analytics-eligible customer sessions found.")
        return

    by_store = customer_df.groupby("store_id", as_index=False).agg(
        total_groups=("group_key", "nunique"),
        total_walkins=("walkin_key", "nunique"),
        avg_time_spent=("duration_mins", "mean"),
        conversions=("is_conversion", "sum"),
    )
    by_store["conversion_rate"] = np.where(
        by_store["total_walkins"] > 0,
        by_store["conversions"] / by_store["total_walkins"],
        np.nan,
    )
    by_store["avg_time_spent"] = by_store["avg_time_spent"].fillna(0.0)

    best_conv = by_store.sort_values("conversion_rate", ascending=False).head(1)
    best_crowd = by_store.sort_values("total_walkins", ascending=False).head(1)
    low_conv = by_store.sort_values("conversion_rate", ascending=True).head(1)
    info_cols = st.columns(3)
    info_cols[0].metric(
        "Highest Conversion Store",
        str(best_conv["store_id"].iloc[0]) if not best_conv.empty else "N/A",
        "N/A" if best_conv.empty or pd.isna(best_conv["conversion_rate"].iloc[0]) else f"{float(best_conv['conversion_rate'].iloc[0]):.2%}",
    )
    info_cols[1].metric(
        "Highest Crowd Store",
        str(best_crowd["store_id"].iloc[0]) if not best_crowd.empty else "N/A",
        f"{int(best_crowd['total_walkins'].iloc[0])}" if not best_crowd.empty else "0",
    )
    info_cols[2].metric(
        "Lowest Conversion Store",
        str(low_conv["store_id"].iloc[0]) if not low_conv.empty else "N/A",
        "N/A" if low_conv.empty or pd.isna(low_conv["conversion_rate"].iloc[0]) else f"{float(low_conv['conversion_rate'].iloc[0]):.2%}",
    )

    c1, c2, c3 = st.columns(3)
    granularity = c1.selectbox("Trend Granularity", options=["Day", "Month", "Year"], index=1, key="overview_granularity")
    scope = c2.selectbox("Scope", options=["Store", "Region", "Pan India"], index=0, key="overview_scope")
    if scope == "Store":
        entities = sorted(customer_df["store_id"].dropna().astype(str).unique().tolist())
    elif scope == "Region":
        entities = sorted(customer_df["region"].dropna().astype(str).unique().tolist())
    else:
        entities = ["Pan India"]
    selected_entity = c3.selectbox("Entity", options=entities, index=0, key="overview_entity")

    trend_df = customer_df.copy()
    if scope == "Store":
        trend_df = trend_df[trend_df["store_id"] == selected_entity]
    elif scope == "Region":
        trend_df = trend_df[trend_df["region"] == selected_entity]

    trend_df = trend_df.dropna(subset=["date_dt"]).copy()
    if trend_df.empty:
        st.info("No date-parsed rows available for trend/compare.")
    else:
        if granularity == "Day":
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y-%m-%d")
        elif granularity == "Month":
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y-%m")
        else:
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y")

        period_agg = trend_df.groupby("period", as_index=False).agg(
            walkins=("walkin_key", "nunique"),
            groups=("group_key", "nunique"),
            avg_time_spent=("duration_mins", "mean"),
            conversions=("is_conversion", "sum"),
        )
        period_agg["conversion_rate"] = np.where(period_agg["walkins"] > 0, period_agg["conversions"] / period_agg["walkins"], np.nan)
        period_agg = period_agg.sort_values("period")
        st.plotly_chart(
            px.line(
                period_agg,
                x="period",
                y=["walkins", "groups"],
                markers=True,
                title=f"{scope} Trend ({selected_entity})",
            ),
            use_container_width=True,
        )

        if len(period_agg) >= 2:
            current = period_agg.iloc[-1]
            previous = period_agg.iloc[-2]
            delta_walkins = int(current["walkins"] - previous["walkins"])
            delta_conv = float(current["conversion_rate"] - previous["conversion_rate"]) if not pd.isna(current["conversion_rate"]) and not pd.isna(previous["conversion_rate"]) else np.nan
            st.caption(
                f"Period Delta ({current['period']} vs {previous['period']}): "
                f"Walk-ins {delta_walkins:+d}, "
                f"Conversion {'N/A' if pd.isna(delta_conv) else f'{delta_conv:+.2%}'}."
            )

    st.markdown("**Top Stores By Conversion**")
    st.dataframe(
        by_store.sort_values("conversion_rate", ascending=False).head(10),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("**Bottom Stores (Needs Attention)**")
    st.dataframe(
        by_store.sort_values("conversion_rate", ascending=True).head(10),
        use_container_width=True,
        hide_index=True,
    )


def _render_model_accuracy_overview(output: AnalysisOutput, db_path: Path, out_dir: Path) -> None:
    st.subheader("Model Accuracy Overview")
    st.caption(
        "This page tracks how model accuracy improves from your feedback. "
        "Your confirmed feedback is treated as ground truth."
    )
    history_df = _load_model_accuracy_history(out_dir=out_dir)
    if history_df.empty:
        try:
            _persist_model_accuracy_snapshot(db_path=db_path, out_dir=out_dir, output=output, source="ui_snapshot")
            history_df = _load_model_accuracy_history(out_dir=out_dir)
        except Exception:
            history_df = pd.DataFrame()
    if history_df.empty:
        st.info("No accuracy history yet. Save some feedback and run analysis/retrain cycle.")
        return

    settings = get_app_settings(db_path)
    scheduler_enabled = _setting_bool(settings, "cfg_scheduler_enabled", True)
    interval_minutes = _setting_int(settings, "cfg_scheduler_interval_minutes", 30, minimum=1, maximum=1440)
    next_run_dt = _parse_iso_utc(settings.get("cfg_scheduler_next_run_at", ""))
    if next_run_dt is None and scheduler_enabled:
        next_run_dt = datetime.now(tz=timezone.utc) + timedelta(minutes=int(interval_minutes))
    next_run_label = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "Not scheduled"

    latest_by_store = (
        history_df.sort_values(by=["snapshot_date", "snapshot_ts_utc"])
        .groupby("store_id", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    weighted_scored = float(pd.to_numeric(latest_by_store.get("scored_rows", 0), errors="coerce").fillna(0).sum())
    weighted_matched = float(pd.to_numeric(latest_by_store.get("matched_rows", 0), errors="coerce").fillna(0).sum())
    weighted_accuracy = (weighted_matched * 100.0 / weighted_scored) if weighted_scored > 0 else 0.0
    total_pending_retrain = int(pd.to_numeric(latest_by_store.get("pending_retrain_rows", 0), errors="coerce").fillna(0).sum())

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("Current Accuracy", f"{weighted_accuracy:.2f}%" if weighted_scored > 0 else "N/A")
    kpi_cols[1].metric("Scored Feedback Rows", int(weighted_scored))
    kpi_cols[2].metric("Matched Rows", int(weighted_matched))
    kpi_cols[3].metric("Queued For Retrain", int(total_pending_retrain))
    kpi_cols[4].metric("Next Scheduler Run", next_run_label)
    st.caption("`Queued For Retrain` shows confirmed rows not yet consumed by the latest promoted model.")

    trend_df = history_df.copy()
    trend_df["snapshot_date_dt"] = pd.to_datetime(trend_df["snapshot_date"], errors="coerce")
    trend_df = trend_df.dropna(subset=["snapshot_date_dt"]).copy()
    if trend_df.empty:
        st.info("No valid trend dates found yet.")
        return
    trend_df = trend_df.sort_values(by=["snapshot_date_dt", "store_id"])
    try:
        chart = px.line(
            trend_df,
            x="snapshot_date_dt",
            y="accuracy_pct",
            color="store_id",
            markers=True,
            hover_data=["model_id", "scored_rows", "matched_rows", "mismatch_rows", "pending_retrain_rows"],
            labels={"snapshot_date_dt": "Date", "accuracy_pct": "Accuracy (%)", "store_id": "Store"},
            title="Daily Model Accuracy Trend",
        )
        st.plotly_chart(chart, use_container_width=True)
    except Exception:
        pass

    st.markdown("**Latest Accuracy By Store**")
    st.dataframe(
        latest_by_store[
            [
                "snapshot_date",
                "store_id",
                "model_id",
                "accuracy_pct",
                "scored_rows",
                "matched_rows",
                "mismatch_rows",
                "pending_retrain_rows",
                "source",
            ]
        ].sort_values(by=["snapshot_date", "store_id"], ascending=[False, True]),
        use_container_width=True,
        hide_index=True,
    )


def _render_store_detail(output: AnalysisOutput, time_bucket_minutes: int, root_dir: Path) -> None:
    st.subheader("Store Drill-down")
    db_path = Path(str(st.session_state.get("db_path", root_dir / "store_registry.db"))).resolve()
    walkin_df = _load_onfly_walkin_business_df(root_dir=root_dir, db_path=db_path)
    if walkin_df.empty:
        st.info("No walk-in session data found for drill-down yet.")
        return
    stores = sorted(walkin_df["store_id"].dropna().astype(str).unique().tolist())
    selected_store = st.selectbox("Store", options=stores, index=0, key="store_walkin_select")
    sdf = walkin_df[walkin_df["store_id"] == selected_store].copy()
    customer_df = sdf[sdf["is_customer"]].copy()
    if customer_df.empty:
        st.warning("Selected store has no analytics-eligible customer sessions yet.")
        return

    summary = _summarize_walkin_metrics(sdf)
    kcols = st.columns(4)
    kcols[0].metric("Total Groups", int(summary["groups"]))
    kcols[1].metric("Total Walk-ins", int(summary["walkins"]))
    kcols[2].metric("Avg Time Spent (mins)", f"{float(summary['avg_time_spent']):.2f}")
    kcols[3].metric("Conversion Rate", "N/A" if pd.isna(summary["conversion_rate"]) else f"{float(summary['conversion_rate']):.2%}")

    gender = (
        customer_df.assign(gender=customer_df["gender"].replace("", "Unknown"))
        .groupby("gender", as_index=False)
        .agg(walkins=("walkin_key", "nunique"))
        .sort_values("walkins", ascending=False)
    )
    age = (
        customer_df.assign(age_band=customer_df["age_band"].replace("", "Unknown"))
        .groupby("age_band", as_index=False)
        .agg(walkins=("walkin_key", "nunique"))
        .sort_values("age_band")
    )
    split_cols = st.columns(2)
    split_cols[0].markdown("**Gender Split**")
    split_cols[0].dataframe(gender, use_container_width=True, hide_index=True)
    split_cols[1].markdown("**Age Group Split**")
    split_cols[1].dataframe(age, use_container_width=True, hide_index=True)

    trend_grain = st.selectbox("Trend Granularity", options=["Day", "Month", "Year"], index=0, key="store_trend_grain")
    trend_df = customer_df.dropna(subset=["date_dt"]).copy()
    if trend_df.empty:
        st.info("No valid date rows for trend.")
    else:
        if trend_grain == "Day":
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y-%m-%d")
        elif trend_grain == "Month":
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y-%m")
        else:
            trend_df["period"] = trend_df["date_dt"].dt.strftime("%Y")
        agg = trend_df.groupby("period", as_index=False).agg(
            walkins=("walkin_key", "nunique"),
            groups=("group_key", "nunique"),
            avg_time_spent=("duration_mins", "mean"),
            conversions=("is_conversion", "sum"),
        )
        agg["conversion_rate"] = np.where(agg["walkins"] > 0, agg["conversions"] / agg["walkins"], np.nan)
        agg = agg.sort_values("period")
        chart_cols = st.columns(2)
        chart_cols[0].plotly_chart(
            px.line(agg, x="period", y=["walkins", "groups"], markers=True, title="Walk-ins & Groups Trend"),
            use_container_width=True,
        )
        chart_cols[1].plotly_chart(
            px.line(agg, x="period", y=["conversion_rate", "avg_time_spent"], markers=True, title="Conversion & Avg Time Trend"),
            use_container_width=True,
        )

        if len(agg) >= 2:
            cur = agg.iloc[-1]
            prev = agg.iloc[-2]
            delta_cols = st.columns(4)
            delta_cols[0].metric("Walk-ins Delta", int(cur["walkins"]), int(cur["walkins"] - prev["walkins"]))
            delta_cols[1].metric("Groups Delta", int(cur["groups"]), int(cur["groups"] - prev["groups"]))
            conv_delta = np.nan if pd.isna(cur["conversion_rate"]) or pd.isna(prev["conversion_rate"]) else cur["conversion_rate"] - prev["conversion_rate"]
            delta_cols[2].metric("Conversion Delta", "N/A" if pd.isna(cur["conversion_rate"]) else f"{float(cur['conversion_rate']):.2%}", "N/A" if pd.isna(conv_delta) else f"{float(conv_delta):+.2%}")
            avg_delta = float(cur["avg_time_spent"] - prev["avg_time_spent"]) if not pd.isna(cur["avg_time_spent"]) and not pd.isna(prev["avg_time_spent"]) else 0.0
            delta_cols[3].metric("Avg Time Delta (mins)", f"{float(cur['avg_time_spent']):.2f}", f"{avg_delta:+.2f}")

    # Benchmarks: selected store vs region and pan-india averages.
    region = str(customer_df["region"].dropna().astype(str).iloc[0]) if not customer_df["region"].dropna().empty else "Unknown"
    region_df = walkin_df[(walkin_df["region"] == region) & (walkin_df["is_customer"])].copy()
    pan_df = walkin_df[walkin_df["is_customer"]].copy()
    bcols = st.columns(3)
    bcols[0].metric("Store Conversion", "N/A" if pd.isna(summary["conversion_rate"]) else f"{float(summary['conversion_rate']):.2%}")
    region_conv = _summarize_walkin_metrics(region_df).get("conversion_rate", np.nan)
    bcols[1].metric("Region Avg Conversion", "N/A" if pd.isna(region_conv) else f"{float(region_conv):.2%}")
    pan_conv = _summarize_walkin_metrics(pan_df).get("conversion_rate", np.nan)
    bcols[2].metric("Pan-India Avg Conversion", "N/A" if pd.isna(pan_conv) else f"{float(pan_conv):.2%}")

    session_split = customer_df.groupby("session_status", as_index=False).agg(count=("walkin_key", "nunique"))
    entry_split = customer_df.groupby("entry_type", as_index=False).agg(count=("walkin_key", "nunique"))
    purchase_split = customer_df.groupby("purchase_signal_bag", as_index=False).agg(count=("walkin_key", "nunique"))
    st.markdown("**Session Close Type**")
    st.dataframe(session_split.sort_values("count", ascending=False), use_container_width=True, hide_index=True)
    st.markdown("**Entry Type Split**")
    st.dataframe(entry_split.sort_values("count", ascending=False), use_container_width=True, hide_index=True)
    st.markdown("**Purchase Signal Summary**")
    st.dataframe(purchase_split.sort_values("count", ascending=False), use_container_width=True, hide_index=True)


def _build_daily_proof_df(image_df: pd.DataFrame, store_result: object, store_id: str) -> pd.DataFrame:
    daily_proof_df = (
        store_result.daily_proof.copy()
        if hasattr(store_result, "daily_proof") and not store_result.daily_proof.empty
        else pd.DataFrame()
    )
    if not daily_proof_df.empty:
        return daily_proof_df
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
    if fallback.empty:
        return fallback
    fallback["store_id"] = store_id
    fallback["folder_name"] = fallback["date"]
    fallback["individual_people"] = 0
    fallback["group_people"] = 0
    fallback["converted"] = 0
    fallback["conversion_rate"] = 0.0
    return fallback[
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


def _gpt_validation_store_dir(root_dir: Path, store_id: str) -> Path:
    return root_dir / "exports" / "current" / "gpt_validation" / store_id


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _load_gpt_outputs(root_dir: Path, store_id: str) -> dict[str, pd.DataFrame]:
    base = _gpt_validation_store_dir(root_dir=root_dir, store_id=store_id)
    return {
        "validation": _read_csv_if_exists(base / "gpt_validation_results.csv"),
        "frame_summary": _read_csv_if_exists(base / "gpt_validation_frame_summary.csv"),
        "store_summary": _read_csv_if_exists(base / "gpt_store_date_summary.csv"),
        "yolo_vs_gpt": _read_csv_if_exists(base / "yolo_vs_gpt_accuracy.csv"),
        "gpt_vs_reviewer": _read_csv_if_exists(base / "gpt_vs_reviewer_accuracy.csv"),
        "gpt_vs_reviewer_detail": _read_csv_if_exists(base / "gpt_vs_reviewer_detail.csv"),
        "walkin_sequence": _read_csv_if_exists(base / "gpt_walkin_sequence_table.csv"),
    }


def _build_gpt_frame_index(gpt_validation_df: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, Any]]:
    if gpt_validation_df.empty:
        return {}
    df = gpt_validation_df.copy()
    for col in ["capture_date", "camera_id", "image_name", "entity_id", "gpt_label"]:
        if col not in df.columns:
            df[col] = ""
    if "annotated_image_path" not in df.columns:
        df["annotated_image_path"] = ""
    if "yolo_detected" not in df.columns:
        df["yolo_detected"] = False
    if "gpt_extra_detection" not in df.columns:
        df["gpt_extra_detection"] = False

    df["capture_date"] = df["capture_date"].map(_normalize_capture_date_key)
    df["camera_id"] = df["camera_id"].astype(str).str.strip()
    df["image_name"] = df["image_name"].astype(str).str.strip()
    df["entity_id"] = df["entity_id"].astype(str).str.strip()
    df["gpt_label"] = df["gpt_label"].map(_label_to_display)
    df["yolo_detected"] = df["yolo_detected"].fillna(False).astype(bool)
    df["gpt_extra_detection"] = df["gpt_extra_detection"].fillna(False).astype(bool)

    frame_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (cap_date, cam, name), part in df.groupby(["capture_date", "camera_id", "image_name"], sort=False):
        working = part.copy()
        working["_sort_idx"] = (
            working["entity_id"]
            .str.extract(r"(\d+)", expand=False)
            .fillna("9999")
            .astype(int)
        )
        working = working.sort_values(["_sort_idx", "entity_id"]).reset_index(drop=True)
        track_ids = [str(v).strip() for v in working["entity_id"].tolist() if str(v).strip()]
        pred_map = {
            str(row.get("entity_id", "")).strip(): str(row.get("gpt_label", "")).strip()
            for _, row in working.iterrows()
            if str(row.get("entity_id", "")).strip()
        }
        yolo_map = {
            str(row.get("entity_id", "")).strip(): bool(row.get("yolo_detected", False))
            for _, row in working.iterrows()
            if str(row.get("entity_id", "")).strip()
        }
        extra_map = {
            str(row.get("entity_id", "")).strip(): bool(row.get("gpt_extra_detection", False))
            for _, row in working.iterrows()
            if str(row.get("entity_id", "")).strip()
        }
        annotated_path = ""
        ann = working["annotated_image_path"].dropna().astype(str).str.strip()
        ann = ann[ann != ""]
        if not ann.empty:
            annotated_path = str(ann.iloc[0])

        frame_index[(str(cap_date), str(cam), str(name))] = {
            "track_ids": track_ids,
            "pred_map": pred_map,
            "yolo_map": yolo_map,
            "extra_map": extra_map,
            "annotated_image_path": annotated_path,
        }
    return frame_index


def _render_onfly_pipeline_journey(db_path: Path) -> None:
    st.subheader("Manual data sync of IRIS")
    st.caption("Live on-fly run visibility: stage status, counts, failures, and scheduler heartbeat.")
    st.markdown("**Run On-Fly Now**")

    def _normalize_onfly_source_input(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return raw
        folder_id = parse_drive_folder_id(raw)
        if folder_id:
            return f"https://drive.google.com/drive/folders/{folder_id}"
        if re.fullmatch(r"[A-Za-z0-9_-]{20,}", raw):
            return f"https://drive.google.com/drive/folders/{raw}"
        return raw

    cfg_settings = get_app_settings(db_path)
    default_store = str(cfg_settings.get("cfg_onfly_store_id", "") or "TEST_STORE_D07").strip() or "TEST_STORE_D07"
    default_source = str(cfg_settings.get("cfg_onfly_source_url", "") or "").strip() or "https://drive.google.com/drive/folders/1Wd8X8t-wF_HhPQPYuuFHjqTq6Ojc3Nnw"
    default_max = int(pd.to_numeric(cfg_settings.get("cfg_onfly_max_images", 100), errors="coerce") or 100)
    default_conf = float(pd.to_numeric(cfg_settings.get("cfg_onfly_conf", 0.18), errors="coerce") or 0.18)

    known_stores = sorted({str(s.store_id).strip() for s in list_stores(db_path) if str(s.store_id).strip()})
    store_options = known_stores if known_stores else [default_store]
    default_idx = store_options.index(default_store) if default_store in store_options else 0
    run_store_id = st.selectbox("Store", options=store_options, index=default_idx, key="onfly_run_store_id")
    run_source_raw = st.text_input(
        "Source Path / Drive URL / Drive Folder ID",
        value=default_source,
        key="onfly_run_source_input",
        help="Supports full Drive URL, folder key only, local folder path, or image folder path.",
    )
    run_overwrite = st.checkbox("Overwrite existing processed data", value=False, key="onfly_run_overwrite")
    normalized_source = _normalize_onfly_source_input(run_source_raw)
    st.caption(f"Normalized Source: `{normalized_source}`")
    st.caption("If reports already exist: overwrite OFF -> reuses delta and skips cached; overwrite ON -> full reprocess.")

    if st.button("Run Pipeline Now", key="onfly_pipeline_run_now_btn", type="primary"):
        if not str(run_store_id or "").strip():
            st.error("Store ID is required.")
        elif not str(normalized_source or "").strip():
            st.error("Source path/URL/folder ID is required.")
        else:
            gkey = str(os.getenv("GOOGLE_API_KEY", "") or "").strip()
            okey = str(os.getenv("OPENAI_API_KEY", "") or "").strip()
            if parse_drive_folder_id(normalized_source) and not gkey:
                st.error("GOOGLE_API_KEY is missing in runtime env. Add it in `.env.local` and restart `iris`.")
            else:
                out_root = db_path.parent / "exports" / "current" / "onfly"
                existing_runs = list_onfly_pipeline_runs(db_path=db_path, store_id=str(run_store_id).strip(), limit=20)
                latest_same_source = next(
                    (
                        r
                        for r in existing_runs
                        if str(r.get("source_uri", "")).strip() == normalized_source and str(r.get("status", "")).strip().lower() == "success"
                    ),
                    None,
                )
                def _hostify(path_text: str) -> str:
                    p = str(path_text or "").strip()
                    if not p:
                        return ""
                    if p.startswith("/app/data/"):
                        return str((db_path.parent / p.replace("/app/data/", "")).resolve())
                    return p

                if latest_same_source and not run_overwrite:
                    img_path = _hostify(str(latest_same_source.get("report_image_results_csv", "") or ""))
                    walk_path = _hostify(str(latest_same_source.get("report_walkin_sessions_csv", "") or ""))
                    store_path = _hostify(str(latest_same_source.get("report_store_date_csv", "") or ""))
                    all_ok = all([img_path, walk_path, store_path, Path(img_path).exists(), Path(walk_path).exists(), Path(store_path).exists()])
                    if all_ok:
                        st.success(f"Existing successful result found (Run ID: {latest_same_source.get('run_id')}). Reusing cached result.")
                        st.markdown("**Report Paths (latest)**")
                        st.write(f"- Image Results: `{img_path}`")
                        st.write(f"- Walk-in Sessions: `{walk_path}`")
                        st.write(f"- Store-Date Report: `{store_path}`")
                        st.info("Set 'Overwrite existing processed data' = ON if you want a full rerun.")
                        st.stop()

                cfg = OnFlyConfig(
                    store_id=str(run_store_id).strip(),
                    source_uri=normalized_source,
                    db_path=db_path,
                    out_dir=out_root,
                    detector_type="yolo",
                    conf_threshold=float(default_conf),
                    max_images=int(default_max),
                    gpt_enabled=bool(okey),
                    openai_api_key=okey,
                    openai_model=str(os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini"),
                    force_reprocess=bool(run_overwrite),
                    run_mode="manual_ui",
                    allow_detector_fallback=True,
                )
                progress = st.progress(0, text="LIST: discovering images")
                with st.spinner("Running on-fly pipeline..."):
                    try:
                        progress.progress(15, text="SKIP_CHECK: checking delta")
                        summary = run_onfly_pipeline(cfg)
                        progress.progress(100, text="Done")
                        st.success(
                            "Run complete: "
                            f"listed={summary.get('total_listed', 0)}, "
                            f"new={summary.get('new_images', 0)}, "
                            f"relevant={summary.get('yolo_relevant', 0)}, "
                            f"gpt_done={summary.get('gpt_done', 0)}"
                        )
                        out = summary.get("outputs", {}) if isinstance(summary.get("outputs", {}), dict) else {}
                        def _friendly(path_text: str) -> str:
                            p = _hostify(path_text)
                            if not p:
                                return "Not generated"
                            try:
                                return str(Path(p).relative_to(db_path.parent.parent))
                            except Exception:
                                return p
                        st.markdown("**Report Paths**")
                        st.write(f"- Image Results: `{_friendly(str(out.get('image_results_csv', '')) )}`")
                        st.write(f"- Walk-in Sessions: `{_friendly(str(out.get('walkin_sessions_csv', '')) )}`")
                        st.write(f"- Store-Date Report: `{_friendly(str(out.get('store_report_csv', '')) )}`")
                        st.caption("Step-by-step scan details are visible below in Stage Timeline and Scheduler Execution History.")
                        st.rerun()
                    except Exception as exc:  # pragma: no cover - UI guard
                        st.error(f"Pipeline run failed: {exc}")

    st.markdown("---")
    if st.button("Refresh Pipeline Status", key="onfly_pipeline_refresh_btn"):
        st.rerun()
    stores = [str(s.store_id or "").strip() for s in list_stores(db_path)]
    stores = sorted([s for s in stores if str(s).strip()])
    options = ["(All Stores)"] + stores
    selected_store = st.selectbox("Store Filter", options=options, index=0, key="onfly_pipeline_store_filter")
    store_filter = "" if selected_store == "(All Stores)" else selected_store

    runs = list_onfly_pipeline_runs(db_path=db_path, store_id=store_filter, limit=200)
    runs_df = pd.DataFrame(runs)
    if runs_df.empty:
        st.info("No on-fly pipeline runs found yet. Trigger `run_iris.bat onfly-run-now` and refresh.")
        return

    for col in [
        "images_discovered",
        "images_skipped",
        "images_processed",
        "images_relevant",
        "images_irrelevant",
        "gpt_success_count",
        "gpt_failed_count",
    ]:
        runs_df[col] = pd.to_numeric(runs_df.get(col, 0), errors="coerce").fillna(0).astype(int)

    display_cols = [
        "run_id",
        "store_id",
        "business_date",
        "source_type",
        "status",
        "current_stage",
        "images_discovered",
        "images_skipped",
        "images_processed",
        "images_relevant",
        "images_irrelevant",
        "gpt_success_count",
        "gpt_failed_count",
        "started_at",
        "ended_at",
        "last_heartbeat_at",
    ]
    st.markdown("**Run List**")
    st.dataframe(runs_df[[c for c in display_cols if c in runs_df.columns]], use_container_width=True, hide_index=True, height=260)

    run_ids = runs_df["run_id"].astype(str).tolist()
    selected_run = st.selectbox("Run ID", options=run_ids, index=0, key="onfly_pipeline_run_selector")
    run_row = runs_df[runs_df["run_id"].astype(str) == str(selected_run)].head(1)
    if run_row.empty:
        st.info("Select a run to inspect details.")
        return
    rr = run_row.iloc[0]
    st.markdown("**Run Detail**")
    mcols = st.columns(6)
    mcols[0].metric("Discovered", int(rr.get("images_discovered", 0)))
    mcols[1].metric("Skipped", int(rr.get("images_skipped", 0)))
    mcols[2].metric("Processed", int(rr.get("images_processed", 0)))
    mcols[3].metric("Relevant", int(rr.get("images_relevant", 0)))
    mcols[4].metric("GPT Success", int(rr.get("gpt_success_count", 0)))
    mcols[5].metric("GPT Failed", int(rr.get("gpt_failed_count", 0)))
    st.caption(
        f"Status={rr.get('status', '')} | Current Stage={rr.get('current_stage', '')} | "
        f"Started={rr.get('started_at', '')} | Ended={rr.get('ended_at', '')}"
    )

    st.markdown("**Report Paths**")
    st.code(
        "\n".join(
            [
                f"image_results: {str(rr.get('report_image_results_csv', '') or '')}",
                f"walkin_sessions: {str(rr.get('report_walkin_sessions_csv', '') or '')}",
                f"store_date: {str(rr.get('report_store_date_csv', '') or '')}",
            ]
        ),
        language="text",
    )
    if str(rr.get("error_message", "") or "").strip():
        st.error(f"Failed at stage `{rr.get('current_stage', '')}`: {rr.get('error_message', '')}")
        trace = str(rr.get("error_trace", "") or "").strip()
        if trace:
            st.code(trace[:3000], language="text")

    def _restore_onfly_run_to_canonical(selected_store_id: str, selected_run_id: str) -> dict[str, Any]:
        out_dir = db_path.parent / "exports" / "current" / "onfly" / selected_store_id
        out_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            image_rows = conn.execute(
                "SELECT * FROM onfly_image_state WHERE store_id=? AND last_run_id=? ORDER BY date_display,image_name",
                (selected_store_id, selected_run_id),
            ).fetchall()
            frame_df = pd.DataFrame([dict(r) for r in image_rows])
            if frame_df.empty:
                raise RuntimeError(f"No image rows found for run_id={selected_run_id}")
            frame_df = frame_df.rename(
                columns={
                    "date_display": "Date",
                    "yolo_relevant": "relevant",
                    "gpt_customer_count": "customer_count",
                    "gpt_staff_count": "staff_count",
                    "gpt_conversions": "conversions",
                    "gpt_bounce": "bounce",
                }
            )

            def _folder_from_rel(rel: Any) -> str:
                txt = str(rel or "").strip().replace("\\", "/")
                if not txt:
                    return ""
                first = txt.split("/", 1)[0].strip()
                parsed = datetime.strptime(first, "%Y-%m-%d") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", first) else None
                return parsed.strftime("%d-%m-%Y") if parsed is not None else first

            frame_df["folder_name"] = frame_df["relative_path"].map(_folder_from_rel) if "relative_path" in frame_df.columns else frame_df.get("Date", "")
            if "date_source" in frame_df.columns:
                frame_df = frame_df.drop(columns=["date_source"])
            preferred = ["store_id", "image_id", "relative_path", "folder_name", "Date", "image_name", "camera_id", "timestamp_hint"]
            frame_df = frame_df[[c for c in preferred if c in frame_df.columns] + [c for c in frame_df.columns if c not in preferred]]

            walk_rows = conn.execute(
                """
                SELECT
                    w.id, w.store_id, w.run_id, w.image_id,
                    s.date_display AS folder_name,
                    s.image_name AS image_name,
                    w.date, w.walkin_id, w.group_id, w.role,
                    w.entry_time, w.exit_time, w.time_spent_mins, w.session_status,
                    w.entry_type, w.gender, w.age_band, w.attire_visual_marker,
                    w.primary_clothing, w.jewellery_load, w.bag_type, w.clothing_style_archetype,
                    w.engagement_type, w.engagement_depth, w.purchase_signal_bag, w.included_in_analytics,
                    w.created_at
                FROM onfly_walkin_sessions w
                LEFT JOIN onfly_image_state s ON s.store_id=w.store_id AND s.image_id=w.image_id
                WHERE w.store_id=? AND w.run_id=?
                ORDER BY w.date,w.walkin_id,w.id
                """,
                (selected_store_id, selected_run_id),
            ).fetchall()
            walk_df = pd.DataFrame([dict(r) for r in walk_rows])
            if not walk_df.empty:
                walk_df["folder_name"] = walk_df["folder_name"].fillna("")
                walk_df["date"] = walk_df["folder_name"]
                preferred_walk = ["id", "store_id", "run_id", "image_id", "folder_name", "image_name", "date"]
                walk_df = walk_df[[c for c in preferred_walk if c in walk_df.columns] + [c for c in walk_df.columns if c not in preferred_walk]]

        image_out = out_dir / "onfly_image_results.csv"
        walk_out = out_dir / "onfly_walkin_sessions.csv"
        frame_df.to_csv(image_out, index=False)
        if walk_df.empty:
            pd.DataFrame(columns=["id", "store_id", "run_id", "image_id", "folder_name", "image_name", "date"]).to_csv(walk_out, index=False)
            walk_count = 0
        else:
            walk_df.to_csv(walk_out, index=False)
            walk_count = int(len(walk_df))
        return {
            "image_csv": str(image_out),
            "walkin_csv": str(walk_out),
            "image_rows": int(len(frame_df)),
            "walk_rows": walk_count,
        }

    if st.button("Restore Selected Run To Canonical Files", key="onfly_restore_run_btn"):
        try:
            restored = _restore_onfly_run_to_canonical(str(rr.get("store_id", "")), str(selected_run))
            st.success(
                f"Restored run `{selected_run}` to canonical files. "
                f"image_rows={restored['image_rows']}, walkin_rows={restored['walk_rows']}"
            )
            st.write(f"- Image Results: `{restored['image_csv']}`")
            st.write(f"- Walk-in Sessions: `{restored['walkin_csv']}`")
        except Exception as exc:
            st.error(f"Restore failed: {exc}")

    events = list_onfly_pipeline_run_events(db_path=db_path, run_id=str(selected_run), limit=2000)
    events_df = pd.DataFrame(events)
    stage_order = ["LIST", "SKIP_CHECK", "DOWNLOAD", "YOLO", "GPT", "REPORT_WRITER", "DASHBOARD_INGEST"]
    st.markdown("**Stage Timeline**")
    if events_df.empty:
        st.info("No stage events found for this run.")
    else:
        events_df["stage_rank"] = events_df["stage"].map({s: i for i, s in enumerate(stage_order)}).fillna(999).astype(int)
        events_df = events_df.sort_values(["stage_rank", "created_at", "event_id"], ascending=[True, True, True])
        timeline_cols = [
            "created_at",
            "stage",
            "event_type",
            "image_name",
            "message",
            "error_message",
            "attempt_no",
        ]
        st.dataframe(events_df[[c for c in timeline_cols if c in events_df.columns]], use_container_width=True, hide_index=True, height=280)

    settings = get_app_settings(db_path)
    st.markdown("**Scheduler Execution History**")
    history_raw = str(settings.get("cfg_onfly_scheduler_history_json", "[]") or "[]")
    try:
        history = json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []
    if not history:
        st.info("No scheduler history yet.")
    else:
        hist_df = pd.DataFrame(history).sort_values("ran_at", ascending=False)
        st.dataframe(hist_df.head(40), use_container_width=True, hide_index=True, height=220)


def _render_report_module(output: AnalysisOutput, root_dir: Path, db_path: Path) -> None:
    st.subheader("Report Module")
    st.caption("Choose store/date and download report data for offline analysis.")

    select_placeholder = "-- Select --"
    mapped_store_ids = sorted({str(s.store_id).strip() for s in list_stores(db_path) if str(s.store_id).strip()})
    store_ids = sorted(set(list(output.stores.keys()) + mapped_store_ids))
    if not store_ids:
        st.info("No stores found. Map at least one store first.")
        return
    selected_store = st.selectbox(
        "Store",
        options=[select_placeholder, *store_ids],
        index=0,
        key="report_module_store_v2",
    )
    if selected_store == select_placeholder:
        st.info("Select a store to load report options.")
        return
    store_result = output.stores.get(selected_store)
    if store_result is not None:
        image_df = _normalize_image_df(store_result.image_insights)
        customer_sessions_df = (
            store_result.customer_sessions.copy()
            if hasattr(store_result, "customer_sessions") and not store_result.customer_sessions.empty
            else pd.DataFrame()
        )
        daily_proof_df = _build_daily_proof_df(image_df=image_df, store_result=store_result, store_id=selected_store)
    else:
        image_df = pd.DataFrame()
        customer_sessions_df = pd.DataFrame()
        daily_proof_df = pd.DataFrame()
    summary_rows = output.all_stores_summary[output.all_stores_summary["store_id"] == selected_store]
    summary_row = summary_rows.iloc[0] if not summary_rows.empty else pd.Series(dtype=object)
    business_kpi = _business_kpi_summary(image_df=image_df, customer_sessions_df=customer_sessions_df) if not image_df.empty else {
        "entries": 0,
        "closed_exits": 0,
        "converted": 0,
        "bounced": 0,
        "conversion_rate": np.nan,
    }
    gpt_outputs = _load_gpt_outputs(root_dir=root_dir, store_id=selected_store)
    onfly_index_rows = get_onfly_report_index(db_path=db_path, store_id=selected_store)
    onfly_index_df = pd.DataFrame(onfly_index_rows)

    image_dates = [str(v) for v in image_df["capture_date"].dropna().astype(str).unique()] if "capture_date" in image_df.columns else []
    onfly_dates = [str(v) for v in onfly_index_df.get("business_date", pd.Series(dtype=str)).dropna().astype(str).unique()] if not onfly_index_df.empty else []
    merged_dates = sorted({d for d in (image_dates + onfly_dates) if str(d).strip()}, reverse=True)
    date_options = [select_placeholder, "All Dates"] + merged_dates
    selected_date = st.selectbox(
        "Date",
        options=date_options,
        index=0,
        key=f"report_module_date_v2_{selected_store}",
    )
    selected_report = st.selectbox(
        "Which report",
        options=[
            select_placeholder,
            "Top Summary",
            "Daily Walk-in & Conversion Report",
            "Daily Calculation Proof (Folder Date Based)",
            "On-Fly Store-Date Summary",
            "On-Fly Image Results",
            "On-Fly Walk-in Sessions",
            "Frame-Level Proof",
            "Data Health",
            "Camera Hotspots",
            "Location Hotspots",
            "GPT Validation Results (Test Folder)",
            "GPT Store-Date Summary (Test Folder)",
            "YOLO vs GPT Accuracy (Test Folder)",
            "GPT vs Reviewer Accuracy (Test Folder)",
            "GPT Consolidated Walk-in Table (Test Folder)",
        ],
        index=0,
        key=f"report_module_type_v2_{selected_store}",
    )
    if selected_date == select_placeholder or selected_report == select_placeholder:
        st.info("Select date and report type to load report data.")
        return

    walkin_columns = [
        "Date",
        "Walk-in ID",
        "Group ID",
        "Role",
        "Entry Time",
        "Exit Time",
        "Time Spent (mins)",
        "Session Status",
        "Entry Type",
        "Gender",
        "Age Band",
        "Attire / Visual Marker",
        "Primary Clothing",
        "Jewellery Load",
        "Bag Type",
        "Primary Clothing Style Archetype",
        "Engagement Type",
        "Engagement Depth",
        "Purchase Signal (Bag)",
        "Included in Analytics",
    ]
    report_df = pd.DataFrame()
    report_download_df = pd.DataFrame()
    if selected_report == "Top Summary":
        report_df = pd.DataFrame(
            [
                {
                    "store_id": selected_store,
                    "total_images": int(summary_row.get("total_images", 0)),
                    "valid_images": int(summary_row.get("valid_images", 0)),
                    "relevant_images": int(summary_row.get("relevant_images", 0)),
                    "total_people": int(summary_row.get("total_people", 0)),
                    "estimated_visits": int(summary_row.get("estimated_visits", 0)),
                    "avg_dwell_sec": float(summary_row.get("avg_dwell_sec", 0.0)),
                    "bounce_rate": summary_row.get("bounce_rate", np.nan),
                    "footfall": int(summary_row.get("footfall", 0)),
                    "los_alerts": int(summary_row.get("loss_of_sale_alerts", 0)),
                    "daily_walkins": int(summary_row.get("daily_walkins", 0)),
                    "daily_conversions": int(summary_row.get("daily_conversions", 0)),
                    "daily_conversion_rate": summary_row.get("daily_conversion_rate", np.nan),
                    "entries": int(business_kpi.get("entries", 0)),
                    "closed_exits": int(business_kpi.get("closed_exits", 0)),
                    "converted": int(business_kpi.get("converted", 0)),
                    "bounced": int(business_kpi.get("bounced", 0)),
                    "conversion_rate": business_kpi.get("conversion_rate", np.nan),
                }
            ]
        )
    elif selected_report == "Daily Walk-in & Conversion Report":
        report_df = (
            store_result.daily_report.copy()
            if hasattr(store_result, "daily_report") and not store_result.daily_report.empty
            else pd.DataFrame()
        )
    elif selected_report == "Daily Calculation Proof (Folder Date Based)":
        if not gpt_outputs["store_summary"].empty:
            report_df = gpt_outputs["store_summary"].copy()
        else:
            report_df = daily_proof_df.copy()
    elif selected_report == "On-Fly Store-Date Summary":
        onfly_store_csv = root_dir.parent / "exports" / "current" / "onfly" / "onfly_store_date_report.csv"
        if onfly_store_csv.exists():
            try:
                report_df = pd.read_csv(onfly_store_csv)
            except Exception:
                report_df = pd.DataFrame()
        if not report_df.empty and "store_id" in report_df.columns:
            report_df = report_df[report_df["store_id"].astype(str) == selected_store].copy()
    elif selected_report == "On-Fly Image Results":
        image_csv = ""
        if not onfly_index_df.empty:
            latest = onfly_index_df.sort_values("updated_at", ascending=False).head(1).iloc[0]
            image_csv = str(latest.get("image_results_csv", "") or "").strip()
        if image_csv and Path(image_csv).exists():
            try:
                report_df = pd.read_csv(Path(image_csv))
            except Exception:
                report_df = pd.DataFrame()
    elif selected_report == "On-Fly Walk-in Sessions":
        walkin_csv = ""
        if not onfly_index_df.empty:
            latest = onfly_index_df.sort_values("updated_at", ascending=False).head(1).iloc[0]
            walkin_csv = str(latest.get("walkin_sessions_csv", "") or "").strip()
        if walkin_csv and Path(walkin_csv).exists():
            try:
                report_df = pd.read_csv(Path(walkin_csv))
            except Exception:
                report_df = pd.DataFrame()
        audit_csv = ""
        if walkin_csv:
            audit_candidate = Path(walkin_csv).with_name("onfly_walkin_sessions_audit.csv")
            if audit_candidate.exists():
                audit_csv = str(audit_candidate)
        show_audit = st.checkbox(
            "Show Audit Columns",
            value=False,
            key="onfly_walkin_show_audit_cols",
            help="Toggle full debug/audit fields for investigation.",
        )
        if show_audit and audit_csv:
            try:
                report_df = pd.read_csv(Path(audit_csv))
            except Exception:
                pass
        if show_audit and not audit_csv:
            st.info("Audit file not found yet for this run. Run on-fly pipeline once to generate it.")
        if not report_df.empty:
            default_cols = list(report_df.columns)
            if not show_audit:
                for c in [
                    "matched_session_id",
                    "match_score",
                    "match_reason",
                    "direction_confidence",
                    "match_fingerprint",
                    "debug_parsed_time",
                    "created_at",
                    "debug_gpt_event_type",
                ]:
                    if c in default_cols:
                        default_cols.remove(c)
            selected_cols = st.multiselect(
                "Visible Columns",
                options=list(report_df.columns),
                default=default_cols,
                key="onfly_walkin_visible_columns",
            )
            if selected_cols:
                report_df = report_df[selected_cols].copy()
    elif selected_report == "Frame-Level Proof":
        report_df = image_df.copy()
        report_df["open_frame"] = report_df.apply(
            lambda r: _row_image_hyperlink(
                r,
                store_id=selected_store,
                root_dir=root_dir,
                auth_token=str(st.session_state.get("session_token", "")).strip(),
            ),
            axis=1,
        )
        proof_columns = [
            "capture_date",
            "source_folder",
            "timestamp",
            "filename",
            "open_frame",
            "camera_id",
            "floor_name",
            "location_name",
            "person_count",
            "relevant",
            "track_ids",
            "group_ids",
            "store_day_customer_ids",
            "customer_ids",
            "drive_link",
            "detection_error",
        ]
        report_df = report_df[[col for col in proof_columns if col in report_df.columns]].copy()
    elif selected_report == "Data Health":
        report_df = image_df[
            [
                "capture_date",
                "filename",
                "camera_id",
                "is_valid",
                "reject_reason",
                "detection_error",
            ]
        ].copy()
        report_df.insert(0, "store_id", selected_store)
    elif selected_report == "Camera Hotspots":
        report_df = (
            store_result.camera_hotspots.copy()
            if hasattr(store_result, "camera_hotspots") and not store_result.camera_hotspots.empty
            else pd.DataFrame()
        )
    elif selected_report == "Location Hotspots":
        report_df = (
            store_result.location_hotspots.copy()
            if hasattr(store_result, "location_hotspots") and not store_result.location_hotspots.empty
            else pd.DataFrame()
        )
    elif selected_report == "GPT Validation Results (Test Folder)":
        report_df = gpt_outputs["validation"].copy()
    elif selected_report == "GPT Store-Date Summary (Test Folder)":
        report_df = gpt_outputs["store_summary"].copy()
    elif selected_report == "YOLO vs GPT Accuracy (Test Folder)":
        report_df = gpt_outputs["yolo_vs_gpt"].copy()
    elif selected_report == "GPT vs Reviewer Accuracy (Test Folder)":
        report_df = gpt_outputs["gpt_vs_reviewer_detail"].copy()
        if report_df.empty:
            report_df = gpt_outputs["gpt_vs_reviewer"].copy()
    elif selected_report == "GPT Consolidated Walk-in Table (Test Folder)":
        report_df = gpt_outputs["walkin_sequence"].copy()
        if report_df.empty:
            report_df = pd.DataFrame(columns=walkin_columns)
        else:
            report_df = report_df.reindex(columns=walkin_columns)

    date_filter_col = ""
    if "date" in report_df.columns:
        date_filter_col = "date"
    elif "Date" in report_df.columns:
        date_filter_col = "Date"
    elif "capture_date" in report_df.columns:
        date_filter_col = "capture_date"
    if date_filter_col and selected_date != "All Dates":
        report_df = report_df[report_df[date_filter_col].astype(str) == str(selected_date)].copy()
    report_download_df = report_df.copy()

    allow_empty_download = selected_report == "GPT Consolidated Walk-in Table (Test Folder)"
    if report_df.empty and not allow_empty_download:
        st.info("No rows available for this report with the selected filters.")
        return
    if report_df.empty and allow_empty_download:
        st.info("No rows yet. Download will contain empty template with required columns.")

    report_file_stub = re.sub(r"[^A-Za-z0-9_]+", "_", selected_report.strip().lower())
    date_stub = "all_dates" if selected_date == "All Dates" else re.sub(r"[^0-9A-Za-z_-]+", "_", selected_date)
    file_name = f"{selected_store}_{report_file_stub}_{date_stub}.csv"
    csv_bytes = report_download_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
    )
    if selected_report == "GPT Validation Results (Test Folder)":
        view_df = report_df.head(500).copy()
        if "annotated_image_path" in view_df.columns:
            view_df["preview_image"] = view_df["annotated_image_path"].map(
                lambda p: _hover_preview_data_uri(Path(str(p).strip()), max_size=280)
                if str(p or "").strip() and Path(str(p).strip()).exists()
                else ""
            )
        if "preview_image" in view_df.columns:
            columns = ["preview_image"] + [c for c in view_df.columns if c != "preview_image"]
            view_df = view_df[columns]
            st.dataframe(
                view_df,
                use_container_width=True,
                hide_index=True,
                column_config={"preview_image": st.column_config.ImageColumn("Preview")},
            )
        else:
            st.dataframe(view_df, use_container_width=True, hide_index=True)
    elif report_df.empty:
        st.dataframe(report_df.head(0), use_container_width=True, hide_index=True)
    else:
        st.dataframe(report_df.head(500), use_container_width=True, hide_index=True)


def _render_qa_timeline(output: AnalysisOutput, db_path: Path, active_email: str, root_dir: Path) -> None:
    st.subheader("Frame Review")
    st.caption("Frame-by-frame validation report to verify people counts, customer IDs, and image-level links.")
    if not output.stores:
        st.info("No store analysis loaded.")
        return

    select_placeholder = "-- Select Store --"
    store_ids = sorted(output.stores.keys())
    preselected_store = _query_value("store", "").strip()
    store_options = [select_placeholder, *store_ids]
    default_value = preselected_store if preselected_store in store_ids else select_placeholder
    default_index = store_options.index(default_value)
    sid = st.selectbox("Store", options=store_options, index=default_index, key="qa_store_v2")
    if sid == select_placeholder:
        st.info("Select a store to load pending review rows.")
        return
    runtime_settings = _ensure_config_defaults(db_path)
    cfg_auto_confirm = _setting_bool(runtime_settings, "cfg_feedback_auto_confirm", True)
    cfg_batch_confidence = _setting_float(runtime_settings, "cfg_feedback_batch_confidence", 0.9, minimum=0.0, maximum=1.0)
    cfg_fast_edit_mode = _setting_bool(runtime_settings, "cfg_feedback_fast_edit_mode", True)
    cfg_hide_reviewed = _setting_bool(runtime_settings, "cfg_feedback_hide_reviewed", True)
    cfg_rerun_after_save = _setting_bool(runtime_settings, "cfg_feedback_rerun_after_save", False)
    cfg_retrain_min_rows = _setting_int(runtime_settings, "cfg_retrain_min_rows", 10, minimum=1, maximum=100000)
    image_df = _normalize_image_df(output.stores[sid].image_insights)
    if image_df.empty:
        st.info("No image rows available for this store.")
        return
    notice = str(st.session_state.pop("feedback_relearn_notice", "") or "").strip()
    if notice:
        st.success(notice)
    save_notice = str(st.session_state.pop("feedback_save_notice", "") or "").strip()
    if save_notice:
        st.info(save_notice)

    def _frame_key(capture_date: object, camera_id: object, filename: object) -> tuple[str, str, str]:
        return (
            _normalize_capture_date_key(capture_date),
            str(camera_id or "").strip(),
            str(filename or "").strip(),
        )

    def _track_key(capture_date: object, camera_id: object, filename: object, track_id: object) -> tuple[str, str, str, str]:
        return (*_frame_key(capture_date, camera_id, filename), str(track_id or "").strip())

    image_df = image_df.sort_values("timestamp", ascending=False).reset_index(drop=True)
    image_df["predicted_label"] = image_df.apply(_predicted_label, axis=1)
    image_df["track_count"] = image_df["track_ids"].map(lambda x: len(_safe_json_list(x)))
    unique_ids = sorted(
        {
            str(cid)
            for ids in (
                image_df["store_day_customer_ids"].tolist()
                if "store_day_customer_ids" in image_df.columns
                else image_df["customer_ids"].tolist()
            )
            for cid in _safe_json_list(ids)
            if str(cid).strip()
        }
    )
    existing_feedback_rows = list_qa_feedback(
        db_path=db_path,
        store_id=sid,
        review_status=None,
        limit=5000,
    )
    accuracy_summary, accuracy_trend_df = _build_feedback_accuracy_report(
        feedback_rows=existing_feedback_rows,
        image_df=image_df,
        db_path=db_path,
        store_id=sid,
    )
    gpt_outputs = _load_gpt_outputs(root_dir=root_dir, store_id=sid)
    gpt_validation_df = gpt_outputs.get("validation", pd.DataFrame()).copy()
    gpt_frame_index = _build_gpt_frame_index(gpt_validation_df)
    gpt_yolo_vs_df = gpt_outputs.get("yolo_vs_gpt", pd.DataFrame()).copy()
    gpt_vs_reviewer_df = gpt_outputs.get("gpt_vs_reviewer", pd.DataFrame()).copy()

    top_cols = st.columns(6)
    top_cols[0].metric("Frames", int(len(image_df)))
    top_cols[1].metric("Detected People", int(image_df["person_count"].sum()))
    top_cols[2].metric("Unique Customer IDs", int(len(unique_ids)))
    scored_rows = int(accuracy_summary.get("scored_rows", 0.0))
    accuracy_label = f"{float(accuracy_summary.get('accuracy_pct', 0.0)):.2f}%" if scored_rows > 0 else "N/A"
    top_cols[3].metric("Feedback Match Accuracy", accuracy_label)
    top_cols[4].metric("Compared Feedback Rows", scored_rows)
    top_cols[5].metric("No Customer Labels", int(accuracy_summary.get("no_customer_rows", 0.0)))
    st.caption(
        f"Frames with drive link: {int((image_df['drive_link'].fillna('') != '').sum())} | "
        f"Matched={int(accuracy_summary.get('matched_rows', 0.0))} | "
        f"Mismatched={int(accuracy_summary.get('mismatch_rows', 0.0))}"
    )
    if not gpt_validation_df.empty:
        yolo_match_pct = (
            round(
                float(
                    pd.to_numeric(gpt_yolo_vs_df.get("match", False), errors="coerce")
                    .fillna(False)
                    .astype(bool)
                    .mean()
                    * 100.0
                ),
                2,
            )
            if not gpt_yolo_vs_df.empty
            else None
        )
        reviewer_acc_pct = (
            float(
                pd.to_numeric(
                    gpt_vs_reviewer_df.get("accuracy_pct", pd.Series([0.0])),
                    errors="coerce",
                )
                .fillna(0.0)
                .iloc[0]
            )
            if not gpt_vs_reviewer_df.empty
            else None
        )
        gpt_extra_count = (
            int(gpt_validation_df["gpt_extra_detection"].fillna(False).astype(bool).sum())
            if "gpt_extra_detection" in gpt_validation_df.columns
            else 0
        )
        st.caption(
            "GPT post-relevance validation loaded. "
            f"YOLO vs GPT={f'{yolo_match_pct:.2f}%' if yolo_match_pct is not None else 'N/A'} | "
            f"GPT vs reviewer={f'{reviewer_acc_pct:.2f}%' if reviewer_acc_pct is not None else 'N/A'} | "
            f"GPT extra detections={gpt_extra_count}"
        )

    st.markdown("**Feedback Accuracy Trend**")
    out_dir = Path(str(st.session_state.get("ctrl_out_str", "data/exports/current"))).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    trend_path = out_dir / f"store_{sid}_feedback_accuracy_trend.csv"
    if accuracy_trend_df.empty:
        st.info("No scored feedback rows yet. Save feedback to start tracking model match accuracy.")
    else:
        accuracy_trend_df.to_csv(trend_path, index=False)
        st.caption(f"Accuracy trend export: {trend_path}")
        try:
            fig = px.line(
                accuracy_trend_df,
                x="run_index",
                y="accuracy_pct",
                markers=True,
                hover_data=["model_version", "total_rows", "matched_rows", "mismatch_rows", "last_feedback_at"],
                labels={"run_index": "Model Run Index", "accuracy_pct": "Match Accuracy (%)"},
                title=f"{sid} Feedback Match Accuracy",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass
        st.dataframe(accuracy_trend_df, use_container_width=True, hide_index=True, height=220)

    st.markdown("**Validation Table (Top 10 Frames)**")
    st.caption(
        "Use this single table to review images, assign feedback labels, and save in bulk. "
        "Keep `Select` checked only for rows you want to save. "
        "Use `No Customer` for empty/no-customer frames. "
        "Use `Tn Pred` vs `Tn Feedback` columns for per-track corrections. "
        "Saving again updates existing track feedback for the same frame+track."
    )
    latest_feedback_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    latest_frame_feedback_by_key: dict[tuple[str, str, str], dict[str, object]] = {}
    latest_track_feedback_by_key: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for feedback_row in sorted(
        existing_feedback_rows,
        key=lambda r: int(r.get("id", 0) or 0),
        reverse=True,
    ):
        key = _frame_key(
            feedback_row.get("capture_date", ""),
            feedback_row.get("camera_id", ""),
            feedback_row.get("filename", ""),
        )
        if key not in latest_feedback_by_key:
            latest_feedback_by_key[key] = feedback_row
        track_id = str(feedback_row.get("track_id", "") or "").strip()
        if not track_id and key not in latest_frame_feedback_by_key:
            latest_frame_feedback_by_key[key] = feedback_row
        if track_id:
            track_key = _track_key(
                feedback_row.get("capture_date", ""),
                feedback_row.get("camera_id", ""),
                feedback_row.get("filename", ""),
                track_id,
            )
            if track_key not in latest_track_feedback_by_key:
                latest_track_feedback_by_key[track_key] = feedback_row
    reviewed_frame_keys = {
        (d, c, f)
        for (d, c, f, _tid) in latest_track_feedback_by_key.keys()
    }
    reviewed_frame_keys |= set(latest_frame_feedback_by_key.keys())
    preview_cache_key = f"qa_preview_cache_{sid}"
    preview_cache = st.session_state.get(preview_cache_key)
    if not isinstance(preview_cache, dict):
        preview_cache = {}
        st.session_state[preview_cache_key] = preview_cache

    def _preview_uri_cached(row: pd.Series) -> str:
        frame_key = _frame_key(row.get("capture_date", ""), row.get("camera_id", ""), row.get("filename", ""))
        gpt_meta = gpt_frame_index.get(frame_key, {})
        gpt_annotated = str(gpt_meta.get("annotated_image_path", "") or "").strip() if isinstance(gpt_meta, dict) else ""
        if gpt_annotated and Path(gpt_annotated).exists():
            return _hover_preview_data_uri(Path(gpt_annotated), max_size=320)
        cache_key = (
            str(row.get("capture_date", "") or "").strip(),
            str(row.get("camera_id", "") or "").strip(),
            str(row.get("filename", "") or "").strip(),
            str(row.get("path", "") or "").strip(),
            str(row.get("person_boxes", "") or "").strip(),
            str(row.get("staff_flags", "") or "").strip(),
            str(row.get("track_ids", "") or "").strip(),
            320,
        )
        cached = str(preview_cache.get(cache_key, "") or "")
        if cached:
            return cached
        generated = _overlay_or_source_preview_uri(row, store_id=sid, root_dir=root_dir, max_size=320)
        preview_cache[cache_key] = generated
        if len(preview_cache) > 600:
            for old_key in list(preview_cache.keys())[:120]:
                preview_cache.pop(old_key, None)
        return generated

    gpt_max_slots = max(
        [len(list(v.get("track_ids", []))) for v in gpt_frame_index.values() if isinstance(v, dict)] or [1]
    )
    max_track_slots = max(
        1,
        min(
            20,
            int(
                max(
                    image_df.head(10)["track_ids"].map(
                        lambda raw: len([str(x) for x in _safe_json_list(raw) if str(x).strip()])
                    ).max()
                    or 1,
                    gpt_max_slots,
                )
            ),
        ),
    )

    def _prepare_batch_rows(base_df: pd.DataFrame, slot_numbers: list[int]) -> pd.DataFrame:
        df = base_df.copy()
        df["track_ids_list"] = df.apply(
            lambda r: (
                [
                    str(x).strip()
                    for x in list(
                        gpt_frame_index.get(
                            _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                            {},
                        ).get("track_ids", [])
                    )
                    if str(x).strip()
                ]
                or [str(x) for x in _safe_json_list(r.get("track_ids", "")) if str(x).strip()]
            ),
            axis=1,
        )
        df["staff_flags_list"] = df["staff_flags"].map(
            lambda raw: [bool(x) for x in _safe_json_list(raw)]
        )
        df["capture_date"] = df["capture_date"].astype(str)
        df["timestamp"] = df["timestamp"].astype(str)
        df["predicted_label"] = df.apply(_predicted_label, axis=1).map(_label_to_display)
        df["preview_image"] = df.apply(_preview_uri_cached, axis=1)
        df["feedback_label"] = df.apply(_feedback_label_default, axis=1).astype(str)
        df["feedback_comment"] = ""
        df["frame_no_customer_label"] = df.apply(
            lambda r: "NO_CUSTOMER" if int(pd.to_numeric([r.get("person_count", 0)], errors="coerce")[0] or 0) <= 0 else "",
            axis=1,
        )
        df["selected"] = True
        df["feedback_status"] = df.apply(
            lambda r: (
                "reviewed"
                if _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")) in reviewed_frame_keys
                else ""
            ),
            axis=1,
        )
        df["last_feedback"] = df.apply(
            lambda r: str(
                latest_feedback_by_key.get(
                    _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                    {},
                ).get("corrected_label", "")
                or ""
            ),
            axis=1,
        ).map(_label_to_display)
        df["frame_no_customer_label"] = df.apply(
            lambda r: (
                "NO_CUSTOMER"
                if _label_to_canonical(
                    latest_frame_feedback_by_key.get(
                        _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                        {},
                    ).get("corrected_label", "")
                    or ""
                )
                == "no_person"
                else ""
                or str(r.get("frame_no_customer_label", "") or "")
            ),
            axis=1,
        )
        df["track_ids"] = df["track_ids_list"].map(
            lambda raw: ", ".join([str(x) for x in list(raw) if str(x).strip()])
        )
        for slot in slot_numbers:
            df[f"track_{slot}_id"] = df.apply(
                lambda r: (
                    list(r.get("track_ids_list", []))[slot - 1]
                    if len(list(r.get("track_ids_list", []))) >= slot
                    else ""
                ),
                axis=1,
            )
            df[f"track_{slot}_predicted"] = df.apply(
                lambda r: (
                    str(
                        gpt_frame_index.get(
                            _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                            {},
                        )
                        .get("pred_map", {})
                        .get(str(r.get(f"track_{slot}_id", "") or "").strip(), "")
                        or ""
                    ).strip()
                    or (
                        _label_to_display("staff")
                        if len(list(r.get("staff_flags_list", []))) >= slot and bool(list(r.get("staff_flags_list", []))[slot - 1])
                        else (
                            _label_to_display("customer")
                            if len(list(r.get("staff_flags_list", []))) >= slot
                            else ""
                        )
                    )
                ),
                axis=1,
            )
            df[f"track_{slot}_yolo"] = df.apply(
                lambda r: (
                    "YOLO"
                    if bool(
                        gpt_frame_index.get(
                            _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                            {},
                        )
                        .get("yolo_map", {})
                        .get(str(r.get(f"track_{slot}_id", "") or "").strip(), False)
                    )
                    else (
                        "GPT_EXTRA"
                        if str(r.get(f"track_{slot}_id", "") or "").strip()
                        and str(
                            gpt_frame_index.get(
                                _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                                {},
                            )
                            .get("pred_map", {})
                            .get(str(r.get(f"track_{slot}_id", "") or "").strip(), "")
                            or ""
                        ).strip()
                        else ""
                    )
                ),
                axis=1,
            )
            df[f"track_{slot}_feedback"] = df.apply(
                lambda r: (
                    _label_to_display(
                        latest_track_feedback_by_key.get(
                            _track_key(
                                r.get("capture_date", ""),
                                r.get("camera_id", ""),
                                r.get("filename", ""),
                                r.get(f"track_{slot}_id", ""),
                            ),
                            {},
                        ).get("corrected_label", "")
                        or ""
                    )
                )
                if str(r.get(f"track_{slot}_id", "") or "").strip()
                else "",
                axis=1,
            )
            df[f"track_{slot}_label"] = df.apply(
                lambda r: (
                    str(r.get(f"track_{slot}_feedback", "") or "").strip().upper()
                    if str(r.get(f"track_{slot}_feedback", "") or "").strip()
                    else ""
                ),
                axis=1,
            )
        df = df.drop(columns=["track_ids_list", "staff_flags_list"], errors="ignore")
        return df

    slot_default = min(max_track_slots, 4)
    visible_track_slots = st.slider(
        "Track columns (for multi-person frames)",
        min_value=1,
        max_value=max_track_slots,
        value=slot_default,
        step=1,
        key=f"qa_track_slots_{sid}",
        help="Increase this when a frame has more than 4 track IDs.",
    )
    slot_numbers = list(range(1, int(visible_track_slots) + 1))
    st.caption(
        "Feedback settings are managed in `Access > Config > Feedback`. "
        f"Current: auto_confirm={cfg_auto_confirm}, default_confidence={cfg_batch_confidence:.2f}, "
        f"fast_edit={cfg_fast_edit_mode}, hide_reviewed={cfg_hide_reviewed}, rerun_after_save={cfg_rerun_after_save}."
    )

    batch_rows = _prepare_batch_rows(image_df.head(10), slot_numbers=slot_numbers)
    hide_reviewed = bool(cfg_hide_reviewed)
    if hide_reviewed:
        batch_rows = batch_rows[batch_rows["feedback_status"] == ""].copy()
        if batch_rows.empty:
            st.info(
                "All top 10 frames are already reviewed and hidden. "
                "To re-label old rows, set `Access > Config > Feedback > Hide Reviewed Rows In Pending = OFF` and refresh."
            )

    editor_columns = ["selected", "preview_image", "capture_date", "camera_id", "filename", "frame_no_customer_label", "feedback_comment", "track_ids"]
    disabled_columns = [
        "preview_image",
        "capture_date",
        "camera_id",
        "filename",
        "track_ids",
        "drive_link",
    ]
    column_config: dict[str, object] = {
        "selected": st.column_config.CheckboxColumn("Select"),
        "preview_image": st.column_config.ImageColumn("Preview"),
        "frame_no_customer_label": st.column_config.SelectboxColumn("No Customer", options=["", "NO_CUSTOMER"]),
        "feedback_comment": st.column_config.TextColumn("Comment"),
        "track_ids": st.column_config.TextColumn("Track IDs"),
        "drive_link": st.column_config.LinkColumn("Drive", display_text="Open"),
    }
    for slot in slot_numbers:
        editor_columns.extend([f"track_{slot}_id", f"track_{slot}_predicted", f"track_{slot}_yolo", f"track_{slot}_label"])
        disabled_columns.extend([f"track_{slot}_id", f"track_{slot}_predicted", f"track_{slot}_yolo"])
        column_config[f"track_{slot}_id"] = st.column_config.TextColumn(f"T{slot} ID")
        column_config[f"track_{slot}_predicted"] = st.column_config.TextColumn(f"T{slot} Pred")
        column_config[f"track_{slot}_yolo"] = st.column_config.TextColumn(f"T{slot} Source")
        column_config[f"track_{slot}_label"] = st.column_config.SelectboxColumn(
            f"T{slot} Feedback",
            options=TRACK_FEEDBACK_OPTIONS,
        )
    editor_columns.extend(["drive_link"])
    editor_state_key = f"qa_batch_editor_v2_{sid}"
    form_state_key = f"qa_batch_form_v2_{sid}"
    # Reset legacy editor state after schema changes so columns/edits stay stable.
    for legacy_key in (f"qa_batch_editor_{sid}", f"qa_batch_form_{sid}"):
        st.session_state.pop(legacy_key, None)

    with st.form(key=form_state_key, clear_on_submit=False):
        auto_confirm_feedback = bool(cfg_auto_confirm)
        batch_confidence = float(cfg_batch_confidence)
        rerun_after_save = bool(cfg_rerun_after_save)
        pending_retrain_rows = 0
        retrain_key = f"qa_last_retrain_feedback_id__{sid}"
        try:
            last_retrain_feedback_id = int(str(runtime_settings.get(retrain_key, "0") or "0"))
        except Exception:
            last_retrain_feedback_id = 0
        confirmed_rows_for_store = [r for r in existing_feedback_rows if str(r.get("review_status", "")).strip().lower() == "confirmed"]
        pending_retrain_rows = len([r for r in confirmed_rows_for_store if int(r.get("id", 0) or 0) > last_retrain_feedback_id])
        st.caption(
            f"Pending retrain rows: {pending_retrain_rows} | "
            f"Retrain min rows: {cfg_retrain_min_rows} | "
            f"Next scheduler run: {str(runtime_settings.get('cfg_scheduler_next_run_at', '') or 'Not scheduled')}"
        )
        st.caption("If Auto-confirm is ON, saved feedback moves to Review History directly.")
        try:
            edited_batch_df = st.data_editor(
                batch_rows[editor_columns],
                use_container_width=True,
                hide_index=True,
                height=420,
                key=editor_state_key,
                disabled=disabled_columns,
                column_config=column_config,
            )
        except Exception:
            st.dataframe(batch_rows, use_container_width=True, hide_index=True, height=420)
            edited_batch_df = batch_rows[editor_columns].copy()
        submit_batch = st.form_submit_button("Save Selected Feedback (Top 10)", type="primary")

    if submit_batch:
        settings = get_app_settings(db_path)
        active_model_key = f"qa_active_model_id__{sid}"
        active_model_id = str(settings.get(active_model_key, "baseline_rules_v1") or "baseline_rules_v1")
        saved = 0
        confirmed = 0
        track_saved = 0
        track_confirmed = 0
        track_updated = 0
        track_created = 0
        frame_saved = 0
        frame_confirmed = 0
        frame_updated = 0
        frame_created = 0
        relearned = 0
        source_lookup = {
            _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")): r
            for _, r in image_df.iterrows()
        }
        for _, row in edited_batch_df.iterrows():
            if not bool(row.get("selected", False)):
                continue
            capture_date = _normalize_capture_date_key(row.get("capture_date", ""))
            camera_id = str(row.get("camera_id", "") or "").strip()
            filename = str(row.get("filename", "") or "").strip()
            if not filename:
                continue
            comment = str(row.get("feedback_comment", "") or "").strip()
            source_key = _frame_key(capture_date, camera_id, filename)
            source_row = source_lookup.get(source_key)
            if source_row is None:
                matched = image_df[
                    (image_df["filename"].astype(str) == filename)
                    & (image_df["camera_id"].astype(str) == camera_id)
                ]
                if matched.empty:
                    continue
                source_row = matched.iloc[0]
                capture_date = _normalize_capture_date_key(source_row.get("capture_date", "") or capture_date)
            banner_relearned_for_row = False
            desired_status = "confirmed" if bool(auto_confirm_feedback) else "pending"
            desired_confidence = float(batch_confidence)
            frame_feedback_value = str(row.get("frame_no_customer_label", "") or "").strip().upper()
            if frame_feedback_value == "NO_CUSTOMER":
                frame_key = _frame_key(capture_date, camera_id, filename)
                frame_label_canonical = _label_to_canonical(frame_feedback_value)
                frame_predicted_canonical = _label_to_canonical(_predicted_label(source_row))
                existing_frame_feedback = latest_frame_feedback_by_key.get(frame_key)
                existing_frame_id = int(existing_frame_feedback.get("id", 0) or 0) if isinstance(existing_frame_feedback, dict) else 0
                if existing_frame_id > 0:
                    existing_label = _label_to_canonical((existing_frame_feedback or {}).get("corrected_label", ""))
                    existing_comment = str((existing_frame_feedback or {}).get("comment", "") or "").strip()
                    existing_status = str((existing_frame_feedback or {}).get("review_status", "pending") or "pending").strip().lower()
                    existing_confidence = float(
                        pd.to_numeric([(existing_frame_feedback or {}).get("confidence", 0.0)], errors="coerce")[0] or 0.0
                    )
                    if not (
                        existing_label == frame_label_canonical
                        and existing_comment == comment
                        and existing_status == desired_status
                        and abs(existing_confidence - desired_confidence) < 1e-6
                    ):
                        update_qa_feedback_entry(
                            db_path=db_path,
                            feedback_id=existing_frame_id,
                            corrected_label=frame_label_canonical,
                            comment=comment,
                            confidence=desired_confidence,
                            reviewer_email=(active_email or "system@local"),
                            review_status=desired_status,
                        )
                        frame_updated += 1
                        if desired_status == "confirmed":
                            confirmed += 1
                            frame_confirmed += 1
                    latest_frame_feedback_by_key[frame_key] = {
                        "id": int(existing_frame_id),
                        "corrected_label": frame_label_canonical,
                        "review_status": desired_status,
                        "comment": comment,
                        "confidence": desired_confidence,
                    }
                    saved += 1
                    frame_saved += 1
                else:
                    frame_feedback_id = add_qa_feedback(
                        db_path=db_path,
                        store_id=sid,
                        capture_date=capture_date,
                        filename=filename,
                        camera_id=camera_id,
                        track_id="",
                        predicted_label=str(frame_predicted_canonical),
                        corrected_label=frame_label_canonical,
                        confidence=desired_confidence,
                        needs_review=not bool(auto_confirm_feedback),
                        actor_email=(active_email or "system@local"),
                        model_version=active_model_id,
                        drive_link=str(source_row.get("drive_link", "") or "").strip(),
                        comment=comment,
                        review_status=desired_status,
                        reviewer_email=(active_email or "system@local") if desired_status == "confirmed" else "",
                    )
                    latest_frame_feedback_by_key[frame_key] = {
                        "id": int(frame_feedback_id),
                        "corrected_label": frame_label_canonical,
                        "review_status": desired_status,
                        "comment": comment,
                        "confidence": desired_confidence,
                    }
                    saved += 1
                    frame_saved += 1
                    frame_created += 1
                    if desired_status == "confirmed":
                        confirmed += 1
                        frame_confirmed += 1
            for slot in slot_numbers:
                track_id_value = str(row.get(f"track_{slot}_id", "") or "").strip()
                track_label_value = str(row.get(f"track_{slot}_label", "") or "").strip().upper()
                if not track_id_value or not track_label_value:
                    continue
                if track_label_value not in FEEDBACK_LABEL_OPTIONS:
                    continue
                track_label_canonical = _label_to_canonical(track_label_value)
                track_predicted_canonical = _label_to_canonical(str(row.get(f"track_{slot}_predicted", "") or ""))
                if not track_predicted_canonical:
                    track_predicted_canonical = _label_to_canonical(_predicted_label(source_row))
                track_key = _track_key(capture_date, camera_id, filename, track_id_value)
                existing_track_feedback = latest_track_feedback_by_key.get(track_key)
                existing_track_id = int(existing_track_feedback.get("id", 0) or 0) if isinstance(existing_track_feedback, dict) else 0
                if existing_track_id > 0:
                    existing_label = _label_to_canonical((existing_track_feedback or {}).get("corrected_label", ""))
                    existing_comment = str((existing_track_feedback or {}).get("comment", "") or "").strip()
                    existing_status = str((existing_track_feedback or {}).get("review_status", "pending") or "pending").strip().lower()
                    existing_confidence = float(
                        pd.to_numeric([(existing_track_feedback or {}).get("confidence", 0.0)], errors="coerce")[0] or 0.0
                    )
                    if (
                        existing_label == track_label_canonical
                        and existing_comment == comment
                        and existing_status == desired_status
                        and abs(existing_confidence - desired_confidence) < 1e-6
                    ):
                        continue
                    update_qa_feedback_entry(
                        db_path=db_path,
                        feedback_id=existing_track_id,
                        corrected_label=track_label_canonical,
                        comment=comment,
                        confidence=desired_confidence,
                        reviewer_email=(active_email or "system@local"),
                        review_status=desired_status,
                    )
                    track_feedback_id = existing_track_id
                    track_updated += 1
                    if desired_status == "confirmed":
                        confirmed += 1
                        track_confirmed += 1
                else:
                    track_feedback_id = add_qa_feedback(
                        db_path=db_path,
                        store_id=sid,
                        capture_date=capture_date,
                        filename=filename,
                        camera_id=camera_id,
                        track_id=track_id_value,
                        predicted_label=str(track_predicted_canonical),
                        corrected_label=track_label_canonical,
                        confidence=desired_confidence,
                        needs_review=not bool(auto_confirm_feedback),
                        actor_email=(active_email or "system@local"),
                        model_version=active_model_id,
                        drive_link=str(source_row.get("drive_link", "") or "").strip(),
                        comment=comment,
                        review_status=desired_status,
                        reviewer_email=(active_email or "system@local") if desired_status == "confirmed" else "",
                    )
                    track_created += 1
                    if desired_status == "confirmed":
                        confirmed += 1
                        track_confirmed += 1
                latest_track_feedback_by_key[track_key] = {
                    "id": int(track_feedback_id),
                    "capture_date": capture_date,
                    "camera_id": camera_id,
                    "filename": filename,
                    "track_id": track_id_value,
                    "corrected_label": track_label_canonical,
                    "review_status": desired_status,
                    "comment": comment,
                    "confidence": desired_confidence,
                }
                saved += 1
                track_saved += 1
                if (not banner_relearned_for_row) and track_label_canonical == "poster_banner" and int(source_row.get("person_count", 0) or 0) > 0:
                    relearned += _learn_false_positive_signatures_from_row(
                        db_path=db_path,
                        store_id=sid,
                        row=source_row,
                        root_dir=root_dir,
                        feedback_id=int(track_feedback_id),
                    )
                    banner_relearned_for_row = True
        selected_count = int(pd.to_numeric(edited_batch_df.get("selected", False), errors="coerce").fillna(0).astype(int).sum())
        if selected_count <= 0:
            st.info("No rows were selected to save.")
        elif saved <= 0:
            st.warning(
                "Rows were selected, but no feedback label changed. "
                "Pick at least one `Tn Feedback` value (or `No Customer`) and click save again."
            )
        else:
            st.success(
                f"Saved {saved} feedback rows (frame-level={frame_saved}, track-level={track_saved}, "
                f"created={frame_created + track_created}, updated={frame_updated + track_updated}). "
                f"Auto-confirmed={confirmed} (frame-level={frame_confirmed}, track-level={track_confirmed}). "
                f"Poster-signatures learned={relearned}."
            )
            latest_settings = _ensure_config_defaults(db_path)
            queue_count = _pending_retrain_rows_for_store(db_path=db_path, store_id=sid, settings=latest_settings)
            next_run_dt = _parse_iso_utc(latest_settings.get("cfg_scheduler_next_run_at", ""))
            if next_run_dt is None and _setting_bool(latest_settings, "cfg_scheduler_enabled", True):
                interval_minutes = _setting_int(latest_settings, "cfg_scheduler_interval_minutes", 30, minimum=1, maximum=1440)
                next_run_dt = datetime.now(tz=timezone.utc) + timedelta(minutes=int(interval_minutes))
            next_run_label = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "Not scheduled"
            st.session_state["feedback_save_notice"] = (
                f"Queued for retrain: {int(queue_count)} rows | Next scheduler run: {next_run_label}"
            )
            if bool(rerun_after_save):
                st.session_state["force_rerun_analysis"] = True
            st.rerun()

    st.markdown("**Review Workspace**")
    feedback_rows = list_qa_feedback(
        db_path=db_path,
        store_id=sid,
        review_status=None,
        limit=5000,
    )
    feedback_df = pd.DataFrame(feedback_rows)
    if feedback_df.empty:
        st.info("No feedback rows yet. Use Pending Review table above and click Save.")
        return

    feedback_df["review_status"] = feedback_df["review_status"].astype(str).str.lower()
    def _feedback_predicted_display(row: pd.Series) -> str:
        key = _frame_key(row.get("capture_date", ""), row.get("camera_id", ""), row.get("filename", ""))
        track_id = str(row.get("track_id", "") or "").strip()
        source_row = image_lookup.get(key)
        if source_row is not None:
            if track_id:
                track_pred = _resolve_track_prediction_from_source_row(source_row, track_id=track_id)
                if track_pred:
                    return _label_to_display(track_pred)
            return _label_to_display(_predicted_label(source_row))
        return _label_to_display(row.get("predicted_label", ""))

    feedback_df["corrected_label"] = feedback_df["corrected_label"].map(_label_to_display)
    feedback_df["image_name"] = feedback_df["filename"].astype(str)
    feedback_df["drive_link"] = feedback_df["drive_link"].map(_valid_link_or_empty)
    image_lookup = {
        _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")): r
        for _, r in image_df.iterrows()
    }
    feedback_df["predicted_label"] = feedback_df.apply(_feedback_predicted_display, axis=1)
    feedback_df["thumbnail"] = feedback_df.apply(
        lambda r: _preview_uri_cached(
            image_lookup.get(
                _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")),
                pd.Series(dtype=object),
            )
        )
        if _frame_key(r.get("capture_date", ""), r.get("camera_id", ""), r.get("filename", "")) in image_lookup
        else "",
        axis=1,
    )

    pending_df = feedback_df[feedback_df["review_status"] == "pending"].copy()
    history_df = feedback_df[feedback_df["review_status"].isin(["confirmed", "rejected"])].copy()

    settings = _ensure_config_defaults(db_path)
    retrain_key = f"qa_last_retrain_feedback_id__{sid}"
    try:
        last_retrain_feedback_id = int(str(settings.get(retrain_key, "0") or "0"))
    except Exception:
        last_retrain_feedback_id = 0
    confirmed_df = feedback_df[feedback_df["review_status"] == "confirmed"].copy()
    pending_retrain_rows = int(
        len(
            confirmed_df[
                pd.to_numeric(confirmed_df.get("id", 0), errors="coerce").fillna(0).astype(int) > int(last_retrain_feedback_id)
            ]
        )
    )
    retrain_min_rows = _setting_int(settings, "cfg_retrain_min_rows", 10, minimum=1, maximum=100000)
    next_run_dt = _parse_iso_utc(settings.get("cfg_scheduler_next_run_at", ""))
    next_run_label = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "Not scheduled"
    active_model_key = f"qa_active_model_id__{sid}"
    active_model_id = str(settings.get(active_model_key, "baseline_rules_v1") or "baseline_rules_v1")

    center_cols = st.columns(5)
    center_cols[0].metric("Current Model", active_model_id)
    center_cols[1].metric("Last Retrain Marker", int(last_retrain_feedback_id))
    center_cols[2].metric("Pending Retrain Rows", int(pending_retrain_rows))
    center_cols[3].metric("Retrain Eligible", "YES" if pending_retrain_rows >= retrain_min_rows else "NO")
    center_cols[4].metric("Next Scheduler Run", next_run_label)

    retrain_queue_df = confirmed_df[
        pd.to_numeric(confirmed_df.get("id", 0), errors="coerce").fillna(0).astype(int) > int(last_retrain_feedback_id)
    ].copy()
    if not retrain_queue_df.empty:
        st.markdown("**Retrain Queue (Confirmed And Waiting)**")
        st.caption("These confirmed feedback rows will be consumed by next retrain cycle.")
        try:
            st.dataframe(
                retrain_queue_df[
                    [
                        "id",
                        "capture_date",
                        "camera_id",
                        "filename",
                        "track_id",
                        "corrected_label",
                        "confidence",
                        "reviewed_at",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                height=180,
            )
        except Exception:
            st.dataframe(retrain_queue_df, use_container_width=True, hide_index=True, height=180)

    tabs = st.tabs(["Pending Review", "Review History"])
    with tabs[0]:
        st.caption("Rows awaiting reviewer confirmation.")
        if pending_df.empty:
            st.success("No pending rows. New saved feedback is auto-confirmed as per Config.")
        else:
            try:
                st.dataframe(
                    pending_df[
                        [
                            "thumbnail",
                            "image_name",
                            "camera_id",
                            "track_id",
                            "predicted_label",
                            "corrected_label",
                            "confidence",
                            "comment",
                            "drive_link",
                            "created_at",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=280,
                    column_config={
                        "thumbnail": st.column_config.ImageColumn("Thumbnail"),
                        "drive_link": st.column_config.LinkColumn("Drive Link", display_text="Open"),
                    },
                )
            except Exception:
                st.dataframe(pending_df, use_container_width=True, hide_index=True, height=280)

    with tabs[1]:
        st.caption("Confirmed/rejected history. Image-level report first, then detailed row edit.")
        if history_df.empty:
            st.info("No review history yet.")
        else:
            history_rollup = history_df.copy()
            history_rollup["track_id"] = history_rollup["track_id"].astype(str).str.strip()
            history_rollup["track_slot"] = history_rollup["track_id"].apply(
                lambda t: f"T{t}" if t else "FRAME"
            )
            history_rollup["predicted_item"] = history_rollup.apply(
                lambda r: f"{str(r.get('track_slot', 'FRAME'))}:{str(r.get('predicted_label', '') or '').strip()}",
                axis=1,
            )
            history_rollup["corrected_item"] = history_rollup.apply(
                lambda r: f"{str(r.get('track_slot', 'FRAME'))}:{str(r.get('corrected_label', '') or '').strip()}",
                axis=1,
            )
            grouped_history = (
                history_rollup.groupby(
                    ["capture_date", "camera_id", "image_name", "review_status"],
                    as_index=False,
                )
                .agg(
                    thumbnail=("thumbnail", "first"),
                    predicted_feedback=("predicted_item", lambda s: " | ".join([str(x) for x in s if str(x).strip()])),
                    corrected_feedback=("corrected_item", lambda s: " | ".join([str(x) for x in s if str(x).strip()])),
                    confidence=("confidence", "max"),
                    comments=("comment", lambda s: " | ".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
                    drive_link=("drive_link", "first"),
                    reviewed_at=("reviewed_at", "max"),
                )
                .sort_values(by=["reviewed_at", "capture_date", "camera_id", "image_name"], ascending=[False, False, True, True])
            )
            st.markdown("**Image-Level Feedback Report**")
            try:
                st.dataframe(
                    grouped_history[
                        [
                            "thumbnail",
                            "capture_date",
                            "camera_id",
                            "image_name",
                            "review_status",
                            "predicted_feedback",
                            "corrected_feedback",
                            "confidence",
                            "comments",
                            "drive_link",
                            "reviewed_at",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=280,
                    column_config={
                        "thumbnail": st.column_config.ImageColumn("Thumbnail"),
                        "drive_link": st.column_config.LinkColumn("Drive Link", display_text="Open"),
                    },
                )
            except Exception:
                st.dataframe(grouped_history, use_container_width=True, hide_index=True, height=280)

            st.markdown("**Detailed Feedback Rows**")
            try:
                st.dataframe(
                    history_df[
                        [
                            "thumbnail",
                            "image_name",
                            "camera_id",
                            "track_id",
                            "review_status",
                            "predicted_label",
                            "corrected_label",
                            "confidence",
                            "comment",
                            "drive_link",
                            "reviewed_at",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    height=300,
                    column_config={
                        "thumbnail": st.column_config.ImageColumn("Thumbnail"),
                        "drive_link": st.column_config.LinkColumn("Drive Link", display_text="Open"),
                    },
                )
            except Exception:
                st.dataframe(history_df, use_container_width=True, hide_index=True, height=300)

            st.caption(
                "History is read-only for now. To correct an old row, set `Hide Reviewed Rows In Pending` = OFF "
                "in Access > Config > Feedback, relabel it in Pending Review, and save."
            )

    return



def _render_customer_journeys(output: AnalysisOutput, root_dir: Path) -> None:
    st.subheader("Customer Journey Verification")
    if not output.stores:
        st.info("No store analysis loaded.")
        return
    select_placeholder = "-- Select Store --"
    store_ids = sorted(output.stores.keys())
    preselected_store = _query_value("store", "").strip()
    store_options = [select_placeholder, *store_ids]
    default_value = preselected_store if preselected_store in store_ids else select_placeholder
    default_index = store_options.index(default_value)
    sid = st.selectbox("Store", options=store_options, index=default_index, key="journey_store_v2")
    if sid == select_placeholder:
        st.info("Select a store to load customer journey verification.")
        return
    auth_token = str(st.session_state.get("session_token", "") or "").strip()
    image_df = _normalize_image_df(output.stores[sid].image_insights)
    summary_df, events = _build_customer_journey_summary(image_df=image_df)
    if summary_df.empty:
        st.info("No unique customer IDs available yet. Run analysis and ensure relevant frames exist.")
        return

    st.caption("Unique IDs are derived from tracked detections across camera frames.")
    limit_options = [20, 50, 80, 100, 200]
    requested_limit_raw = _query_value("customer_limit", "").strip()
    default_limit = 20
    if requested_limit_raw.isdigit():
        parsed_limit = int(requested_limit_raw)
        if parsed_limit in limit_options:
            default_limit = parsed_limit
    limit = st.selectbox(
        "Customer IDs to display",
        options=limit_options,
        index=limit_options.index(default_limit),
    )
    show_df = summary_df.head(int(limit)).copy()
    show_df["first_seen"] = show_df["first_seen"].astype(str)
    show_df["last_seen"] = show_df["last_seen"].astype(str)
    st.dataframe(show_df, use_container_width=True, hide_index=True)

    st.markdown("**Customer Face Validation Grid**")
    st.caption("One sample frame per customer ID. Use this to quickly validate 80+ detected customers.")
    face_cols = st.columns(5)
    shown_ids = show_df["customer_id"].astype(str).tolist()
    for idx, cid in enumerate(shown_ids):
        events_for_customer = events.get(cid, [])
        first_evt = events_for_customer[0] if events_for_customer else {}
        caption = f"{cid}"
        with face_cols[idx % 5]:
            resolved_evt_path = _resolve_event_image_path(first_evt, store_id=sid, root_dir=root_dir)
            frame_link = _event_verification_link(first_evt, store_id=sid, auth_token=auth_token)
            if resolved_evt_path is not None:
                st.image(str(resolved_evt_path), caption=caption, use_container_width=True)
                if frame_link:
                    st.markdown(f"[Open verification]({frame_link})")
            else:
                if frame_link:
                    st.markdown(f"[{caption}]({frame_link})")
                else:
                    st.caption(caption)

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
    events_df["frame_link"] = events_df.apply(
        lambda r: _event_verification_link(
            evt={
                "filename": r.get("filename", ""),
                "timestamp": r.get("timestamp", ""),
                "drive_link": r.get("drive_link", ""),
                "path": r.get("path", ""),
            },
            store_id=sid,
            auth_token=auth_token,
        ),
        axis=1,
    )
    events_df["drive_link"] = events_df["drive_link"].map(_valid_link_or_empty)
    try:
        st.dataframe(
            events_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "frame_link": st.column_config.LinkColumn("Image Link", display_text="Open"),
                "drive_link": st.column_config.LinkColumn("Drive Image", display_text="Open"),
            },
        )
    except Exception:
        st.dataframe(events_df, use_container_width=True, hide_index=True)

    st.markdown("**Visual Verification**")
    gallery_cols = st.columns(4)
    hover_items: list[str] = []
    for idx, evt in enumerate(customer_events[:20]):
        caption = f"{evt.get('timestamp')} | {evt.get('camera_id')} | {evt.get('filename')}"
        with gallery_cols[idx % 4]:
            resolved_evt_path = _resolve_event_image_path(evt, store_id=sid, root_dir=root_dir)
            frame_link = _valid_link_or_empty(_event_verification_link(evt, store_id=sid, auth_token=auth_token))
            preview_uri = _hover_preview_data_uri(resolved_evt_path) if resolved_evt_path is not None else ""
            if resolved_evt_path is not None:
                st.image(str(resolved_evt_path), caption=caption, use_container_width=True)
                if frame_link:
                    st.markdown(f"[Open verification]({frame_link})")
            else:
                if frame_link:
                    st.markdown(f"[{evt.get('filename', 'Open frame')}]({frame_link})")
                else:
                    st.caption(caption)
            if frame_link:
                safe_name = html.escape(str(evt.get("filename", "Open frame")))
                safe_link = html.escape(frame_link, quote=True)
                if preview_uri:
                    hover_items.append(
                        (
                            '<div class="iris-hover-item">'
                            f'<a href="{safe_link}" target="_self">{safe_name}</a>'
                            f'<div class="iris-hover-card"><img src="{preview_uri}" alt="{safe_name}" /></div>'
                            "</div>"
                        )
                    )
                else:
                    hover_items.append(
                        f'<div class="iris-hover-item"><a href="{safe_link}" target="_self">{safe_name}</a></div>'
                    )
    if hover_items:
        st.markdown("**Hover Preview Links**")
        st.markdown(
            '<div class="iris-hover-list">' + "".join(hover_items) + "</div>",
            unsafe_allow_html=True,
        )


def _render_quality_summary(output: AnalysisOutput) -> None:
    st.subheader("Data Health")
    st.caption("Store-wise data reliability report: invalid files, naming issues, and detection errors.")
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


def _linked_cloud_store_rows(stores: list[object]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for store in stores:
        source_uri = str(getattr(store, "drive_folder_url", "") or "").strip()
        provider = detect_source_provider(source_uri)
        if not source_uri or provider not in {"gdrive", "s3"}:
            continue
        rows.append(
            {
                "store_id": str(getattr(store, "store_id", "")),
                "store_name": str(getattr(store, "store_name", "")),
                "source_provider": provider,
                "source_url": source_uri,
                "updated_at": str(getattr(store, "updated_at", "")),
            }
        )
    return rows


def _discover_store_camera_ids(root_dir: Path, store_id: str, configured_ids: list[str]) -> list[str]:
    discovered = {str(cid).strip().upper() for cid in configured_ids if str(cid).strip()}
    store_dir = root_dir / store_id
    if store_dir.exists() and store_dir.is_dir():
        scanned = 0
        for path in store_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            parsed = parse_filename(path.name)
            if parsed is not None and parsed.camera_id.strip():
                discovered.add(parsed.camera_id.strip().upper())
            scanned += 1
            if scanned >= 50000:
                break
    return sorted(discovered)


def _render_store_mapping(
    db_path: Path,
    data_root: Path,
    auto_sync_after_save: bool,
    default_user_password: str,
    active_email: str,
) -> None:
    st.subheader("Store Mapping")
    st.caption("Select store and update only source link. Store name is auto-filled.")
    stores = list_stores(db_path)
    master_df = pd.DataFrame(list_store_master(db_path=db_path))
    master_ids = (
        sorted(master_df["store_id"].astype(str).tolist())
        if not master_df.empty and "store_id" in master_df.columns
        else []
    )
    store_ids = sorted(set([s.store_id for s in stores] + master_ids))
    if not store_ids:
        st.info("No stores available. Load Store Master first.")
        return

    if "map_store_id" not in st.session_state:
        st.session_state["map_store_id"] = store_ids[0]
    if st.session_state["map_store_id"] not in store_ids:
        st.session_state["map_store_id"] = store_ids[0]
    current_sid = st.selectbox("Store", options=store_ids, key="map_store_id")
    if current_sid != st.session_state.get("map_last_store_id", ""):
        _prefill_store_mapping_fields(db_path=db_path, store_id=current_sid)

    current_name = st.session_state.get("map_store_name", "").strip() or current_sid
    st.markdown(f"**Store Name:** {current_name}")
    st.text_input(
        "Source URL (Google Drive / AWS S3)",
        key="map_drive_url",
        help="Supported: Google Drive folder URL, s3://bucket/prefix, or S3 HTTPS URL.",
    )

    existing_drive = str(st.session_state.get("map_existing_drive_url", "")).strip()
    new_drive = str(st.session_state.get("map_drive_url", "")).strip()
    drive_changed = bool(existing_drive and new_drive and existing_drive != new_drive)
    if existing_drive:
        st.caption(f"Current source URL: {existing_drive}")
    if drive_changed:
        st.checkbox(
            "Replace existing source URL for this store",
            key="map_replace_drive_url",
            help="Required when updating an existing store to a different source URL.",
        )

    save_cols = st.columns([1, 1, 2])
    if save_cols[0].button("Save / Update Store", type="primary"):
        sid = current_sid.strip()
        sname = current_name
        semail = str(st.session_state.get("map_store_email", "")).strip().lower()
        if not semail:
            master = get_store_master_by_id(db_path=db_path, store_id=sid)
            semail = str((master or {}).get("store_email", "")).strip().lower()
        if not semail:
            semail = f"{sid.lower()}@iris.local"
        sdrive = st.session_state["map_drive_url"].strip()
        if not sid or not sname:
            st.error("Store ID and Store Name are required.")
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
        sid = current_sid.strip()
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
        cloud_rows = _linked_cloud_store_rows(stores)
        if cloud_rows:
            st.markdown("**Registered Stores (Cloud Links Only)**")
            st.dataframe(pd.DataFrame(cloud_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No cloud-linked stores found yet.")
    else:
        st.info("No stores registered yet.")


def _render_camera_zones(db_path: Path, root_dir: Path) -> None:
    st.subheader("Store Camera Mapping")
    st.caption("Map camera IDs to floor/location master. Entry direction and line are optional advanced settings.")
    stores = list_stores(db_path)
    if not stores:
        st.info("Create at least one store before camera setup.")
        return
    store_ids = [s.store_id for s in stores]
    selected_store = st.selectbox("Store", options=store_ids, key="camera_view_store")

    st.markdown("**Location Name Master**")
    with st.form("location_master_form", clear_on_submit=False):
        lm_cols = st.columns(2)
        lm_floor = lm_cols[0].text_input("Floor Name", value="Ground")
        lm_location = lm_cols[1].text_input("Location Name")
        save_location = st.form_submit_button("Add Location")
    if save_location:
        if not lm_location.strip():
            st.error("Location Name is required.")
        else:
            upsert_location_master(
                db_path=db_path,
                store_id=selected_store,
                floor_name=lm_floor.strip() or "Ground",
                location_name=lm_location.strip(),
            )
            st.success("Location added.")

    location_rows = list_location_master(db_path=db_path, store_id=selected_store)
    location_df = pd.DataFrame(location_rows)
    if location_df.empty:
        st.caption("No locations defined yet for this store.")
    else:
        st.dataframe(location_df, use_container_width=True, hide_index=True)
        with st.expander("Delete location"):
            delete_floor = st.selectbox(
                "Floor",
                options=sorted(location_df["floor_name"].astype(str).unique().tolist()),
                key=f"delete_floor_{selected_store}",
            )
            delete_candidates = (
                location_df[location_df["floor_name"].astype(str) == str(delete_floor)]["location_name"]
                .astype(str)
                .tolist()
            )
            delete_location = st.selectbox(
                "Location",
                options=delete_candidates,
                key=f"delete_location_{selected_store}",
            )
            if st.button("Delete Selected Location", key=f"delete_location_btn_{selected_store}"):
                deleted = delete_location_master(
                    db_path=db_path,
                    store_id=selected_store,
                    floor_name=str(delete_floor),
                    location_name=str(delete_location),
                )
                if deleted:
                    st.success("Location deleted.")
                else:
                    st.warning("Location not found.")

    cfg_list = list_camera_configs(db_path=db_path, store_id=selected_store)
    cfg_by_camera = {cfg.camera_id: cfg for cfg in cfg_list}
    camera_ids = _discover_store_camera_ids(
        root_dir=root_dir,
        store_id=selected_store,
        configured_ids=[cfg.camera_id for cfg in cfg_list],
    )
    if not camera_ids:
        st.info("No camera IDs detected from filenames yet. Sync store images first.")
        camera_ids = sorted(cfg_by_camera.keys())
    st.markdown("**Camera -> Location Mapping**")
    if camera_ids:
        selected_camera = st.selectbox("Camera ID", options=camera_ids, key=f"camera_map_id_{selected_store}")
    else:
        selected_camera = st.text_input("Camera ID", value="", key=f"camera_map_manual_{selected_store}").strip().upper()

    selected_cfg = cfg_by_camera.get(str(selected_camera).strip().upper())
    location_options = []
    location_lookup: dict[str, tuple[str, str]] = {}
    for row in location_rows:
        floor_name = str(row.get("floor_name", "Ground")).strip() or "Ground"
        location_name = str(row.get("location_name", "")).strip()
        label = f"{floor_name} > {location_name}"
        location_options.append(label)
        location_lookup[label] = (floor_name, location_name)

    default_location_label = ""
    if selected_cfg is not None:
        default_location_label = f"{selected_cfg.floor_name or 'Ground'} > {selected_cfg.location_name or selected_cfg.camera_id}"
        if default_location_label not in location_options:
            location_options.append(default_location_label)
            location_lookup[default_location_label] = (
                selected_cfg.floor_name or "Ground",
                selected_cfg.location_name or selected_cfg.camera_id,
            )
    if not location_options and selected_camera:
        fallback_label = f"Ground > {selected_camera}"
        location_options = [fallback_label]
        location_lookup[fallback_label] = ("Ground", str(selected_camera))

    if location_options:
        selected_location_label = st.selectbox(
            "Location Name Master",
            options=location_options,
            index=(location_options.index(default_location_label) if default_location_label in location_options else 0),
            key=f"camera_map_location_{selected_store}",
        )
    else:
        selected_location_label = ""

    adv_default_role = selected_cfg.camera_role if selected_cfg is not None else "INSIDE"
    adv_default_line = float(selected_cfg.entry_line_x) if selected_cfg is not None else 0.5
    adv_default_dir = selected_cfg.entry_direction if selected_cfg is not None else "OUTSIDE_TO_INSIDE"
    with st.expander("Advanced Traffic Settings (Optional)"):
        st.caption("Use these only for footfall/session crossing logic.")
        adv_role = st.selectbox(
            "Role",
            options=["ENTRANCE", "INSIDE", "BILLING", "BACKROOM", "EXIT", "ZONE"],
            index=(["ENTRANCE", "INSIDE", "BILLING", "BACKROOM", "EXIT", "ZONE"].index(adv_default_role) if adv_default_role in ["ENTRANCE", "INSIDE", "BILLING", "BACKROOM", "EXIT", "ZONE"] else 1),
            key=f"adv_role_{selected_store}",
        )
        adv_line_x = st.slider(
            "Entry Line X",
            min_value=0.0,
            max_value=1.0,
            value=float(adv_default_line),
            step=0.01,
            key=f"adv_line_{selected_store}",
        )
        adv_dir = st.selectbox(
            "Entry Direction",
            options=["OUTSIDE_TO_INSIDE", "INSIDE_TO_OUTSIDE"],
            index=(0 if adv_default_dir == "OUTSIDE_TO_INSIDE" else 1),
            key=f"adv_dir_{selected_store}",
        )

    if st.button("Save Store Camera Mapping", type="primary", key=f"save_camera_map_{selected_store}"):
        camera_id = str(selected_camera).strip().upper()
        if not camera_id:
            st.error("Camera ID is required.")
        else:
            floor_name, location_name = location_lookup.get(selected_location_label, ("Ground", camera_id))
            upsert_camera_config(
                db_path=db_path,
                store_id=selected_store,
                camera_id=camera_id,
                camera_role=adv_role,
                floor_name=floor_name,
                location_name=location_name,
                entry_line_x=float(adv_line_x),
                entry_direction=adv_dir,
            )
            st.success("Store camera mapping saved.")

    cfg_df = pd.DataFrame([c.__dict__ for c in list_camera_configs(db_path=db_path, store_id=selected_store)])
    if cfg_df.empty:
        st.caption("No camera configuration found for this store.")
    else:
        st.markdown("**Current Store Camera Mapping**")
        st.dataframe(
            cfg_df[["camera_id", "floor_name", "location_name"]],
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Show advanced traffic fields"):
            st.dataframe(
                cfg_df[["camera_id", "camera_role", "entry_line_x", "entry_direction"]],
                use_container_width=True,
                hide_index=True,
            )


def _recent_store_snapshot_paths(root_dir: Path, store_id: str, limit: int) -> list[Path]:
    store_dir = root_dir / store_id
    if not store_dir.exists() or not store_dir.is_dir():
        return []
    paths: list[Path] = []
    for path in store_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            paths.append(path)
    paths.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return paths[: max(1, int(limit))]


def _render_employee_management(db_path: Path, employee_assets_root: Path, root_dir: Path) -> None:
    st.subheader("Employee Management")
    stores = list_stores(db_path)
    if not stores:
        st.info("Create at least one store before employee onboarding.")
        return
    store_ids = [s.store_id for s in stores]

    st.caption("AM/CM can label employee faces directly from photo previews.")
    mode = st.radio(
        "Onboarding Mode",
        options=["Upload and Label", "Label From Store Snapshots"],
        horizontal=True,
        key="employee_onboarding_mode",
    )

    if mode == "Upload and Label":
        st.markdown("**Upload Photos and Fill Name (Per Image)**")
        upload_store = st.selectbox("Store", options=store_ids, key="employee_upload_store")
        default_name = st.text_input(
            "Default Name (optional)",
            key="employee_default_name",
            help="If provided, you can apply this name to all uploaded photos with one click.",
        )
        upload_files = st.file_uploader(
            "Employee Image Files",
            type=["jpg", "jpeg", "png", "webp", "bmp"],
            accept_multiple_files=True,
            key="employee_upload_files_multi",
        )
        if upload_files:
            if st.button("Apply Default Name to All", key="employee_apply_default_name"):
                for idx, _file in enumerate(upload_files):
                    st.session_state[f"employee_name_upload_{upload_store}_{idx}"] = default_name.strip()
                st.rerun()
            preview_cols = st.columns(4)
            for idx, file in enumerate(upload_files):
                key = f"employee_name_upload_{upload_store}_{idx}"
                if default_name.strip() and key not in st.session_state:
                    st.session_state[key] = default_name.strip()
                with preview_cols[idx % 4]:
                    st.image(file.getvalue(), use_container_width=True)
                    st.caption(file.name)
                    st.text_input("Employee Name", key=key)
            if st.button("Save Labeled Photos", type="primary", key="employee_save_labeled_upload"):
                missing = [
                    file.name
                    for idx, file in enumerate(upload_files)
                    if not str(st.session_state.get(f"employee_name_upload_{upload_store}_{idx}", "")).strip()
                ]
                if missing:
                    st.error(f"Employee name is required for: {', '.join(missing[:5])}")
                else:
                    uploaded = 0
                    for idx, file in enumerate(upload_files):
                        add_employee_image(
                            db_path=db_path,
                            employee_assets_root=employee_assets_root,
                            store_id=upload_store,
                            employee_name=str(st.session_state.get(f"employee_name_upload_{upload_store}_{idx}", "")).strip(),
                            original_filename=file.name,
                            content=file.getvalue(),
                        )
                        uploaded += 1
                    st.success(f"Saved {uploaded} labeled employee image(s).")
        else:
            st.caption("Upload photos to preview and label.")
    else:
        st.markdown("**Select Store and Label From Captured Snapshots**")
        snapshot_store = st.selectbox("Store", options=store_ids, key="employee_snapshot_store")
        max_snapshots = st.selectbox("Snapshots to review", options=[12, 24, 36, 48, 60], index=1)
        candidates = _recent_store_snapshot_paths(
            root_dir=root_dir,
            store_id=snapshot_store,
            limit=int(max_snapshots),
        )
        if not candidates:
            st.info("No store snapshots found yet. Sync store images first.")
        else:
            preview_cols = st.columns(4)
            for idx, path in enumerate(candidates):
                select_key = f"employee_snapshot_pick_{snapshot_store}_{idx}"
                name_key = f"employee_snapshot_name_{snapshot_store}_{idx}"
                with preview_cols[idx % 4]:
                    st.image(str(path), use_container_width=True)
                    st.caption(path.name)
                    st.checkbox("Use this", key=select_key, value=False)
                    st.text_input("Employee Name", key=name_key)
            if st.button("Save Selected Snapshots", type="primary", key="employee_save_snapshot_labels"):
                selected: list[tuple[Path, str]] = []
                missing_name: list[str] = []
                for idx, path in enumerate(candidates):
                    if bool(st.session_state.get(f"employee_snapshot_pick_{snapshot_store}_{idx}", False)):
                        employee_name = str(st.session_state.get(f"employee_snapshot_name_{snapshot_store}_{idx}", "")).strip()
                        if not employee_name:
                            missing_name.append(path.name)
                        else:
                            selected.append((path, employee_name))
                if not selected and not missing_name:
                    st.warning("Select at least one snapshot.")
                elif missing_name:
                    st.error(f"Employee name is required for selected images: {', '.join(missing_name[:5])}")
                else:
                    saved = 0
                    for path, employee_name in selected:
                        add_employee_image(
                            db_path=db_path,
                            employee_assets_root=employee_assets_root,
                            store_id=snapshot_store,
                            employee_name=employee_name,
                            original_filename=path.name,
                            content=path.read_bytes(),
                        )
                        saved += 1
                    st.success(f"Saved {saved} labeled employee image(s) from store snapshots.")

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
        if "accessible_stores" not in users_df.columns:
            users_df["accessible_stores"] = ""
        else:
            users_df["accessible_stores"] = users_df["accessible_stores"].fillna("").astype(str)
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
5. Bulk CSV access upload is deprecated in lightweight mode. Use Store Access Mapping for controlled updates.
6. `Access > Config`: run analysis and export updates.

### Quick Hints
- `manager_type=store_user` uses `store_id` or first value from `store_ids`.
- `manager_type=cluster_manager/area_manager` should use `store_ids` with `|` separator.
- Mapping save replaces previous store mapping for that user, so maintenance stays simple.
- Keep Admin and User default passwords different for security.
        """
    )


def _pipeline_custom_settings_from_db(db_path: Path) -> dict[str, object]:
    settings = get_app_settings(db_path)
    raw = str(settings.get("pipeline_custom_settings_json", "")).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _save_pipeline_custom_settings(db_path: Path, settings_obj: dict[str, object]) -> None:
    upsert_app_settings(
        db_path=db_path,
        settings={
            "pipeline_custom_settings_json": json.dumps(settings_obj, separators=(",", ":")),
            "pipeline_last_mode": "Custom",
        },
    )


def _apply_pipeline_preset(mode: str, db_path: Path) -> None:
    preset = PIPELINE_PRESETS.get(mode, {})
    if mode == "Custom":
        preset = _pipeline_custom_settings_from_db(db_path)
    if not isinstance(preset, dict):
        return
    for key, value in preset.items():
        st.session_state[key] = value


def _confidence_help_text(conf: float) -> str:
    pct = int(round(conf * 100))
    if conf < 0.20:
        return f"{pct}%: High recall, more false positives."
    if conf <= 0.35:
        return f"{pct}%: Balanced (recommended baseline)."
    if conf <= 0.55:
        return f"{pct}%: High precision, may miss distant people."
    return f"{pct}%: Very strict; use only for clean close-range views."


def _run_scheduler_cycle(
    *,
    db_path: Path,
    root_dir: Path,
    out_dir: Path,
    employee_assets_root: Path,
    conf_threshold: float,
    detector_type: str,
    time_bucket_minutes: int,
    bounce_threshold_sec: int,
    session_gap_sec: int,
    session_timeout_sec: int,
    capture_date_filter: date | None,
    enable_age_gender: bool,
    write_gzip_exports: bool,
    keep_plain_csv: bool,
) -> tuple[AnalysisOutput | None, dict[str, object]]:
    settings = _ensure_config_defaults(db_path)
    summary: dict[str, object] = {
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "sync_runs": 0,
        "sync_ok": 0,
        "sync_warn": 0,
        "pending_feedback_rows": 0,
        "retrain_runs": 0,
        "retrain_ok": 0,
        "predict_rerun": False,
        "message": "",
    }
    stores = list_stores(db_path=db_path)
    scheduler_actor = "scheduler@local"

    if _setting_bool(settings, "cfg_scheduler_task_sync_enabled", True):
        for store in stores:
            ok, _ = sync_store_from_drive(store, data_root=root_dir, db_path=db_path)
            summary["sync_runs"] = int(summary.get("sync_runs", 0)) + 1
            if ok:
                summary["sync_ok"] = int(summary.get("sync_ok", 0)) + 1
            else:
                summary["sync_warn"] = int(summary.get("sync_warn", 0)) + 1

    if _setting_bool(settings, "cfg_scheduler_task_feedback_enabled", True):
        pending_rows = list_qa_feedback(db_path=db_path, store_id=None, review_status="pending", limit=200000)
        summary["pending_feedback_rows"] = int(len(pending_rows))

    if _setting_bool(settings, "cfg_scheduler_task_retrain_enabled", True):
        min_rows = _setting_int(settings, "cfg_retrain_min_rows", 10, minimum=1, maximum=100000)
        for store in stores:
            ok, _, _ = _feedback_retrain_cycle(
                db_path=db_path,
                store_id=store.store_id,
                actor_email=scheduler_actor,
                min_new_rows=int(min_rows),
                force_retrain=False,
            )
            summary["retrain_runs"] = int(summary.get("retrain_runs", 0)) + 1
            if ok:
                summary["retrain_ok"] = int(summary.get("retrain_ok", 0)) + 1

    output: AnalysisOutput | None = None
    if _setting_bool(settings, "cfg_scheduler_task_predict_enabled", True):
        cfg_map_obj = camera_config_map(db_path=db_path)
        cfg_map = {
            sid: {
                cid: {
                    "camera_role": cfg.camera_role,
                    "location_name": cfg.location_name,
                    "floor_name": getattr(cfg, "floor_name", ""),
                    "entry_line_x": cfg.entry_line_x,
                    "entry_direction": cfg.entry_direction,
                }
                for cid, cfg in cams.items()
            }
            for sid, cams in cfg_map_obj.items()
        }
        output = _run_analysis(
            db_path=db_path,
            root_dir=root_dir,
            out_dir=out_dir,
            employee_assets_root=employee_assets_root,
            conf_threshold=float(conf_threshold),
            detector_type=str(detector_type),
            time_bucket_minutes=int(time_bucket_minutes),
            bounce_threshold_sec=int(bounce_threshold_sec),
            session_gap_sec=int(session_gap_sec),
            write_gzip_exports=bool(write_gzip_exports),
            keep_plain_csv=bool(keep_plain_csv),
            camera_configs_by_store=cfg_map,
            max_images_per_store=0,
            store_filter="",
            capture_date_filter=capture_date_filter,
            session_timeout_sec=int(session_timeout_sec),
            enable_age_gender=bool(enable_age_gender),
            export_pilot_store_id="",
            export_pilot_date=capture_date_filter.isoformat() if capture_date_filter else "",
            false_positive_signatures_by_store=_false_positive_signature_map(db_path=db_path),
            use_parallel=False,
            use_streaming=False,
        )
        summary["predict_rerun"] = True
    summary["ended_at"] = datetime.now(tz=timezone.utc).isoformat()
    summary["message"] = (
        f"sync_ok={summary['sync_ok']}/{summary['sync_runs']}, "
        f"pending_feedback={summary['pending_feedback_rows']}, "
        f"retrain_ok={summary['retrain_ok']}/{summary['retrain_runs']}, "
        f"predict_rerun={summary['predict_rerun']}"
    )
    return output, summary


def _render_pipeline_configuration_controls(db_path: Path) -> bool:
    st.subheader("Config")
    st.caption("Single place for run, feedback, retrain, scheduler, and sync settings.")
    settings = _ensure_config_defaults(db_path)
    min_interval = _scheduler_min_interval_minutes(settings)
    current_interval = _setting_int(settings, "cfg_scheduler_interval_minutes", 30, minimum=1, maximum=1440)
    if current_interval < min_interval:
        current_interval = int(min_interval)
        upsert_app_settings(db_path=db_path, settings={"cfg_scheduler_interval_minutes": str(current_interval)})
        settings = _ensure_config_defaults(db_path)

    select_placeholder = "-- Select Config Module --"
    config_modules = ["Feedback", "Retrain", "Scheduler", "Sync", "Run Mode"]
    config_options = [select_placeholder, *config_modules]
    discover_cols = st.columns([2, 2, 3])
    selected_module = discover_cols[0].selectbox(
        "Config Module",
        options=config_options,
        index=0,
        key="cfg_module_select_v2",
    )
    module_search = discover_cols[1].text_input(
        "Search Setting",
        value="",
        key="cfg_module_search",
        placeholder="e.g. scheduler, feedback, confidence",
    ).strip().lower()
    discover_cols[2].caption(
        "Each setting shows meaning, impact, recommended value, and editability. "
        "Scheduler minimum interval is auto-protected."
    )

    show_all_modules = not module_search

    def _show_module(name: str) -> bool:
        if selected_module == select_placeholder:
            return False
        if show_all_modules:
            return selected_module == name
        return module_search in name.lower()

    if selected_module == select_placeholder:
        st.info("Select a config module from dropdown to load settings.")
        return False

    if _show_module("Feedback"):
        with st.expander("Feedback Settings", expanded=True):
            st.caption("Meaning: controls how feedback is captured from Frame Review.")
            f_cols = st.columns([1, 1, 1])
            feedback_auto_confirm = f_cols[0].toggle(
                "Auto-confirm on Save",
                value=_setting_bool(settings, "cfg_feedback_auto_confirm", True),
                help="Recommended: ON. Impact: saved feedback directly becomes retrain-eligible; no extra approve step.",
                key="cfg_feedback_auto_confirm_toggle",
            )
            feedback_fast_edit = f_cols[1].toggle(
                "Fast Edit Mode",
                value=_setting_bool(settings, "cfg_feedback_fast_edit_mode", True),
                help="Recommended: ON. Impact: faster table edits by hiding thumbnails in pending table.",
                key="cfg_feedback_fast_edit_toggle",
            )
            feedback_hide_reviewed = f_cols[2].toggle(
                "Hide Reviewed Rows",
                value=_setting_bool(settings, "cfg_feedback_hide_reviewed", True),
                help="Recommended: ON. Impact: rows already reviewed disappear from Pending tab.",
                key="cfg_feedback_hide_reviewed_toggle",
            )
            f2_cols = st.columns([1, 1, 2])
            feedback_confidence = f2_cols[0].slider(
                "Default Confidence",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                value=float(_setting_float(settings, "cfg_feedback_batch_confidence", 0.9, minimum=0.0, maximum=1.0)),
                key="cfg_feedback_batch_conf_slider",
                help="Recommended: 0.90. Impact: default confidence for batch feedback rows.",
            )
            feedback_rerun = f2_cols[1].toggle(
                "Re-run Analysis After Save",
                value=_setting_bool(settings, "cfg_feedback_rerun_after_save", False),
                help="Recommended: OFF for speed. ON gives immediate full refresh but slower save.",
                key="cfg_feedback_rerun_toggle",
            )
            f2_cols[2].markdown(
                "**Editable**: Yes  \n"
                "**Manual Entry**: Confidence is manual; toggles are operational switches."
            )
            if st.button("Save Feedback Settings", key="cfg_save_feedback"):
                upsert_app_settings(
                    db_path=db_path,
                    settings={
                        "cfg_feedback_auto_confirm": "1" if feedback_auto_confirm else "0",
                        "cfg_feedback_fast_edit_mode": "1" if feedback_fast_edit else "0",
                        "cfg_feedback_hide_reviewed": "1" if feedback_hide_reviewed else "0",
                        "cfg_feedback_batch_confidence": f"{float(feedback_confidence):.2f}",
                        "cfg_feedback_rerun_after_save": "1" if feedback_rerun else "0",
                    },
                )
                st.success("Feedback settings saved.")

    if _show_module("Retrain"):
        with st.expander("Retrain Settings", expanded=(selected_module == "Retrain")):
            st.caption("Meaning: controls retrain eligibility thresholds.")
            r_cols = st.columns([1, 2])
            retrain_min_rows = r_cols[0].number_input(
                "Minimum New Feedback Rows",
                min_value=1,
                max_value=100000,
                step=1,
                value=int(_setting_int(settings, "cfg_retrain_min_rows", 10, minimum=1, maximum=100000)),
                key="cfg_retrain_min_rows_input",
                help="Recommended: 10. Impact: retrain only runs after this many new confirmed rows.",
            )
            pending_confirmed = len(list_qa_feedback(db_path=db_path, store_id=None, review_status="confirmed", limit=200000))
            r_cols[1].markdown(
                f"**Current confirmed feedback rows**: `{pending_confirmed}`  \n"
                f"**Recommended**: `10` for frequent iteration.  \n"
                "**Editable**: Yes"
            )
            if st.button("Save Retrain Settings", key="cfg_save_retrain"):
                upsert_app_settings(db_path=db_path, settings={"cfg_retrain_min_rows": str(int(retrain_min_rows))})
                st.success("Retrain settings saved.")

    if _show_module("Scheduler"):
        with st.expander("Scheduler Settings", expanded=(selected_module == "Scheduler")):
            st.caption("Meaning: always-on queue runner executes sync/feedback/retrain/prediction cycles.")
            s_cols = st.columns([1, 1, 1])
            scheduler_enabled = s_cols[0].toggle(
                "Enable Scheduler",
                value=_setting_bool(settings, "cfg_scheduler_enabled", True),
                key="cfg_scheduler_enabled_toggle",
                help="Recommended: ON. Impact: automatic queue execution every interval.",
            )
            scheduler_interval = s_cols[1].number_input(
                "Interval (minutes)",
                min_value=int(min_interval),
                max_value=1440,
                step=1,
                value=int(max(current_interval, min_interval)),
                key="cfg_scheduler_interval_input",
                help="Minimum is auto-calculated from enabled task times + buffer.",
            )
            scheduler_buffer = s_cols[2].number_input(
                "Buffer (minutes)",
                min_value=0,
                max_value=120,
                step=1,
                value=int(_setting_int(settings, "cfg_scheduler_buffer_minutes", 5, minimum=0, maximum=120)),
                key="cfg_scheduler_buffer_input",
                help="Recommended: 5. Impact: safety gap to prevent overlapping runs.",
            )
            t_cols = st.columns(5)
            task_settings = [
                ("sync", "Sync", "cfg_scheduler_task_sync_enabled", "cfg_scheduler_est_sync_minutes"),
                ("feedback", "Feedback Queue", "cfg_scheduler_task_feedback_enabled", "cfg_scheduler_est_feedback_minutes"),
                ("retrain", "Retrain", "cfg_scheduler_task_retrain_enabled", "cfg_scheduler_est_retrain_minutes"),
                ("predict", "Predictions", "cfg_scheduler_task_predict_enabled", "cfg_scheduler_est_predict_minutes"),
                ("refresh", "Refresh Output", "cfg_scheduler_task_refresh_enabled", "cfg_scheduler_est_refresh_minutes"),
            ]
            scheduler_payload: dict[str, str] = {}
            for idx, (_slug, title, enabled_key, est_key) in enumerate(task_settings):
                enabled_value = t_cols[idx].toggle(
                    title,
                    value=_setting_bool(settings, enabled_key, True),
                    key=f"{enabled_key}_toggle",
                )
                est_value = t_cols[idx].number_input(
                    f"{title} est (min)",
                    min_value=1,
                    max_value=180,
                    step=1,
                    value=int(_setting_int(settings, est_key, 2, minimum=1, maximum=180)),
                    key=f"{est_key}_input",
                )
                scheduler_payload[enabled_key] = "1" if enabled_value else "0"
                scheduler_payload[est_key] = str(int(est_value))
            tmp_settings = dict(settings)
            tmp_settings.update(scheduler_payload)
            tmp_settings["cfg_scheduler_buffer_minutes"] = str(int(scheduler_buffer))
            recalculated_min = _scheduler_min_interval_minutes(tmp_settings)
            next_run_dt = _parse_iso_utc(settings.get("cfg_scheduler_next_run_at", ""))
            next_run_label = next_run_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S") if next_run_dt else "Not scheduled yet"
            st.caption(
                f"Minimum Allowed Interval: `{recalculated_min} min` | "
                f"Current Interval: `{max(int(scheduler_interval), recalculated_min)} min` | "
                f"Next Run: `{next_run_label}`"
            )
            if st.button("Save Scheduler Settings", key="cfg_save_scheduler"):
                scheduler_payload.update(
                    {
                        "cfg_scheduler_enabled": "1" if scheduler_enabled else "0",
                        "cfg_scheduler_buffer_minutes": str(int(scheduler_buffer)),
                        "cfg_scheduler_interval_minutes": str(int(max(int(scheduler_interval), recalculated_min))),
                    }
                )
                upsert_app_settings(db_path=db_path, settings=scheduler_payload)
                st.success("Scheduler settings saved.")

    if _show_module("Sync"):
        with st.expander("Sync Settings", expanded=(selected_module == "Sync")):
            st.caption("Meaning: source refresh behavior before/after analysis or mapping save.")
            s_cols = st.columns([1, 1, 2])
            auto_sync_linked = s_cols[0].toggle(
                "Auto-Sync Sources",
                value=bool(st.session_state.get("ctrl_auto_sync_linked_drives", True)),
                key="cfg_sync_auto_linked",
                help="Recommended: ON. Impact: pulls latest source files before analysis.",
            )
            auto_sync_on_save = s_cols[1].toggle(
                "Auto-Sync On Save",
                value=bool(st.session_state.get("ctrl_auto_sync_on_save", False)),
                key="cfg_sync_auto_on_save",
                help="Recommended: OFF during bulk edits. ON for immediate sync on mapping save.",
            )
            s_cols[2].markdown("**Editable**: Yes  \n**Manual Entry**: toggle switches only.")
            st.session_state["ctrl_auto_sync_linked_drives"] = bool(auto_sync_linked)
            st.session_state["ctrl_auto_sync_on_save"] = bool(auto_sync_on_save)

    if not _show_module("Run Mode"):
        return False

    bounce_options = [30, 60, 90, 120, 180, 240, 300]
    session_options = [10, 20, 30, 45, 60, 90, 120]
    timeout_options = [60, 120, 180, 240, 300, 600]
    if st.session_state.get("ctrl_bounce_threshold_sec") not in bounce_options:
        st.session_state["ctrl_bounce_threshold_sec"] = 120
    if st.session_state.get("ctrl_session_gap_sec") not in session_options:
        st.session_state["ctrl_session_gap_sec"] = 30
    if st.session_state.get("ctrl_session_timeout_sec") not in timeout_options:
        st.session_state["ctrl_session_timeout_sec"] = 180
    st.session_state["ctrl_max_images_per_store"] = 0
    if "pipeline_mode" not in st.session_state:
        last_mode = str(get_app_settings(db_path).get("pipeline_last_mode", PIPELINE_PRESET_DEFAULT)).strip()
        st.session_state["pipeline_mode"] = last_mode if last_mode in PIPELINE_PRESETS else PIPELINE_PRESET_DEFAULT

    mode_cols = st.columns([2, 1, 1])
    selected_mode = mode_cols[0].selectbox(
        "Run Mode",
        options=list(PIPELINE_PRESETS.keys()),
        key="pipeline_mode",
        help="Full Scan (Dev): full folder scan with age/gender on. Test: smaller quick run. Custom: your saved profile.",
    )
    last_applied_mode = str(st.session_state.get("pipeline_mode_applied", "")).strip()
    if selected_mode != last_applied_mode:
        _apply_pipeline_preset(selected_mode, db_path=db_path)
        upsert_app_settings(db_path=db_path, settings={"pipeline_last_mode": selected_mode})
        st.session_state["pipeline_mode_applied"] = selected_mode
        st.rerun()
    if mode_cols[1].button("Apply Mode", key="pipeline_apply_mode"):
        _apply_pipeline_preset(selected_mode, db_path=db_path)
        upsert_app_settings(db_path=db_path, settings={"pipeline_last_mode": selected_mode})
        st.session_state["pipeline_mode_applied"] = selected_mode
        st.success(f"Applied mode: {selected_mode}")
        st.rerun()
    if mode_cols[2].button("Save Current as Custom", key="pipeline_save_custom"):
        custom_payload = {
            "ctrl_enable_age_gender": bool(st.session_state.get("ctrl_enable_age_gender", False)),
            "ctrl_auto_sync_linked_drives": bool(st.session_state.get("ctrl_auto_sync_linked_drives", True)),
            "ctrl_auto_sync_on_save": bool(st.session_state.get("ctrl_auto_sync_on_save", False)),
            "ctrl_detector_type": str(st.session_state.get("ctrl_detector_type", "yolo")),
            "ctrl_conf_threshold": float(st.session_state.get("ctrl_conf_threshold", 0.25)),
            "ctrl_bounce_threshold_sec": int(st.session_state.get("ctrl_bounce_threshold_sec", 120)),
            "ctrl_session_gap_sec": int(st.session_state.get("ctrl_session_gap_sec", 30)),
            "ctrl_session_timeout_sec": int(st.session_state.get("ctrl_session_timeout_sec", 180)),
            "ctrl_time_bucket_minutes": int(st.session_state.get("ctrl_time_bucket_minutes", 1)),
        }
        _save_pipeline_custom_settings(db_path=db_path, settings_obj=custom_payload)
        st.session_state["pipeline_mode"] = "Custom"
        st.session_state["pipeline_mode_applied"] = "Custom"
        st.success("Saved current values as Custom mode.")

    store_rows = list_stores(db_path=db_path)
    store_ids = sorted({str(row.store_id).strip() for row in store_rows if str(row.store_id).strip()})
    if "ctrl_store_filter_select" not in st.session_state:
        st.session_state["ctrl_store_filter_select"] = "(All Stores)"
    if st.session_state["ctrl_store_filter_select"] not in ["(All Stores)", *store_ids]:
        st.session_state["ctrl_store_filter_select"] = "(All Stores)"

    with st.form("analysis_controls_form", clear_on_submit=False):
        ctrl_cols_1 = st.columns(3)
        ctrl_cols_1[0].text_input(
            "Root Directory",
            key="ctrl_root_str",
            help="Folder containing store folders and date subfolders. In Docker this is usually /app/data/stores.",
        )
        ctrl_cols_1[1].text_input(
            "Export Directory",
            key="ctrl_out_str",
            help="Location where analysis CSV exports are written.",
        )
        current_root = str(st.session_state.get("ctrl_root_str", ""))
        current_out = str(st.session_state.get("ctrl_out_str", ""))
        storage_hint = "Cloud/Container volume" if current_root.startswith("/app/") else "Local path"
        ctrl_cols_1[2].markdown(
            f"**Storage Mode**  \n`{storage_hint}`  \nRoot: `{current_root}`  \nExport: `{current_out}`"
        )

        ctrl_cols_2 = st.columns(3)
        ctrl_cols_2[0].slider(
            "Detection Confidence",
            min_value=0.05,
            max_value=0.9,
            step=0.01,
            key="ctrl_conf_threshold",
            help="Lower catches more people but can increase false detections. 0.25 is the current recommended baseline.",
        )
        ctrl_cols_2[0].caption(_confidence_help_text(float(st.session_state.get("ctrl_conf_threshold", 0.25))))
        ctrl_cols_2[1].markdown("**Scan Mode**  \n`Live (Full Folder)`")
        st.session_state["ctrl_max_images_per_store"] = 0
        ctrl_cols_2[2].selectbox(
            "Bounce Threshold (Seconds)",
            options=bounce_options,
            key="ctrl_bounce_threshold_sec",
            help="Visits below this dwell threshold are treated as bounce.",
        )

        ctrl_cols_2b = st.columns(3)
        ctrl_cols_2b[0].selectbox(
            "Session Gap (Seconds)",
            options=session_options,
            key="ctrl_session_gap_sec",
            help="Gap threshold to split sessions.",
        )
        ctrl_cols_2b[1].selectbox(
            "Session Timeout (Seconds)",
            options=timeout_options,
            key="ctrl_session_timeout_sec",
            help="Fallback closure timeout for store-day customer IDs.",
        )
        ctrl_cols_2b[2].selectbox(
            "Time Bucket (Minutes)",
            options=[1, 5, 15],
            key="ctrl_time_bucket_minutes",
            help="Chart bucket size only (reporting view).",
        )

        ctrl_cols_3 = st.columns(4)
        yolo_available = _is_yolo_available()
        deepface_available = _is_deepface_available()
        allow_mock_detector = os.getenv("IRIS_ALLOW_MOCK_DETECTOR", "0").strip() == "1"
        detector_options = ["yolo"]
        detector_options.append("opencv_hog")
        if allow_mock_detector:
            detector_options.append("mock")
        if st.session_state.get("ctrl_detector_type") == "mock" and not allow_mock_detector:
            st.session_state["ctrl_detector_type"] = "yolo"
        if st.session_state.get("ctrl_detector_type") == "yolo" and not yolo_available:
            st.session_state["ctrl_detector_type"] = "opencv_hog"
        if st.session_state["ctrl_detector_type"] not in detector_options:
            st.session_state["ctrl_detector_type"] = detector_options[0]
        ctrl_cols_3[0].selectbox(
            "Detector",
            options=detector_options,
            key="ctrl_detector_type",
            help="YOLO (recommended) or OpenCV HOG fallback. MOCK is hidden unless IRIS_ALLOW_MOCK_DETECTOR=1.",
        )
        ctrl_cols_3[1].toggle(
            "Auto-Sync Sources",
            key="ctrl_auto_sync_linked_drives",
            help="Sync mapped source URLs before each analysis run.",
        )
        ctrl_cols_3[2].toggle(
            "Auto-Sync On Save",
            key="ctrl_auto_sync_on_save",
            help="Sync selected store immediately after store mapping save.",
        )
        ctrl_cols_3[3].toggle(
            "Enable Age/Gender",
            key="ctrl_enable_age_gender",
            help="Use DeepFace for age/gender likelihood on customer crops.",
        )
        if bool(st.session_state.get("ctrl_enable_age_gender", False)) and not deepface_available:
            st.session_state["ctrl_enable_age_gender"] = False

        ctrl_cols_4 = st.columns(3)
        ctrl_cols_4[0].selectbox(
            "Store Filter",
            options=["(All Stores)", *store_ids],
            key="ctrl_store_filter_select",
            help="Choose one store or all stores.",
        )
        ctrl_cols_4[1].text_input(
            "Capture Date (YYYY-MM-DD)",
            key="ctrl_capture_date",
            help="Optional day filter. Accepts YYYY-MM-DD or YYYYMMDD.",
        )
        ctrl_cols_4[2].toggle(
            "Use Calendar Date",
            key="ctrl_use_capture_date_picker",
            help="Turn on to apply the date selected in calendar.",
        )
        date_cols = st.columns([1, 3, 1])
        date_cols[0].markdown("")
        date_cols[1].date_input(
            "Capture Date Picker",
            value=date.today(),
            key="ctrl_capture_date_picker",
            help="Optional calendar selection. If selected, this value is used.",
        )
        date_cols[2].markdown("")
        rerun_clicked = st.form_submit_button("Regenerate Analysis + CSV", type="primary")
        st.caption("Keep this tab open while analysis runs. Navigating during run can interrupt current execution.")
        selected_detector = str(st.session_state.get("ctrl_detector_type", "yolo"))
        if selected_detector == "yolo" and not yolo_available:
            st.caption(
                "YOLO is not installed in this runtime. Either enable full build (`IRIS_ENABLE_YOLO=1`) or switch to `opencv_hog`."
            )
            if not allow_mock_detector:
                st.caption("MOCK detector is disabled in production mode (`IRIS_ALLOW_MOCK_DETECTOR=0`).")
        if not deepface_available:
            st.caption("DeepFace runtime not available. Age/Gender is auto-disabled until dependency is installed.")
    # Keep gzip behavior frozen for operational simplicity.
    st.session_state["ctrl_write_gzip_exports"] = True
    st.session_state["ctrl_keep_plain_csv"] = True
    selected_store = str(st.session_state.get("ctrl_store_filter_select", "(All Stores)")).strip()
    st.session_state["ctrl_store_filter"] = "" if selected_store == "(All Stores)" else selected_store
    picked_date = st.session_state.get("ctrl_capture_date_picker")
    if bool(st.session_state.get("ctrl_use_capture_date_picker", False)) and isinstance(picked_date, date):
        st.session_state["ctrl_capture_date"] = picked_date.isoformat()

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
        st.session_state["ctrl_conf_threshold"] = 0.18
    if "ctrl_time_bucket_minutes" not in st.session_state:
        st.session_state["ctrl_time_bucket_minutes"] = 1
    if "ctrl_bounce_threshold_sec" not in st.session_state:
        st.session_state["ctrl_bounce_threshold_sec"] = 120
    if "ctrl_session_gap_sec" not in st.session_state:
        st.session_state["ctrl_session_gap_sec"] = 30
    if "ctrl_session_timeout_sec" not in st.session_state:
        st.session_state["ctrl_session_timeout_sec"] = 180
    if "ctrl_max_images_per_store" not in st.session_state:
        st.session_state["ctrl_max_images_per_store"] = 0
    if "ctrl_detector_type" not in st.session_state:
        st.session_state["ctrl_detector_type"] = "yolo"
    if "ctrl_store_filter" not in st.session_state:
        st.session_state["ctrl_store_filter"] = ""
    if "ctrl_capture_date" not in st.session_state:
        st.session_state["ctrl_capture_date"] = ""
    if "ctrl_enable_age_gender" not in st.session_state:
        st.session_state["ctrl_enable_age_gender"] = False
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
    if current_page == "Config":
        rerun_clicked = _render_pipeline_configuration_controls(db_path=db_path)
    if bool(st.session_state.pop("force_rerun_analysis", False)):
        rerun_clicked = True

    root_dir = Path(st.session_state["ctrl_root_str"]).expanduser().resolve()
    out_dir = Path(st.session_state["ctrl_out_str"]).expanduser().resolve()
    conf_threshold = float(st.session_state["ctrl_conf_threshold"])
    time_bucket_minutes = int(st.session_state["ctrl_time_bucket_minutes"])
    bounce_threshold_sec = int(st.session_state["ctrl_bounce_threshold_sec"])
    session_gap_sec = int(st.session_state["ctrl_session_gap_sec"])
    session_timeout_sec = int(st.session_state["ctrl_session_timeout_sec"])
    st.session_state["ctrl_max_images_per_store"] = 0
    max_images_per_store = 0
    detector_type = str(st.session_state["ctrl_detector_type"])
    store_filter = str(st.session_state.get("ctrl_store_filter", "")).strip()
    capture_date_str = str(st.session_state.get("ctrl_capture_date", "")).strip()
    capture_date_filter: date | None = None
    if capture_date_str:
        try:
            normalized_capture_date = capture_date_str
            if len(capture_date_str) == 8 and capture_date_str.isdigit():
                normalized_capture_date = (
                    f"{capture_date_str[0:4]}-{capture_date_str[4:6]}-{capture_date_str[6:8]}"
                )
            capture_date_filter = date.fromisoformat(normalized_capture_date)
        except ValueError:
            st.error(f"Invalid capture date '{capture_date_str}'. Use YYYY-MM-DD.")
            capture_date_filter = None
    enable_age_gender = bool(st.session_state.get("ctrl_enable_age_gender", False))
    write_gzip_exports = bool(st.session_state["ctrl_write_gzip_exports"])
    keep_plain_csv = bool(st.session_state["ctrl_keep_plain_csv"])
    auto_sync_linked_drives = bool(st.session_state["ctrl_auto_sync_linked_drives"])
    auto_sync_on_save = bool(st.session_state["ctrl_auto_sync_on_save"])

    scheduler_settings = _ensure_config_defaults(db_path)
    scheduler_min_interval = _scheduler_min_interval_minutes(scheduler_settings)
    scheduler_interval = _setting_int(
        scheduler_settings,
        "cfg_scheduler_interval_minutes",
        30,
        minimum=scheduler_min_interval,
        maximum=1440,
    )
    if scheduler_interval != _setting_int(scheduler_settings, "cfg_scheduler_interval_minutes", 30, minimum=1, maximum=1440):
        upsert_app_settings(db_path=db_path, settings={"cfg_scheduler_interval_minutes": str(int(scheduler_interval))})
        scheduler_settings = _ensure_config_defaults(db_path)

    next_run_dt = _parse_iso_utc(scheduler_settings.get("cfg_scheduler_next_run_at", ""))
    st.session_state["scheduler_next_run_at"] = next_run_dt.isoformat() if next_run_dt else ""
    st.session_state["scheduler_interval_minutes"] = int(scheduler_interval)
    st.session_state["scheduler_min_interval_minutes"] = int(scheduler_min_interval)

    st.caption("Live mode: full-folder scan is always enabled.")

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
                        "location_name": cfg.location_name,
                        "floor_name": getattr(cfg, "floor_name", ""),
                        "entry_line_x": cfg.entry_line_x,
                        "entry_direction": cfg.entry_direction,
                    }
                    for cid, cfg in cams.items()
                }
                for sid, cams in cfg_map_obj.items()
            }
            output = _run_analysis(
                db_path=db_path,
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
                store_filter=store_filter,
                capture_date_filter=capture_date_filter,
                session_timeout_sec=int(session_timeout_sec),
                enable_age_gender=enable_age_gender,
                export_pilot_store_id=store_filter,
                export_pilot_date=capture_date_filter.isoformat() if capture_date_filter else "",
                false_positive_signatures_by_store=_false_positive_signature_map(db_path=db_path),
            )
            st.session_state["analysis_output"] = output
            st.session_state["analysis_export_mtime"] = _export_summary_mtime(out_dir)
            if st.session_state.get("login_email"):
                log_user_activity(db_path=db_path, actor_email=st.session_state.get("login_email",""), action_code="ANALYSIS_RUN")
            st.success("Analysis completed and CSV exports updated.")

    output: AnalysisOutput | None = st.session_state.get("analysis_output")
    if output is None:
        output = _load_or_run_default(root_dir=root_dir, out_dir=out_dir)
        st.session_state["analysis_output"] = output
        st.session_state["analysis_export_mtime"] = _export_summary_mtime(out_dir)
    else:
        current_mtime = _export_summary_mtime(out_dir)
        cached_mtime = float(st.session_state.get("analysis_export_mtime", 0.0) or 0.0)
        if current_mtime > cached_mtime:
            output = _load_or_run_default(root_dir=root_dir, out_dir=out_dir)
            st.session_state["analysis_output"] = output
            st.session_state["analysis_export_mtime"] = current_mtime
            st.info("Loaded latest exports from disk.")
    if output is not None and _summary_total_images(output) == 0:
        source_count = _count_source_images(root_dir=root_dir, store_filter=store_filter)
        if source_count > 0:
            st.warning(
                "Exports are empty/stale while source images exist. "
                f"Found ~{source_count} source images in `{root_dir}`."
            )
            st.caption(
                "Auto-recovery is manual to keep UI responsive. "
                "Use the button below to regenerate exports when needed."
            )
            if st.button("Regenerate Analysis From Source", key="manual_empty_export_recover", type="primary"):
                with st.spinner("Regenerating analysis from source images..."):
                    cfg_map_obj = camera_config_map(db_path=db_path)
                    cfg_map = {
                        sid: {
                            cid: {
                                "camera_role": cfg.camera_role,
                                "location_name": cfg.location_name,
                                "floor_name": getattr(cfg, "floor_name", ""),
                                "entry_line_x": cfg.entry_line_x,
                                "entry_direction": cfg.entry_direction,
                            }
                            for cid, cfg in cams.items()
                        }
                        for sid, cams in cfg_map_obj.items()
                    }
                    output = _run_analysis(
                        db_path=db_path,
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
                        store_filter=store_filter,
                        capture_date_filter=capture_date_filter,
                        session_timeout_sec=int(session_timeout_sec),
                        enable_age_gender=enable_age_gender,
                        export_pilot_store_id=store_filter,
                        export_pilot_date=capture_date_filter.isoformat() if capture_date_filter else "",
                        false_positive_signatures_by_store=_false_positive_signature_map(db_path=db_path),
                    )
                    st.session_state["analysis_output"] = output
                    st.session_state["analysis_export_mtime"] = _export_summary_mtime(out_dir)
                    st.success("Auto-recovery completed. Dashboard data refreshed.")
        else:
            st.info(
                "No source images found for the current root path. "
                f"Current root: `{root_dir}`. Sync source first, then regenerate analysis."
            )

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

    if current_page == "Config":
        st.caption("Use the configuration form above to run analysis.")
    elif current_page == "Overview":
        _render_overview(view_output)
    elif current_page == "Model Accuracy":
        _render_model_accuracy_overview(view_output, db_path=db_path, out_dir=out_dir)
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
        st.info("Bulk Access Upload is deprecated for the lightweight pipeline mode.")
    elif current_page == "Setup Help":
        _render_setup_help()
    elif current_page == "Store Detail":
        _render_store_detail(view_output, time_bucket_minutes=time_bucket_minutes, root_dir=root_dir)
    elif current_page in {"Report Module", "Data Health"}:
        _render_report_module(view_output, root_dir=root_dir, db_path=db_path)
    elif current_page == "Customer Journeys":
        _render_customer_journeys(view_output, root_dir=root_dir)
    elif current_page == "Store Mapping":
        _render_store_mapping(
            db_path=db_path,
            data_root=root_dir,
            auto_sync_after_save=auto_sync_on_save,
            default_user_password=default_user_password,
            active_email=active_email,
        )
    elif current_page == "Store Camera Mapping":
        _render_camera_zones(db_path=db_path, root_dir=root_dir)
    elif current_page == "Employee Management":
        _render_employee_management(
            db_path=db_path,
            employee_assets_root=employee_assets_root,
            root_dir=root_dir,
        )
    elif current_page in {"Pipeline Journey", "Manual data sync of IRIS", "Maual data sync of IRIS"}:
        _render_onfly_pipeline_journey(db_path=db_path)

    elif current_page == "Frame Review":
        _render_qa_timeline(output=view_output, db_path=db_path, active_email=active_email, root_dir=root_dir)

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
    else:
        st.warning(
            f"Page '{current_page}' is not mapped in this build. Showing Overview instead."
        )
        _render_overview(view_output)

if __name__ == "__main__":
    main()

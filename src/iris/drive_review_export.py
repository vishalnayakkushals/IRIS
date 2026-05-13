from __future__ import annotations

import os
import re
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from iris.runtime_bootstrap import load_env_file
from iris.store_registry import parse_drive_folder_id
from iris.source_clients import SourceImage

REVIEW_FOLDER_NAME = "_IRIS_RELEVANT_BY_CAMERA"
_PLACEHOLDER_MARKERS = {
    "",
    "replace_with_private_key_from_it_admin",
    "replace_with_service_account_email",
    "replace_with_private_key_id",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def unique_review_filename(item: SourceImage) -> str:
    token = str(item.source_item_id or item.image_id or item.image_name or "item").strip()
    token = _SAFE_NAME.sub("_", token).strip("._-") or "item"
    image_name = str(item.image_name or "image.jpg").strip() or "image.jpg"
    return f"{token}__{image_name}"


def drive_review_export_status() -> tuple[bool, str]:
    load_env_file()
    private_key = str(os.getenv("GOOGLE_PRIVATE_KEY", "")).strip()
    client_email = str(os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")).strip()
    private_key_id = str(os.getenv("GOOGLE_SERVICE_ACCOUNT_ID", "")).strip()
    if private_key in _PLACEHOLDER_MARKERS or "BEGIN PRIVATE KEY" not in private_key:
        return False, "GOOGLE_PRIVATE_KEY is not configured with a real service-account private key"
    if client_email in _PLACEHOLDER_MARKERS or "@" not in client_email:
        return False, "GOOGLE_SERVICE_ACCOUNT_EMAIL is not configured with a real service-account email"
    if private_key_id in _PLACEHOLDER_MARKERS:
        return False, "GOOGLE_SERVICE_ACCOUNT_ID is not configured with a real private-key id"
    return True, ""


class DriveRelevantShortcutExporter:
    def __init__(self, source_uri: str) -> None:
        ok, reason = drive_review_export_status()
        if not ok:
            raise RuntimeError(reason)
        folder_id = parse_drive_folder_id(source_uri)
        if not folder_id:
            raise RuntimeError("Drive review export requires a Google Drive source folder URL")

        private_key = str(os.getenv("GOOGLE_PRIVATE_KEY", "")).replace("\\n", "\n")
        creds_info = {
            "type": "service_account",
            "client_email": str(os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")).strip(),
            "private_key_id": str(os.getenv("GOOGLE_SERVICE_ACCOUNT_ID", "")).strip(),
            "private_key": private_key,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._root_folder_id = folder_id
        self._date_folder_ids: dict[str, str] = {}
        self._review_root_ids: dict[str, str] = {}
        self._camera_folder_ids: dict[tuple[str, str], str] = {}
        self._shortcut_name_cache: dict[str, set[str]] = {}

    def export_shortcut(self, item: SourceImage) -> dict[str, Any]:
        if str(item.source_provider or "").strip().lower() != "gdrive":
            return {"status": "skipped", "reason": "not_gdrive"}
        target_id = str(item.source_item_id or "").strip()
        date_source = str(item.date_source or "").strip()
        if not target_id or not date_source:
            return {"status": "skipped", "reason": "missing_target_or_date"}

        date_folder_id = self._get_date_folder_id(date_source)
        if not date_folder_id:
            return {"status": "skipped", "reason": "date_folder_not_found"}

        camera_id = str(item.camera_id or "").strip() or "UNKNOWN_CAMERA"
        camera_folder_id = self._get_camera_folder_id(date_source, camera_id, date_folder_id)
        shortcut_name = unique_review_filename(item)
        existing_names = self._shortcut_name_cache.setdefault(camera_folder_id, set())
        if shortcut_name in existing_names:
            return {"status": "skipped", "reason": "already_exported", "name": shortcut_name}

        shortcut = self._service.files().create(
            body={
                "name": shortcut_name,
                "mimeType": "application/vnd.google-apps.shortcut",
                "shortcutDetails": {"targetId": target_id},
                "parents": [camera_folder_id],
            },
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
        existing_names.add(shortcut_name)
        return {
            "status": "created",
            "shortcut_id": str(shortcut.get("id", "")).strip(),
            "shortcut_name": str(shortcut.get("name", "")).strip(),
            "camera_id": camera_id,
            "date_source": date_source,
        }

    def _get_date_folder_id(self, date_source: str) -> str:
        if date_source in self._date_folder_ids:
            return self._date_folder_ids[date_source]
        folder_id = self._find_child_folder(self._root_folder_id, date_source, create=False)
        self._date_folder_ids[date_source] = folder_id
        return folder_id

    def _get_camera_folder_id(self, date_source: str, camera_id: str, date_folder_id: str) -> str:
        cache_key = (date_source, camera_id)
        if cache_key in self._camera_folder_ids:
            return self._camera_folder_ids[cache_key]
        review_root_id = self._review_root_ids.get(date_source)
        if not review_root_id:
            review_root_id = self._find_child_folder(date_folder_id, REVIEW_FOLDER_NAME, create=True)
            self._review_root_ids[date_source] = review_root_id
        camera_folder_id = self._find_child_folder(review_root_id, camera_id, create=True)
        self._camera_folder_ids[cache_key] = camera_folder_id
        return camera_folder_id

    def _find_child_folder(self, parent_id: str, name: str, *, create: bool) -> str:
        escaped_name = str(name).replace("\\", "\\\\").replace("'", "\\'")
        response = self._service.files().list(
            q=(
                f"'{parent_id}' in parents and trashed = false and "
                "mimeType = 'application/vnd.google-apps.folder' and "
                f"name = '{escaped_name}'"
            ),
            fields="files(id,name)",
            pageSize=10,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()
        files = response.get("files", []) or []
        if files:
            return str(files[0].get("id", "")).strip()
        if not create:
            return ""
        created = self._service.files().create(
            body={
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            },
            fields="id,name",
            supportsAllDrives=True,
        ).execute()
        return str(created.get("id", "")).strip()

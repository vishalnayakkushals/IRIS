from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from iris.runtime_bootstrap import load_env_file
from iris.store_registry import parse_drive_folder_id
from iris.source_clients import SourceImage

REVIEW_FOLDER_NAME = "Relevant image"
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


def original_review_filename(item: SourceImage) -> str:
    return str(item.image_name or "image.jpg").strip() or "image.jpg"


def _service_account_file() -> Path | None:
    raw = str(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def _service_account_file_status(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"GOOGLE_SERVICE_ACCOUNT_FILE does not exist: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"GOOGLE_SERVICE_ACCOUNT_FILE is not valid JSON: {exc}"
    if data.get("type") != "service_account":
        return False, "GOOGLE_SERVICE_ACCOUNT_FILE is not a service_account JSON"
    if "@" not in str(data.get("client_email", "")):
        return False, "GOOGLE_SERVICE_ACCOUNT_FILE is missing client_email"
    if "BEGIN PRIVATE KEY" not in str(data.get("private_key", "")):
        return False, "GOOGLE_SERVICE_ACCOUNT_FILE is missing a real private_key"
    return True, ""


def drive_review_export_status() -> tuple[bool, str]:
    load_env_file()
    account_file = _service_account_file()
    if account_file is not None:
        return _service_account_file_status(account_file)

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


def _build_drive_credentials() -> service_account.Credentials:
    account_file = _service_account_file()
    scopes = ["https://www.googleapis.com/auth/drive"]
    if account_file is not None:
        return service_account.Credentials.from_service_account_file(str(account_file), scopes=scopes)

    private_key = str(os.getenv("GOOGLE_PRIVATE_KEY", "")).replace("\\n", "\n")
    creds_info = {
        "type": "service_account",
        "client_email": str(os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")).strip(),
        "private_key_id": str(os.getenv("GOOGLE_SERVICE_ACCOUNT_ID", "")).strip(),
        "private_key": private_key,
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)


class DriveRelevantImageExporter:
    def __init__(self, source_uri: str) -> None:
        ok, reason = drive_review_export_status()
        if not ok:
            raise RuntimeError(reason)
        folder_id = parse_drive_folder_id(source_uri)
        if not folder_id:
            raise RuntimeError("Drive review export requires a Google Drive source folder URL")

        creds = _build_drive_credentials()
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._source_root_id = folder_id
        root = self._service.files().get(
            fileId=folder_id,
            fields="id,name,parents",
            supportsAllDrives=True,
        ).execute()
        self._source_root_name = str(root.get("name", "")).strip()
        parents = root.get("parents", []) or []
        self._source_root_parent_id = str(parents[0]).strip() if parents else ""
        self._destination_parent_id = folder_id
        self._date_folder_ids: dict[str, str] = {}
        self._review_root_id = ""
        self._name_cache: dict[str, set[str]] = {}

    def export_image(self, item: SourceImage) -> dict[str, Any]:
        if str(item.source_provider or "").strip().lower() != "gdrive":
            return {"status": "skipped", "reason": "not_gdrive"}
        target_id = str(item.source_item_id or "").strip()
        date_source = self._date_folder_name(item)
        if not target_id or not date_source:
            return {"status": "skipped", "reason": "missing_target_or_date"}

        date_folder_id = self._get_output_date_folder_id(date_source)
        image_name = original_review_filename(item)
        existing_names = self._name_cache.setdefault(date_folder_id, self._list_child_names(date_folder_id))
        if image_name in existing_names:
            return {"status": "skipped", "reason": "already_exported", "name": image_name, "date_source": date_source}

        copied = self._service.files().copy(
            fileId=target_id,
            body={
                "name": image_name,
                "parents": [date_folder_id],
            },
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
        existing_names.add(image_name)
        return {
            "status": "created",
            "file_id": str(copied.get("id", "")).strip(),
            "file_name": str(copied.get("name", "")).strip(),
            "web_view_link": str(copied.get("webViewLink", "")).strip(),
            "date_source": date_source,
        }

    def export_shortcut(self, item: SourceImage) -> dict[str, Any]:
        return self.export_image(item)

    def _date_folder_name(self, item: SourceImage) -> str:
        date_source = str(item.date_source or "").strip()
        if date_source:
            return date_source
        return self._source_root_name

    def _get_output_date_folder_id(self, date_source: str) -> str:
        if date_source in self._date_folder_ids:
            return self._date_folder_ids[date_source]
        review_root_id = self._get_review_root_id(date_source)
        folder_id = self._find_child_folder(review_root_id, date_source, create=True)
        self._date_folder_ids[date_source] = folder_id
        return folder_id

    def _get_review_root_id(self, date_source: str) -> str:
        if self._review_root_id:
            return self._review_root_id
        destination_parent_id = self._destination_parent_id
        if self._source_root_name == date_source and self._source_root_parent_id:
            destination_parent_id = self._source_root_parent_id
        self._review_root_id = self._find_child_folder(destination_parent_id, REVIEW_FOLDER_NAME, create=True)
        return self._review_root_id

    def _list_child_names(self, parent_id: str) -> set[str]:
        names: set[str] = set()
        token = None
        while True:
            response = self._service.files().list(
                q=f"'{parent_id}' in parents and trashed = false",
                fields="nextPageToken,files(name)",
                pageSize=1000,
                pageToken=token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            ).execute()
            names.update(str(item.get("name", "")).strip() for item in response.get("files", []) or [] if item.get("name"))
            token = response.get("nextPageToken")
            if not token:
                break
        return names

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


DriveRelevantShortcutExporter = DriveRelevantImageExporter

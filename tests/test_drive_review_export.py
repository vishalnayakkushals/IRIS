from __future__ import annotations

import json

from iris.drive_review_export import DriveRelevantImageExporter, drive_review_export_status
from iris.source_clients import SourceImage


class _Request:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class _FakeFiles:
    def __init__(self):
        self.children: dict[str, list[dict[str, str]]] = {}
        self.created_folders: list[tuple[str, str]] = []
        self.copied_files: list[tuple[str, str, str]] = []
        self._seq = 0

    def list(self, **kwargs):
        query = str(kwargs.get("q", ""))
        parent = query.split("'")[1]
        name = ""
        if "name = '" in query:
            name = query.split("name = '", 1)[1].split("'", 1)[0]
        rows = self.children.get(parent, [])
        if name:
            rows = [row for row in rows if row.get("name") == name and row.get("mimeType") == "application/vnd.google-apps.folder"]
        return _Request({"files": rows})

    def create(self, body, **kwargs):
        self._seq += 1
        folder_id = f"folder_{self._seq}"
        parent = body["parents"][0]
        name = body["name"]
        row = {"id": folder_id, "name": name, "mimeType": "application/vnd.google-apps.folder"}
        self.children.setdefault(parent, []).append(row)
        self.children.setdefault(folder_id, [])
        self.created_folders.append((parent, name))
        return _Request({"id": folder_id, "name": name})

    def copy(self, fileId, body, **kwargs):
        self._seq += 1
        file_id = f"copy_{self._seq}"
        parent = body["parents"][0]
        name = body["name"]
        self.children.setdefault(parent, []).append({"id": file_id, "name": name, "mimeType": "image/jpeg"})
        self.copied_files.append((fileId, parent, name))
        return _Request({"id": file_id, "name": name, "webViewLink": f"https://drive.test/{file_id}"})


class _FakeService:
    def __init__(self):
        self.files_api = _FakeFiles()

    def files(self):
        return self.files_api


def _exporter(service: _FakeService, *, root_name: str = "RRNAGAR BLR", root_parent: str = "") -> DriveRelevantImageExporter:
    exporter = DriveRelevantImageExporter.__new__(DriveRelevantImageExporter)
    exporter._service = service
    exporter._source_root_id = "source_root"
    exporter._source_root_name = root_name
    exporter._source_root_parent_id = root_parent
    exporter._destination_parent_id = "source_root"
    exporter._date_folder_ids = {}
    exporter._review_root_id = ""
    exporter._name_cache = {}
    return exporter


def _image(name: str = "15-41-36_D01-1.jpg") -> SourceImage:
    return SourceImage(
        image_id="gdrive:source_file",
        image_name=name,
        relative_path=f"2026-05-10/{name}",
        source_provider="gdrive",
        source_item_id="source_file",
        source_url="https://drive.google.com/file/d/source_file/view",
        date_source="2026-05-10",
        date_display="10-05-2026",
        camera_id="D01",
        timestamp_hint="2026-05-10 15:41:36",
    )


def test_relevant_image_export_creates_required_drive_structure_and_preserves_filename():
    service = _FakeService()
    exporter = _exporter(service)

    result = exporter.export_image(_image())

    assert result["status"] == "created"
    assert service.files_api.created_folders == [
        ("source_root", "Relevant image"),
        ("folder_1", "2026-05-10"),
    ]
    assert service.files_api.copied_files == [
        ("source_file", "folder_2", "15-41-36_D01-1.jpg"),
    ]


def test_relevant_image_export_skips_duplicate_filename_in_same_date_folder():
    service = _FakeService()
    exporter = _exporter(service)

    first = exporter.export_image(_image())
    second = exporter.export_image(_image())

    assert first["status"] == "created"
    assert second == {
        "status": "skipped",
        "reason": "already_exported",
        "name": "15-41-36_D01-1.jpg",
        "date_source": "2026-05-10",
    }
    assert len(service.files_api.copied_files) == 1


def test_relevant_image_export_uses_parent_when_source_uri_is_date_folder():
    service = _FakeService()
    exporter = _exporter(service, root_name="2026-05-10", root_parent="store_parent")

    exporter.export_image(_image())

    assert service.files_api.created_folders[0] == ("store_parent", "Relevant image")


def test_relevant_image_export_skips_non_drive_sources():
    service = _FakeService()
    exporter = _exporter(service)
    item = _image()
    item = SourceImage(
        image_id=item.image_id,
        image_name=item.image_name,
        relative_path=item.relative_path,
        source_provider="local",
        source_item_id=item.source_item_id,
        source_url=item.source_url,
        date_source=item.date_source,
        date_display=item.date_display,
        camera_id=item.camera_id,
        timestamp_hint=item.timestamp_hint,
    )

    result = exporter.export_image(item)

    assert result == {"status": "skipped", "reason": "not_gdrive"}
    assert service.files_api.copied_files == []


def test_drive_review_export_status_accepts_service_account_file(tmp_path, monkeypatch):
    key_path = tmp_path / "service-account.json"
    key_path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "client_email": "iris@test-project.iam.gserviceaccount.com",
                "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(key_path))
    monkeypatch.setenv("GOOGLE_PRIVATE_KEY", "replace_with_private_key_from_it_admin")

    assert drive_review_export_status() == (True, "")

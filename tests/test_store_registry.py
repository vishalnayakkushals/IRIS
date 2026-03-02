from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from iris.store_registry import (
    _sync_store_from_drive_api,
    camera_config_map,
    list_camera_configs,
    upsert_camera_config,
    add_employee_image,
    get_store_by_email,
    list_employees,
    list_stores,
    parse_drive_folder_id,
    upsert_store,
)


def test_store_email_mapping_and_lookup(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(
        db_path=db,
        store_id="store_1",
        store_name="Store One",
        email="store1@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/abc123",
    )
    upsert_store(
        db_path=db,
        store_id="store_2",
        store_name="Store Two",
        email="store2@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/xyz987",
    )

    stores = list_stores(db)
    assert [s.store_id for s in stores] == ["store_1", "store_2"]
    mapped = get_store_by_email(db, "store2@example.com")
    assert mapped is not None
    assert mapped.store_id == "store_2"


def test_store_email_is_case_insensitive_and_unique(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(
        db_path=db,
        store_id="store_1",
        store_name="Store One",
        email="Store1@Example.com",
        drive_folder_url="",
    )

    mapped = get_store_by_email(db, "store1@example.com")
    assert mapped is not None
    assert mapped.store_id == "store_1"
    assert mapped.email == "store1@example.com"

    try:
        upsert_store(
            db_path=db,
            store_id="store_2",
            store_name="Store Two",
            email="STORE1@example.com",
            drive_folder_url="",
        )
        assert False, "Expected duplicate email validation to fail"
    except ValueError:
        pass


def test_employee_image_upload_persists_record(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    assets = tmp_path / "employees"
    upsert_store(
        db_path=db,
        store_id="store_1",
        store_name="Store One",
        email="store1@example.com",
        drive_folder_url="",
    )

    image_path = add_employee_image(
        db_path=db,
        employee_assets_root=assets,
        store_id="store_1",
        employee_name="Alex",
        original_filename="alex.jpg",
        content=b"\xff\xd8\xff\xe0",
    )
    assert image_path.exists()

    employees = list_employees(db_path=db, store_id="store_1")
    assert len(employees) == 1
    assert employees[0]["employee_name"] == "Alex"


def test_employee_upload_requires_registered_store(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    assets = tmp_path / "employees"
    try:
        add_employee_image(
            db_path=db,
            employee_assets_root=assets,
            store_id="unknown_store",
            employee_name="Alex",
            original_filename="alex.jpg",
            content=b"\xff\xd8\xff\xe0",
        )
        assert False, "Expected upload to fail for unregistered store"
    except ValueError:
        pass


def test_parse_drive_folder_id() -> None:
    url = "https://drive.google.com/drive/folders/19tnfe64JVzdYUXuXJI1JVqOyRKQMBj3L"
    assert parse_drive_folder_id(url) == "19tnfe64JVzdYUXuXJI1JVqOyRKQMBj3L"
    assert parse_drive_folder_id("https://example.com") is None


def test_employee_upload_is_optimized_to_jpeg(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    assets = tmp_path / "employees"
    upsert_store(
        db_path=db,
        store_id="store_1",
        store_name="Store One",
        email="store1@example.com",
        drive_folder_url="",
    )

    # Create a PNG in-memory, expect optimized JPEG output on disk.
    buf = BytesIO()
    Image.new("RGB", (2000, 1200), color=(10, 120, 200)).save(buf, format="PNG")
    image_path = add_employee_image(
        db_path=db,
        employee_assets_root=assets,
        store_id="store_1",
        employee_name="Alex",
        original_filename="alex.png",
        content=buf.getvalue(),
    )
    assert image_path.suffix.lower() == ".jpg"
    assert image_path.exists()


def test_drive_api_sync_path_with_mocked_requests(tmp_path: Path, monkeypatch) -> None:
    from iris.store_registry import StoreRecord

    target = tmp_path / "stores" / "s1"
    target.mkdir(parents=True)
    store = StoreRecord("s1", "Store 1", "s1@example.com", "https://drive.google.com/drive/folders/f123", "", "")

    calls = {"list": 0, "download": 0}

    class Resp:
        def __init__(self, status_code=200, payload=None, content=b""):
            self.status_code = status_code
            self._payload = payload or {}
            self.content = content

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("http error")

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=0):
        if url.endswith('/drive/v3/files'):
            calls["list"] += 1
            return Resp(payload={"files": [{"id": "file1", "name": "09-57-27_D02-1.jpg", "mimeType": "image/jpeg"}]})
        calls["download"] += 1
        # minimal jpeg bytes
        return Resp(content=b"\xff\xd8\xff\xe0" + b"0" * 10)

    monkeypatch.setattr("iris.store_registry.requests.get", fake_get)
    ok, msg = _sync_store_from_drive_api(store=store, target_dir=target, api_key="k")
    assert ok is True
    assert "api_sync" in msg
    assert calls["list"] >= 1
    assert calls["download"] >= 1


def test_camera_config_persistence(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(
        db_path=db,
        store_id="store_1",
        store_name="Store One",
        email="store1@example.com",
        drive_folder_url="",
    )
    upsert_camera_config(
        db_path=db,
        store_id="store_1",
        camera_id="D01",
        camera_role="ENTRANCE",
        entry_line_x=0.42,
        entry_direction="OUTSIDE_TO_INSIDE",
    )
    cfgs = list_camera_configs(db_path=db, store_id="store_1")
    assert len(cfgs) == 1
    assert cfgs[0].camera_id == "D01"
    assert cfgs[0].camera_role == "ENTRANCE"
    mapped = camera_config_map(db_path=db)
    assert mapped["store_1"]["D01"].entry_line_x == 0.42

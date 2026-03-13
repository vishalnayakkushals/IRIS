from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from iris.store_registry import (
    _drive_api_list_files_recursive,
    _sync_store_from_drive_api,
    detect_source_provider,
    ensure_store_login,
    camera_config_map,
    list_synced_stores,
    list_user_store_access,
    replace_user_store_access,
    create_role,
    create_user,
    delete_role,
    get_app_settings,
    list_camera_configs,
    upsert_camera_config,
    add_employee_image,
    get_store_by_email,
    list_employees,
    list_roles,
    set_role_permissions,
    list_stores,
    parse_drive_folder_id,
    sync_store_from_drive,
    list_model_versions,
    maybe_auto_rollback_model,
    promote_model_version,
    register_model_version,
    upsert_manager_access,
    upsert_app_settings,
    upsert_user_account,
    upsert_store,
    user_store_scope,
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


def test_drive_api_list_non_json_response_is_explained(monkeypatch) -> None:
    class Resp:
        status_code = 200
        text = "<html>quota exceeded</html>"

        def raise_for_status(self):
            return None

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr("iris.store_registry.requests.get", lambda *args, **kwargs: Resp())
    try:
        _drive_api_list_files_recursive(folder_id="f123", api_key="k")
        assert False, "Expected non-JSON response handling to fail"
    except RuntimeError as exc:
        assert "non-JSON response" in str(exc)


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
        floor_name="Ground",
        location_name="Zone1",
        entry_line_x=0.42,
        entry_direction="OUTSIDE_TO_INSIDE",
    )
    cfgs = list_camera_configs(db_path=db, store_id="store_1")
    assert len(cfgs) == 1
    assert cfgs[0].camera_id == "D01"
    assert cfgs[0].camera_role == "ENTRANCE"
    assert cfgs[0].floor_name == "Ground"
    assert cfgs[0].location_name == "Zone1"
    mapped = camera_config_map(db_path=db)
    assert mapped["store_1"]["D01"].entry_line_x == 0.42


def test_auth_and_license_workflow(tmp_path: Path) -> None:
    from iris.store_registry import (
        authenticate_user,
        create_license,
        create_user,
        list_license_audit,
        transition_license,
        upsert_store,
    )

    db = tmp_path / "registry.db"
    upsert_store(db_path=db, store_id="s1", store_name="S1", email="s1@example.com", drive_folder_url="")
    create_user(db_path=db, email="admin@example.com", full_name="Admin", password="Secret123!", role_names=["admin"])
    assert authenticate_user(db_path=db, email="admin@example.com", password="Secret123!") is not None

    lid = create_license(db_path=db, store_id="s1", license_type="trade_display", actor_email="admin@example.com")
    transition_license(db_path=db, license_id=lid, new_status="review", actor_email="admin@example.com")
    transition_license(db_path=db, license_id=lid, new_status="approved", actor_email="admin@example.com")
    audit = list_license_audit(db_path=db, license_id=lid)
    assert len(audit) >= 3


def test_model_registry_and_auto_rollback(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    bad_id = register_model_version(
        db_path=db,
        model_name="iris_customer_model",
        version_tag="v_bad",
        metrics_json='{"error_rate": 0.55}',
        artifact_path="data/models/bad.json",
        status="candidate",
    )
    good_id = register_model_version(
        db_path=db,
        model_name="iris_customer_model",
        version_tag="v_good",
        metrics_json='{"error_rate": 0.05}',
        artifact_path="data/models/good.json",
        status="candidate",
    )
    promote_model_version(db_path=db, model_name="iris_customer_model", model_id=bad_id)

    # configure rollback target on bad model
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE model_versions SET rollback_target_model_id=? WHERE model_id=?",
        (good_id, bad_id),
    )
    conn.commit()
    conn.close()

    rolled, msg = maybe_auto_rollback_model(db_path=db, model_name="iris_customer_model", max_error_rate=0.35)
    assert rolled is True
    assert "rolled back" in msg

    versions = list_model_versions(db_path=db, model_name="iris_customer_model")
    statuses = {v["model_id"]: v["status"] for v in versions}
    assert statuses[good_id] == "active"


def test_delete_role_blocks_admin(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    ok, message = delete_role(db_path=db, role_name="admin")
    assert ok is False
    assert "protected" in message


def test_delete_role_blocks_assigned_role(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    create_role(db_path=db, role_name="auditor", description="Audit role")
    create_user(
        db_path=db,
        email="auditor.user@example.com",
        full_name="Auditor User",
        password="Secret123!",
        role_names=["auditor"],
    )
    ok, message = delete_role(db_path=db, role_name="auditor")
    assert ok is False
    assert "assigned" in message


def test_delete_role_removes_unassigned_role(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    create_role(db_path=db, role_name="auditor", description="Audit role")
    set_role_permissions(
        db_path=db,
        role_name="auditor",
        permissions=[("dashboard", 1, 0), ("stores", 1, 1)],
    )
    ok, message = delete_role(db_path=db, role_name="auditor")
    assert ok is True
    assert "deleted" in message
    role_names = [x["role_name"] for x in list_roles(db)]
    assert "auditor" not in role_names


def test_app_settings_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_app_settings(
        db_path=db,
        settings={
            "app_name": "IRIS HQ",
            "font_family": "Segoe UI",
            "background_color": "#f4f6f8",
        },
    )
    settings = get_app_settings(db_path=db)
    assert settings["app_name"] == "IRIS HQ"
    assert settings["font_family"] == "Segoe UI"
    assert settings["background_color"] == "#f4f6f8"


def test_store_login_auto_create_and_scope(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(db_path=db, store_id="S001", store_name="Store 001", email="s001@example.com", drive_folder_url="")
    result = ensure_store_login(
        db_path=db,
        store_id="S001",
        store_email="s001@example.com",
        store_name="Store 001",
        default_password="Temp@123",
    )
    assert result["created"] is True
    access_rows = list_user_store_access(db_path=db, email="s001@example.com")
    assert len(access_rows) == 1
    assert access_rows[0]["store_id"] == "S001"
    scope = user_store_scope(db_path=db, email="s001@example.com")
    assert scope["restricted"] is True
    assert scope["store_ids"] == ["S001"]


def test_manager_mapping_supports_multiple_stores(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(db_path=db, store_id="S001", store_name="Store 001", email="s001@example.com", drive_folder_url="")
    upsert_store(db_path=db, store_id="S002", store_name="Store 002", email="s002@example.com", drive_folder_url="")
    result = upsert_manager_access(
        db_path=db,
        manager_type="cluster_manager",
        email="cm@example.com",
        full_name="CM User",
        store_ids=["S001", "S002"],
        default_password="Temp@123",
        force_password_reset=False,
    )
    assert result["stores_mapped"] == 2
    scope = user_store_scope(db_path=db, email="cm@example.com")
    assert scope["restricted"] is True
    assert set(scope["store_ids"]) == {"S001", "S002"}


def test_replace_user_store_access_overwrites_previous_mapping(tmp_path: Path) -> None:
    db = tmp_path / "registry.db"
    upsert_store(db_path=db, store_id="S001", store_name="Store 001", email="s001@example.com", drive_folder_url="")
    upsert_store(db_path=db, store_id="S002", store_name="Store 002", email="s002@example.com", drive_folder_url="")
    upsert_user_account(
        db_path=db,
        email="manager@example.com",
        full_name="Manager",
        role_names=["area_manager"],
        password="Temp@123",
    )
    replace_user_store_access(db_path=db, email="manager@example.com", store_ids=["S001"])
    replace_user_store_access(db_path=db, email="manager@example.com", store_ids=["S002"])
    rows = list_user_store_access(db_path=db, email="manager@example.com")
    assert len(rows) == 1
    assert rows[0]["store_id"] == "S002"


def test_detect_source_provider_supports_gdrive_s3_local(tmp_path: Path) -> None:
    local_dir = tmp_path / "images"
    local_dir.mkdir(parents=True)
    assert detect_source_provider("https://drive.google.com/drive/folders/abc123") == "gdrive"
    assert detect_source_provider("s3://my-bucket/store-a") == "s3"
    assert detect_source_provider(str(local_dir)) == "local"


def test_list_synced_stores_can_filter_by_provider(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "registry.db"
    data_root = tmp_path / "stores"
    local_source = tmp_path / "local_src"
    local_source.mkdir(parents=True)
    Image.new("RGB", (16, 16), color=(120, 90, 60)).save(local_source / "09-00-00_D01-1.jpg")

    upsert_store(
        db_path=db,
        store_id="LOCAL1",
        store_name="Local Store",
        email="local@example.com",
        drive_folder_url=str(local_source),
    )
    local_store = [s for s in list_stores(db) if s.store_id == "LOCAL1"][0]
    ok_local, _ = sync_store_from_drive(local_store, data_root=data_root, db_path=db)
    assert ok_local is True

    upsert_store(
        db_path=db,
        store_id="GDRIVE1",
        store_name="Drive Store",
        email="drive@example.com",
        drive_folder_url="https://drive.google.com/drive/folders/f123",
    )
    drive_store = [s for s in list_stores(db) if s.store_id == "GDRIVE1"][0]

    class _FakeGdown:
        @staticmethod
        def download_folder(url: str, output: str, quiet: bool, remaining_ok: bool) -> None:
            out = Path(output)
            out.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (16, 16), color=(100, 80, 70)).save(out / "09-00-00_D01-1.jpg")

    import sys

    monkeypatch.setitem(sys.modules, "gdown", _FakeGdown)
    ok_drive, _ = sync_store_from_drive(drive_store, data_root=data_root, db_path=db)
    assert ok_drive is True

    only_gdrive = list_synced_stores(db_path=db, provider_filter="gdrive")
    only_local = list_synced_stores(db_path=db, provider_filter="local")
    assert [r["store_id"] for r in only_gdrive] == ["GDRIVE1"]
    assert [r["store_id"] for r in only_local] == ["LOCAL1"]

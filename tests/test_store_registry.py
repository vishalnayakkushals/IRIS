from __future__ import annotations

from pathlib import Path

from store_registry import (
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

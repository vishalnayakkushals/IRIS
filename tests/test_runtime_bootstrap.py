from __future__ import annotations

from pathlib import Path

from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths


def test_load_env_file_sets_missing_keys_only(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "GOOGLE_API_KEY=test-google",
                "OPENAI_API_KEY='test-openai'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "keep-existing")

    loaded = load_env_file(env_file)

    assert loaded == env_file.resolve()
    assert Path(loaded).exists()
    assert resolve_runtime_paths()["db_path"].name == "store_registry.db"
    assert str(__import__("os").environ["GOOGLE_API_KEY"]) == "test-google"
    assert str(__import__("os").environ["OPENAI_API_KEY"]) == "keep-existing"


def test_resolve_runtime_paths_honors_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("IRIS_APP_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("IRIS_DATA_DIR", str(tmp_path / "shared-data"))
    monkeypatch.setenv("IRIS_DB_PATH", str(tmp_path / "db" / "iris.db"))
    monkeypatch.setenv("IRIS_STORES_ROOT", str(tmp_path / "stores-root"))
    monkeypatch.setenv("IRIS_EXPORT_DIR", str(tmp_path / "exports-root"))
    monkeypatch.setenv("IRIS_EMPLOYEE_ASSETS_DIR", str(tmp_path / "assets-root"))

    paths = resolve_runtime_paths()

    assert paths["app_dir"] == (tmp_path / "app").resolve()
    assert paths["data_dir"] == (tmp_path / "shared-data").resolve()
    assert paths["db_path"] == (tmp_path / "db" / "iris.db").resolve()
    assert paths["stores_root"] == (tmp_path / "stores-root").resolve()
    assert paths["exports_dir"] == (tmp_path / "exports-root").resolve()
    assert paths["employee_assets_dir"] == (tmp_path / "assets-root").resolve()

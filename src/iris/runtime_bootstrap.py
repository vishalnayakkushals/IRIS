from __future__ import annotations

import os
from pathlib import Path


def _strip_quotes(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {'"', "'"}:
        return raw[1:-1]
    return raw


def load_env_file(env_file: str | Path | None = None) -> Path | None:
    candidate = Path(env_file).expanduser().resolve() if env_file else None
    if candidate is None:
        repo_root = Path(__file__).resolve().parents[2]
        for default in [
            Path(os.getenv("IRIS_ENV_FILE", "")).expanduser() if os.getenv("IRIS_ENV_FILE", "").strip() else None,
            repo_root / ".env.local",
            repo_root / "deploy" / "no_docker" / ".env.local",
        ]:
            if default is not None and default.exists():
                candidate = default.resolve()
                break
    if candidate is None or not candidate.exists():
        return None

    for line in candidate.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env_key = str(key).strip()
        if not env_key or env_key in os.environ:
            continue
        os.environ[env_key] = _strip_quotes(value)
    return candidate


def resolve_runtime_paths() -> dict[str, Path]:
    app_dir = Path(os.getenv("IRIS_APP_DIR", "")).expanduser().resolve() if os.getenv("IRIS_APP_DIR", "").strip() else Path(__file__).resolve().parents[2]
    data_dir = Path(os.getenv("IRIS_DATA_DIR", "")).expanduser().resolve() if os.getenv("IRIS_DATA_DIR", "").strip() else (app_dir / "data").resolve()
    stores_root = Path(os.getenv("IRIS_STORES_ROOT", "")).expanduser().resolve() if os.getenv("IRIS_STORES_ROOT", "").strip() else (data_dir / "stores").resolve()
    exports_dir = Path(os.getenv("IRIS_EXPORT_DIR", "")).expanduser().resolve() if os.getenv("IRIS_EXPORT_DIR", "").strip() else (data_dir / "exports" / "current").resolve()
    db_path = Path(os.getenv("IRIS_DB_PATH", "")).expanduser().resolve() if os.getenv("IRIS_DB_PATH", "").strip() else (data_dir / "store_registry.db").resolve()
    employee_assets_dir = (
        Path(os.getenv("IRIS_EMPLOYEE_ASSETS_DIR", "")).expanduser().resolve()
        if os.getenv("IRIS_EMPLOYEE_ASSETS_DIR", "").strip()
        else (data_dir / "employee_assets").resolve()
    )
    return {
        "app_dir": app_dir,
        "data_dir": data_dir,
        "stores_root": stores_root,
        "exports_dir": exports_dir,
        "db_path": db_path,
        "employee_assets_dir": employee_assets_dir,
    }

from __future__ import annotations

from pathlib import Path


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _secret_paths(data_dir: Path | None = None) -> tuple[Path, Path]:
    root = (data_dir or _default_data_dir()) / "secrets"
    return root / "master.key", root / "google_api_key.enc"


def _ensure_mode_600(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        # Windows filesystems may not support POSIX chmod semantics.
        pass


def save_google_api_key(api_key: str, data_dir: Path | None = None) -> Path:
    from cryptography.fernet import Fernet  # type: ignore

    value = str(api_key or "").strip()
    if not value:
        raise ValueError("Empty API key cannot be saved.")
    key_path, secret_path = _secret_paths(data_dir=data_dir)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        fernet_key = key_path.read_bytes()
    else:
        fernet_key = Fernet.generate_key()
        key_path.write_bytes(fernet_key)
    _ensure_mode_600(key_path)

    token = Fernet(fernet_key).encrypt(value.encode("utf-8"))
    secret_path.write_bytes(token)
    _ensure_mode_600(secret_path)
    return secret_path


def load_google_api_key(data_dir: Path | None = None) -> str:
    from cryptography.fernet import Fernet  # type: ignore

    key_path, secret_path = _secret_paths(data_dir=data_dir)
    if not key_path.exists() or not secret_path.exists():
        return ""
    try:
        fernet_key = key_path.read_bytes()
        token = secret_path.read_bytes()
        return Fernet(fernet_key).decrypt(token).decode("utf-8").strip()
    except Exception:
        return ""


def delete_google_api_key(data_dir: Path | None = None) -> bool:
    _, secret_path = _secret_paths(data_dir=data_dir)
    if not secret_path.exists():
        return False
    secret_path.unlink(missing_ok=True)
    return True

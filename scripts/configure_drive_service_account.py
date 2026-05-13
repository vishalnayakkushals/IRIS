from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SECRET_DIR = REPO_ROOT / ".local-secrets"
DEFAULT_TARGET = LOCAL_SECRET_DIR / "google_service_account.json"
ENV_PATH = REPO_ROOT / ".env.local"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure IRIS Google Drive write access from a service-account JSON key")
    parser.add_argument("--json", required=True, type=Path, help="Path to downloaded Google service-account JSON key")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Local private destination for the key")
    return parser.parse_args()


def _validate_service_account_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "service_account":
        raise RuntimeError("JSON key is not a service_account key")
    if "@" not in str(data.get("client_email", "")):
        raise RuntimeError("JSON key is missing client_email")
    if "BEGIN PRIVATE KEY" not in str(data.get("private_key", "")):
        raise RuntimeError("JSON key is missing a real private_key")
    return data


def _set_env_value(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f"{key}="
    updated = False
    out: list[str] = []
    for line in lines:
        if line.startswith(prefix):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")
    return out


def main() -> None:
    args = parse_args()
    source = args.json.expanduser().resolve()
    if not source.exists():
        raise RuntimeError(f"Service-account JSON not found: {source}")
    data = _validate_service_account_json(source)

    target = args.target.expanduser()
    if not target.is_absolute():
        target = (REPO_ROOT / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target:
        shutil.copy2(source, target)

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    rel_or_abs = str(target)
    lines = _set_env_value(lines, "GOOGLE_SERVICE_ACCOUNT_FILE", rel_or_abs)
    lines = _set_env_value(lines, "GOOGLE_SERVICE_ACCOUNT_EMAIL", str(data.get("client_email", "")).strip())
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    print("Drive service-account JSON configured.")
    print(f"GOOGLE_SERVICE_ACCOUNT_FILE={target}")
    print(f"GOOGLE_SERVICE_ACCOUNT_EMAIL={data.get('client_email', '')}")
    print("Share the source Drive parent folder with this email as Editor before running exports.")


if __name__ == "__main__":
    main()

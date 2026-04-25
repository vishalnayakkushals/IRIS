from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'local_runtime_manager.py'
spec = importlib.util.spec_from_file_location('local_runtime_manager', SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_compose_local_env_contains_required_runtime_fields(tmp_path: Path) -> None:
    text = module._compose_local_env(tmp_path, 'openai-test', 'google-test')

    assert 'IRIS_APP_DIR=' in text
    assert 'IRIS_DATA_DIR=' in text
    assert 'GOOGLE_API_KEY=google-test' in text
    assert 'OPENAI_API_KEY=openai-test' in text
    assert 'OPENAI_VISION_MODEL=gpt-4.1-mini' in text


def test_read_key_file_returns_empty_for_missing(tmp_path: Path) -> None:
    missing = tmp_path / 'missing.txt'
    assert module._read_key_file(missing) == ''

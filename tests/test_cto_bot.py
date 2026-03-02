from pathlib import Path

from cto_bot import run_once


def test_cto_bot_generates_logs(tmp_path: Path) -> None:
    report = run_once(tmp_path, include_pytest=False)

    assert report.run_id
    assert (tmp_path / "cto-bot.log").exists()
    json_files = list(tmp_path.glob("cto-bot-*.json"))
    assert len(json_files) == 1

    content = json_files[0].read_text(encoding="utf-8")
    assert '"checks"' in content
    assert report.remediations

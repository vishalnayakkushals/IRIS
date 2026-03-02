from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_LOG_DIR = Path("data/ops_logs")


@dataclass
class CheckResult:
    role: str
    command: str
    ok: bool
    return_code: int
    output_tail: str
    started_at: str
    finished_at: str


@dataclass
class BotRunReport:
    run_id: str
    started_at: str
    finished_at: str
    healthy: bool
    checks: list[CheckResult]
    remediations: list[str]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_command(command: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    out = proc.stdout[-4000:]
    return proc.returncode, out


def _checks(include_pytest: bool = True) -> list[tuple[str, str, dict[str, str] | None]]:
    checks: list[tuple[str, str, dict[str, str] | None]] = []
    if include_pytest:
        checks.append(("QA", "PYTHONPATH=. pytest -q", {**os.environ, "PYTHONPATH": "."}))
    checks.extend([
        ("CTO", "python -m py_compile iris_analysis.py store_registry.py iris_dashboard.py cto_bot.py", None),
        ("DevOps", "python -m pip --version", None),
    ])
    return checks


def _attempt_remediation(failed: Iterable[CheckResult]) -> list[str]:
    actions: list[str] = []
    for item in failed:
        if "pytest" in item.command:
            code, _ = _run_command("PYTHONPATH=. pytest -q")
            actions.append(f"retest_after_env_guard={'ok' if code == 0 else 'failed'}")
        elif "py_compile" in item.command:
            actions.append("py_compile_failure_requires_code_fix")
        else:
            actions.append(f"no_auto_fix_for:{shlex.quote(item.command)}")
    return actions


def run_once(log_dir: Path = DEFAULT_LOG_DIR, include_pytest: bool = True) -> BotRunReport:
    log_dir.mkdir(parents=True, exist_ok=True)
    started = _utc_now_iso()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    results: list[CheckResult] = []
    for role, cmd, env in _checks(include_pytest=include_pytest):
        s = _utc_now_iso()
        code, out = _run_command(cmd, env=env)
        e = _utc_now_iso()
        results.append(
            CheckResult(
                role=role,
                command=cmd,
                ok=(code == 0),
                return_code=code,
                output_tail=out,
                started_at=s,
                finished_at=e,
            )
        )

    failed = [r for r in results if not r.ok]
    remediations = _attempt_remediation(failed) if failed else ["none_needed"]
    finished = _utc_now_iso()

    report = BotRunReport(
        run_id=run_id,
        started_at=started,
        finished_at=finished,
        healthy=(len(failed) == 0),
        checks=results,
        remediations=remediations,
    )

    json_path = log_dir / f"cto-bot-{run_id}.json"
    json_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    line = (
        f"{finished} run_id={run_id} healthy={report.healthy} "
        f"failed={len(failed)} remediations={';'.join(remediations)}\n"
    )
    with (log_dir / "cto-bot.log").open("a", encoding="utf-8") as f:
        f.write(line)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="IRIS CTO bot health orchestrator")
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR), help="Directory for bot logs")
    parser.add_argument("--skip-pytest", action="store_true", help="Skip QA pytest check")
    args = parser.parse_args()

    report = run_once(Path(args.log_dir), include_pytest=not args.skip_pytest)
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.healthy else 1


if __name__ == "__main__":
    sys.exit(main())

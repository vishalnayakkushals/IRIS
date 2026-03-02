# IRIS Developer Documentation

## 1) Local setup
```bash
python -m pip install -r requirements.txt
```

## 2) Run tests
```bash
PYTHONPATH=. pytest -q
```

## 3) Main modules
- `iris_analysis.py`: analysis engine + export/load helpers.
- `iris_dashboard.py`: Streamlit UI and analytics controls.
- `store_registry.py`: SQLite registry + camera/store config + asset/sync helpers.
- `analyze_stores.py`: CLI batch entrypoint.

## 4) Data/output paths
- Input snapshots: `data/stores/<store_id>/*.jpg`
- Exports: `data/exports/current/`

## 5) CI/CD
- Workflow: `.github/workflows/python-package-conda.yml`
- Lint: flake8 critical + style report.
- Tests: pytest with `PYTHONPATH=.`

## 6) Development rules
- Update at least one governance artifact in each feature PR:
  - `docs/planning/execution-status.md`
  - `docs/actionable-review-checklist.md`
  - `release-notes/*.md`
- Keep API/schema contracts in sync when interface changes.


## 7) Autonomous CTO bot
- Entrypoint: `cto_bot.py`
- Roles inside run: QA, CTO, DevOps checks
- Logs: `data/ops_logs/cto-bot.log` and `data/ops_logs/cto-bot-<run_id>.json`
- CI scheduler: `.github/workflows/cto-bot.yml` (every 30 minutes + push + manual trigger).

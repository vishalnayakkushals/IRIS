# IRIS Developer Documentation

## 1) Local setup
```bash
python -m pip install -r requirements.txt
```

## 2) Run tests
```bash
PYTHONPATH=src pytest -q
```

## 3) Main modules
- `src/iris/iris_analysis.py`: analysis engine + export/load helpers.
- `src/iris/iris_dashboard.py`: Streamlit UI and analytics controls.
- `src/iris/store_registry.py`: SQLite registry + camera/store config + asset/sync helpers.
- `scripts/analyze_stores.py`: CLI batch entrypoint.

## 4) Data/output paths
- Input snapshots: `data/stores/<store_id>/*.jpg`
- Exports: `data/exports/current/`

## 5) CI/CD
- Workflow: `.github/workflows/python-package-conda.yml`
- Lint: flake8 critical + style report.
- Tests: pytest with `PYTHONPATH=src`

## 6) Development rules
- Update at least one governance artifact in each feature PR:
  - `docs/planning/execution-status.md`
  - `docs/actionable-review-checklist.md`
  - `release-notes/*.md`
- Keep API/schema contracts in sync when interface changes.

# CTO Performance Observer (Isolated)

This folder is a fully isolated, removable performance logging layer for IRIS.

## Isolation Guarantee
- All code and data are under `CTO/`.
- Main app does not import from `CTO/`.
- If `CTO/` is deleted, product runtime is unaffected.

## Main Log Path
- `CTO/logs/perf_events.jsonl` (single source of truth)

## What it tracks
- Run lifecycle (`run_start`, `run_end`)
- Optional code-fix command timing (`fix_command`)
- Page probe timing (`page_probe`) for URLs you choose
- Status and notes per run

## Quick Usage
1. Run a fix cycle + probe:
```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
python CTO/scripts/perf_cycle.py --note "fix: feedback save latency" --command "docker restart deploy-iris-1" --url "http://localhost:8765/?module=Reports"
```

2. Probe only (no command):
```powershell
python CTO/scripts/perf_cycle.py --note "manual browse check" --url "http://localhost:8765/?module=Reports" --url "http://localhost:8765/?module=Access&section=Config"
```

3. Analyze latest run vs previous:
```powershell
python CTO/scripts/perf_analyze.py
```

## Reports
- `CTO/reports/latest_perf_report.md`
- `CTO/reports/perf_regression_report.csv`

## Optional BAT wrapper
```powershell
CTO\run_cto_cycle.bat "fix: restart check" "docker restart deploy-iris-1"
```

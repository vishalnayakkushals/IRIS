# IRIS No-Docker Deployment Pack

This folder prepares IRIS to run without Docker as:

- web app
- core scheduler worker
- on-fly scheduler worker
- browser-managed operations

## Runtime shape

### Web app
- Startup script: `scripts/start_web_app.py`
- Opens Streamlit on `IRIS_STREAMLIT_HOST:IRIS_STREAMLIT_PORT`
- Browser ops remain in:
  - `Reports`
  - `Access`
  - `Operations`

### Core scheduler worker
- Startup script: `scripts/start_scheduler_worker_service.py`
- Runs the general queue/retrain/predict scheduler
- Scheduler controls remain in browser under:
  - `Access > Config > Scheduler`

### On-fly scheduler worker
- Startup script: `scripts/start_onfly_scheduler_service.py`
- Reads store/source/hourly/nightly config from DB
- Scheduler controls remain in browser under:
  - `Operations > Manual data sync of IRIS`

## Persistent paths

Recommended VM layout:

- App code: `/opt/iris/app`
- Data: `/opt/iris/data`
- DB: `/opt/iris/data/store_registry.db`
- Exports: `/opt/iris/data/exports/current`
- Stores: `/opt/iris/data/stores`
- Employee assets: `/opt/iris/data/employee_assets`
- Env file: `/opt/iris/shared/iris.env`

The startup scripts will also work with repo-local defaults if no env file is provided.

## Environment and secrets

1. Copy:
   - `deploy/no_docker/.env.example`
2. Save as:
   - `/opt/iris/shared/iris.env`
3. Set:
   - `IRIS_ENV_FILE=/opt/iris/shared/iris.env`

Secrets should live in the env file or in your VM secret manager.

## Install dependencies

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Direct startup commands

### Web app

```bash
export IRIS_ENV_FILE=/opt/iris/shared/iris.env
python scripts/start_web_app.py
```

### Core scheduler

```bash
export IRIS_ENV_FILE=/opt/iris/shared/iris.env
python scripts/start_scheduler_worker_service.py
```

### On-fly scheduler

```bash
export IRIS_ENV_FILE=/opt/iris/shared/iris.env
python scripts/start_onfly_scheduler_service.py
```

## Files and services for go-live

### Required files
- `scripts/start_web_app.py`
- `scripts/start_scheduler_worker_service.py`
- `scripts/start_onfly_scheduler_service.py`
- `src/iris/runtime_bootstrap.py`
- `deploy/no_docker/.env.example`
- `deploy/no_docker/linux/*.service`
- `deploy/no_docker/windows/install_nssm_services.ps1`

### Required services
- `iris-web`
- `iris-scheduler`
- `iris-onfly-scheduler`

## Browser-only ops state

After services are running:

- on-fly source/schedule is managed in browser
- scheduler next run / last run / active schedule are visible in browser
- manual data sync remains browser-triggerable

## Recommended VM go-live checklist

1. Python installed and venv created
2. `requirements.txt` installed
3. `IRIS_ENV_FILE` created and secured
4. writable persistent data directory created
5. web app service installed
6. core scheduler service installed
7. on-fly scheduler service installed
8. port `8765` exposed behind reverse proxy / firewall
9. Google/OpenAI keys validated
10. first browser login + scheduler status verified

## Notes

- No Docker is required for this deployment path.
- SQLite remains acceptable for small/single-host deployment, but Postgres is recommended for larger cloud production later.
- Browser-only ops means scheduling and on-fly job control happen in UI; secrets still remain server-side.

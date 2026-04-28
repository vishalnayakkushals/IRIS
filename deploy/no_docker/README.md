# IRIS No-Docker Deployment Pack

Single supported local runtime for IRIS:

- FastAPI + React on `http://localhost:8767`
- PostgreSQL as the primary database
- browser-controlled sync and scheduler actions

The official local startup path remains:

```text
start_iris.bat
```

## Runtime Shape

### Web app
- Startup entry: `start_iris.bat`
- Internal launcher: `start_iris.ps1`
- Server command path: `scripts/start_api_server.py`
- URL: `http://localhost:8767`

### Browser-controlled sync
- Auto-sync stays controlled from the web app
- Scheduler visibility stays in the React Scheduler page
- Manual sync, run list, run detail, and stage timeline all stay inside the same app

## Persistent Paths

Recommended VM layout:

- App code: `/opt/iris/app`
- Data: `/opt/iris/data`
- Env file: `/opt/iris/shared/iris.env`

The startup scripts also work with repo-local defaults when needed.

## Environment And Secrets

1. Copy `deploy/no_docker/.env.example`
2. Save as `/opt/iris/shared/iris.env`
3. Set `IRIS_ENV_FILE=/opt/iris/shared/iris.env`

Secrets should remain in the env file or your VM secret manager.

## Install Dependencies

From repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## Direct Startup Command

```bash
export IRIS_ENV_FILE=/opt/iris/shared/iris.env
python scripts/start_api_server.py
```

## Required Files

- `start_iris.bat`
- `start_iris.ps1`
- `scripts/start_api_server.py`
- `scripts/prepare_production_db.py`
- `src/iris/runtime_bootstrap.py`
- `deploy/no_docker/.env.example`

## Browser Ops State

After startup:

- on-fly source and schedule are managed in browser
- scheduler next run, last run, and active schedule are visible in browser
- manual data sync remains browser-triggerable

## Recommended Go-Live Checklist

1. Python installed and runtime verified
2. `requirements.txt` and `backend/requirements.txt` installed
3. `.env.local` or `IRIS_ENV_FILE` created and secured
4. Postgres 17 running and `python scripts/prepare_production_db.py` applied
5. Writable persistent data directory created
6. FastAPI + React started through `start_iris.bat` or `python scripts/start_api_server.py`
7. Port `8767` exposed behind reverse proxy
8. Google/OpenAI keys validated
9. First browser login at `8767` verified

## Notes

- No Docker is required for this deployment path.
- The supported operator experience is now the single React + FastAPI app on `8767`.
- Browser-only ops means scheduling and on-fly job control happen in UI while secrets stay server-side.

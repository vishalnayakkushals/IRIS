# IRIS no-Docker Windows service setup

This folder provides an optional NSSM-based setup for:

- IRIS-Web
- IRIS-Scheduler
- IRIS-Onfly-Scheduler

## Prerequisites

1. Python virtual environment created at:
   - `C:\IRIS\.venv`
2. Repo available at:
   - `C:\IRIS`
3. Env file created at:
   - `C:\IRIS\shared\iris.env`
4. NSSM installed

## Install services

Run PowerShell as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\no_docker\windows\install_nssm_services.ps1
```

## Service behavior

- `IRIS-Web` launches `scripts/start_web_app.py`
- `IRIS-Scheduler` launches `scripts/start_scheduler_worker_service.py`
- `IRIS-Onfly-Scheduler` launches `scripts/start_onfly_scheduler_service.py`

## Logs

Services write logs under:

- `C:\IRIS\logs`

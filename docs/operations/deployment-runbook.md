# IRIS Deployment Runbook

## Current Supported App URL

UI + API: `http://localhost:8767`

## Local Startup

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
.\start_iris.bat
```

## First Login

Default local admin credentials:

- `vishal.nayak@kushals.com`
- `ChangeMe123!`

Change the password after sign-in.

## Recommended Deployment Path

Use the single-service FastAPI + React deployment under [deploy/cloud/README.md](C:/Users/Kushals.DESKTOP-D51MT8S/Desktop/Github/IRIS/deploy/cloud/README.md).

## Activity Logging

- UI actions are logged in `user_activity`
- Review logs in the management app under `Activity Logs`

## Troubleshooting

### App does not start

Use:

```powershell
.\start_iris.bat
```

Then inspect:

```powershell
Get-Content deploy\no_docker\runtime_logs\web.err.log -Tail 100
```

### Import or package errors

Use the supported startup flow through `start_iris.bat` or `scripts/start_api_server.py` so `PYTHONPATH` includes repo root plus `src`.

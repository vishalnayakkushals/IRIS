# IRIS Local Server Restart And Troubleshooting Runbook

**Last updated:** 2026-05-14

This document explains how to restart IRIS locally, identify the common localhost/login issue, and handle routine operational checks without using Codex or Claude.

---

## Problem Statement

Sometimes `http://localhost:8767/login` does not open even though port `8767` looks active.

The most common local cause is:

- The IPv6 localhost proxy is still running on `::1:8767`.
- The real FastAPI server on `0.0.0.0:8767` or `127.0.0.1:8767` has stopped.
- Browser requests to `localhost` hit the proxy first.
- The proxy has no real API server to forward to, so the browser shows a failed load or PowerShell shows `The response ended prematurely`.

In simple English: the doorbell is working, but the shop behind the door is closed.

---

## Glossary

| Term | Meaning |
| --- | --- |
| FastAPI | The Python backend server that serves IRIS API and the built React app. |
| React static app | The frontend files copied into `backend/app/static/`. |
| Port `8767` | The local IRIS web/API port. |
| `0.0.0.0:8767` | The real API listener. This also allows LAN devices to connect if firewall allows it. |
| `127.0.0.1:8767` | IPv4 localhost. Good for checking whether FastAPI is alive. |
| `::1:8767` | IPv6 localhost. IRIS uses a small proxy here because some Windows browsers resolve `localhost` to IPv6 first. |
| IPv6 proxy | `scripts/localhost_ipv6_proxy.py`; forwards `::1:8767` traffic to `127.0.0.1:8767`. |
| Health check | `http://127.0.0.1:8767/api/health`; should return `{"status":"ok","service":"iris-api"}`. |
| PID | Process ID. Used to know which process owns the port. |
| `.env.local` | Local secrets/config file required for JWT, database, and runtime settings. |

---

## One-Command Restart

Run this from PowerShell:

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
powershell -ExecutionPolicy Bypass -File .\scripts\restart_iris_local.ps1 -OpenBrowser
```

If you do not want the browser to open automatically:

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
powershell -ExecutionPolicy Bypass -File .\scripts\restart_iris_local.ps1
```

Expected successful output:

```text
IRIS is healthy.
Local URL: http://localhost:8767/login
API health: http://127.0.0.1:8767/api/health
```

---

## What The Restart Script Does

The script `scripts/restart_iris_local.ps1` performs these steps:

1. Stops anything currently using port `8767`.
2. Loads `.env.local`.
3. Sets `PYTHONPATH` to include the repo root and `src/`.
4. Starts FastAPI with uvicorn on `0.0.0.0:8767`.
5. Waits until `http://127.0.0.1:8767/api/health` returns `200`.
6. Starts the IPv6 proxy on `::1:8767`.
7. Writes fresh PID files under `deploy/no_docker/runtime_logs/pids/`.

This avoids the stale-proxy problem where `localhost` is open but the real API is down.

The script opens two minimized PowerShell windows to keep the API server and IPv6 proxy alive. Closing those windows stops the local app.

---

## How To Diagnose Without AI Help

### Step 1: Check Real API Health

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8767/api/health -UseBasicParsing
```

Good result:

```text
StatusCode : 200
Content    : {"status":"ok","service":"iris-api"}
```

If this fails, the real API is not running.

### Step 2: Check Browser/Login Route

```powershell
Invoke-WebRequest -Uri http://localhost:8767/login -UseBasicParsing
```

Good result:

```text
StatusCode : 200
```

If `/api/health` works but `/login` does not, check the IPv6 proxy.

### Step 3: Check Who Owns Port 8767

```powershell
Get-NetTCPConnection -LocalPort 8767 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess |
  Sort-Object OwningProcess -Unique
```

Healthy pattern:

```text
0.0.0.0   8767   Listen   <api_pid>
::1       8767   Listen   <proxy_pid>
```

Broken pattern:

```text
::1       8767   Listen   <proxy_pid>
```

If only `::1` is listening, the proxy is alive but the actual API is down. Run the restart script.

### Step 4: Check Logs

```powershell
Get-Content .\deploy\no_docker\runtime_logs\api_live_uvicorn.log -Tail 80
Get-Content .\deploy\no_docker\runtime_logs\localhost_ipv6_proxy.log -Tail 80
```

Use this when the restart script says health check failed.

---

## Common Issues And Solutions

| Symptom | Meaning | Solution |
| --- | --- | --- |
| `localhost/login` fails with premature response | IPv6 proxy is running but FastAPI is down | Run `scripts/restart_iris_local.ps1` |
| `127.0.0.1/api/health` fails | FastAPI is not running | Run restart script and check API log |
| `127.0.0.1/api/health` works but LAN IP does not | Firewall or network profile issue | Run `scripts/enable_api_network_access.ps1` as Administrator |
| Login page opens but credentials fail | App is running; user/password issue | Verify user in app/admin DB; do not restart repeatedly |
| Page opens old UI after code change | Static frontend was not rebuilt/copied | Run frontend build and copy static assets |
| YOLO/date report is slow | Pipeline workload is large, not a login problem | Do not restart unless API health fails |

---

## Simple Decision Tree

1. Does `http://127.0.0.1:8767/api/health` return `200`?
   If no, restart local server.

2. Does `http://localhost:8767/login` open?
   If no but health works, restart local server to refresh the IPv6 proxy.

3. Does login page open but password fail?
   Do not restart. This is an auth/user issue.

4. Does the app open locally but not on another device?
   Do not rebuild. Check firewall/network profile.

5. Did code change but page still looks old?
   Rebuild frontend and copy static files.

---

## Token-Saving Tasks You Can Do Without Codex Or Claude

These tasks are safe to do manually after reading this document:

| Task | Command / Location |
| --- | --- |
| Restart local IRIS | `powershell -ExecutionPolicy Bypass -File .\scripts\restart_iris_local.ps1` |
| Open login | `http://localhost:8767/login` |
| Check API health | `Invoke-WebRequest -Uri http://127.0.0.1:8767/api/health -UseBasicParsing` |
| Check port ownership | `Get-NetTCPConnection -LocalPort 8767` |
| Read API logs | `Get-Content .\deploy\no_docker\runtime_logs\api_live_uvicorn.log -Tail 80` |
| Export YOLO review table | Use `/scheduler` -> `YOLO Relevant Review Table` -> `Export Review CSV` |
| Run full-folder YOLO | Use `/scheduler` -> `YOLO Relevant Review Table` -> `Run YOLO Full Folder` |
| Disable OpenAI calls | `/scheduler` -> uncheck `OpenAI GPT calls` |
| Confirm app is alive before meeting | Health check plus open `/overview`, `/scheduler`, `/reports` |

Use Codex/Claude only when:

- You need code changes.
- Tests fail and logs do not explain the cause.
- Data counts do not match and need database/source reconciliation.
- A new UI, report, or pipeline behavior is required.
- A command looks destructive or unclear.

---

## Frontend Rebuild If UI Looks Old

Only use this when source code changed but the browser still shows old UI:

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
cd frontend
npm run build
Remove-Item -Recurse -Force ..\backend\app\static\assets\*
Copy-Item -Recurse -Force dist\* ..\backend\app\static\
cd ..
powershell -ExecutionPolicy Bypass -File .\scripts\restart_iris_local.ps1
```

Do not run this for simple login/down issues. Restart first.

---

## LAN Access Check

If local machine works but other people on the same Wi-Fi/LAN cannot open the app:

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
powershell -ExecutionPolicy Bypass -File .\scripts\enable_api_network_access.ps1 -Port 8767 -SetPrivateProfile
```

Then share:

```text
http://<your-pc-ip>:8767/login
```

Example:

```text
http://192.168.1.113:8767/login
```

---

## What Not To Do

- Do not run full YOLO scans just to fix login.
- Do not delete `data/store_registry.db`.
- Do not delete `.env.local`.
- Do not run `git reset --hard`.
- Do not rebuild Docker for a local no-Docker login issue.
- Do not repeatedly click pipeline buttons if only the web app is down.

---

## Final Quick Fix Command

When in doubt, use this:

```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
powershell -ExecutionPolicy Bypass -File .\scripts\restart_iris_local.ps1 -OpenBrowser
```

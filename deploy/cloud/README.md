# IRIS Cloud Deployment Guide

This is the supported production deployment story for IRIS.

## Canonical Production Shape

IRIS is now a **multi-service Python application** with one web process and three dedicated background workers:

| Service | Responsibility | Systemd unit |
| --- | --- | --- |
| FastAPI + React SPA | User-facing web/API app | `iris-api.service` |
| Core scheduler worker | operational recurring jobs | `iris-core-scheduler.service` |
| On-fly scheduler worker | store scan schedule, retries, run orchestration | `iris-onfly-scheduler.service` |
| Store auto-sync worker | mapped parent-folder polling | `iris-store-auto-sync.service` |
| PostgreSQL | platform metadata + dashboard truth | managed or self-hosted |
| Nginx | TLS and reverse proxy | `nginx` |

The web process does **not** run scheduler loops in-process anymore.

---

## Ports

| Port | Service | Exposure |
| --- | --- | --- |
| 80 | Nginx HTTP | Public |
| 443 | Nginx HTTPS | Public |
| 8767 | IRIS web/API | Internal only |
| 5432 | PostgreSQL | Internal only |

---

## Files In This Directory

| File | Purpose |
| --- | --- |
| `setup_ubuntu.sh` | VM bootstrap |
| `.env.production.example` | production environment template |
| `iris-api.service` | web/API systemd unit |
| `iris-core-scheduler.service` | recurring scheduler worker |
| `iris-onfly-scheduler.service` | on-fly scheduler worker |
| `iris-store-auto-sync.service` | mapped-store polling worker |
| `nginx.conf` | reverse proxy configuration |
| `postgres_init.sql` | manual PostgreSQL bootstrap |

---

## Deployment Steps

### 1. Bootstrap the VM

```bash
sudo bash /path/to/deploy/cloud/setup_ubuntu.sh
```

### 2. Copy the code

```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
  /local/path/to/IRIS/ deploy_user@your-server:/opt/iris/app/
sudo chown -R iris:iris /opt/iris/app
```

### 3. Install dependencies

```bash
sudo -u iris /opt/iris/app/.venv/bin/pip install --upgrade pip wheel
sudo -u iris /opt/iris/app/.venv/bin/pip install -r /opt/iris/app/requirements.txt
sudo -u iris /opt/iris/app/.venv/bin/pip install -r /opt/iris/app/backend/requirements.txt
```

### 4. Configure the environment

```bash
sudo cp /opt/iris/app/deploy/cloud/.env.production.example /opt/iris/shared/iris.env
sudo chmod 640 /opt/iris/shared/iris.env
sudo chown iris:iris /opt/iris/shared/iris.env
sudo nano /opt/iris/shared/iris.env
```

Minimum required values:
- `POSTGRES_URL`
- `POSTGRES_SYNC_URL`
- `JWT_SECRET`
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `IRIS_DATA_ROOT`

### 5. Prepare the database schema

```bash
cd /opt/iris/app
sudo -u iris bash -c "
  IRIS_ENV_FILE=/opt/iris/shared/iris.env \
  /opt/iris/app/.venv/bin/python scripts/prepare_production_db.py
"
```

### 6. Install and enable all services

```bash
sudo cp /opt/iris/app/deploy/cloud/iris-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable iris-api iris-core-scheduler iris-onfly-scheduler iris-store-auto-sync
sudo systemctl start iris-api iris-core-scheduler iris-onfly-scheduler iris-store-auto-sync
```

### 7. Validate

```bash
curl http://127.0.0.1:8767/api/health
sudo systemctl status iris-api iris-core-scheduler iris-onfly-scheduler iris-store-auto-sync
```

### 8. Enable TLS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d iris.your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

---

## Operational Notes

- `scripts/start_api_server.py` runs runtime preparation first (`backend/app/runtime_startup.py`) before spawning uvicorn.
- `scripts/start_scheduler_worker_service.py`, `scripts/start_onfly_scheduler_service.py`, and `scripts/start_store_auto_sync_service.py` are the supported worker entry points.
- SQLite remains the fast pipeline-state store; PostgreSQL remains the dashboard/platform source-of-truth.
- The 3 PM batch-saving schedule remains untouched and continues to run through the worker model.

---

## Restarts

```bash
sudo systemctl restart iris-api iris-core-scheduler iris-onfly-scheduler iris-store-auto-sync
sudo nginx -t && sudo systemctl reload nginx
```

---

## Smoke Test

```bash
cd /opt/iris/app
sudo -u iris IRIS_ENV_FILE=/opt/iris/shared/iris.env /opt/iris/app/.venv/bin/python scripts/smoke_test.py \
  --url http://127.0.0.1:8767 \
  --email admin@yourdomain.com \
  --password 'YourAdminPassword'
```

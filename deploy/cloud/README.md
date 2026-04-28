# IRIS Cloud Deployment Guide

Ubuntu 22.04 LTS production deployment for IRIS — 150 stores, ~225K images/day.

---

## Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 100 GB SSD | 500 GB SSD (image cache) |
| Network | 100 Mbps | 1 Gbps |
| Python | 3.11 | 3.11 |
| PostgreSQL | 16 | 16 |
| Redis | 7.x | 7.x |

Root (or sudo) access required.

---

## Port Map

| Port | Service | Exposure |
|---|---|---|
| 80 | Nginx HTTP (redirects to 443) | Public |
| 443 | Nginx HTTPS — React SPA + API | Public |
| 8765 | Streamlit dashboard (iris-web) | Internal / VPN only |
| 8766 | FastAPI + React SPA (iris-api) | Internal (proxied by Nginx) |
| 5432 | PostgreSQL | Internal only |
| 6379 | Redis | Internal only |

Firewall rule: expose only 80 and 443 publicly. Block 5432, 6379, 8765, 8766 from the internet.

---

## Step-by-Step Deployment

### Step 1 — Bootstrap the server

```bash
# Upload this deploy/cloud/ folder to the server then run:
sudo bash /path/to/deploy/cloud/setup_ubuntu.sh
```

The script installs all system packages, PostgreSQL 16, creates the `iris` system user, sets up directory layout, creates the Python venv, creates `iris_user` + `iris_db` in Postgres (reads password from `$IRIS_DB_PASSWORD` env var), installs Nginx config and systemd units, and prints a completion checklist.

To supply the DB password non-interactively:

```bash
sudo IRIS_DB_PASSWORD='your_secure_password' bash setup_ubuntu.sh
```

---

### Step 2 — Deploy the application code

```bash
# From your local machine or CI runner:
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
    /local/path/to/iris/ deploy_user@your-server:/opt/iris/app/

# Fix ownership on the server:
sudo chown -R iris:iris /opt/iris/app
```

---

### Step 3 — Install Python dependencies

```bash
sudo -u iris /opt/iris/app/.venv/bin/pip install --upgrade pip wheel
sudo -u iris /opt/iris/app/.venv/bin/pip install -r /opt/iris/app/requirements.txt
sudo -u iris /opt/iris/app/.venv/bin/pip install -r /opt/iris/app/backend/requirements.txt
```

---

### Step 4 — Configure the environment file

```bash
# Copy the template (setup_ubuntu.sh may have already done this)
sudo cp /opt/iris/app/deploy/cloud/.env.production.example /opt/iris/shared/iris.env
sudo chmod 640 /opt/iris/shared/iris.env
sudo chown iris:iris /opt/iris/shared/iris.env

# Edit and fill every CHANGE_ME value
sudo nano /opt/iris/shared/iris.env
```

Minimum required values to set:

```
POSTGRES_URL         — use the password you passed to setup_ubuntu.sh
POSTGRES_SYNC_URL    — same password
JWT_SECRET           — generate: python -c "import secrets; print(secrets.token_hex(32))"
OPENAI_API_KEY       — from platform.openai.com
GOOGLE_API_KEY       — from console.cloud.google.com (if Drive sync is enabled)
STORE_ID             — your primary store identifier
```

---

### Step 5 — Run database migrations

```bash
cd /opt/iris/app
sudo -u iris bash -c "
  IRIS_ENV_FILE=/opt/iris/shared/iris.env \
  /opt/iris/app/.venv/bin/python -m alembic upgrade head
"
```

---

### Step 6 — Seed initial data (first deploy only)

```bash
cd /opt/iris/app
sudo -u iris bash -c "
  IRIS_ENV_FILE=/opt/iris/shared/iris.env \
  /opt/iris/app/.venv/bin/python scripts/add_user.py \
    --email admin@yourdomain.com \
    --password 'ChangeMe123!'
"
```

---

### Step 7 — Start IRIS services

```bash
sudo systemctl start iris-api
sudo systemctl start iris-web
sudo systemctl start iris-celery-worker

# Verify all three are active
sudo systemctl status iris-api iris-web iris-celery-worker
```

---

### Step 8 — Enable SSL with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d iris.your-domain.com

# After certbot succeeds, uncomment the HTTPS server block in:
sudo nano /etc/nginx/sites-available/iris
sudo nginx -t && sudo systemctl reload nginx
```

---

## Checking Logs

```bash
# FastAPI server
journalctl -u iris-api -f

# Streamlit dashboard
journalctl -u iris-web -f

# Celery pipeline worker
journalctl -u iris-celery-worker -f

# Nginx
tail -f /var/log/nginx/iris_error.log

# PostgreSQL
journalctl -u postgresql -f

# All IRIS units together
journalctl -u iris-api -u iris-web -u iris-celery-worker -f --since "10 min ago"
```

---

## Restarting Services

```bash
# Restart one service
sudo systemctl restart iris-api

# Rolling restart (API down briefly, web stays up)
sudo systemctl restart iris-celery-worker
sudo systemctl restart iris-api
sudo systemctl restart iris-web

# Reload nginx config without dropping connections
sudo nginx -t && sudo systemctl reload nginx
```

---

## Database Backup

### Manual backup

```bash
# Dump to compressed file
sudo -u postgres pg_dump -Fc iris_db -f /opt/iris/data/backups/iris_db_$(date +%Y%m%d_%H%M%S).dump

# Restore
sudo -u postgres pg_restore -d iris_db -Fc /opt/iris/data/backups/iris_db_YYYYMMDD_HHMMSS.dump
```

### Automated daily backup via cron

```bash
sudo mkdir -p /opt/iris/data/backups
sudo chown iris:iris /opt/iris/data/backups

# Add to root crontab (sudo crontab -e):
0 2 * * * sudo -u postgres pg_dump -Fc iris_db -f /opt/iris/data/backups/iris_db_$(date +\%Y\%m\%d).dump && find /opt/iris/data/backups -name "*.dump" -mtime +14 -delete
```

---

## Scaling Notes

**Target load: 150 stores, ~225K images/day (~2.6 images/sec peak)**

### Connection pool

Each of the three processes (iris-api, iris-celery-worker, optionally iris-web) opens its own pool. With `DB_POOL_SIZE=20` and `DB_MAX_OVERFLOW=30`, worst-case open connections = 3 processes × 50 = 150 connections, well within `max_connections=300`.

For horizontal scale (multiple API instances behind a load balancer), deploy **PgBouncer** in transaction-pool mode in front of PostgreSQL and point all `POSTGRES_URL` vars to PgBouncer (port 6432).

### Celery workers

Each worker process handles 4 concurrent tasks (`--concurrency=4`). YOLO inference tasks are CPU-bound; GPT analysis tasks are I/O-bound (OpenAI API calls).

For 150 stores running nightly:

- Nightly pipeline window: ~4 hours (midnight–4 am IST)
- Required throughput: ~38 stores/hour
- Recommended: 2–4 worker processes with `--concurrency=4` each

Add a second worker by deploying a second VM and pointing it at the same Redis broker and Postgres DB, or by running a second systemd instance:

```bash
# iris-celery-worker@2.service (copy the unit, change hostname)
ExecStart=... --hostname=iris-worker-2@%%h
```

### Image storage

At 225K images/day × ~150 KB average = ~32 GB/day. Use an NFS mount or S3-compatible object store at `IRIS_DATA_ROOT` for shared access across workers. The data directory layout (`/opt/iris/data/stores/`, `/opt/iris/data/exports/`) is the canonical mount point.

### Redis

Single Redis node is sufficient up to ~500 queued tasks. Enable Redis persistence (`appendonly yes` in `/etc/redis/redis.conf`) and set a memory limit:

```
maxmemory 512mb
maxmemory-policy allkeys-lru
```

---

## Health Check Endpoints

```bash
# API liveness
curl http://localhost:8766/health

# API detailed status
curl http://localhost:8766/api/v1/status

# Celery task queue depth (from python)
# /opt/iris/app/.venv/bin/python -c "
# from backend.app.celery_app.worker import celery_app
# i = celery_app.control.inspect(); print(i.active())
# "
```

---

## Files in this Directory

| File | Purpose |
|---|---|
| `setup_ubuntu.sh` | One-shot bootstrap for Ubuntu 22.04 |
| `postgres_init.sql` | Manual SQL init (alternative to bootstrap) |
| `nginx.conf` | Nginx site config — proxy + gzip + SSL placeholder |
| `iris-api.service` | Systemd unit for FastAPI server |
| `iris-web.service` | Systemd unit for Streamlit dashboard |
| `iris-celery-worker.service` | Systemd unit for Celery pipeline worker |
| `.env.production.example` | Environment variable template |
| `README.md` | This file |

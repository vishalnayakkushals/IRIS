# IRIS Cloud Deployment Guide

Single-service production shape for IRIS:

- one FastAPI process
- one embedded React build
- one internal application port: `8767`
- one primary database: PostgreSQL

This folder is the supported production deployment path for the app you are demoing on `http://localhost:8767`.

## Target Shape

| Component | Purpose |
|---|---|
| `iris-api.service` | FastAPI + embedded React SPA on `127.0.0.1:8767` |
| PostgreSQL 16/17 | Primary database |
| Nginx | Public reverse proxy and TLS |

Redis, Celery, and Streamlit are not part of the supported deployment story in this folder.

## Port Map

| Port | Service | Exposure |
|---|---|---|
| 80 | Nginx HTTP | Public |
| 443 | Nginx HTTPS | Public |
| 8767 | IRIS app (FastAPI + React) | Internal only |
| 5432 | PostgreSQL | Internal only |

Expose only `80` and `443` publicly.

## Deployment Steps

### 1. Bootstrap the VM

```bash
sudo bash /path/to/deploy/cloud/setup_ubuntu.sh
```

Optional password injection:

```bash
sudo IRIS_DB_PASSWORD='your_secure_password' bash setup_ubuntu.sh
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

```text
POSTGRES_URL
POSTGRES_SYNC_URL
JWT_SECRET
OPENAI_API_KEY
GOOGLE_API_KEY
IRIS_DATA_ROOT
```

### 5. Prepare the database schema

```bash
cd /opt/iris/app
sudo -u iris bash -c "
  IRIS_ENV_FILE=/opt/iris/shared/iris.env \
  /opt/iris/app/.venv/bin/python scripts/prepare_production_db.py
"
```

This is the supported production-safe schema bootstrap path. Do not use `alembic upgrade head` here.

### 6. Seed the first admin user

```bash
cd /opt/iris/app
sudo -u iris bash -c "
  IRIS_ENV_FILE=/opt/iris/shared/iris.env \
  /opt/iris/app/.venv/bin/python scripts/add_user.py \
    --email admin@yourdomain.com \
    --password 'ChangeMe123!'
"
```

### 7. Start the app

```bash
sudo systemctl start iris-api
sudo systemctl status iris-api
```

### 8. Enable TLS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d iris.your-domain.com
sudo nginx -t && sudo systemctl reload nginx
```

## Validation

```bash
# Quick health check
curl http://localhost:8767/api/health
sudo systemctl status iris-api

# Full smoke test (run from /opt/iris/app)
sudo -u iris /opt/iris/app/.venv/bin/python scripts/smoke_test.py \
  --url http://localhost:8767 \
  --email admin@yourdomain.com \
  --password 'YourAdminPassword'

# After TLS is up, re-run against the public domain
python scripts/smoke_test.py \
  --url https://iris.your-domain.com \
  --email admin@yourdomain.com \
  --password 'YourAdminPassword'
```

All 7 checks must pass before handing over to users:

- Health endpoint responds 200
- React SPA loads (HTML served)
- Login returns a JWT token
- Dashboard overview loads
- Store list returns data
- Pipeline run history accessible
- Security headers present (X-Frame-Options, X-Content-Type-Options)

## Restarting

```bash
sudo systemctl restart iris-api
sudo nginx -t && sudo systemctl reload nginx
```

## Backups

```bash
sudo mkdir -p /opt/iris/data/backups
sudo chown iris:iris /opt/iris/data/backups
sudo -u postgres pg_dump -Fc iris_db -f /opt/iris/data/backups/iris_db_$(date +%Y%m%d_%H%M%S).dump
```

## Files In This Directory

| File | Purpose |
|---|---|
| `setup_ubuntu.sh` | Ubuntu bootstrap for the single-service deployment |
| `postgres_init.sql` | Manual Postgres role/database bootstrap |
| `nginx.conf` | Reverse proxy config to internal port `8767` |
| `iris-api.service` | Systemd unit for the supported app service |
| `.env.production.example` | Environment template |
| `README.md` | This guide |

#!/usr/bin/env bash
# =============================================================================
# IRIS Cloud Bootstrap — Ubuntu 22.04 LTS
# Run as root on a fresh VM:  sudo bash setup_ubuntu.sh
# =============================================================================
set -euo pipefail

IRIS_APP_DIR="/opt/iris/app"
IRIS_DATA_DIR="/opt/iris/data"
IRIS_SHARED_DIR="/opt/iris/shared"
IRIS_VENV="${IRIS_APP_DIR}/.venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[IRIS]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERR ]${NC} $*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || error "Must be run as root."

# =============================================================================
# 1. APT — base packages
# =============================================================================
info "Updating apt and installing base packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    build-essential \
    nginx \
    curl \
    git \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common \
    libpq-dev

# =============================================================================
# 2. PostgreSQL 16
# =============================================================================
info "Installing PostgreSQL 16..."
if ! command -v psql &>/dev/null; then
    # Add PostgreSQL APT repo
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/postgresql-archive-keyring.gpg] \
https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y
fi
apt-get install -y postgresql-16 postgresql-client-16

# =============================================================================
# 3. System user — iris
# =============================================================================
info "Creating system user 'iris'..."
if ! id iris &>/dev/null; then
    useradd -r -s /bin/false iris
fi

# =============================================================================
# 4. Directory layout
# =============================================================================
info "Creating directory layout..."
mkdir -p "${IRIS_APP_DIR}" "${IRIS_DATA_DIR}" "${IRIS_SHARED_DIR}"
chown -R iris:iris "${IRIS_APP_DIR}" "${IRIS_DATA_DIR}"
chmod 750 "${IRIS_SHARED_DIR}"
chown iris:iris "${IRIS_SHARED_DIR}"

# Sub-directories expected by runtime_bootstrap
for subdir in stores exports/current employee_assets logs; do
    mkdir -p "${IRIS_DATA_DIR}/${subdir}"
done
chown -R iris:iris "${IRIS_DATA_DIR}"

# =============================================================================
# 5. Python venv
# =============================================================================
info "Creating Python 3.11 venv at ${IRIS_VENV}..."
python3.11 -m venv "${IRIS_VENV}"
"${IRIS_VENV}/bin/pip" install --upgrade pip wheel setuptools

# =============================================================================
# 6. Postgres — production tuning
# =============================================================================
info "Applying PostgreSQL production tuning..."
PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
if [[ -z "${PG_CONF}" ]]; then
    warn "Could not locate postgresql.conf — skipping tuning. Apply manually."
else
    # Back up original
    cp "${PG_CONF}" "${PG_CONF}.orig"

    # Apply settings — append a tuning block so originals remain readable
    cat >> "${PG_CONF}" <<'PGEOF'

# ── IRIS Production Tuning ────────────────────────────────────────────────────
max_connections            = 300
shared_buffers             = 256MB
effective_cache_size       = 1GB
work_mem                   = 4MB
maintenance_work_mem       = 64MB
checkpoint_completion_target = 0.9
wal_buffers                = 16MB
default_statistics_target  = 100
random_page_cost           = 1.1
timezone                   = 'Asia/Kolkata'
PGEOF
    info "PostgreSQL tuning applied → ${PG_CONF}"
fi

# =============================================================================
# 7. Postgres — create user + database
# =============================================================================
info "Configuring PostgreSQL iris_user / iris_db..."

# Require DB password from env; abort with helpful message if absent
IRIS_DB_PASSWORD="${IRIS_DB_PASSWORD:-}"
if [[ -z "${IRIS_DB_PASSWORD}" ]]; then
    warn "IRIS_DB_PASSWORD env var not set."
    warn "Defaulting to 'CHANGE_ME' — update /opt/iris/shared/iris.env immediately."
    IRIS_DB_PASSWORD="CHANGE_ME"
fi

systemctl start postgresql || true

# Run as postgres superuser
su -c "psql -v ON_ERROR_STOP=1 <<SQL
DO \\\$do\\\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'iris_user') THEN
      CREATE ROLE iris_user WITH LOGIN PASSWORD '${IRIS_DB_PASSWORD}';
   ELSE
      ALTER ROLE iris_user WITH PASSWORD '${IRIS_DB_PASSWORD}';
   END IF;
END
\\\$do\\\$;

SELECT 'iris_db exists' WHERE EXISTS (SELECT 1 FROM pg_database WHERE datname='iris_db') \\gset
DO \\\$do\\\$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'iris_db') THEN
      CREATE DATABASE iris_db OWNER iris_user;
   END IF;
END
\\\$do\\\$;

GRANT ALL PRIVILEGES ON DATABASE iris_db TO iris_user;
\\c iris_db
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SQL
" postgres

info "PostgreSQL user iris_user and database iris_db ready."

# =============================================================================
# 8. Nginx — install site config
# =============================================================================
info "Installing nginx site config..."
if [[ -f "${SCRIPT_DIR}/nginx.conf" ]]; then
    cp "${SCRIPT_DIR}/nginx.conf" /etc/nginx/sites-available/iris
    ln -sf /etc/nginx/sites-available/iris /etc/nginx/sites-enabled/iris
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && info "Nginx config OK." || warn "Nginx config test failed — check /etc/nginx/sites-available/iris"
else
    warn "nginx.conf not found in ${SCRIPT_DIR} — skipping."
fi

# =============================================================================
# 9. Systemd services
# =============================================================================
info "Installing systemd service units..."
for svc_file in iris-api.service; do
    if [[ -f "${SCRIPT_DIR}/${svc_file}" ]]; then
        cp "${SCRIPT_DIR}/${svc_file}" /etc/systemd/system/
        info "  Installed /etc/systemd/system/${svc_file}"
    else
        warn "  ${svc_file} not found in ${SCRIPT_DIR} — skipping."
    fi
done
systemctl daemon-reload

# =============================================================================
# 10. Enable & start infrastructure services
# =============================================================================
info "Enabling and starting infrastructure services..."
systemctl enable --now nginx
systemctl enable --now postgresql

# Enable IRIS service (don't start yet — env file must be populated first)
systemctl enable iris-api.service  || true

# =============================================================================
# 11. env file placeholder
# =============================================================================
ENV_DEST="${IRIS_SHARED_DIR}/iris.env"
if [[ ! -f "${ENV_DEST}" ]]; then
    if [[ -f "${SCRIPT_DIR}/.env.production.example" ]]; then
        cp "${SCRIPT_DIR}/.env.production.example" "${ENV_DEST}"
        chmod 640 "${ENV_DEST}"
        chown iris:iris "${ENV_DEST}"
        warn "Copied .env.production.example → ${ENV_DEST}"
        warn "You MUST edit ${ENV_DEST} before starting IRIS services."
    fi
fi

# =============================================================================
# 12. Final checklist
# =============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           IRIS Ubuntu Bootstrap — COMPLETE                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. Copy your IRIS source code/repo to ${IRIS_APP_DIR}"
echo "     e.g.:  rsync -a /path/to/repo/ ${IRIS_APP_DIR}/"
echo "            chown -R iris:iris ${IRIS_APP_DIR}"
echo ""
echo "  2. Install Python dependencies:"
echo "     ${IRIS_VENV}/bin/pip install -r ${IRIS_APP_DIR}/requirements.txt"
echo "     ${IRIS_VENV}/bin/pip install -r ${IRIS_APP_DIR}/backend/requirements.txt"
echo ""
echo "  3. Edit the env file:"
echo "     nano ${IRIS_SHARED_DIR}/iris.env"
echo "     (set POSTGRES_URL, JWT_SECRET, OPENAI_API_KEY, GOOGLE_API_KEY, etc.)"
echo ""
echo "  4. Prepare the database schema:"
echo "     cd ${IRIS_APP_DIR}"
echo "     IRIS_ENV_FILE=${IRIS_SHARED_DIR}/iris.env \\"
echo "       ${IRIS_VENV}/bin/python scripts/prepare_production_db.py"
echo ""
echo "  5. Start IRIS services:"
echo "     systemctl start iris-api"
echo ""
echo "  6. Verify:"
echo "     systemctl status iris-api"
echo "     journalctl -u iris-api -f"
echo ""
echo "  7. SSL (recommended):"
echo "     apt install certbot python3-certbot-nginx"
echo "     certbot --nginx -d your.domain.com"
echo ""
echo -e "${YELLOW}Port map:  8767 FastAPI+React | 5432 PG (internal)${NC}"
echo ""

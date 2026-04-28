-- =============================================================================
-- IRIS PostgreSQL Initialisation Script
-- Run once as the postgres superuser on the target server:
--   sudo -u postgres psql -f postgres_init.sql
--
-- Before running, replace CHANGE_ME with the real password or pass it as:
--   sudo -u postgres psql -v iris_pass="'s3cr3t'" -f postgres_init.sql
--   Then change: PASSWORD 'CHANGE_ME' → PASSWORD :iris_pass
-- =============================================================================

-- ── 1. Role ──────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = 'iris_user'
    ) THEN
        CREATE ROLE iris_user
            WITH LOGIN
                 PASSWORD 'CHANGE_ME'        -- replace before running
                 CONNECTION LIMIT 280;       -- headroom below max_connections=300
        RAISE NOTICE 'Role iris_user created.';
    ELSE
        RAISE NOTICE 'Role iris_user already exists — skipping creation.';
    END IF;
END
$$;

-- ── 2. Database ───────────────────────────────────────────────────────────────
-- NOTE: CREATE DATABASE cannot run inside a transaction block.
--       Run this section separately if using psql's \i inside a transaction.
SELECT 'CREATE DATABASE iris_db OWNER iris_user ENCODING ''UTF8'' LC_COLLATE ''en_US.UTF-8'' LC_CTYPE ''en_US.UTF-8'' TEMPLATE template0'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'iris_db'
) \gexec

-- ── 3. Privileges ─────────────────────────────────────────────────────────────
GRANT ALL PRIVILEGES ON DATABASE iris_db TO iris_user;

-- ── 4. Connect to iris_db and finish setup ────────────────────────────────────
\connect iris_db

-- Allow iris_user to create objects in the public schema
GRANT ALL ON SCHEMA public TO iris_user;

-- ── 5. Extensions ────────────────────────────────────────────────────────────
-- pg_stat_statements: query performance tracking
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- uuid-ossp: UUID generation helpers (useful for primary keys)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── 6. Default timezone ───────────────────────────────────────────────────────
ALTER DATABASE iris_db SET timezone TO 'Asia/Kolkata';

-- ── 7. Ownership assertion (idempotent) ───────────────────────────────────────
ALTER DATABASE iris_db OWNER TO iris_user;

-- ── 8. Revoke public access (security hardening) ─────────────────────────────
-- Prevent other roles from connecting unless explicitly granted.
REVOKE CONNECT ON DATABASE iris_db FROM PUBLIC;
GRANT  CONNECT ON DATABASE iris_db TO iris_user;

-- ── Done ──────────────────────────────────────────────────────────────────────
\echo '-------------------------------------------------------------------'
\echo 'IRIS Postgres init complete.'
\echo 'Remember to update POSTGRES_URL in /opt/iris/shared/iris.env'
\echo 'and run:  alembic upgrade head'
\echo '-------------------------------------------------------------------'

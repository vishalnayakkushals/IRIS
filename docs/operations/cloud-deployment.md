# Cloud Deployment Guide (IRIS)

This guide provides a practical path to deploy IRIS in cloud environments.

## 1) Recommended target architecture

- **App runtime**: containerized Python service (analysis + dashboard).
- **Database**: managed Postgres (migrate from SQLite for multi-user/prod).
- **Storage**: object storage for snapshots/exports.
- **Secrets**: cloud secret manager for API keys and credentials.
- **Monitoring**: uptime checks + logs + alerting.

## 2) Environments

- **dev**: shared integration environment.
- **staging**: production-like validation.
- **prod**: business traffic.

## 3) Deployment sequence

1. Build Docker image from repo.
2. Run automated tests in CI.
3. Push versioned image to container registry.
4. Deploy to staging, run smoke checks.
5. Promote same image digest to production.

## 4) Minimum env vars

- `GOOGLE_API_KEY` (optional, for robust Drive sync)
- `IRIS_DATA_ROOT` (snapshot root)
- `IRIS_EXPORT_ROOT` (export path)

## 5) Ops checklist

- Backups enabled for DB and exports.
- TLS enabled on all public endpoints.
- Role-based access control for dashboard/API.
- Error budget + alert thresholds configured.
- Runbook and on-call escalation available.

## 6) Cloud providers

This architecture works on AWS, GCP, or Azure. Pick provider based on team familiarity and existing contracts; keep the same app/container pattern across providers.

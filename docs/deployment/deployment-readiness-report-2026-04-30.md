# IRIS Deployment Readiness Report

**Updated:** 2026-05-12

## Verdict

IRIS is now aligned around a dedicated-worker runtime story and is substantially closer to repeatable cloud deployment.

## Ready

- FastAPI + React single web surface
- dedicated worker entry points
- PostgreSQL + SQLite split documented
- cost-saving controls live in code
- smart frame sampling live
- cloud service templates available under `deploy/cloud/`

## Still Requires Operational Validation

- final end-to-end cloud smoke test on the target host
- production secrets setup
- monitoring/alerting setup for worker failures and stalled heartbeats
- backup/restore drills for PostgreSQL and SQLite export state

## Risk Areas

| Area | Risk |
| --- | --- |
| Google Drive connectivity | external network/API instability can slow runs |
| OpenAI quota | GPT retries may queue rather than complete immediately |
| Mixed SQLite/PostgreSQL reads | acceptable today, but should keep being documented clearly |

## Recommended Release Gate

Before production handover:
1. web app health passes
2. worker services all healthy
3. manual sync works
4. scheduled sync works
5. download/export works
6. cost metrics endpoint returns data
7. heartbeat stale detection verified

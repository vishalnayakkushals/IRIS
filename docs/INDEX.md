# IRIS Documentation Index

**Last updated:** 2026-05-14

This index is the current ownership map for documentation. If a document conflicts with one listed as source-of-truth below, follow the source-of-truth document and update the stale file or archive it.

## Source-of-Truth Documents

| Document | Owner | Purpose |
| --- | --- | --- |
| `README.md` | Engineering | Main product/runtime overview and local validation steps |
| `docs/deployment/cost-optimization-plan.md` | Engineering + Management | Cost controls, savings model, measured-vs-projected guidance |
| `docs/process/onfly_pipeline_logic.md` | Engineering | Business and technical pipeline flow |
| `docs/AI_HANDOVER_STORAGE.md` | Engineering | AI agent handover and runtime truth |
| `deploy/cloud/README.md` | Engineering / DevOps | Canonical cloud deployment guide |
| `docs/developer/generated-vs-source-policy.md` | Engineering | Generated artifact, static asset, and ownership policy |

## Active Supporting Docs

| Area | Document | Notes |
| --- | --- | --- |
| Deployment readiness | `docs/deployment/deployment-readiness-report-2026-04-30.md` | Updated to match React + FastAPI + worker runtime |
| Infra sizing | `docs/deployment/IRIS-Server-Requirement-150-Stores.md` | Capacity planning for cloud rollout |
| Architecture | `docs/developer/data-flow-architecture.md` | Canonical module/data flow |
| Developer onboarding | `docs/developer/developer-doc.md` | Safe change rules and testing baseline |
| Planning | `docs/planning/execution-status.md` | Current execution snapshot |
| Operations | `docs/operations/deployment-runbook.md` | Runbook/checklist support |
| Operations | `docs/operations/local-server-restart-and-troubleshooting.md` | Local no-Docker restart, localhost/login troubleshooting, and token-saving manual checks |
| Operations | `docs/operations/platform_data_cutover_inventory.md` | Historical migration inventory; references to Streamlit are legacy only |
| Product | `docs/prd/iris-platform-prd-v1.md` | Product framing; keep aligned with runtime stack |

## Generated vs Source Boundaries

- Frontend source lives under `frontend/src/**`.
- Built frontend assets live under `backend/app/static/**`.
- Runtime/export data lives under `data/**` and is not source-of-truth code.
- For the detailed policy, see `docs/developer/generated-vs-source-policy.md`.

## Update Rules

1. When code changes alter runtime behavior, update the relevant source-of-truth doc in the same change set.
2. When adding a new major doc, add it to this index and state whether it is source-of-truth or supporting.
3. Archive or delete transitional docs once they are superseded.
4. Keep `CHANGE_LEDGER.md` aligned with module ownership and runtime truth.

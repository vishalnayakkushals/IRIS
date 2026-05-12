# Generated vs Source Policy

**Last updated:** 2026-05-12

This document defines what is editable source, what is generated output, and what must stay aligned during deploys.

## 1. Source Code

Editable source-of-truth code:
- `backend/app/**` except `backend/app/static/**`
- `frontend/src/**`
- `src/iris/**`
- `scripts/**`
- `tests/**`
- `deploy/cloud/**`
- source-of-truth docs listed in `docs/INDEX.md`

These files should be edited directly and reviewed in Git.

## 2. Generated Frontend Assets

Generated build artifacts:
- `backend/app/static/index.html`
- `backend/app/static/assets/**`

### Policy
- These files are generated from `frontend/src/**` via `npm run build`.
- They remain committed in Git because the FastAPI runtime serves them directly and deployment targets may not run a frontend build step at release time.
- Do not hand-edit generated files.
- Any intentional UI change must be made in `frontend/src/**`, then rebuilt and mirrored into `backend/app/static/**`.

## 3. Runtime Data and Exports

Runtime/generated data:
- `data/exports/**`
- `data/uploads/**`
- SQLite runtime state such as `store_registry.db`
- temporary logs under `deploy/no_docker/runtime_logs/**`

### Policy
- Treat these as runtime artifacts, not source code.
- They can be inspected for debugging, but should not be manually treated as the product source-of-truth.
- Canonical business logic must be reflected in code and documentation, not only in generated CSV/JSON outputs.

## 4. Documentation Ownership

- `README.md`, `docs/deployment/cost-optimization-plan.md`, `docs/process/onfly_pipeline_logic.md`, `docs/AI_HANDOVER_STORAGE.md`, and `deploy/cloud/README.md` are source-of-truth documents.
- Other docs are supporting or historical unless explicitly promoted in `docs/INDEX.md`.

## 5. Release Checklist for Generated Assets

When frontend code changes:
1. Update `frontend/src/**`
2. Run `npm run build` in `frontend/`
3. Mirror `frontend/dist/**` into `backend/app/static/**`
4. Smoke-test the FastAPI-served app
5. Update `CHANGE_LEDGER.md`

## 6. Temporary / Stray Files

- Temporary files such as ad-hoc tracked-file dumps must not remain in the repo root.
- If a helper dump is needed briefly, keep it outside the repo or ensure it is gitignored and removed before completion.

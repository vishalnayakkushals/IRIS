# B2B SOP Checklist Status (IRIS)

Source reviewed: `B2B Projects – Development & Deployment SOP` (Confluence export, 2026-03-31).

Status legend:
- `Done Now`: already implemented and available now.
- `Completed In This Update`: implemented as part of this checklist pass.
- `Future / External`: requires org/admin setup outside repo code, or deliberate future rollout.
- `Not Applicable`: SOP item is stack-specific and does not map directly to IRIS runtime.

## Checklist Matrix
| SOP Area | Requirement | Status | Evidence / Notes |
|---|---|---|---|
| Repo structure | `README.md` present with setup/run docs | Done Now | `README.md` |
| Repo structure | `.env.example` present | Completed In This Update | `.env.example` |
| Repo structure | `.gitignore` present | Done Now | `.gitignore` |
| Branching | Work only via feature/bugfix/hotfix branches | Future / External | Process rule; enforce with branch protection + team discipline. |
| Branching | No direct commit to `main` | Future / External | Needs GitHub branch protection policy. |
| PR process | PR must include what/why/how-to-test/UI/DB impact | Completed In This Update | `.github/pull_request_template.md` |
| PR review | Minimum one approval before merge | Future / External | Needs repo branch protection settings. |
| CI/CD | Build + tests run on push/PR | Done Now | `.github/workflows/python-package-conda.yml` |
| Preview before merge | Temporary preview link for stakeholder review | Done Now (project-specific) | IRIS currently uses local/Docker run for preview; optional tunnel process can be documented when needed. |
| Deployment | Standard deploy flow documented | Done Now | `README.md`, `AGENTS.md`, `deploy/docker-compose.yml` |
| Deployment safety | No ad-hoc production server edits | Future / External | Ops policy + access control item; not fully enforceable from repo only. |
| Secrets | Never commit API keys/passwords | Done Now (policy) | Existing security guidance + `.gitignore`; continue manual discipline. |
| Secrets | Store runtime keys in env/config, not source | Done Now | Runtime uses env vars in scripts/services. |
| Database | Controlled DB schema/data updates | Done Now (partial) | SQLite migrations/initialization in code; production DB governance still policy-driven. |
| DB backup | Daily backup + restore test | Future / External | Requires infrastructure automation outside this repo. |
| RBAC | In-app role-based access controls | Done Now | `src/iris/store_registry.py`, `src/iris/iris_dashboard.py` |
| Daily workflow | Pull latest, branch, test, PR, merge, verify | Done Now (process) | Documented by team workflow and AGENTS instructions. |

## What Was Completed Now
1. Added environment template for safe/local configuration: `.env.example`.
2. Added PR checklist template aligned with SOP review requirements: `.github/pull_request_template.md`.
3. Added this SOP status document for clear now-vs-future tracking.

## Future Actions (Recommended)
1. Enable branch protection on `main`: require PR, require 1 reviewer, block direct pushes.
2. Require passing CI checks before merge (`Python Package CI`).
3. Add a protected release flow (tag/release checklist) if needed for production cadence.
4. Implement infrastructure-level automated DB backup + restore drill tracking.

## Notes
- SOP mentions `React + Node + MySQL` and `AWS CodeCommit`; IRIS is currently a Python/Streamlit pipeline hosted in GitHub.
- Where stack-specific items do not map 1:1, equivalent IRIS controls are documented above.

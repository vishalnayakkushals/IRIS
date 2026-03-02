# IRIS Organization Architecture and End-to-End Delivery Process

This document defines how the team operates from idea to production support so anyone can understand ownership and flow.

## 1) Team architecture

## Leadership lane

- **CTO**: technical strategy, architecture approvals, security/compliance signoff.
- **PM**: product priorities, scope and release decisions.
- **BA**: business requirements, acceptance criteria, stakeholder traceability.

## Delivery lane

- **Full Stack Developers**: API, UI, data integration, automation.
- **QA Engineers**: test strategy, release quality gates, regression signoff.
- **DevOps/Platform**: CI/CD, cloud infra, monitoring, incident response.

## User lane

- **Business User / Store Operator**: UAT feedback, workflow validation, operational acceptance.

---

## 2) Department-by-department responsibilities

### CTO

- Approve architecture and coding standards.
- Own risk register for scale/security/data privacy.
- Run weekly architecture review.

### BA

- Write business process map and pain points.
- Convert stakeholder inputs into testable requirements.
- Maintain requirement -> feature -> test traceability.

### PM

- Prioritize backlog by impact and urgency.
- Maintain sprint goals, release milestones, and dependency tracking.
- Publish delivery status every sprint.

### Full Stack Dev

- Implement features with tests and docs.
- Keep OpenAPI/schema/contracts updated.
- Provide migration plans for data model changes.

### QA

- Define unit/integration/UAT acceptance plan.
- Automate regressions and maintain defect triage.
- Block release on Sev-1/Sev-2 defects.

### User (Store / Ops)

- Validate whether feature solves real workflow.
- Report usability/accuracy issues with examples.
- Approve rollout for their store cohort.

---

## 3) Full journey (beginning to end)

1. **Discovery** (BA + PM + Users)
   - Capture business problem, KPI, and constraints.
2. **Solution design** (CTO + Dev + QA)
   - Approve architecture and define API/data contracts.
3. **Sprint planning** (PM + Team)
   - Commit scope, definition of done, test plan.
4. **Implementation** (Dev)
   - Code + tests + docs in feature branches.
5. **Quality gate** (QA)
   - Execute tests, validate acceptance criteria.
6. **Release prep** (PM + CTO + DevOps)
   - Final checks, release notes, rollback plan.
7. **Cloud deploy** (DevOps)
   - Promote to staging then production through CI/CD.
8. **Hypercare & feedback** (All)
   - Monitor KPIs, fix defects, feed roadmap.

---

## 4) Governance artifacts (must update each change)

- `docs/planning/execution-status.md` (done vs pipeline tracker)
- `docs/planning/project-delivery-plan.md` (master plan)
- `docs/actionable-review-checklist.md` (checklist truth source)
- `release-notes/*.md` (what changed and why)
- `api/openapi.yaml` + `schemas/*.json` (contracts)

Rule: every feature PR should update at least one governance artifact with status impact.

# IRIS System Foundations (Permanent)

This document defines the non-negotiable operating model for IRIS projects.

## 1) Project discipline (mandatory)

Every project must maintain all three artifacts:

1. **Daily release cadence**
   - Ship to a shared environment every working day.
   - If no user-facing change is shipped, release an internal hardening increment.
2. **Release notes**
   - Each release must include what changed, why, impact/risk, rollback notes, and verification status.
3. **Idea board**
   - Every project tracks candidate opportunities in two buckets:
     - **Feature ideas**
     - **Problem statements**

## 2) Full-stack operating scope

Teams are expected to reason end-to-end across:

- Product (problem framing, goals, tradeoffs)
- Marketing (positioning, messaging hooks, impact narrative)
- Design (UX consistency, accessibility, interaction quality)
- Engineering (architecture, implementation, operability)
- QA (validation strategy, acceptance criteria, test evidence)
- Business functions (compliance, finance, legal, sales enablement)

## 3) Structural layers (three-layer model)

All work should explicitly map to these layers:

1. **Process / innovation engineers**
   - Convert problems to candidate solutions.
   - Define experiments, prototypes, and decision criteria.
2. **Functional specialists**
   - Build and integrate implementation per domain expertise.
3. **Output / QC controllers**
   - Validate quality gates, release readiness, and post-release outcomes.

Core execution loop:

`Problem -> Build -> Release -> Feedback`

## 4) Systems ground rules

These apply to all environments and tools:

1. **UI consistency**
   - Common design language, naming, and behavior patterns.
2. **Tooling consistency**
   - Shared linting, formatting, and developer workflow standards.
3. **Database connection discipline**
   - Defined environments, least privilege, audited credentials usage.
4. **Environment promotion order**
   - Local first -> controlled shared environments -> production.

## 5) Enforcement hooks

- Pull requests must reference release-note entry + idea-board item (new or existing).
- Feature work without acceptance criteria is blocked from release.
- Changes that violate local-first promotion are rejected by process.

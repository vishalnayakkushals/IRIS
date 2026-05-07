# IRIS Deployment — Email Drafts
**Date:** 2026-04-30

---

## EMAIL 1 — Simple Mail (Send to all three)

**To:** Engineering Head; Product Head; Developer
**Subject:** IRIS Platform — Deployment Status & Next Steps

---

Hi Team,

Quick update on IRIS before we move to cloud deployment.

The platform is running and stable locally (Windows service on port 8767). The React dashboard, pipeline, reports, and walk-in analytics are all working. A validation bug was also fixed today — the image cross-reference report was showing images from wrong cameras, now corrected.

However, we are **not yet cloud-ready**. Three blockers remain: JWT secret needs to be set for production, database needs to migrate from SQLite to PostgreSQL, and the app has not been tested on a cloud server.

Full details — tech stack, server specs, blockers, file cleanup, and project flow — are in the deployment readiness document at:

```
docs/deployment/deployment-readiness-report-2026-04-30.md
```

BRD is at `docs/business/iris-brd.md` and PRD is at `docs/prd/iris-platform-prd-v1.md` — both are current.

Can we align on a date to complete the cloud deployment checklist? I'd suggest targeting next week.

Thanks,
[Your Name]

---
---

## EMAIL 2 — Detailed Mail (Full context — attach the deployment doc instead of writing in body)

**To:** Engineering Head; Product Head; Developer
**Subject:** IRIS Platform — Deployment Readiness Report, Tech Stack Rationale & Hosting Requirements [Action Required]

---

Dear Team,

I am writing to provide a structured deployment review for the IRIS Retail Intelligence Platform ahead of its cloud go-live. Please treat this as a pre-deployment gate review. A full document has been prepared and is available at:

**`docs/deployment/deployment-readiness-report-2026-04-30.md`**

Below is the executive summary of each area. The document contains the complete detail, rationale, and remediation steps.

---

**1. Project Requirement Documents**

All governing documents are in place and up to date:
- BRD → `docs/business/iris-brd.md`
- PRD → `docs/prd/iris-platform-prd-v1.md`
- Data Flow Architecture → `docs/developer/data-flow-architecture.md`
- Change Ledger (all code changes logged) → `CHANGE_LEDGER.md`

No BRD or PRD gaps have been identified. Both documents are current as of this date.

---

**2. Tech Stack — Summary**

The platform uses three layers:

*Frontend:* React 18 + TypeScript + Vite + TailwindCSS + Tremor (analytics components) + Recharts. Served as a static bundle from the FastAPI server.

*Backend (API):* Python 3.11 + FastAPI + Uvicorn + SQLAlchemy + JWT auth + Celery + Redis. Handles all REST API routes, authentication, report generation, and pipeline orchestration.

*AI/ML Pipeline:* YOLOv8n (person detection, runs on CPU) + OpenAI GPT-4.1-mini vision (semantic customer/staff classification) + OpenCV + Pandas.

*Database:* SQLite (current runtime) → PostgreSQL (production target, migration scripts ready).

**Why Python and not another language?** All AI/ML libraries — YOLO, OpenCV, NumPy, Pandas — exist only in the Python ecosystem. There is no equivalent in Node.js or Go for this workload. FastAPI was chosen over Django/Flask because it is async-native, 3–5x faster for API throughput, and has built-in Pydantic validation. Full rationale for every technology choice is in Section 2 of the deployment document.

---

**3. Hosting Requirements**

IT has confirmed deployment on **AWS EC2**. Updated specification for full production scale (150 stores, 8–10 cameras each):

| Component | AWS Instance | Purpose |
| --- | --- | --- |
| App Server | `c6i.large` (2 vCPU, 4 GB) | FastAPI + React dashboard |
| AI Workers | `c6i.2xlarge` (8 vCPU, 16 GB) | YOLO inference + pipeline |
| Beat Scheduler | `t3.micro` (1 GB) | Cron job scheduler |
| Database | `db.t3.large` RDS PostgreSQL, Multi-AZ | Analytics + session storage |
| Cache / Queue | `cache.t3.medium` ElastiCache Redis | Celery job broker |
| Load Balancer | ALB + ACM certificate | HTTPS termination |

- **Infrastructure cost (1-year reserved):** ~USD 523/month
- **OpenAI GPT API cost (54,000 calls/day):** ~USD 6,500–13,000/month — this is the dominant budget item
- **Storage:** Images are never stored on the server — processed in memory and discarded. DB grows ~2.7 GB/month (text records only); plateaus at ~90 GB with 90-day retention.

Full AWS specification with EBS volumes, networking, security groups, and phased rollout plan:
`docs/deployment/IRIS-Server-Requirement-150-Stores.md`

---

**4. Deployment Readiness — Current Status: NOT CLOUD-READY**

The application is running and functional locally. It is NOT yet deployed to any cloud environment. Status as of 2026-05-07:

✅ Application runs on local Windows service (port 8767)
✅ Docker image builds and runs correctly
✅ All API routes, auth, reports, pipeline, and dashboard functional
✅ Walk-in sessions being generated and stored from live GPT pipeline
✅ GPT analysis live — `gpt_enabled` flag wired per store; Streamlit fully retired (React + FastAPI only)
✅ Static asset bundle cleaned; redundant ports stopped
❌ JWT secret not set for production (using insecure default)
❌ CORS not configured for production domain
❌ No TLS / HTTPS configured
❌ Secrets not moved to AWS Secrets Manager
❌ OpenAI account not yet at Tier 3+ (required for 54,000 calls/day at scale)
❌ No cloud deployment or smoke test done yet

**Action required from Engineering:** Complete the blockers listed in Section 4 of the deployment document before any cloud go-live.

---

**5. Codebase Cleanup — RESOLVED**

Old frontend bundle files and Streamlit source files have been removed as of 2026-05-07. The Streamlit dashboard (`iris_dashboard.py`, 8,410 lines) and all related files have been permanently deleted. The React + FastAPI app is the sole UI. `npm run build` produces a clean bundle with zero errors across 3,884 modules.

---

**6. Project Flow — How IRIS Works**

Camera → Google Drive → IRIS Drive Sync → YOLO Scan → GPT Analysis → Walk-in Session Creation → SQLite DB → FastAPI → React Dashboard → Reports/Downloads

Full step-by-step flow with data table names, file paths, and component names is in Section 6 of the deployment document.

---

**Requested Actions:**

| Action | Owner | Deadline |
| --- | --- | --- |
| Review deployment document and confirm AWS EC2 spec | Product Head | This week |
| Set production `JWT_SECRET` and `CORS_ORIGINS` for cloud domain | Developer | Before cloud deploy |
| Move all secrets to AWS Secrets Manager (API keys, DB creds, JWT) | Developer | Before cloud deploy |
| Provision EC2 instances per spec: `c6i.large` (App), `c6i.2xlarge` × N (Workers), `t3.micro` (Beat), RDS `db.t3.large` Multi-AZ, ElastiCache `cache.t3.medium`, ALB + ACM | Engineering Head | Before cloud deploy |
| Run PostgreSQL migration on RDS (`alembic upgrade head`) | Developer | Before cloud deploy |
| Upgrade OpenAI account to Tier 3+ (54,000 calls/day requires higher rate limits) | Engineering Head | Before cloud deploy |
| Implement staggered Drive sync schedule across 150 stores (avoid burst) | Developer | Before cloud deploy |
| Implement 90-day DB retention job (keeps DB at ~90 GB plateau) | Developer | Phase 2 |
| First cloud smoke test — login, pipeline trigger, report download | Engineering + Developer | After provisioning |

---

Please review the document at `docs/deployment/deployment-readiness-report-2026-04-30.md` and revert with any questions or changes needed to the BRD/PRD.

Thanks and regards,
[Your Name]

---
*Attachment note: Share the file `docs/deployment/deployment-readiness-report-2026-04-30.md` as a PDF or copy-paste its contents when sending externally.*

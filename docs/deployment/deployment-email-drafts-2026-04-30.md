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

For production (6 stores, 2 cameras each):
- **RAM:** 8 GB minimum
- **CPU:** 4 vCPUs
- **Storage:** 100 GB SSD (app server) + managed PostgreSQL storage
- **Supporting services:** Managed Redis (1 GB), managed PostgreSQL (4 GB RAM)
- **Estimated cloud cost:** USD 80–150/month on AWS/GCP/Azure

Minimum viable (smaller scale): 4 GB RAM, 2 vCPUs, 20 GB storage.

---

**4. Deployment Readiness — Current Status: NOT CLOUD-READY**

The application is running and functional locally. It is NOT yet deployed to any cloud environment. Real-time output status:

✅ Application runs on local Windows service (port 8767)
✅ Docker image builds and runs correctly
✅ All API routes, auth, reports, pipeline, and dashboard functional
✅ Walk-in sessions being generated and stored
⚠️ Walk-in data is currently seeded (Apr 8–9 historical data). Live pipeline needs to be triggered on Apr 23+ images to generate real-time output.
❌ JWT secret not set for production (using insecure default)
❌ Database not migrated to PostgreSQL (SQLite cannot handle concurrent cloud writes)
❌ CORS not configured for production domain
❌ No TLS / HTTPS configured
❌ Secrets not moved to cloud secrets manager
❌ No cloud deployment or smoke test done yet

**Action required from Engineering:** Complete the 6 blockers listed in Section 4 of the deployment document before any cloud go-live.

---

**5. Redundant Files — Cleanup Required**

Old frontend bundle files from prior builds accumulate in `backend/app/static/assets/` (multiple versions of the same JS files). These are dead code and must be cleaned before deployment. Also two leftover Python processes are running on ports 8768 and 8769 from development sessions — these should be stopped.

Cleanup commands are provided in Section 5 of the deployment document. This is a 5-minute task for the developer.

---

**6. Project Flow — How IRIS Works**

Camera → Google Drive → IRIS Drive Sync → YOLO Scan → GPT Analysis → Walk-in Session Creation → SQLite DB → FastAPI → React Dashboard → Reports/Downloads

Full step-by-step flow with data table names, file paths, and component names is in Section 6 of the deployment document.

---

**Requested Actions:**

| Action | Owner | Deadline |
|---|---|---|
| Review deployment document and confirm requirements | Product Head | This week |
| Set production JWT_SECRET and update CORS origins | Developer | Before cloud deploy |
| Run PostgreSQL migration (`alembic upgrade head`) | Developer | Before cloud deploy |
| Trigger live GPT pipeline on Apr 23+ images | Developer | This week |
| Cloud server provisioning (8GB RAM, 4 vCPU) | Engineering Head | Before cloud deploy |
| Stop redundant ports 8768 and 8769 | Developer | Immediately |
| Clean old static asset bundles | Developer | Before deployment |
| First cloud smoke test | Engineering + Developer | After provisioning |

---

Please review the document at `docs/deployment/deployment-readiness-report-2026-04-30.md` and revert with any questions or changes needed to the BRD/PRD.

Thanks and regards,
[Your Name]

---
*Attachment note: Share the file `docs/deployment/deployment-readiness-report-2026-04-30.md` as a PDF or copy-paste its contents when sending externally.*

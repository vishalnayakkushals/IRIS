# Release Notes - 2026-04-26

## Feature Name
- [IRIS Frontend Architecture Migration (React + FastAPI)]

## What’s New
- Successfully replaced legacy Streamlit Python UI with a statically-served React framework (Vite, Tailwind, Shadcn, Tremor).
- Refactored five main dashboards natively: Overview, Store Detail, Scheduler, Quality Assurance, and Store Admin.
- Introduced `backend/app/main.py` using Uvicorn & FastAPI to serve application routes independently.
- Setup explicitly for AWS EC2 Deployment CI/CD (local dev -> push -> remote git pull).

## Impact
- Improves performance significantly by removing WebSocket bottlenecks inherently tied to Streamlit.
- Reduces errors related to concurrent data fetching because the state is now offloaded statically to the client (React).
- Supports business objective: Enterprise-grade web security and speed scaling across 150 target stores.

## Metrics / Monitoring
- KPI being tracked: Sub-500ms API response loads for detailed UI components.
- Expected improvement: Zero SQLite locking crashes at scale during heavy YOLO ingestion tests.
- Dashboard / Tool used: React UI on `http://localhost:8766/overview`
- Monitoring owner: Development Team

## Availability
- Web (Browser-based Native Desktop Application)
- Release version (if applicable): v1.1.0-React-Migration

## Risks / Known Issues
- Moving credentials fully to React means strict CORS bindings in `main.py`.
- Uvicorn must boot before API endpoints engage.

## Rollback Plan
- The legacy Streamlit code is strictly untouched `src/run_dashboard.py`. At any point, the Streamlit server can be brought back online until absolute parity confidence is achieved.

## Validation
- Successfully ran `npm run build` and loaded static assets securely.
- Mock YOLO Ingestion run: `scripts/mock_ingest.py` effectively scaled 3 concurrent times under heavy simulated loads without server timeout.

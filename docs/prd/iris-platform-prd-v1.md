# IRIS Platform PRD (Senior PM Grade)

## 1. Document Header
- **Feature Name:** IRIS Retail Intelligence Platform Runtime
- **Owner:** Product (IRIS)
- **Stakeholders:** Retail Operations, IT, Store Admins, Engineering, QA, Management
- **Target Release Date:** Rolling phased releases
- **Version:** v1.0

## 2. Problem Statement
Retail operations need consistent, privacy-safe, near-real-time store intelligence across 100+ stores and multi-camera environments. Existing manual review is not scalable and is weak in auditability and role-based governance.

## 3. Product Goals
1. Deliver store-level analytics (footfall, dwell, hotspots, LOS indicators) from low-frame snapshots.
2. Enable production admin controls for stores, users, roles, camera configs, and license governance.
3. Keep operating cost low using compact storage and lightweight runtime architecture.

## 4. Scope
### In Scope
- Snapshot analytics runtime + export pipeline
- Auth/RBAC + custom roles
- License workflow + audit timeline
- Alert routing registry
- Store master + staff image management
- Multi-camera baseline stitching support

### Out of Scope (this PRD version)
- POS live adapters in production
- Fully managed external messaging providers (Slack/WhatsApp live dispatch)

## 5. User Stories
- As an **Admin**, I can create stores/users/roles and manage permissions from UI.
- As a **Store User**, I can manage only my store’s configuration and staff assets.
- As a **Management Viewer**, I can review analytics with read-only access.
- As **Compliance/Operations**, I can track license state changes with complete audit history.

## 6. Functional Requirements
- FR-001: Store onboarding and update from UI must persist to DB.
- FR-002: User creation, password set/reset, role assignment, and permission matrix must persist to DB.
- FR-003: License workflow must support guarded transitions and audit logs.
- FR-004: Alert routes must support channel registration and route-event logging.
- FR-005: Dashboard must provide QA timeline and per-store camera-aware views.
- FR-006: Staff image upload must support variable staff counts per store and optimized storage.

## 7. Non-Functional Requirements
- Cost-efficient storage and compute for 100+ stores.
- Low-latency dashboard navigation for recent exports.
- Secure password hashing for all user credentials.
- Auditability for operationally sensitive workflows.

## 8. Edge Cases
- Store with 0 camera configs should still analyze files using discovered camera IDs.
- Billing/backroom cameras should be excluded from behavior analytics but preserved in raw frame records.
- Duplicate store email/user email should be rejected with explicit message.
- Invalid license transitions must be blocked and logged.

## 9. Dependencies
- Python runtime + Streamlit
- SQLite persistence
- Optional Google Drive sync + optional detector model runtime
- Future: POS APIs and external messaging APIs

## 10. Analytics / Tracking
- Store-level KPIs: footfall, estimated visits, dwell, bounce, hotspots, LOS alerts
- Admin KPIs: active users, role coverage, license throughput, route event counts

## 11. Release Notes (Excerpt-ready)
- Added runtime auth/RBAC and UI controls for users/roles/permissions.
- Added license workflow runtime and audit timeline.
- Added alert route registry and event logs.
- Added QA timeline and multi-camera baseline stitching support.
- Added store-master import and DB persistence for scalable operations.

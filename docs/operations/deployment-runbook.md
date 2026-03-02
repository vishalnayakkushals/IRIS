# IRIS Deployment Runbook (Container + Cloud)

## Local container run

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

UI: `http://localhost:8765`

## Admin login (first run)
Default seeded admin emails:
- `vishal.nayak@kushals.com`
- `mayur.pathak@kushals.com`

Default password created by seed logic:
- `ChangeMe123!`

Immediately change using **Auth/RBAC** tab.

## Cloud deployment (recommended low-cost)

### Option A: Render/Fly/Railway
1. Connect GitHub repo.
2. Build command: `docker build -t iris .`
3. Start command: Docker default CMD.
4. Mount persistent volume at `/app/data`.
5. Expose port `8765`.

### Option B: VM (AWS Lightsail / GCP e2-small)
1. Install Docker + Compose.
2. Clone repo.
3. `docker compose -f deploy/docker-compose.yml up --build -d`
4. Add reverse proxy (Nginx + TLS).

## Activity logging and bug loop
- UI actions are logged in DB table `user_activity`.
- Review logs in dashboard tab **Activity Logs**.
- Export logs from DB for bug triage and continuous fixes.

## Two-way bug fix loop
1. User performs actions in UI.
2. Activity logs capture actor + action + timestamp.
3. Ops/CTO module reads logs and identifies failure patterns.
4. Patches are deployed via CI/CD.

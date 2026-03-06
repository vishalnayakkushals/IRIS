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


## Troubleshooting: "docker is not recognized" (Windows)

If you see:

```text
'docker' is not recognized as an internal or external command
```

It means Docker is not installed (or Docker Desktop is not running / PATH not loaded).

### Fix steps (Windows)
1. Install **Docker Desktop for Windows** (official installer).
2. Restart your machine after install (important for PATH updates).
3. Start Docker Desktop and wait until it shows **Engine running**.
4. Open a **new** terminal and run:
   ```bash
   docker --version
   docker compose version
   ```
5. Then run IRIS:
   ```bash
   docker compose -f deploy/docker-compose.yml up --build -d
   ```

### If Docker is not available yet (temporary local run)
You can still run IRIS without Docker:

```bash
python -m pip install -r requirements.txt
streamlit run src/run_dashboard.py --server.port 8765
```

Open: `http://localhost:8765`

## Troubleshooting: `COPY requirements.txt .` not found during Docker build

If you see:

```text
COPY requirements.txt .
... "/requirements.txt": not found
```

Cause: Docker build context is incorrectly set to `deploy/` instead of repo root.

Fix in this repo (`deploy/docker-compose.yml`):
- `build.context: ..`
- `build.dockerfile: deploy/Dockerfile`

Verify and rerun from project root:

```bash
git pull
cat deploy/docker-compose.yml
docker compose -f deploy/docker-compose.yml up --build -d
```


## Windows path sanity check (common mistake)

Run Docker commands from the repo root (the folder that contains `.git`, `requirements.txt`, and `deploy/`).

```powershell
cd "C:\Users\<you>\Desktop\GitHub\IRIS"
git pull
Get-Content deploy\docker-compose.yml
docker compose -f deploy/docker-compose.yml up --build -d
```

If `git pull` says `not a git repository`, you are one folder too high; run `cd IRIS` first.


## Troubleshooting: `ImportError: attempted relative import with no known parent package`

If the container starts but `http://localhost:8765` shows:

```text
ImportError: attempted relative import with no known parent package
```

Use latest code where dashboard imports are package-based (`from iris...`) and Docker sets:
- `PYTHONPATH=/app/src`

Then rebuild and restart:

```bash
docker compose -f deploy/docker-compose.yml build --no-cache
docker compose -f deploy/docker-compose.yml up -d
```


## Troubleshooting: dependencies re-download on every build

If each build re-downloads all Python packages, common causes are:

- using `docker compose ... build --no-cache`
- changed `requirements.txt`
- first-time install of heavy ML deps (`ultralytics` / `torch`)

Recommended day-to-day commands:

```bash
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

Use `--no-cache` only when you intentionally need a clean rebuild.

## Troubleshooting: container did not restart with latest code

If `docker compose build` + `docker compose up -d` appears to keep old behavior, run a hard refresh:

```bash
git pull origin main
docker compose -f deploy/docker-compose.yml down
docker image rm deploy-iris:latest || true
docker compose -f deploy/docker-compose.yml up --build --force-recreate -d
docker compose -f deploy/docker-compose.yml logs -f iris
```

This forces container recreation from a newly built image.

For the specific import issue, if logs show:

```text
from .iris_analysis import ...
```

then the container is from older code. Latest dashboard code uses:
- `from iris.iris_analysis ...`
- `from iris.store_registry ...`


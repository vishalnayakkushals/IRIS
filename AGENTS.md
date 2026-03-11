# IRIS Agent Workflow

## Source of Truth
- Primary repository path: `C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS`
- GitHub repository: `https://github.com/vishalnayakkushals/IRIS`
- Default branch: `main`

## Required Working Style
- Apply code changes locally in the canonical path.
- Validate with runnable commands (especially Docker for deployment issues).
- Commit only intended files with clear commit messages.
- Push each completed change set to `origin/main` so local and GitHub remain aligned.

## Standard Local Deploy Commands
```powershell
cd "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
git pull origin main
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

## Docker Build Mode
- Default: lightweight build (`IRIS_ENABLE_YOLO=0`) for faster startup.
- Full YOLO build when needed:
```powershell
$env:IRIS_ENABLE_YOLO="1"
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

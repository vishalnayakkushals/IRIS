# Deploy frontend: clean stale chunks, build, copy.
# Run from repo root: .\scripts\deploy_frontend.ps1
# This must be run after every frontend change to avoid stale chunk crashes.

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$static = Join-Path $repo "backend\app\static"
$dist   = Join-Path $repo "frontend\dist"

Write-Host "==> Cleaning static assets..." -ForegroundColor Cyan
if (Test-Path "$static\assets") {
    Remove-Item -Recurse -Force "$static\assets"
}
if (Test-Path "$static\index.html") {
    Remove-Item -Force "$static\index.html"
}

Write-Host "==> Building frontend..." -ForegroundColor Cyan
Push-Location (Join-Path $repo "frontend")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Pop-Location
}

Write-Host "==> Copying build to static/..." -ForegroundColor Cyan
Copy-Item -Recurse -Force "$dist\*" "$static\"

Write-Host "==> Done. Hard-refresh the browser (Ctrl+Shift+R)." -ForegroundColor Green

# IRIS API Server - Start Script
# Run this from the IRIS folder: .\start_iris.ps1
# Or double-click it in Explorer

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  IRIS - Starting API Server on :8767  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$pythonExe = "C:\Python312\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "ERROR: Approved Python not found at $pythonExe" -ForegroundColor Red
    Write-Host "Install or restore the approved system Python before starting IRIS." -ForegroundColor Red
    exit 1
}

# ── Kill anything on port 8767 ────────────────────────────────────────────────
Write-Host "Clearing port 8767..." -ForegroundColor Yellow
$listening = Get-NetTCPConnection -LocalPort 8767 -ErrorAction SilentlyContinue |
             Where-Object {$_.State -in "Listen","Bound"} |
             Select-Object -ExpandProperty OwningProcess -Unique

foreach ($p in $listening) {
    $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "  Stopped: $($proc.ProcessName) [PID $p]" -ForegroundColor DarkGray
    }
}

# Also stop any lingering Python/uvicorn for this project
Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*uvicorn*" -or
    $_.CommandLine -like "*start_api_server*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "  Stopped uvicorn [PID $($_.ProcessId)]" -ForegroundColor DarkGray
}

Start-Sleep -Seconds 3

# ── Load .env.local ───────────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot ".env.local"
if (Test-Path $envFile) {
    Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match '^\s*[A-Z_]+=.+' } | ForEach-Object {
        $parts = $_ -split '=', 2
        $k = $parts[0].Trim(); $v = $parts[1].Trim()
        [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
    Write-Host "Loaded .env.local" -ForegroundColor Green
} else {
    Write-Host "WARNING: .env.local not found" -ForegroundColor Red
}

$approvedPostgres = "postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db"
if (-not $env:POSTGRES_URL) {
    Write-Host "ERROR: POSTGRES_URL is missing from .env.local" -ForegroundColor Red
    exit 1
}
if ($env:POSTGRES_URL -ne $approvedPostgres) {
    Write-Host "ERROR: POSTGRES_URL must be exactly:" -ForegroundColor Red
    Write-Host "  $approvedPostgres" -ForegroundColor Yellow
    Write-Host "Current value:" -ForegroundColor Red
    Write-Host "  $($env:POSTGRES_URL)" -ForegroundColor Yellow
    exit 1
}

$env:PYTHONPATH = "$PSScriptRoot;$PSScriptRoot\src"

# ── Start uvicorn ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Starting server..." -ForegroundColor Green
Write-Host "  URL:  http://localhost:8767" -ForegroundColor White
Write-Host "  Python: $pythonExe" -ForegroundColor White
Write-Host "  Login: vishal.nayak@kushals.com / ChangeMe123!" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $pythonExe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8767 --reload

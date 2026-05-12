# IRIS API Server - Start Script
# Run this from the IRIS folder: .\start_iris.ps1
# Or double-click it in Explorer

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  IRIS - Starting API Server on :8767  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$approvedPython = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$pythonExe = $approvedPython
if (-not (Test-Path $pythonExe)) {
    Write-Host "ERROR: Approved Python not found at $pythonExe" -ForegroundColor Red
    Write-Host "Install Python 3.12 in the standard local path before starting IRIS." -ForegroundColor Red
    exit 1
}

$proxyPidFile = Join-Path $PSScriptRoot "deploy\no_docker\runtime_logs\pids\localhost_ipv6_proxy.pid"
if (Test-Path $proxyPidFile) {
    $oldProxyPid = Get-Content $proxyPidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($oldProxyPid -match '^\d+$') {
        Stop-Process -Id ([int]$oldProxyPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $proxyPidFile -Force -ErrorAction SilentlyContinue
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
    Write-Host "ERROR: .env.local not found" -ForegroundColor Red
    exit 1
}

$approvedPostgres = "postgresql+asyncpg://iris_user:iris_password@127.0.0.1/iris_db"
$localhostPostgres = "postgresql+asyncpg://iris_user:iris_password@localhost/iris_db"
if (-not $env:POSTGRES_URL) {
    Write-Host "ERROR: POSTGRES_URL is missing from .env.local" -ForegroundColor Red
    exit 1
}
if ($env:POSTGRES_URL -eq $localhostPostgres) {
    $env:POSTGRES_URL = $approvedPostgres
    Write-Host "Normalized POSTGRES_URL from localhost to 127.0.0.1 for runtime consistency." -ForegroundColor Green
}
if ($env:POSTGRES_SYNC_URL -eq "postgresql+psycopg2://iris_user:iris_password@localhost/iris_db") {
    $env:POSTGRES_SYNC_URL = "postgresql+psycopg2://iris_user:iris_password@127.0.0.1/iris_db"
}
if ($env:POSTGRES_URL -ne $approvedPostgres) {
    Write-Host "ERROR: POSTGRES_URL must be exactly:" -ForegroundColor Red
    Write-Host "  $approvedPostgres" -ForegroundColor Yellow
    Write-Host "Allowed local alias also supported:" -ForegroundColor Red
    Write-Host "  $localhostPostgres" -ForegroundColor Yellow
    Write-Host "Current value:" -ForegroundColor Red
    Write-Host "  $($env:POSTGRES_URL)" -ForegroundColor Yellow
    exit 1
}
if (-not $env:JWT_SECRET) {
    Write-Host "ERROR: JWT_SECRET is missing from .env.local" -ForegroundColor Red
    exit 1
}
if ($env:API_PORT -and $env:API_PORT -ne "8767") {
    Write-Host "ERROR: API_PORT must stay 8767. Current value: $($env:API_PORT)" -ForegroundColor Red
    exit 1
}

$env:PYTHONPATH = "$PSScriptRoot;$PSScriptRoot\src"
$env:API_HOST = "0.0.0.0"
$env:API_PORT = "8767"
$env:API_RELOAD = "0"

$proxyScript = Join-Path $PSScriptRoot "scripts\localhost_ipv6_proxy.py"
$proxyStdout = Join-Path $PSScriptRoot "deploy\no_docker\runtime_logs\localhost_ipv6_proxy.out.log"
$proxyStderr = Join-Path $PSScriptRoot "deploy\no_docker\runtime_logs\localhost_ipv6_proxy.err.log"
if (Test-Path $proxyScript) {
    New-Item -ItemType Directory -Force -Path (Split-Path $proxyPidFile) | Out-Null
    Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $proxyScript, "8767" `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $proxyStdout `
        -RedirectStandardError $proxyStderr `
        -WindowStyle Hidden | Out-Null
    Write-Host "Started localhost IPv6 proxy on [::1]:8767" -ForegroundColor Green
}

# ── Start supported API launcher ──────────────────────────────────────────────
Write-Host ""
Write-Host "Starting server..." -ForegroundColor Green
Write-Host "  URL:  http://localhost:8767" -ForegroundColor White
Write-Host "  Python: $pythonExe" -ForegroundColor White
Write-Host "  Login: vishal.nayak@kushals.com / ChangeMe123!" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray
Write-Host ""

& $pythonExe "$PSScriptRoot\scripts\start_api_server.py"

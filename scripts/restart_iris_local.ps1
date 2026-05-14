param(
  [int]$Port = 8767,
  [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$PythonExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}
$PythonwExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $PythonwExe)) {
  $PythonwExe = $PythonExe
}

$RuntimeLogDir = Join-Path $RepoRoot "deploy\no_docker\runtime_logs"
$PidDir = Join-Path $RuntimeLogDir "pids"
New-Item -ItemType Directory -Force -Path $RuntimeLogDir, $PidDir | Out-Null

function Stop-IrisPortListeners {
  param([int]$TargetPort)

  Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*run_iris_api_$TargetPort.cmd*" -or
    $_.CommandLine -like "*run_iris_proxy_$TargetPort.cmd*" -or
    $_.CommandLine -like "*run_api_server_detached.py*" -or
    $_.CommandLine -like "*api_live_uvicorn.log*" -or
    $_.CommandLine -like "*localhost_ipv6_proxy.log*"
  } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

  $listeners = Get-NetTCPConnection -LocalPort $TargetPort -ErrorAction SilentlyContinue |
    Where-Object { $_.State -in @("Listen", "Bound", "Established") } |
    Select-Object -ExpandProperty OwningProcess -Unique

  foreach ($ownerPid in $listeners) {
    if (-not $ownerPid -or $ownerPid -eq 0) { continue }
    $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
      Write-Host "Stopped $($proc.ProcessName) on port $TargetPort [PID $ownerPid]" -ForegroundColor DarkGray
    }
  }
}

function Import-EnvLocal {
  $envFile = Join-Path $RepoRoot ".env.local"
  if (-not (Test-Path $envFile)) {
    throw ".env.local not found at $envFile"
  }

  Get-Content $envFile -Encoding UTF8 |
    Where-Object { $_ -match '^\s*[A-Z_][A-Z0-9_]*=.+' } |
    ForEach-Object {
      $parts = $_ -split "=", 2
      [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
    }
}

function Wait-IrisHealth {
  param([int]$TargetPort)

  $healthUrl = "http://127.0.0.1:$TargetPort/api/health"
  for ($i = 1; $i -le 30; $i++) {
    try {
      $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -eq 200) {
        return $true
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $false
}

Write-Host "Restarting IRIS local server on port $Port..." -ForegroundColor Cyan
Stop-IrisPortListeners -TargetPort $Port
Start-Sleep -Seconds 2

Import-EnvLocal
$env:PYTHONPATH = "$RepoRoot;$RepoRoot\src"
$env:API_HOST = "0.0.0.0"
$env:API_PORT = [string]$Port
$env:API_RELOAD = "0"

$apiLog = Join-Path $RuntimeLogDir "api_live_uvicorn.log"
Remove-Item $apiLog -Force -ErrorAction SilentlyContinue
$apiLauncher = Join-Path $RepoRoot "scripts\run_api_server_detached.py"
Start-Process -FilePath $PythonwExe -ArgumentList @($apiLauncher) -WorkingDirectory $RepoRoot -WindowStyle Hidden | Out-Null

if (-not (Wait-IrisHealth -TargetPort $Port)) {
  Write-Host "IRIS API did not become healthy. Last API log lines:" -ForegroundColor Red
  if (Test-Path $apiLog) {
    Get-Content $apiLog -Tail 80
  }
  throw "Health check failed: http://127.0.0.1:$Port/api/health"
}

$proxyScript = Join-Path $RepoRoot "scripts\localhost_ipv6_proxy.py"
if (Test-Path $proxyScript) {
  Start-Process -FilePath $PythonwExe -ArgumentList @($proxyScript, [string]$Port) -WorkingDirectory $RepoRoot -WindowStyle Hidden | Out-Null
  Start-Sleep -Seconds 1
}

$apiPid = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalAddress -eq "0.0.0.0" -and $_.State -eq "Listen" } |
  Select-Object -First 1 -ExpandProperty OwningProcess
$proxyPid = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalAddress -eq "::1" -and $_.State -eq "Listen" } |
  Select-Object -First 1 -ExpandProperty OwningProcess

if ($apiPid) { Set-Content -Path (Join-Path $PidDir "web.pid") -Value $apiPid }
if ($proxyPid) { Set-Content -Path (Join-Path $PidDir "localhost_ipv6_proxy.pid") -Value $proxyPid }

Write-Host "IRIS is healthy." -ForegroundColor Green
Write-Host "Local URL: http://localhost:$Port/login" -ForegroundColor White
Write-Host "API health: http://127.0.0.1:$Port/api/health" -ForegroundColor White
Write-Host "API PID: $apiPid | IPv6 proxy PID: $proxyPid" -ForegroundColor DarkGray

if ($OpenBrowser) {
  Start-Process "http://localhost:$Port/login"
}

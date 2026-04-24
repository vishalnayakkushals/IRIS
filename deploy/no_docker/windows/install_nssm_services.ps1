$ErrorActionPreference = "Stop"

param(
    [string]$RepoRoot = "C:\IRIS",
    [string]$PythonExe = "C:\IRIS\.venv\Scripts\python.exe",
    [string]$EnvFile = "C:\IRIS\shared\iris.env",
    [string]$NssmExe = "C:\nssm\win64\nssm.exe"
)

if (-not (Test-Path $NssmExe)) {
    throw "NSSM not found: $NssmExe"
}

function Install-IrisService {
    param(
        [string]$Name,
        [string]$ScriptPath
    )

    & $NssmExe install $Name $PythonExe $ScriptPath
    & $NssmExe set $Name AppDirectory $RepoRoot
    & $NssmExe set $Name AppEnvironmentExtra "IRIS_ENV_FILE=$EnvFile"
    & $NssmExe set $Name Start SERVICE_AUTO_START
    & $NssmExe set $Name AppStdout "$RepoRoot\\logs\\$Name.out.log"
    & $NssmExe set $Name AppStderr "$RepoRoot\\logs\\$Name.err.log"
}

New-Item -ItemType Directory -Force -Path "$RepoRoot\\logs" | Out-Null

Install-IrisService -Name "IRIS-Web" -ScriptPath "$RepoRoot\\scripts\\start_web_app.py"
Install-IrisService -Name "IRIS-Scheduler" -ScriptPath "$RepoRoot\\scripts\\start_scheduler_worker_service.py"
Install-IrisService -Name "IRIS-Onfly-Scheduler" -ScriptPath "$RepoRoot\\scripts\\start_onfly_scheduler_service.py"

Write-Host "Installed IRIS NSSM services."

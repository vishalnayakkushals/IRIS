param(
    [string]$RepoPath = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS",
    [ValidateSet("restart", "rebuild")]
    [string]$Mode = "rebuild",
    [switch]$SkipPull,
    [int]$TimeoutSec = 180,
    [int]$LogTail = 80
)

$ErrorActionPreference = "Stop"
$ComposeFile = "deploy/docker-compose.yml"
$UiService = "iris"
$SchedulerService = "iris-scheduler"
$UiContainer = "deploy-iris-1"
$SchedulerContainer = "deploy-iris-scheduler-1"

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $Action
}

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (exit code: $LASTEXITCODE)"
    }
}

Invoke-Step -Name "Set Repo" -Action {
    Set-Location $RepoPath
    Write-Host "Repo: $(Get-Location)"
}

if (-not $SkipPull) {
    Invoke-Step -Name "Git Pull" -Action {
        git pull origin main
        Assert-LastExitCode -Message "git pull failed"
    }
}

if ($Mode -eq "rebuild") {
    Invoke-Step -Name "Docker Build (iris)" -Action {
        docker compose -f $ComposeFile build $UiService
        Assert-LastExitCode -Message "docker build failed"
    }

    Invoke-Step -Name "Docker Recreate (iris + scheduler)" -Action {
        docker compose -f $ComposeFile up -d --no-deps --force-recreate $UiService $SchedulerService
        Assert-LastExitCode -Message "docker up failed"
    }
} else {
    Invoke-Step -Name "Docker Restart (iris + scheduler)" -Action {
        docker compose -f $ComposeFile restart $UiService $SchedulerService
        Assert-LastExitCode -Message "docker restart failed"
    }
}

Invoke-Step -Name "Wait For Containers + URL" -Action {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $isReady = $false
    do {
        $uiState = ""
        $schedulerState = ""
        try {
            $uiState = (docker inspect -f "{{.State.Status}}" $UiContainer 2>$null).Trim()
        } catch {
            $uiState = ""
        }
        try {
            $schedulerState = (docker inspect -f "{{.State.Status}}" $SchedulerContainer 2>$null).Trim()
        } catch {
            $schedulerState = ""
        }
        if ($uiState -eq "running" -and $schedulerState -eq "running") {
            try {
                $resp = Invoke-WebRequest "http://localhost:8765" -UseBasicParsing -TimeoutSec 5
                if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                    $isReady = $true
                    break
                }
            } catch {
                # still warming up
            }
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if (-not $isReady) {
        throw "Container did not become ready within $TimeoutSec seconds."
    }
    Write-Host "Services are ready on http://localhost:8765" -ForegroundColor Green
}

Invoke-Step -Name "Container Status" -Action {
    docker compose -f $ComposeFile ps
}

Invoke-Step -Name "Recent Logs" -Action {
    $sinceSec = [Math]::Max(60, [Math]::Min($TimeoutSec + 60, 900))
    docker compose -f $ComposeFile logs --since="${sinceSec}s" --tail=$LogTail $UiService $SchedulerService
}

Invoke-Step -Name "Quick Error Scan" -Action {
    $sinceSec = [Math]::Max(60, [Math]::Min($TimeoutSec + 60, 900))
    $logText = docker compose -f $ComposeFile logs --since="${sinceSec}s" --tail=$LogTail $UiService $SchedulerService 2>&1 | Out-String
    $fatalPatterns = @(
        "Traceback",
        "ModuleNotFoundError",
        "ImportError",
        "can't open file",
        "No such file or directory",
        "streamlit.errors"
    )
    $errorMarkers = @()
    foreach ($pattern in $fatalPatterns) {
        if ($logText -match [regex]::Escape($pattern)) {
            $errorMarkers += $pattern
        }
    }
    if ($errorMarkers.Count -gt 0) {
        throw "Potential runtime error markers found in logs: $($errorMarkers -join ', ')"
    }
    Write-Host "No fatal runtime markers found in recent logs." -ForegroundColor Green
}

Invoke-Step -Name "SQLite Probe" -Action {
    docker compose -f $ComposeFile exec $UiService python -c "import sqlite3; p='/app/data/store_registry.db'; conn=sqlite3.connect(p); cur=conn.cursor(); cur.execute('PRAGMA quick_check;'); print('quick_check:', cur.fetchone()[0]); conn.close()"
    Assert-LastExitCode -Message "SQLite probe failed"
}

Write-Host ""
Write-Host "Done. Cursor returned to prompt. No blocking loop active." -ForegroundColor Green

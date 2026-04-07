param(
    [string]$ComposeFile = "deploy/docker-compose.yml",
    [switch]$KeepApi
)

$ErrorActionPreference = "Stop"

Write-Host "[IRIS] Applying lightweight runtime mode..."

$baseServices = @("iris", "iris-onfly-scheduler", "redis")
$stopServices = @(
    "iris-scheduler",
    "iris-gpt-scheduler",
    "iris-yolo-relevance-scheduler",
    "iris-celery-worker",
    "iris-celery-beat"
)
if (-not $KeepApi) {
    $stopServices += "iris-api"
} else {
    $baseServices += "iris-api"
}

Write-Host ("[IRIS] Keeping services: " + ($baseServices -join ", "))
Write-Host ("[IRIS] Stopping optional services: " + ($stopServices -join ", "))

docker compose -f $ComposeFile stop @stopServices | Out-Null
docker compose -f $ComposeFile up -d @baseServices | Out-Null

Write-Host ""
Write-Host "[IRIS] Current containers:"
docker compose -f $ComposeFile ps
Write-Host ""
Write-Host "[IRIS] Current resource usage:"
docker stats --no-stream

Write-Host ""
Write-Host "[IRIS] Lightweight runtime mode is active."

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoPath = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
$openAiKeyPath = if ([string]::IsNullOrWhiteSpace($env:IRIS_OPENAI_KEY_FILE)) {
    "C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\OPEN AI API Key.txt"
} else {
    $env:IRIS_OPENAI_KEY_FILE
}
$googleKeyPath = if ([string]::IsNullOrWhiteSpace($env:IRIS_GOOGLE_KEY_FILE)) {
    "C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\Google Cloud Key.txt"
} else {
    $env:IRIS_GOOGLE_KEY_FILE
}

function Read-SecretFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Name key file not found: $Path"
    }
    $value = (Get-Content -LiteralPath $Path -Raw -ErrorAction Stop).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name key file is empty: $Path"
    }
    return $value
}

try {
    if (-not (Test-Path -LiteralPath $repoPath)) {
        throw "Repo path not found: $repoPath"
    }

    $env:OPENAI_API_KEY = Read-SecretFile -Path $openAiKeyPath -Name "OPENAI"
    $env:GOOGLE_API_KEY = Read-SecretFile -Path $googleKeyPath -Name "GOOGLE"
    $env:OPENAI_VISION_MODEL = "gpt-4.1-mini"

    Set-Location -LiteralPath $repoPath
    Write-Host "[IRIS] Running GPT validation with secure key-file loading..."
    & ".\run_iris.bat" "gpt-test-validation-now"
    if ($LASTEXITCODE -ne 0) {
        throw "run_iris.bat gpt-test-validation-now failed with exit code $LASTEXITCODE"
    }
    Write-Host "[IRIS] Validation run completed."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:GOOGLE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_VISION_MODEL -ErrorAction SilentlyContinue
}

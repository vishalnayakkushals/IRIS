# IRIS API - Windows Service Installer
# Run as Administrator once:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\install_service.ps1

$nssm    = "C:\Users\Kushals.DESKTOP-D51MT8S\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$python  = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS\.venv\Scripts\python.exe"
$script  = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS\scripts\start_api_server.py"
$workdir = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
$logfile = "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS\data\iris_server.log"
$svc     = "IRIS-API"

# Remove old service if exists
if (Get-Service -Name $svc -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing $svc..."
    & $nssm stop $svc confirm
    & $nssm remove $svc confirm
    Start-Sleep 3
}

Write-Host "Registering $svc as Windows Service..."

& $nssm install  $svc $python $script
& $nssm set      $svc AppDirectory   $workdir
& $nssm set      $svc AppStdout      $logfile
& $nssm set      $svc AppStderr      $logfile
& $nssm set      $svc AppRotateFiles 1
& $nssm set      $svc AppRotateBytes 5242880
& $nssm set      $svc AppRestartDelay 10000
& $nssm set      $svc Start          SERVICE_AUTO_START
& $nssm set      $svc DisplayName    "IRIS API Server"
& $nssm set      $svc Description    "IRIS FastAPI backend - restarts on crash, starts on boot"

# Run as current user so it can access .env.local and .venv
$username = "$env:COMPUTERNAME\$env:USERNAME"
$password = Read-Host -AsSecureString "Enter Windows password for $username"
$plain    = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
& $nssm set $svc ObjectName $username $plain
Remove-Variable plain

Write-Host "Starting service..."
& $nssm start $svc
Start-Sleep 5

$status = (Get-Service -Name $svc -ErrorAction SilentlyContinue).Status
if ($status -eq "Running") {
    Write-Host ""
    Write-Host "SUCCESS: $svc is running!" -ForegroundColor Green
    Write-Host "  Auto-starts on boot, auto-restarts on crash"
    Write-Host "  URL: http://localhost:8767"
    Write-Host "  Log: $logfile"
} else {
    Write-Host "Status: $status" -ForegroundColor Red
    Write-Host "Check log: $logfile"
}

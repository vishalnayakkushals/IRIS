$ErrorActionPreference = "Stop"

param(
  [int]$Port = 8767,
  [switch]$SetPrivateProfile
)

function Test-IsAdmin {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Write-Error "Run this script from an elevated PowerShell window (Run as Administrator)."
}

$ruleName = "IRIS FastAPI $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
  New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $Port `
    -Profile Any | Out-Null
  Write-Host "Created inbound firewall rule '$ruleName' for TCP $Port." -ForegroundColor Green
} else {
  Write-Host "Firewall rule '$ruleName' already exists." -ForegroundColor Yellow
}

if ($SetPrivateProfile) {
  Get-NetConnectionProfile | ForEach-Object {
    if ($_.NetworkCategory -ne "Private") {
      Set-NetConnectionProfile -InterfaceIndex $_.InterfaceIndex -NetworkCategory Private
      Write-Host "Set network '$($_.Name)' to Private." -ForegroundColor Green
    }
  }
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' -or $_.IPAddress -like '172.16.*' -or $_.IPAddress -like '172.17.*' -or $_.IPAddress -like '172.18.*' -or $_.IPAddress -like '172.19.*' -or $_.IPAddress -like '172.2?.*' -or $_.IPAddress -like '172.30.*' -or $_.IPAddress -like '172.31.*' } |
  Select-Object -First 1 -ExpandProperty IPAddress)

if ($ip) {
  Write-Host "IRIS should now be reachable on: http://$ip:$Port/" -ForegroundColor Cyan
} else {
  Write-Host "Firewall updated. Check your LAN IP with ipconfig, then open http://<your-ip>:$Port/" -ForegroundColor Cyan
}

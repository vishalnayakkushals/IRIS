$ErrorActionPreference = "Stop"

$Port = 8767
$SetPrivateProfile = $false

for ($i = 0; $i -lt $args.Count; $i++) {
  $arg = [string]$args[$i]
  switch ($arg.ToLowerInvariant()) {
    "-port" {
      if ($i + 1 -ge $args.Count) {
        throw "Missing value for -Port."
      }

      $nextValue = [string]$args[$i + 1]
      $parsedPort = 0
      if (-not [int]::TryParse($nextValue, [ref]$parsedPort)) {
        throw "Invalid port value '$nextValue'."
      }

      $Port = $parsedPort
      $i++
    }
    "-setprivateprofile" {
      $SetPrivateProfile = $true
    }
    default {
      throw "Unknown argument '$arg'. Supported arguments: -Port <number>, -SetPrivateProfile"
    }
  }
}

function Test-IsAdmin {
  $current = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($current)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Write-Host "Requesting Administrator approval to update Windows Firewall..." -ForegroundColor Yellow

  $quotedScriptPath = '"' + $PSCommandPath + '"'
  $relaunchArgs = @(
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $quotedScriptPath,
    "-Port",
    $Port.ToString()
  )

  if ($SetPrivateProfile) {
    $relaunchArgs += "-SetPrivateProfile"
  }

  Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $relaunchArgs
  exit 0
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

$defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" |
  Sort-Object RouteMetric, InterfaceMetric |
  Select-Object -First 1

$ip = $null
if ($defaultRoute) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $defaultRoute.InterfaceIndex |
    Where-Object { $_.IPAddress -ne "127.0.0.1" } |
    Select-Object -First 1 -ExpandProperty IPAddress
}

if (-not $ip) {
  $ip = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
      $_.IPAddress -like '192.168.*' -or
      $_.IPAddress -like '10.*' -or
      $_.IPAddress -like '172.16.*' -or
      $_.IPAddress -like '172.17.*' -or
      $_.IPAddress -like '172.18.*' -or
      $_.IPAddress -like '172.19.*' -or
      $_.IPAddress -like '172.2?.*' -or
      $_.IPAddress -like '172.30.*' -or
      $_.IPAddress -like '172.31.*'
    } |
    Select-Object -First 1 -ExpandProperty IPAddress
}

if ($ip) {
  Write-Host ("IRIS should now be reachable on: http://{0}:{1}/" -f $ip, $Port) -ForegroundColor Cyan
} else {
  Write-Host ("Firewall updated. Check your LAN IP with ipconfig, then open http://<your-ip>:{0}/" -f $Port) -ForegroundColor Cyan
}

# Setup Windows Task Scheduler: run batch_retrieve.py at 6 AM daily
# Run this script once in an elevated (admin) PowerShell.
# The task wakes the computer from sleep to retrieve overnight OpenAI batch results.

$TaskName  = "IRIS-BatchRetrieve"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) { $PythonExe = "python" }

$Script    = Join-Path $ScriptDir "batch_retrieve.py"
$LogFile   = Join-Path $RepoRoot "data\batch_retrieve_task.log"

Write-Host "Repo:   $RepoRoot"
Write-Host "Script: $Script"
Write-Host "Python: $PythonExe"

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task: $TaskName"
}

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$Script`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Daily -At "06:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "IRIS: Retrieve overnight OpenAI batch GPT results at 6 AM. Wakes laptop if sleeping." `
    -Force

Write-Host ""
Write-Host "Task '$TaskName' registered successfully."
Write-Host "The task will run at 6:00 AM daily and wake your laptop from sleep."
Write-Host "To test manually: python `"$Script`""
Write-Host "Logs: $LogFile"

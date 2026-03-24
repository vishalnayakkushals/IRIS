@echo off
setlocal

set "MODE=%~1"
if /I "%MODE%"=="" set "MODE=rebuild"
if /I "%MODE%"=="fast" set "MODE=restart"
if /I "%MODE%"=="full" set "MODE=rebuild"

set "EXTRA="
if /I "%~2"=="--skip-pull" set "EXTRA=-SkipPull"

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%scripts\refresh_and_check.ps1"

if not exist "%PS_SCRIPT%" (
  echo [ERROR] Missing script: "%PS_SCRIPT%"
  exit /b 1
)

echo Running IRIS refresh in %MODE% mode...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Mode %MODE% %EXTRA%
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo [ERROR] IRIS refresh failed with code %EXIT_CODE%.
  exit /b %EXIT_CODE%
)

echo [OK] IRIS refresh finished.
exit /b 0


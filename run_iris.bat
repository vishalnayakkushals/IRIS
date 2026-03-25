@echo off
setlocal EnableExtensions

set "ACTION=%~1"
if /I "%ACTION%"=="" set "ACTION=restart"

set "EXTRA="
if /I "%~2"=="--skip-pull" set "EXTRA=-SkipPull"

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%scripts\refresh_and_check.ps1"
set "COMPOSE_FILE=deploy/docker-compose.yml"

if /I "%ACTION%"=="help" goto :usage
if /I "%ACTION%"=="restart" goto :do_restart
if /I "%ACTION%"=="rebuild" goto :do_rebuild
if /I "%ACTION%"=="status" goto :do_status
if /I "%ACTION%"=="logs" goto :do_logs
if /I "%ACTION%"=="start" goto :do_start
if /I "%ACTION%"=="stop" goto :do_stop
if /I "%ACTION%"=="scheduler-stop" goto :do_scheduler_stop
if /I "%ACTION%"=="scheduler-start" goto :do_scheduler_start
if /I "%ACTION%"=="pull" goto :do_pull
if /I "%ACTION%"=="health" goto :do_health

echo [ERROR] Unknown command: %ACTION%
echo.
goto :usage

:do_restart
call :require_ps
echo [IRIS] Restart mode (pull + restart + readiness check)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Mode restart %EXTRA%
goto :exit_with_code

:do_rebuild
call :require_ps
echo [IRIS] Rebuild mode (pull + build + recreate + readiness check)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" -Mode rebuild %EXTRA%
goto :exit_with_code

:do_pull
echo [IRIS] git pull origin main
git pull origin main
goto :exit_with_code

:do_start
echo [IRIS] Starting iris + scheduler
docker compose -f %COMPOSE_FILE% up -d iris iris-scheduler
goto :exit_with_code

:do_stop
echo [IRIS] Stopping iris + scheduler
docker compose -f %COMPOSE_FILE% stop iris iris-scheduler
goto :exit_with_code

:do_scheduler_stop
echo [IRIS] Stopping scheduler only
docker compose -f %COMPOSE_FILE% stop iris-scheduler
goto :exit_with_code

:do_scheduler_start
echo [IRIS] Starting scheduler only
docker compose -f %COMPOSE_FILE% up -d iris-scheduler
goto :exit_with_code

:do_status
echo [IRIS] docker compose ps
docker compose -f %COMPOSE_FILE% ps
echo.
echo [IRIS] docker stats --no-stream
docker stats --no-stream deploy-iris-1 deploy-iris-scheduler-1
goto :exit_with_code

:do_logs
echo [IRIS] logs (tail 120)
docker compose -f %COMPOSE_FILE% logs --tail=120 iris iris-scheduler
goto :exit_with_code

:do_health
echo [IRIS] quick health checks
docker compose -f %COMPOSE_FILE% ps
if errorlevel 1 goto :exit_with_code
curl -s -o NUL -w "UI HTTP %%{http_code}\n" http://localhost:8765
docker compose -f %COMPOSE_FILE% exec iris python -c "import sqlite3; c=sqlite3.connect('/app/data/store_registry.db'); print('sqlite:ok'); c.close()"
goto :exit_with_code

:require_ps
if exist "%PS_SCRIPT%" goto :eof
echo [ERROR] Missing PowerShell script: "%PS_SCRIPT%"
exit /b 1

:usage
echo Usage:
echo   run_iris.bat restart [--skip-pull]
echo   run_iris.bat rebuild [--skip-pull]
echo   run_iris.bat status
echo   run_iris.bat logs
echo   run_iris.bat start
echo   run_iris.bat stop
echo   run_iris.bat scheduler-stop
echo   run_iris.bat scheduler-start
echo   run_iris.bat pull
echo   run_iris.bat health
echo.
echo Common:
echo   run_iris.bat restart
echo   run_iris.bat rebuild
exit /b 1

:exit_with_code
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Command failed with exit code %EXIT_CODE%.
  exit /b %EXIT_CODE%
)
echo [OK] Done.
exit /b 0


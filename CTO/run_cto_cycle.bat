@echo off
setlocal
cd /d "%~dp0\.."

set "NOTE=%~1"
set "COMMAND=%~2"
if "%NOTE%"=="" set "NOTE=manual-cto-cycle"

if "%COMMAND%"=="" (
  python CTO\scripts\perf_cycle.py ^
    --note "%NOTE%" ^
    --url "http://localhost:8765/?module=Reports" ^
    --url "http://localhost:8765/?module=Access&section=Config" ^
    --url "http://localhost:8765/?module=Operations"
) else (
  python CTO\scripts\perf_cycle.py ^
    --note "%NOTE%" ^
    --command "%COMMAND%" ^
    --url "http://localhost:8765/?module=Reports" ^
    --url "http://localhost:8765/?module=Access&section=Config" ^
    --url "http://localhost:8765/?module=Operations"
)

if errorlevel 1 (
  echo [CTO] Perf cycle failed.
  exit /b 1
)

python CTO\scripts\perf_analyze.py
endlocal

@echo off
setlocal
cd /d "%~dp0\.."

set "NOTE=%~1"
if "%NOTE%"=="" set "NOTE=continuous-browse-watch"

python CTO\scripts\perf_watch.py ^
  --note "%NOTE%" ^
  --interval-seconds 30 ^
  --url "http://localhost:8765/?module=Reports" ^
  --url "http://localhost:8765/?module=Access&section=Config" ^
  --url "http://localhost:8765/?module=Operations"

endlocal

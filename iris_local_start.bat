@echo off
setlocal EnableExtensions
cd /d "%~dp0"
python scripts\local_runtime_manager.py setup-env
if errorlevel 1 goto :fail
python scripts\local_runtime_manager.py start --service all
if errorlevel 1 goto :fail
python scripts\local_runtime_manager.py open
exit /b 0
:fail
echo [ERROR] IRIS local startup failed.
exit /b 1

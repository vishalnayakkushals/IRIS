@echo off
setlocal EnableExtensions
cd /d "%~dp0"
python scripts\local_runtime_manager.py stop --service all
exit /b %ERRORLEVEL%

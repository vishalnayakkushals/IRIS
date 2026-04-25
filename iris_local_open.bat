@echo off
setlocal EnableExtensions
cd /d "%~dp0"
python scripts\local_runtime_manager.py open
exit /b %ERRORLEVEL%

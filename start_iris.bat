@echo off
echo.
echo  =========================================
echo   IRIS - Starting API Server on port 8767
echo  =========================================
echo.
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0start_iris.ps1"
pause

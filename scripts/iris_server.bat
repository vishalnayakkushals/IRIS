@echo off
:loop
echo [IRIS] Starting API server at %date% %time%
cd /d "C:\Users\Kushals.DESKTOP-D51MT8S\Desktop\Github\IRIS"
python scripts\start_api_server.py
echo [IRIS] Server stopped (exit %errorlevel%). Restarting in 10s...
timeout /t 10 /nobreak
goto loop

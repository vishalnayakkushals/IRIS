@echo off
setlocal EnableExtensions

set "ACTION=%~1"
if /I "%ACTION%"=="" set "ACTION=restart"

set "EXTRA="
if /I "%~2"=="--skip-pull" set "EXTRA=-SkipPull"

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%scripts\refresh_and_check.ps1"
set "OPTIMIZE_PS=%SCRIPT_DIR%scripts\optimize_docker_runtime.ps1"
set "COMPOSE_FILE=deploy/docker-compose.yml"
set "ENV_FILE=%SCRIPT_DIR%.env.local"
if not exist "%ENV_FILE%" set "ENV_FILE=%SCRIPT_DIR%.env"
set "COMPOSE_ARGS=-f %COMPOSE_FILE%"
if exist "%ENV_FILE%" set "COMPOSE_ARGS=%COMPOSE_ARGS% --env-file %ENV_FILE%"
set "ONFLY_STORE_ID=%ONFLY_STORE_ID%"
if /I "%ONFLY_STORE_ID%"=="" set "ONFLY_STORE_ID=TEST_STORE_D07"
set "ONFLY_SOURCE_URL=%ONFLY_SOURCE_URL%"
if /I "%ONFLY_SOURCE_URL%"=="" set "ONFLY_SOURCE_URL=https://drive.google.com/drive/folders/1Wd8X8t-wF_HhPQPYuuFHjqTq6Ojc3Nnw"
set "ONFLY_MAX_IMAGES=%ONFLY_MAX_IMAGES%"
if /I "%ONFLY_MAX_IMAGES%"=="" set "ONFLY_MAX_IMAGES=100"
set "OPENAI_KEY_FILE=%OPENAI_KEY_FILE%"
if /I "%OPENAI_KEY_FILE%"=="" set "OPENAI_KEY_FILE=C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\OPEN AI API Key.txt"
set "GOOGLE_KEY_FILE=%GOOGLE_KEY_FILE%"
if /I "%GOOGLE_KEY_FILE%"=="" set "GOOGLE_KEY_FILE=C:\Users\Kushals.DESKTOP-D51MT8S\Downloads\IRIS\Key\Google Cloud Key.txt"
set "OPENAI_VISION_MODEL=%OPENAI_VISION_MODEL%"
if /I "%OPENAI_VISION_MODEL%"=="" set "OPENAI_VISION_MODEL=gpt-4.1-mini"
set "OPENAI_API_BASE=%OPENAI_API_BASE%"
if /I "%OPENAI_API_BASE%"=="" set "OPENAI_API_BASE=https://api.openai.com/v1"

if /I "%ACTION%"=="help" goto :usage
if /I "%ACTION%"=="restart" goto :do_restart
if /I "%ACTION%"=="rebuild" goto :do_rebuild
if /I "%ACTION%"=="status" goto :do_status
if /I "%ACTION%"=="logs" goto :do_logs
if /I "%ACTION%"=="start" goto :do_start
if /I "%ACTION%"=="stop" goto :do_stop
if /I "%ACTION%"=="scheduler-stop" goto :do_scheduler_stop
if /I "%ACTION%"=="scheduler-start" goto :do_scheduler_start
if /I "%ACTION%"=="gpt-scheduler-start" goto :do_gpt_scheduler_start
if /I "%ACTION%"=="gpt-scheduler-stop" goto :do_gpt_scheduler_stop
if /I "%ACTION%"=="gpt-scheduler-logs" goto :do_gpt_scheduler_logs
if /I "%ACTION%"=="stage1-scheduler-start" goto :do_stage1_scheduler_start
if /I "%ACTION%"=="stage1-scheduler-stop" goto :do_stage1_scheduler_stop
if /I "%ACTION%"=="stage1-scheduler-logs" goto :do_stage1_scheduler_logs
if /I "%ACTION%"=="stage1-scan-now" goto :do_stage1_scan_now
if /I "%ACTION%"=="stage1-report-now" goto :do_stage1_report_now
if /I "%ACTION%"=="gpt-test-validation-now" goto :do_gpt_test_validation_now
if /I "%ACTION%"=="onfly-run-now" goto :do_onfly_run_now
if /I "%ACTION%"=="onfly-benchmark" goto :do_onfly_benchmark
if /I "%ACTION%"=="onfly-scheduler-start" goto :do_onfly_scheduler_start
if /I "%ACTION%"=="onfly-scheduler-stop" goto :do_onfly_scheduler_stop
if /I "%ACTION%"=="onfly-scheduler-logs" goto :do_onfly_scheduler_logs
if /I "%ACTION%"=="pull" goto :do_pull
if /I "%ACTION%"=="health" goto :do_health
if /I "%ACTION%"=="light-runtime" goto :do_light_runtime

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
docker compose %COMPOSE_ARGS% up -d iris iris-scheduler
goto :exit_with_code

:do_stop
echo [IRIS] Stopping iris + scheduler
docker compose %COMPOSE_ARGS% stop iris iris-scheduler
goto :exit_with_code

:do_scheduler_stop
echo [IRIS] Stopping scheduler only
docker compose %COMPOSE_ARGS% stop iris-scheduler
goto :exit_with_code

:do_scheduler_start
echo [IRIS] Starting scheduler only
docker compose %COMPOSE_ARGS% up -d iris-scheduler
goto :exit_with_code

:do_gpt_scheduler_start
echo [IRIS] Starting GPT scheduler (profile gpt)
docker compose %COMPOSE_ARGS% --profile gpt up -d iris-gpt-scheduler
goto :exit_with_code

:do_gpt_scheduler_stop
echo [IRIS] Stopping GPT scheduler
docker compose %COMPOSE_ARGS% stop iris-gpt-scheduler
goto :exit_with_code

:do_gpt_scheduler_logs
echo [IRIS] GPT scheduler logs (tail 120)
docker compose %COMPOSE_ARGS% logs --tail=120 iris-gpt-scheduler
goto :exit_with_code

:do_stage1_scheduler_start
echo [IRIS] Starting Stage-1 YOLO relevance scheduler (profile stage1)
docker compose %COMPOSE_ARGS% --profile stage1 up -d iris-yolo-relevance-scheduler
goto :exit_with_code

:do_stage1_scheduler_stop
echo [IRIS] Stopping Stage-1 YOLO relevance scheduler
docker compose %COMPOSE_ARGS% stop iris-yolo-relevance-scheduler
goto :exit_with_code

:do_stage1_scheduler_logs
echo [IRIS] Stage-1 scheduler logs (tail 120)
docker compose %COMPOSE_ARGS% logs --tail=120 iris-yolo-relevance-scheduler
goto :exit_with_code

:do_stage1_scan_now
echo [IRIS] Running Stage-1 YOLO relevance scan now (inside container)
docker compose %COMPOSE_ARGS% exec iris python scripts/yolo_relevance_scan.py --root /app/data/test_stores --out-dir /app/data/exports/current/stage1_relevance --store-id TEST_STORE_D07 --detector yolo --conf 0.18 --gzip-exports --drop-plain-csv
goto :exit_with_code

:do_stage1_report_now
echo [IRIS] Building Stage-1 store report now (from Stage-1 output)
docker compose %COMPOSE_ARGS% exec iris python scripts/stage1_store_report.py --stage1-all /app/data/exports/current/stage1_relevance/stage1_relevance_all.csv.gz --out /app/data/exports/current/vision_eval/store_report.csv
goto :exit_with_code

:do_gpt_test_validation_now
call :load_keys_from_files
echo [IRIS] Running GPT post-relevance validation (test-folder only, default 30 images)
if /I "%OPENAI_API_KEY%"=="" echo [WARN] OPENAI_API_KEY is empty. GPT request will fail.
docker compose %COMPOSE_ARGS% exec -e OPENAI_API_KEY=%OPENAI_API_KEY% iris python scripts/gpt_post_relevance_test.py --store-id TEST_STORE_D07 --stage1-relevant /app/data/exports/current/stage1_relevance/stage1_relevant_images.csv.gz --out-root /app/data/exports/current/gpt_validation --db /app/data/store_registry.db --limit 30 --model %OPENAI_VISION_MODEL% --api-base %OPENAI_API_BASE% --save-json
goto :exit_with_code


:do_onfly_run_now
call :load_keys_from_files
echo [IRIS] Running on-the-fly pipeline now (YOLO relevance + GPT walk-in analysis)
if /I "%GOOGLE_API_KEY%"=="" echo [WARN] GOOGLE_API_KEY is empty. Drive URLs will fail.
if /I "%OPENAI_API_KEY%"=="" echo [WARN] OPENAI_API_KEY is empty. GPT walk-in analysis will be skipped.
set "ONFLY_GPT_FLAG="
if not "%OPENAI_API_KEY%"=="" set "ONFLY_GPT_FLAG=--enable-gpt --openai-model %OPENAI_VISION_MODEL%"
docker compose %COMPOSE_ARGS% exec -e GOOGLE_API_KEY=%GOOGLE_API_KEY% -e OPENAI_API_KEY=%OPENAI_API_KEY% iris python scripts/run_onfly_pipeline.py --store-id %ONFLY_STORE_ID% --source-url %ONFLY_SOURCE_URL% --db /app/data/store_registry.db --out-dir /app/data/exports/current/onfly --detector yolo --conf 0.18 --max-images %ONFLY_MAX_IMAGES% --run-mode manual --allow-detector-fallback %ONFLY_GPT_FLAG%
goto :exit_with_code

:do_onfly_benchmark
call :load_keys_from_files
echo [IRIS] Benchmarking on-the-fly pipeline (3x before/after)
if /I "%GOOGLE_API_KEY%"=="" echo [WARN] GOOGLE_API_KEY is empty. Drive URLs will fail.
docker compose %COMPOSE_ARGS% exec -e GOOGLE_API_KEY=%GOOGLE_API_KEY% -e OPENAI_API_KEY=%OPENAI_API_KEY% iris python scripts/benchmark_onfly_pipeline.py --store-id %ONFLY_STORE_ID% --source-url %ONFLY_SOURCE_URL% --db /app/data/store_registry.db --out-dir /app/data/exports/current/onfly --limit 30 --runs 3 --detector yolo --conf 0.18 --allow-detector-fallback
goto :exit_with_code

:do_onfly_scheduler_start
call :load_keys_from_files
echo [IRIS] Starting on-fly scheduler (profile onfly)
if /I "%GOOGLE_API_KEY%"=="" echo [WARN] GOOGLE_API_KEY is empty. Scheduler will fail for Drive URLs.
docker compose %COMPOSE_ARGS% --profile onfly up -d iris-onfly-scheduler
goto :exit_with_code

:do_onfly_scheduler_stop
echo [IRIS] Stopping on-fly scheduler
docker compose %COMPOSE_ARGS% stop iris-onfly-scheduler
goto :exit_with_code

:do_onfly_scheduler_logs
echo [IRIS] On-fly scheduler logs (tail 120)
docker compose %COMPOSE_ARGS% logs --tail=120 iris-onfly-scheduler
goto :exit_with_code

:do_status
echo [IRIS] docker compose ps
docker compose %COMPOSE_ARGS% ps
echo.
echo [IRIS] docker stats --no-stream
docker stats --no-stream deploy-iris-1 deploy-iris-scheduler-1
goto :exit_with_code

:do_logs
echo [IRIS] logs (tail 120)
docker compose %COMPOSE_ARGS% logs --tail=120 iris iris-scheduler
goto :exit_with_code

:do_health
echo [IRIS] quick health checks
docker compose %COMPOSE_ARGS% ps
if errorlevel 1 goto :exit_with_code
curl -s -o NUL -w "UI HTTP %%{http_code}\n" http://localhost:8765
docker compose %COMPOSE_ARGS% exec iris python -c "import sqlite3; c=sqlite3.connect('/app/data/store_registry.db'); print('sqlite:ok'); c.close()"
goto :exit_with_code

:do_light_runtime
call :require_optimize_ps
echo [IRIS] Switching to lightweight runtime profile
powershell -NoProfile -ExecutionPolicy Bypass -File "%OPTIMIZE_PS%"
goto :exit_with_code

:load_keys_from_files
if /I not "%OPENAI_API_KEY%"=="" goto :load_google_key
if not exist "%OPENAI_KEY_FILE%" goto :load_google_key
for /f "usebackq delims=" %%K in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$v=(Get-Content -Raw -LiteralPath '%OPENAI_KEY_FILE%' -ErrorAction Stop).Trim(); [Console]::Out.Write($v)"`) do set "OPENAI_API_KEY=%%K"
:load_google_key
if /I not "%GOOGLE_API_KEY%"=="" goto :eof
if not exist "%GOOGLE_KEY_FILE%" goto :eof
for /f "usebackq delims=" %%K in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$v=(Get-Content -Raw -LiteralPath '%GOOGLE_KEY_FILE%' -ErrorAction Stop).Trim(); [Console]::Out.Write($v)"`) do set "GOOGLE_API_KEY=%%K"
goto :eof

:require_ps
if exist "%PS_SCRIPT%" goto :eof
echo [ERROR] Missing PowerShell script: "%PS_SCRIPT%"
exit /b 1

:require_optimize_ps
if exist "%OPTIMIZE_PS%" goto :eof
echo [ERROR] Missing PowerShell script: "%OPTIMIZE_PS%"
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
echo   run_iris.bat gpt-scheduler-start
echo   run_iris.bat gpt-scheduler-stop
echo   run_iris.bat gpt-scheduler-logs
echo   run_iris.bat stage1-scheduler-start
echo   run_iris.bat stage1-scheduler-stop
echo   run_iris.bat stage1-scheduler-logs
echo   run_iris.bat stage1-scan-now
echo   run_iris.bat stage1-report-now
echo   run_iris.bat gpt-test-validation-now
echo   run_iris.bat onfly-run-now
echo   run_iris.bat onfly-benchmark
echo   run_iris.bat onfly-scheduler-start
echo   run_iris.bat onfly-scheduler-stop
echo   run_iris.bat onfly-scheduler-logs
echo   run_iris.bat pull
echo   run_iris.bat health
echo   run_iris.bat light-runtime
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

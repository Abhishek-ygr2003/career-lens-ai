@echo off
:: CareerLens AI — Local Ingestion & Pipeline Runner
:: This script is designed to run locally on your Windows machine to leverage
:: your residential/office IP address (bypassing cloud-IP anti-bot blockages on Naukri).
:: You can schedule this script to run daily using Windows Task Scheduler.

echo ============================================================
echo   CareerLens AI — Local Ingestion & Pipeline Runner
echo ============================================================
echo.

:: Ensure working directory is the script folder
cd /d "%~dp0"

:: Check if virtual environment exists
if not exist .venv (
    echo [!] Error: Virtual environment (.venv) not found.
    echo Please run "python -m venv .venv" and "pip install -r requirements.txt" first.
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate

echo.
echo Running Naukri and Foundit ingestion pipeline sequentially...
python run_full_pipeline.py --source both --max-pages 3 --cooldown 5

echo.
echo Running Adzuna ingestion pipeline sequentially...
python run_full_pipeline.py --source adzuna --max-pages 3 --cooldown 5

echo.
echo Running analytics precomputations...
python database/precompute_analytics.py

echo.
echo ============================================================
echo   Pipeline Run Completed Successfully!
echo ============================================================
pause

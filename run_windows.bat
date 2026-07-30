@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: TradingBot - Windows launcher
:: Run this once to set up, then use the menu to start.
:: Requires: Python 3.11+, Git for Windows, internet access
:: ============================================================

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

:: ---- Python check ----
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 ( echo ERROR: Python 3.11+ required. Found %PYVER%. & pause & exit /b 1 )
    if %%a EQU 3 if %%b LSS 11 ( echo ERROR: Python 3.11+ required. Found %PYVER%. & pause & exit /b 1 )
)
echo [OK] Python %PYVER%

:: ---- Git check ----
git --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Git not found. Install Git for Windows from https://git-scm.com
    pause & exit /b 1
)
echo [OK] Git found

:: ---- Git identity (required for commits) ----
git config user.email >nul 2>&1
if errorlevel 1 (
    set /p GIT_EMAIL=Enter your git email:
    git config user.email "!GIT_EMAIL!"
)
git config user.name >nul 2>&1
if errorlevel 1 (
    set /p GIT_NAME=Enter your git name:
    git config user.name "!GIT_NAME!"
)

:: ---- Venv ----
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [OK] Virtual environment active

:: ---- Install deps ----
echo Installing / verifying dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause & exit /b 1
)
echo [OK] Dependencies installed

:: ---- Env vars for SAP AI Core ----
if "%AICORE_AUTH_URL%"=="" (
    echo.
    echo ================================================================
    echo  SAP AI Core credentials needed for LLM calls.
    echo  Press Enter to skip if you have them in .streamlit\secrets.toml
    echo ================================================================
    set /p AICORE_AUTH_URL=AICORE_AUTH_URL (or Enter to skip):
    set /p AICORE_API_URL=AICORE_API_URL (or Enter to skip):
    set /p AICORE_CLIENT_ID=AICORE_CLIENT_ID (or Enter to skip):
    set /p AICORE_CLIENT_SECRET=AICORE_CLIENT_SECRET (or Enter to skip):
    set /p AICORE_RESOURCE_GROUP=AICORE_RESOURCE_GROUP [default]:
    if "!AICORE_RESOURCE_GROUP!"=="" set AICORE_RESOURCE_GROUP=default
)

:: ---- Menu ----
:menu
echo.
echo ============================================================
echo  TradingBot - What would you like to run?
echo ============================================================
echo  1. Autonomous optimizer (agent loop - improves strategy)
echo  2. Historical trainer   (walk-forward backtest + LLM)
echo  3. Dashboard            (Streamlit web UI)
echo  4. Bot runner           (single scan cycle)
echo  5. Exit
echo ============================================================
set /p CHOICE=Enter choice [1-5]:

if "%CHOICE%"=="1" goto run_optimizer
if "%CHOICE%"=="2" goto run_trainer
if "%CHOICE%"=="3" goto run_dashboard
if "%CHOICE%"=="4" goto run_bot
if "%CHOICE%"=="5" exit /b 0
echo Invalid choice. Try again.
goto menu

:run_optimizer
echo.
set /p MAX_ITER=Max iterations [default 500]:
if "%MAX_ITER%"=="" set MAX_ITER=500
set /p PHASE=Start phase A/B/C [default A]:
if "%PHASE%"=="" set PHASE=A
echo Starting autonomous optimizer (phase=%PHASE%, max_iter=%MAX_ITER%)...
python -m autonomous_optimizer --iterations %MAX_ITER% --phase %PHASE%
goto menu

:run_trainer
echo.
set /p QUICK=Quick mode? y/n [default n]:
set TRAINER_FLAGS=
if /i "%QUICK%"=="y" set TRAINER_FLAGS=--quick
echo Starting historical trainer...
python -m historical_trainer %TRAINER_FLAGS%
goto menu

:run_dashboard
echo.
echo Starting Streamlit dashboard at http://localhost:8501
start "" python -m streamlit run dashboard/app.py
goto menu

:run_bot
echo.
echo Running single bot scan cycle...
python bot_runner.py --once
goto menu

@echo off
REM =========================================
REM FER3ON AI V1 — Fast Start Script
REM Starts the bot quickly from the project root.
REM =========================================

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

echo.
echo ===================================
echo  FER3ON AI V1 — Fast Start
echo ===================================
echo.

set PYTHON=.venv\Scripts\python.exe

if /I "%~1"=="test" (
    echo Running quick regression tests...
    %PYTHON% -m pytest -q tests/test_datetime_warnings.py tests/test_execution_orchestrator.py tests/test_production_intelligence.py tests/test_production_integrity.py
    if errorlevel 1 (
        echo [ERROR] Quick tests failed.
        pause
        exit /b 1
    )
)

echo Starting main runtime...
%PYTHON% main.py

endlocal

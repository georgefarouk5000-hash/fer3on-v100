@echo off
REM =========================================
REM FER3ON-AI-V2 — Full Start Script
REM Runs cleanup, checks, and main runtime.
REM =========================================

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

set PYTHON=.venv\Scripts\python.exe
%PYTHON% tools/full_start.py

endlocal

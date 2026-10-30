@echo off
REM =========================================
REM FER3ON V6.0 PRO — Windows Install Script
REM تشغيله مرة واحدة فقط داخل الـ venv
REM =========================================

echo.
echo ===================================
echo  FER3ON V6.0 PRO — Installing packages
echo ===================================
echo.

python -m pip install --upgrade pip
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to upgrade pip
    pause
    exit /b 1
)

pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to install requirements.txt
    pause
    exit /b 1
)

echo.
echo ===================================
echo  Installation complete!
echo  Run bot:       python main.py
echo  Run backtest:  python run_backtest.py --mode full
echo  Run dashboard: streamlit run dashboard.py
echo ===================================
pause

# =========================================
# FER3ON V6.0 PRO — PowerShell Install Script
# شغّله مرة واحدة بعد تفعيل الـ venv
# =========================================

Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host " FER3ON V6.0 PRO — Package Installer" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/2] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: pip upgrade failed" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: pip upgraded" -ForegroundColor Green

Write-Host "[2/2] Installing requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: requirements installation failed" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: all dependencies installed" -ForegroundColor Green

Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host " Installation complete!" -ForegroundColor Green
Write-Host " Run bot:       python main.py" -ForegroundColor Cyan
Write-Host " Run backtest:  python run_backtest.py --mode full" -ForegroundColor Cyan
Write-Host " Run dashboard: streamlit run dashboard.py" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

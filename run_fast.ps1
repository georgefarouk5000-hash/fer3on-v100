# =========================================
# FER3ON AI V1 — Fast Start Script
# Starts the bot quickly from the project root.
# =========================================

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv/Scripts/python.exe')) {
    Write-Host '[ERROR] Virtual environment not found. Run install.ps1 first.' -ForegroundColor Red
    exit 1
}

Write-Host ''
Write-Host '===================================' -ForegroundColor Cyan
Write-Host ' FER3ON AI V1 — Fast Start' -ForegroundColor Cyan
Write-Host '===================================' -ForegroundColor Cyan
Write-Host ''

$pythonExe = '.\.venv\Scripts\python.exe'

if ($args -contains 'test') {
    Write-Host 'Running quick regression tests...' -ForegroundColor Yellow
    & $pythonExe -m pytest -q tests/test_datetime_warnings.py tests/test_execution_orchestrator.py tests/test_production_intelligence.py tests/test_production_integrity.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERROR] Quick tests failed.' -ForegroundColor Red
        exit 1
    }
}

Write-Host 'Starting main runtime...' -ForegroundColor Green
& $pythonExe main.py

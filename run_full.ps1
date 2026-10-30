# =========================================
# FER3ON-AI-V2 — Full Start Script
# Runs cleanup, checks, and main runtime.
# =========================================

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv/Scripts/python.exe')) {
    Write-Host '[ERROR] Virtual environment not found. Run install.ps1 first.' -ForegroundColor Red
    exit 1
}

$pythonExe = '.\.venv\Scripts\python.exe'
& $pythonExe tools/full_start.py

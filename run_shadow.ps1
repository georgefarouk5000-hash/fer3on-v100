$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv/Scripts/python.exe')) {
    throw 'Virtual environment not found. Run install.ps1 first.'
}

$env:FER3ON_SHADOW_ONLY = 'True'
$env:FER3ON_SHADOW_MAX_CYCLES = if ($args.Count -gt 0) { [string]$args[0] } else { '0' }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "Starting FER3ON in SHADOW-ONLY mode; max cycles=$env:FER3ON_SHADOW_MAX_CYCLES"
& .\.venv\Scripts\python.exe main.py
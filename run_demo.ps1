$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    throw 'Virtual environment not found. Create .venv and install requirements.txt first.'
}

$maxCycles = 10
if ($args.Count -gt 0) {
    $parsedCycles = 0
    if (-not [int]::TryParse([string]$args[0], [ref]$parsedCycles) -or $parsedCycles -le 0) {
        throw 'Cycle count must be a positive integer.'
    }
    $maxCycles = $parsedCycles
}

$env:FER3ON_DEMO_TRADING_ENABLED = 'True'
$env:FER3ON_SHADOW_ONLY = 'False'
$env:FER3ON_SHADOW_MAX_CYCLES = [string]$maxCycles
$env:ALLOW_LIVE_TRADING = 'False'
$env:ACCOUNT_MODE = 'DEMO'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "Starting FER3ON with demo-only execution guard; max cycles=$maxCycles"
& .\.venv\Scripts\python.exe -u main.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

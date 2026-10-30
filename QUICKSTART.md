# FER3ON-V100 Quick Start

This guide helps you start the project quickly and safely.

## 1. Prerequisites
- Python 3.10 or 3.11
- Windows environment recommended
- Virtual environment created under .venv

## 2. Setup
Run the installer once:

```bat
install.bat
```

Or with PowerShell:

```powershell
./install.ps1
```

For local credentials, copy `config.env.example` to `config.env` and fill in
only the values you need. `config.env` is ignored by Git; never commit or
publish it.

## 3. Start the project
### Fast start
```bat
run_fast.bat
```

### Full start (cleanup + checks + runtime)
```bat
run_full.bat
```

### Python entrypoint
```bash
python tools/full_start.py
```

### Bounded Demo-account test (10 cycles by default)
```powershell
.\run_demo.ps1
```

This explicitly enables order execution only after MT5 verifies that the
connected account is a Demo account. Pass a positive cycle count to change
the limit, for example `.\run_demo.ps1 20`. This does not mean the ML models
are trained; untrained models remain in their advisory fallback mode.
The script sends real orders to the connected demo account when the strategy
approves a trade; it does not force a trade to open.

## 4. Run checks
```bash
python tools/run_project_checks.py
```

## 5. Validate historical candle files
```powershell
.\.venv\Scripts\python.exe -m testing.historical_data_audit
```

The audit streams the extracted candle CSVs and checks timestamps, OHLC values,
and volume. It does not infer the source timezone, replay the strategy, or train
models; do not treat a clean audit as evidence of trading performance.

## 6. Offline SMC historical replay (research only)
```powershell
.\.venv\Scripts\python.exe -m testing.smc_historical_replay --bars 5000 --assume-utc
```

The timezone flag is a provisional assumption because the source CSV does not
identify its timezone. The replay does not model spread, slippage, or news and
does not train or replace any ML model. Its output is not evidence for enabling
Demo or Live execution.

## 7. Health check
```bash
python tools/system_health_check.py
```

## 8. Useful folders
- runtime/logs — runtime logs
- runtime/state — runtime state
- docs/ — operational documentation
- archive/legacy_docs — archived historical docs

## 9. Notes
- Live trading is disabled by default. Do not enable it from a public or
  unreviewed deployment.
- The demo runner verifies the MT5 account type before allowing order sends.
- Keep automation gated until health checks are green.
- Use the cleanup script whenever you want to remove temporary artifacts.

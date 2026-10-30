# FER3ON Architecture Audit

## Layer Summary
- Intelligence layer: orchestration, memory, RL, and adaptive weighting modules.
- Analysis layer: SMC, structure, liquidity, order-flow, volatility, and session intelligence.
- Decision layer: confidence, arbitration, override logic, and execution probability.
- Execution layer: lot sizing, scale-in, probes, and cooldown logic.
- Protection layer: drawdown protection, broker safety, recovery, and survival mode.

## Dependency Map
- Entry point: main.py
- Core settings: core/settings.py
- Unified arbitration: core/conflict_resolution.py
- Config layer: config/ai_config.py, config/execution_config.py, config/risk_config.py
- Health validation: tools/system_health_check.py

## Execution Flow
1. Market data ingestion
2. Analysis and signal generation
3. AI orchestration and confidence weighting
4. Arbitration and risk validation
5. Execution, recovery, and memory updates

## Stability Notes
- Conflict handling is now routed through a bounded arbitration helper.
- Health checks provide a single validation surface for imports, config, and module compatibility.
- The configuration layer is centralized without replacing active trading strategies.

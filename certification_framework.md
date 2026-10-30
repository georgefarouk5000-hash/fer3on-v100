# Certification Framework

## Scope

- Source of truth: `data/history/trades.csv` closed trades only.
- Update trigger: every MT5 closed-trade sync cycle.
- No new decision architecture added; this framework only measures live FER3ON V2.2 outcomes.

## Certification levels

- 100 Trade Certification — progress auto-updates after every closed trade.
- 200 Trade Certification — progress auto-updates after every closed trade.

## Tracked metrics

- Win Rate
- Profit Factor
- Max Drawdown
- Expectancy
- Recovery Factor
- Sharpe Ratio

## Runtime behavior

- Closed deals enter `data/history/trades.csv` through `core/mt5_history_sync.py`.
- After every sync batch, certification snapshot is recalculated and written to JSON + Markdown outputs.
- Reports do not modify execution decisions; they provide readiness and milestone visibility only.


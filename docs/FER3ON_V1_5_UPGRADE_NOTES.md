# FER3ON AI V1.5 Upgrade Notes

## Applied changes

- Unified decision authority preserved through `ai_v1_decide()` only.
- Quality thresholds relaxed: `MIN_QUALITY_SCORE=50`, `QUALITY_SOFT_FLOOR=45`.
- Composite thresholds updated: `FULL=70`, `REDUCED=50`, `MICRO=38`.
- Frequency increased: `TRADE_COOLDOWN=120`, `TRADE_MIN_INTERVAL=90`.
- Scalp take-profit updated to `1 ATR`.
- Micro fast-profit mode updated to `SL=0.8 ATR`, `TP=1 ATR`, `BASE_RISK_MICRO=0.10`.
- SMC kept trend-following only by hard bias enforcement.
- Counter-trend scalp path enabled only with strong reversal evidence.
- Trade DNA upgraded with decision/composite/risk/duration/execution fields.
- Startup integrity upgraded with module registry and critical function validation.
- Institutional dashboard upgraded with Sharpe, Sortino, Expectancy, Avg Win/Loss, daily/monthly PnL, and strategy ranking.

## Notes

- Existing project architecture was preserved.
- The provided text file mixes V1.1 and V1.5 directives; this package aligns the working codebase to the more complete V1.5 instruction set while keeping capital protection caps unchanged.

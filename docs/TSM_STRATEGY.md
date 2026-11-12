# TSM CHOCH-Retest Strategy

TSM is an independent multi-timeframe strategy. It evaluates closed M15 bars
for 48-bar momentum, a confirmed CHOCH, a separate retest, and later closed-bar
acceptance. The latest closed M5 bar must close beyond the prior three M5 bars'
high (BUY) or low (SELL). A clear opposing H1 or D1 structural bias blocks the
candidate; H1 history is required and D1 context is optional.

The stop is placed 0.15 M15 ATR beyond the latest confirmed prominent M15
swing. A qualifying swing must have at least 1.0 ATR prominence on each side.
The stop is not shortened by the conventional stop-distance cap. Position
sizing uses the actual structural stop distance; portfolio and broker
protections may still reject an order. The target is the nearest viable
opposing M15, H1, or D1 swing, with the next farther swing recorded when
available. Structural targets are not shortened by the generic ATR ceiling.

All M5, H1, and D1 context is filtered to candles fully closed by the M15
decision time. Missing closed M5 or H1 context causes TSM to wait; D1 context
is optional.

The runner is controlled by `FER3ON_TSM_ENABLED` (enabled by default). Order
submission remains subject to this project's verified-demo gate:
`FER3ON_DEMO_TRADING_ENABLED=True`, `FER3ON_SHADOW_ONLY=False`, and an MT5
account verified as demo. The global execution guard in `core/demo_execution.py`
is not bypassed by TSM.

Candidate decisions are recorded in `data/analytics/tsm/candidates.jsonl`.
Execution events are correlated in `data/history/trade_events.jsonl` by
`candidate_id` and `decision_id`.

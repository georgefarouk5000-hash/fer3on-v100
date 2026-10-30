# Runtime Execution Map

## Scope

This document describes the current runtime wiring in `main.py`. A module being
present in the repository or importable at startup does not, by itself, mean it
is invoked by the live loop.

## Entrypoints

- `main.py` — primary MT5 runtime and heartbeat loop.
- `run_fast.bat` — starts `main.py` with the project virtual environment.
- `run_full.bat` / `tools/full_start.py` — cleanup and project checks, then
  starts `main.py`.
- `run_faie_shadow.py` — standalone FAIE demonstration using a **sample**
  `DecisionContext`; it is not a live-market feed or an alternative trading
  runtime.

## Primary Runtime Flow

```text
main.py
  -> connect to MT5 and run core.startup_check
  -> heartbeat loop
      -> read M5 rates and current tick
      -> derive SMC direction using market structure and liquidity
      -> check swing readiness, candle trigger, and SMC entry sequence
      -> calculate confidence, quality, regime, execution metrics,
         ML features/result, and adaptive structural SL/TP
      -> build a live DecisionContext
      -> core.phase2_unified_authority.decide_for_strategy("SMC", snapshot)
          -> core.fer3on_decision_authority.decide_trade(ctx)
              -> core.unified_decision.unified_decide(ctx)
      -> apply quality, session, loss, position, cooldown, portfolio-risk,
         and sizing checks
      -> manage existing positions
      -> if all gates pass and verified demo execution is enabled:
          -> core.trade_executor.execute_trade()
          -> broker order_check / order_send
          -> record trade and update memory/portfolio state
      -> run isolated shadow/advisory sidecars
      -> reconcile history, close outcomes, and watchdog state
```

## Active Decision and Execution Ownership

- `core.phase2_unified_authority.py` is the strategy-aware authority called by
  the primary SMC loop. It normalizes the live snapshot and fails closed on
  decision exceptions.
- `core.fer3on_decision_authority.py` is the canonical facade used by Phase 2;
  `core.unified_decision.py` produces the final decision.
- The active snapshot is not synthetic: it collects current MT5 prices and
  rates, then calls market structure, liquidity, swing structure, candle and
  SMC-entry analysis, confidence, ML, and adaptive SL/TP components.
- `core.trade_executor.py` is the order-sending boundary. Execution is separately
  guarded by demo-account verification and explicit settings; a healthy startup
  check alone does not authorize an order.
- The active loop currently routes the SMC snapshot. The existence of a DAILY
  signal module or strategy-aware authority support does not mean DAILY is
  dispatched by this loop.

## Shadow and Advisory Sidecars

These components observe decisions or record counterfactual results; they do
not replace the canonical authority.

| Component | Runtime trigger | Role and limits |
|---|---|---|
| `analytics.shadow_counterfactual` | Records selected rejected signals after the decision; resolves pending records against later candles | Measures whether rejected signals would have reached SL/TP. Early cycle exits before the logging call are not represented. |
| `analytics.shadow_learning_engine` | Every 60 loop-counter cycles that reach the ready-snapshot section, when importable | Now analyzes only rejected records with resolved candle outcomes; pending, virtual, and malformed outcomes are excluded. Recommendations wait for the configured minimum sample. |
| `core.multi_regime_analyzer` | Each ready snapshot | Logs regime and strategy recommendations. With the approved Daily route enabled, a DAILY recommendation with confidence >= 0.7 selects a valid Daily candidate; otherwise SMC remains primary. |
| Phase 3 orchestrator | Each ready snapshot when `PHASE3_ENABLED` | Runs portfolio, gold context, ML safety, Strategy DNA, Final Brain, and periodic health/calibration analysis. `PHASE3_LIVE_AUTHORITY` is false. Adaptive calibration now consumes closed current-build Truth Layer trades. Gold Context remains explicitly unavailable until it can load a valid macro feed. |
| FAIE shadow logger | Each ready authority decision when `FAIE_SHADOW_LOGGING_ENABLED` | Writes an advisory FAIE decision alongside the real decision. The call site reports persistence failure without affecting the real decision. |
| Virtual shadow ledger | Only when `FER3ON_SHADOW_ONLY` is enabled and a candidate reaches the relevant branch | Records accepted-but-not-executed candidates. This switch is distinct from the Phase 3 and FAIE logging switches. |
| Phase 2 entry controller | Each eligible signal when enabled | Writes an advisory entry plan. Live order behavior remains gated by `PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED`. |
| Phase 5 opportunity allocator | Each ready candidate when available | Computes and displays an advisory ranking. Its risk adjustment and rejection are applied to live sizing/flow only when `PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED` is true. |

### Shadow Readiness Notes

- `run_faie_shadow.py` is a sample-input demonstration; only the `main.py`
  logging call sees the live `DecisionContext`.
- `analytics.shadow_learning_engine` does not manufacture outcomes. It consumes
  `WIN`, `LOSS`, `LOSS_INTRABAR_AMBIGUOUS`, and `TIMEOUT` labels produced by the
  candle resolver. A timeout is a non-win with zero recorded price-distance
  P&L; this is not account-currency P&L.
- Adaptive shadow calibration is scheduled every 50 Phase 3 cycles, but the
  orchestrator now passes closed trades from the current build in the
  Truth Layer. Confidence values in the 0–1 range are converted to percentage
  points; missing or invalid confidence values are not assigned a fabricated
  confidence bucket.
- Gold Context reads `data/feeds/gold_macro_factors.json` (configurable through
  `PHASE3_GOLD_MACRO_FACTORS_PATH`). The JSON must provide a timezone-aware
  `sampled_at`, a non-empty actual `source`, and all seven numeric `factors`
  (`dxy_trend`, `real_yields`, `cpi_pressure`, `nfp_momentum`, `fomc_stance`,
  `geopolitical`, `rate_differential`) in [-100, 100]. Samples older than 72
  hours are unavailable. No provider is bundled: without a real feed, the
  layer reports unavailable instead of presenting generated neutral values
  as observed macro analysis.
- The watchdog probes Telegram's `getMe` endpoint with a 3-second timeout and
  caches the result for five minutes, so it does not perform a network request
  on every decision cycle.
- Daily can be selected by a confident regime recommendation or used as a
  fallback when SMC has no directional signal or its structural entry is not
  ready. Its signal requires a closed-bar D1 EMA trend aligned with a closed
  H4 candle; it then passes the shared Phase-2 authority, portfolio risk,
  sizing, execution, and the existing verified-demo execution guard; live
  order sending remains disabled. Daily sizing and SL/TP use closed H4
  structure/ATR. Position management identifies trades by
  `DAILY_MAGIC` and only tightens stops from the last closed D1 candle; no bot
  was run as part of validation.
- The performance dashboard reads current-build closed-trade metrics from
  the Truth Layer. It does not compare against unverified historical baselines;
  performance alerts remain unevaluated until validated thresholds are defined.

## Startup Validation Limits

`core.runtime_validation.run_runtime_validation()` checks the presence of
eight selected functions (decision authority, quality gate, risk, execution,
memory, trailing, and daily signal). The reported 100/100 score means those
selected imports/functions passed; it is not a whole-project integration test.
`core.startup_check.run_startup_check()` also imports its module registry, but
the `main.py` loop records its result for watchdog reporting and does not use
that status as the sole order-execution gate.

## Known Non-Runtime / Legacy Areas

- `core.ai_v1_authority.py` is not called by the active `main.py` decision path.
- `core.v7_audit.py` and `core.v7_integration.py` are not part of the current
  primary decision chain.
- `core.daily.signal` is checked for availability at startup but the current
  `main.py` loop builds and dispatches an SMC snapshot.
- Repository tests, reports, training scripts, and standalone analyzers are
  tools or validation surfaces, not automatically running trading engines.

## Operational Check

Use the project virtual environment for validation. A successful import or
startup check does not prove live broker connectivity, correct data freshness,
or successful order execution. Confirm the heartbeat, MT5 tick/rates, startup
status, risk guards, and execution permission before enabling demo activity.

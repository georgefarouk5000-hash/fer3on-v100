# FAIE — Phase-2 Specification
## Completing the Remaining Volumes & Rollout Phases

**Status:** binding execution spec, not a re-statement of the vision.
**Supersedes:** nothing. Extends `docs/FAIE/VOLUME_1_CONSTITUTION.md` and
`docs/FAIE/ROADMAP.md`. Every item here traces to a row marked PARTIAL/MISSING in
`docs/FAIE/GAP_ANALYSIS.md`.
**Applies to:** whoever picks up development next — a future session, a human developer, or
Cursor. Every section below is written so it can be implemented without re-deriving context
from the original vision document.

**Ground rule inherited from Volume 1, non-negotiable in every item below:** additive only, no
deletion of existing modules, no code path that sends/modifies/cancels a broker order outside
the existing `core.unified_decision → core.portfolio_risk_authority → execution` chain, and no
fabricated signal presented as if it were real market data.

---

## 0. How to use this document

Each item below has the same six fields the original vision asked for in Volume 2
(**Responsibilities / Interfaces / Inputs / Outputs / Failure Handling / Quality Metrics**),
because "write Volume 2 properly" is itself one of the gaps. Items are grouped by
effort tier so the next session can pick a scope that fits the time available:

- **🟢 Small** (~1 focused session): a single new module, tests, no cross-cutting risk
- **🟡 Medium** (~2-3 sessions): touches multiple files or needs a data-shape decision first
- **🔴 Large** (~one project phase): needs real historical data, a live call site, or a go/no-go
  decision from the person running the account

---

## 1. Volume 2 — System Architecture Specification

The original diagram (`Market → Collector → Normalizer → Market Brain → Evidence Engine →
Reasoning Engine → Scenario Engine → Probability Engine → Risk Constitution → Execution →
Learning → Memory → Audit`) maps onto this codebase as follows. This table itself **is** the
missing Volume 2 deliverable — no new code required, just this mapping kept up to date as
other sections below are implemented.

| Box | Responsibilities | Existing module(s) | Interfaces (in → out) | Failure Handling | Quality Metric |
|---|---|---|---|---|---|
| Market | Raw price/tick source | MT5 connection (`core/` runtime, Windows-only) | broker feed → OHLCV rates | reconnect/backoff (existing) | feed uptime % |
| Collector | Pull rates per timeframe | existing MT5 wrappers | broker → `rates` arrays | stale-data detection (existing) | latency, gap count |
| Normalizer | Clean/align candles across TFs | existing utils (`core/utils.py`, `core/candle_context.py`) | raw rates → normalized candles | drop/flag malformed candles | schema conformance % |
| Market Brain (scoring) | Composite scoring, regime/strategy fit | `brain/master_brain.py` (existing, untouched) | features → composite score | soft-fail to lower confidence tier | existing certification metrics |
| **Market Brain (evidence)** | Analyst reports, no execution | `brain/faie/analysts.py` **(built)** | `DecisionContext` → `AnalystReport[]` | analyst marks itself `partial` on missing data | analyst coverage % (non-partial / total) |
| Evidence Engine | Fuse analyst evidence | `brain/faie/fusion.py` **(built)** | `AnalystReport[]` → `FusedEvidence` | re-normalize weights when analysts are partial | net_score stability across re-runs (determinism test) |
| Reasoning Engine | Detect contradictions | `brain/faie/contradiction.py` **(built)** | `AnalystReport[]` → `ContradictionReport` | none needed — pure function | conflicts found vs. manually-reviewed sample |
| Scenario Engine | Ranked probabilistic outcomes | `brain/faie/scenario.py` **(built)** | `FusedEvidence` + contradiction score → `Scenario[]` | probabilities always renormalized to sum 1.0 (enforced by test) | Brier score once paired with real outcomes (§6) |
| Probability/Decision | Synthesize into advisory Decision | `brain/faie/chief_decision_officer.py` **(built)** | all of the above → `Decision` | never raises — worst case returns NEUTRAL/low-confidence | advisory-vs-live agreement rate (§6) |
| Risk Constitution | Hard/soft risk gates | `core/portfolio_risk_authority.py`, `risk/hard_risk_cap.py` (existing, untouched) | `DecisionContext` → allow/size/block | catastrophic block list (existing `CATASTROPHIC_BLOCKS`) | existing certification drawdown/Sharpe |
| Execution | Order placement | `core/trade_executor.py` / `core/execution_optimizer_v2.py` (existing, **never touched by FAIE**) | sized decision → broker order | existing retry/slippage handling | fill rate, slippage (§4.3 extends this) |
| Learning | Memory & adaptive confidence | `brain/trade_dna.py`, `core/dynamic_confidence.py`, `fer3on_masr/learning/*` (existing) | trade outcomes → updated weights/memory | bounded adaptive range (existing) | existing evolution engine reports |
| Audit | Full trail per decision | `certification/framework.py` (existing) + `Decision.to_dict()` (FAIE, **built**) | every decision/trade → log/report | append-only, never mutated | audit completeness (every live decision has a Decision or legacy-log entry) |

Rows in **bold "(built)"** are done. Everything else in this document fills in the remaining
rows or extends an existing one.

---

## 2. Volume 4 — Missing Analysis Engines

### 2.1 🟡 Elliott Wave Engine
- **Responsibilities:** identify impulse/corrective wave counts on swing-pivot data already
  produced by `core/trend_confluence.py::find_pivots`; emit wave-position evidence (e.g. "in
  wave 3 of an impulse", "corrective ABC likely complete").
- **Interfaces:** `analyze_elliott(rates, pivots) -> ElliottReport` in a new
  `core/elliott_engine.py`; a new `ElliottAnalyst` in `brain/faie/analysts.py` wraps it into
  `Evidence`.
- **Inputs:** OHLCV rates, existing pivot list from `find_pivots`.
- **Outputs:** `ElliottReport{wave_label, degree, confidence, invalidation_price}`.
- **Failure handling:** wave counting is inherently ambiguous — if two counts are equally
  plausible, return `confidence <= 40` and surface both as `alternative_counts`, do not force
  a single confident count.
- **Quality metric:** backtest hit-rate of "wave 3/C completion" calls against realized
  reversals, tracked once §6's backtest harness exists — **do not ship this analyst as
  non-partial in `ChiefDecisionOfficer` until that backtest exists.**

### 2.2 🟡 Correlation / Intermarket Engine
- **Responsibilities:** track correlation between the traded symbol (XAUUSD) and DXY,
  US10Y yields, and major indices; flag when a signal's direction contradicts a strongly
  correlated instrument's recent move.
- **Interfaces:** `compute_correlation(symbol_returns, other_returns, window) -> float` in new
  `core/correlation_engine.py`; a `CorrelationAnalyst` in `brain/faie/analysts.py`.
- **Inputs:** return series for XAUUSD and each tracked instrument (needs a data feed decision
  — see Failure Handling).
- **Outputs:** `CorrelationReport{pairs: [{symbol, corr, agreement}], regime_break: bool}`.
- **Failure handling:** if intermarket data isn't available in the running environment
  (MT5 symbol not subscribed, etc.), the analyst must behave exactly like `VolumeAnalyst`
  today — `partial=True`, abstain, state why in `notes`. **Do not simulate DXY/yields data.**
- **Quality metric:** correlation-break flags reviewed manually for a sample period before
  trusting them as non-partial evidence.

### 2.3 🔴 Real Volume/Order-Flow Engine
- **Responsibilities:** replace `VolumeAnalyst`'s current permanent abstention with a real
  read once genuine tick-volume or order-flow data is available.
- **Interfaces:** extend `DecisionContext` (in `core/unified_decision.py`) with a new
  optional field, e.g. `tick_volume_delta: float = 0.0` — **this is the one item in this
  document that touches an existing file**, and only by adding an optional field with a
  neutral default, which is backward compatible (existing callers unaffected). Then update
  `VolumeAnalyst.analyze()` to use it when non-zero, keeping the `partial=True` fallback
  otherwise.
- **Inputs:** tick volume or (if broker supports it) real order-flow/DOM data.
- **Outputs:** `Evidence` exactly like other analysts — no new type needed.
- **Failure handling:** if `tick_volume_delta == 0.0` (the dataclass default), continue
  treating the analyst as partial — a real reading of exactly zero is indistinguishable from
  "not wired up" at this field's current resolution, so **this needs a second field
  (`tick_volume_available: bool`) before it can be trusted**, to avoid a false "confident
  neutral" read.
- **Quality metric:** N/A until real data source is confirmed available — this is a data
  availability question for whoever owns the broker connection, not a coding task.

---

## 3. New Additions (from the original "إضافات جديدة" list)

### 3.1 🟢 Market Personality Engine
- **Responsibilities:** per-symbol weight/threshold profiles so XAUUSD, FX pairs, and indices
  aren't scored with identical assumptions.
- **Interfaces:** new `brain/faie/personality.py` with
  `PERSONALITY_PROFILES: Dict[str, Dict[str, float]]` (symbol → fusion weight overrides) and
  `get_profile(symbol: str) -> Dict[str, float]`. `ChiefDecisionOfficer.__init__` already
  accepts `fusion_weights` — wiring this in is: `ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))`.
- **Inputs:** `ctx.symbol` (already on `DecisionContext`).
- **Outputs:** a weights dict consumed by the existing `EvidenceFusionEngine`.
- **Failure handling:** unknown symbol → fall back to `DEFAULT_WEIGHTS` from `fusion.py`
  unchanged.
- **Quality metric:** per-symbol backtest comparison (with vs. without personality weighting),
  once §6 exists.

### 3.2 🟡 Institutional Session Engine (upgrade)
- **Responsibilities:** go beyond `core/session_intelligence.py`'s session/phase detection to
  model liquidity-window strength (e.g. London open sweep windows, NY overlap behavior) and
  feed that as a distinct evidence tag, not just a `session_score` number.
- **Interfaces:** extend the existing `MacroAnalyst` or add a `SessionAnalyst` in
  `brain/faie/analysts.py` that reads `ctx.session`, `ctx.session_score`, and calls
  `core.session_intelligence.detect_session_phase` directly (already public) to add
  `Evidence(tags=["session", "liquidity_window"])` distinct from the generic macro read.
- **Inputs:** hour/minute (already flows into `core.session_intelligence`), `ctx.session_score`.
- **Outputs:** `Evidence` with a `liquidity_window_strength` claim.
- **Failure handling:** none new — this reuses an existing, already-tested engine.
- **Quality metric:** compare flagged "weak liquidity window" periods against realized spread/
  slippage in `data/history` — no new data needed, this is analysis, not a new feed.

### 3.3 🟡 Execution Quality Engine (post-trade)
- **Responsibilities:** today's `ExecutionOfficer` (FAIE) only scores *pre-trade* readiness
  (spread/ATR/RR). This item adds the *post-trade* half: slippage, fill delay, and rejection
  rate, feeding back into performance evaluation.
- **Interfaces:** new `analytics/execution_quality.py::record_execution_outcome(ticket,
  requested_price, filled_price, requested_time, filled_time, rejected: bool)` appending to a
  new `data/analytics/execution_quality.csv`; a `summarize_execution_quality() -> Dict`
  reader for use in `certification/framework.py` and, later, as a `RiskOfficer` evidence input.
- **Inputs:** whatever the existing execution layer (`core/trade_executor.py`) already knows
  at order-fill time — this only requires that layer to *call* the new recorder, not change
  its own logic.
- **Outputs:** slippage distribution, delay distribution, rejection rate.
- **Failure handling:** missing fields (e.g. broker doesn't report fill delay) → record `None`,
  exclude from that specific aggregate, don't fabricate a value.
- **Quality metric:** this *is* the quality metric layer — track its own coverage (% of trades
  with complete execution-quality records).

### 3.4 🟡 Portfolio Intelligence (correlated risk)
- **Responsibilities:** flag when several *simultaneously open* trades share directional risk
  (e.g. three BUY XAUUSD positions from different strategies) even though
  `core.portfolio_risk_authority` already correctly treats them as diversification, not
  conflict, at the decision-authority level (per its own documented rule). This is a
  visibility layer on top, not a change to that rule.
- **Interfaces:** new `analytics/portfolio_intelligence.py::assess_correlated_exposure(open_trades: List[Dict]) -> PortfolioRiskNote`,
  reading `core.portfolio_risk_authority.get_portfolio_state().open_trades` (already
  available, read-only, same call `RiskOfficer` already makes).
  `PortfolioRiskNote{same_direction_count, same_direction_symbols, net_directional_exposure}`.
- **Inputs:** existing `PortfolioState.open_trades`.
- **Outputs:** an informational note surfaced through `RiskOfficer`'s existing `notes` field
  (append, don't replace) — **still read-only, still does not block or resize anything.**
- **Failure handling:** empty open-trades list → note says "no correlated exposure", not an
  error.
- **Quality metric:** manual review of flagged periods against realized drawdown.

---

## 4. Volume 9 — Self Audit (Bias / Overfitting / Drift)

- **Responsibilities:** turn the existing `certification/framework.py` win-rate/Sharpe/
  drawdown tracking into a periodic self-review that also asks *why*, not just *what*.
- **Interfaces:** new `certification/self_audit.py`:
  - `detect_bias(reports: List[Decision]) -> BiasReport` — flags if the Chief Decision
    Officer's `top_scenario.direction` is skewed heavily toward one direction across a review
    window regardless of `fused_evidence.net_score` sign distribution (a real bias signature:
    net_score is balanced but the *decision* keeps favoring one side would indicate a scenario-
    engine bug, not market truth).
  - `detect_drift(recent_reports: List[Decision], baseline_reports: List[Decision]) -> DriftReport`
    — compares `per_analyst` net_score distributions between two time windows; large shifts
    flag possible regime change or a broken analyst (e.g. one that's stopped reporting real
    evidence and defaulted to NEUTRAL).
  - `detect_overfitting(certification_metrics_by_period) -> OverfitReport` — compares
    in-sample vs. out-of-sample performance once §6's backtest harness produces both.
- **Inputs:** a history of `Decision.to_dict()` records (already loggable today via
  `run_faie_shadow.py`'s output pattern — this item just needs those logs accumulated over
  time, then read back in bulk) plus existing `certification/framework.py` metrics.
- **Outputs:** `BiasReport` / `DriftReport` / `OverfitReport`, written to
  `data/analytics/self_audit_<date>.json`, in the same style as `certification_status.md`.
- **Failure handling:** insufficient history (< N decisions) → report `status: INSUFFICIENT_DATA`,
  not a false-confidence conclusion.
- **Quality metric:** the audit's own alerts, manually confirmed or rejected over time, become
  the metric (precision of the audit itself) — this is inherently a slow-building metric.

---

## 5. Phase 3 — Wiring the Existing Engines into the New Brain (properly)

Today, `brain/faie/analysts.py` reads `DecisionContext` fields that the *old* engines already
populate — that is an implicit wire, not an explicit one. To make it explicit and reviewable:

- **Responsibilities:** add one clearly-marked, optional call site where the live loop can log
  a FAIE `Decision` next to the real one, with zero effect on behavior.
- **Interfaces:** in whichever module currently builds a `DecisionContext` and calls
  `core.unified_decision.unified_decide(ctx)` (this differs by strategy — `core/daily/signal.py`,
  `core/scalping_engine.py`, `core/smc_entry_engine.py`, `core/micro_trading_engine.py` per
  `core/module_registry.py`), add:
  ```python
  # OPTIONAL, LOGGING-ONLY — see docs/FAIE/PHASE_2_SPECIFICATION.md §5
  if FAIE_SHADOW_LOGGING_ENABLED:
      from brain.faie import ChiefDecisionOfficer
      _faie_decision = ChiefDecisionOfficer().decide(ctx)
      _log_faie_shadow_decision(_faie_decision, ctx)  # new helper, appends JSON, never raises
  ```
  gated by a new `FAIE_SHADOW_LOGGING_ENABLED` flag in `core/settings.py`, **defaulting to
  `False`**.
- **Inputs:** the `DecisionContext` already built at that call site — no new data needed.
- **Outputs:** one JSON log line per real decision cycle, in `data/faie/shadow_log.jsonl`.
- **Failure handling:** `_log_faie_shadow_decision` must wrap everything in try/except and
  never let a FAIE failure block or alter the real decision — this is the single most
  important failure-handling rule in this whole document.
- **Quality metric:** shadow-log coverage (% of live decision cycles that also produced a
  logged FAIE decision) — this is what feeds §6.

---

## 6. Phase 7 — Historical Backtest Harness for FAIE

- **Responsibilities:** replay historical `DecisionContext` sequences (already used by
  `testing/backtester.py` for the legacy pipeline) through `ChiefDecisionOfficer`, and compare
  against what `unified_decide()` actually chose and what actually happened afterward.
- **Interfaces:** new `testing/faie_backtest.py::run_faie_backtest(history_rows) ->
  FaieBacktestReport`, reusing whatever row format `testing/backtester.py` already consumes
  (check that module's existing loader before writing a second one).
- **Inputs:** existing historical CSVs under `data/history/` (already read by
  `core/data_integrity.py::read_csv_records`).
- **Outputs:** `FaieBacktestReport{agreement_rate, disagreement_cases: [...], would_have_avoided_losses: [...], would_have_missed_wins: [...]}`.
- **Failure handling:** if a historical row is missing fields FAIE's analysts need, that row
  is skipped and counted in `skipped_rows`, not filled with defaults that look like real data.
- **Quality metric:** this report *is* the quality gate for Phase 8 — Paper Trading should not
  start until `agreement_rate` and the disagreement cases have been reviewed by a human.

---

## 7. Phases 8-10 — Paper Trading, Live, Full Rollout

These are **decision gates**, not coding tasks. Each requires an explicit human go/no-go, not
an autonomous "it looks ready" judgment from any AI session:

| Phase | Gate condition before proceeding |
|---|---|
| 8. Paper Trading | §6's backtest report reviewed; `FAIE_SHADOW_LOGGING_ENABLED` has run in the live loop (still logging-only, §5) for a minimum period the account owner considers sufficient |
| 9. Small-risk live | Paper trading period reviewed; a human has explicitly decided FAIE's Decision should influence (not replace) the existing risk sizing — this requires a **new, separate, explicitly-reviewed code change**, not an on-by-default flag |
| 10. Full institutional rollout | 9 has run long enough to have real drawdown/Sharpe data through `certification/framework.py`, reviewed against its existing 100/200-trade certification targets |

No section of this document authorizes skipping these gates. If a future session is asked to
"just enable it," it should point back to this table.

---

## 8. Suggested order for the next work session

1. 🟢 §3.1 Market Personality Engine — smallest, no data dependency, immediately testable.
2. 🟢/🟡 §5 Phase 3 shadow-logging call site — highest value-to-effort ratio; everything else
   (§6, §4) depends on logs existing.
3. 🟡 §3.3 Execution Quality Engine (post-trade) — independent of the above, valuable on its
   own for the existing certification framework too.
4. 🟡 §3.4 Portfolio Intelligence — independent, read-only, safe.
5. 🔴 §6 Backtest harness — do this once §5 has produced enough shadow logs, or in parallel
   using pure historical replay (doesn't strictly need §5 first if `testing/backtester.py`'s
   existing historical rows are used directly).
6. 🟡 §2.1/§2.2 Elliott / Correlation engines — hold until a decision on Elliott's inherent
   ambiguity and Correlation's data source is made; don't build speculatively.
7. 🟡 §4 Self Audit — needs a meaningful history of logged decisions (from §5) to be useful;
   building it before that history exists just produces `INSUFFICIENT_DATA` reports.
8. 🔴 §7 Phases 8-10 — human-gated, not schedulable as engineering work.

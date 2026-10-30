# FAIE — Phase-2 Spec Implementation Progress

**This document records what was actually built in the pass that implemented
`docs/FAIE/PHASE_2_SPECIFICATION.md`, following the effort-tier order it suggests in its
§8 "Suggested order for the next work session".** It exists so the next session (human or AI)
doesn't have to re-derive "what's actually done vs. what the spec merely describes" by reading
diffs — see `GAP_ANALYSIS.md` for the always-current status table this feeds into.

**Ground rule honored throughout, same as the spec itself requires:** additive only, no engine
deleted or renamed, no code path added that sends/modifies/cancels a broker order outside the
existing `core.unified_decision → core.portfolio_risk_authority → execution` chain, no
fabricated signal presented as real market data.

---

## What was implemented

### 1. §3.1 Market Personality Engine — 🟢 DONE
- **New file:** `brain/faie/personality.py` — `PERSONALITY_PROFILES` (XAUUSD, EURUSD, GBPUSD)
  + `get_profile(symbol)`, falling back to `fusion.py`'s `DEFAULT_WEIGHTS` for any unknown
  symbol.
- **Wired into:** `run_faie_shadow.py` (`ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))`)
  and `brain/faie/shadow_logging.py::build_shadow_decision()`.
- **Exported from:** `brain/faie/__init__.py`.
- **Tests:** `tests/faie/test_personality.py` (8 tests) — unknown-symbol fallback, case/whitespace
  normalization, profile immutability, analyst-name validity, and direct fusion/CDO integration.
- **Deferred (per spec's own Quality Metric):** the specific per-symbol weight values are a
  first, conservative pass — not yet validated against real outcomes. §6's backtest harness is
  what the spec names as the actual validation step; treat the numbers in
  `PERSONALITY_PROFILES` as a reasonable starting point, not a tuned result.

### 2. §5 Phase 3 — Shadow-Logging Call Site — 🟢/🟡 DONE, enabled by default
- **New file:** `brain/faie/shadow_logging.py` — `build_shadow_decision(ctx)` (pure) and
  `log_faie_shadow_decision(ctx, real_decision_summary=None, log_path=None)` (I/O, never raises,
  returns `False` on any failure instead).
- **New settings:** `core/settings.py` — `FAIE_SHADOW_LOGGING_ENABLED` (env-overridable, default
  `False`) and `FAIE_SHADOW_LOG_PATH` (`data/faie/shadow_log.jsonl`).
- **Deviation from the spec's assumed call site, and why:** the spec guessed the call site
  "differs by strategy — `core/daily/signal.py`, `core/scalping_engine.py`,
  `core/smc_entry_engine.py`, `core/micro_trading_engine.py`". That's not how the current
  codebase is actually wired: `main.py` builds one `DecisionContext` per cycle and calls
  `core.fer3on_decision_authority.decide_trade(ctx)` — a single facade already documented as
  "Single Decision Authority" — which is what actually reaches `unified_decide()` for every
  strategy. The shadow-logging call site was added **there** (`decide_trade()`), plus a matching
  sidecar block in `main.py` right after it (mirroring the existing "PHASE 3 — Institutional
  Shadow Architecture" sidecar already in that file, same try/except-wrapped, never-blocks
  pattern). One call site instead of four, functionally equivalent coverage, no engine touched.
- **Tests:** `tests/faie/test_shadow_logging.py` (8 tests) — constitutional no-execution-token
  scan, Decision object shape, personality-profile usage, JSONL append correctness,
  `real_decision_summary` passthrough, never-raises-on-bad-path, settings default.
- **Manually verified end-to-end** (see session transcript): with
  `FAIE_SHADOW_LOGGING_ENABLED=1`, `brain.faie.log_faie_shadow_decision()` successfully imports
  and appends a well-formed JSON line; with the flag unset (default), `main.py` imports cleanly
  with no FAIE-related output at all, confirming the sidecar is a true no-op when disabled.

### 3. §3.3 Execution Quality Engine (post-trade) — 🟡 DONE
- **New file:** `analytics/execution_quality.py` — `record_execution_outcome(...)` (append-only,
  never raises) and `summarize_execution_quality()` (missing fields excluded from aggregates,
  never fabricated as zero).
- **New setting:** `core/settings.py` — `EXECUTION_QUALITY_CSV` (`data/analytics/execution_quality.csv`).
- **Wired into:** `core/trade_executor.py::execute_trade()` at both outcomes that matter —
  right after a broker rejection (`retcode != TRADE_RETCODE_DONE`) and right after a confirmed
  fill (`✅ TRADE EXECUTED`) — each call wrapped in its own `try/except` on top of the function's
  own internal guard (defense in depth; a logging failure can never surface as an execution
  error). Pre-send guard-clause rejections (hedge block, per-strategy limit, daily cap, missing
  SL/TP) are deliberately **not** recorded here — no order was actually attempted at the broker
  for those, so there is no slippage/delay/rejection-at-broker to measure.
- **Tests:** `tests/test_execution_quality.py` (7 tests) — CSV creation, slippage/delay
  computation, rejection exclusion from aggregates, unwritable-path safety, empty-file handling,
  mixed fill/rejection rate, missing-field exclusion (not zero-fill).

### 4. §3.4 Portfolio Intelligence — 🟡 DONE
- **New file:** `analytics/portfolio_intelligence.py` — `assess_correlated_exposure(open_trades)
  -> PortfolioRiskNote`, read-only over `core.portfolio_risk_authority`'s existing
  `open_trades` shape. Symbol is read from a trade's own `symbol` key if present, else its
  `meta` dict, else `"UNKNOWN"` — `record_trade_open()` was **not** modified to add a `symbol`
  field, keeping this item strictly read-only as the spec requires.
- **Wired into:** `brain/faie/analysts.py::RiskOfficer.analyze()` — appended to the existing
  `notes` string (not replacing it), inside the same `try/except` that already builds the
  portfolio snapshot note.
- **Tests:** `tests/test_portfolio_intelligence.py` (9 tests) — empty/single-trade no-conflict
  cases, multi-trade flagging, net exposure netting across directions, symbol resolution from
  `meta`, malformed-input safety, JSON-shape check. Plus 2 integration tests added to
  `tests/faie/test_faie_master_brain.py` proving `RiskOfficer` surfaces the note and that no
  `hard_gate`-tagged evidence is ever produced from correlated exposure alone (i.e. it stays a
  visibility layer, never a blocking one).

### 5. §6 Historical Backtest Harness — 🔴 DONE
- **New file:** `testing/faie_backtest.py` — `run_faie_backtest(history_rows=None, csv_path=None,
  max_disagreement_cases=200) -> FaieBacktestReport` plus `run_faie_backtest_by_period(...)`
  (chronological split into N periods, built specifically to feed item 6 below).
- **New runner:** `run_faie_backtest.py` — writes a full JSON report to
  `data/faie/backtest/backtest_report_<timestamp>.json` and prints a summary.
- **Deviation from the spec's assumed data source, and why:** the spec assumed
  `testing/backtester.py` already replays historical `DecisionContext` sequences. After reading
  that module, it doesn't — it replays raw OHLC `rates` arrays and generates its own synthetic
  signals internally; no historical `DecisionContext` has ever existed for a real past trade,
  only the trade's final outcome (`data/history/trades.csv`: `date, ticket, signal, lot, profit,
  result, strategy, session, market_regime, exec_grade, rr_ratio, quality_score, brain_score`).
  `run_faie_backtest()` therefore builds a **best-effort partial** `DecisionContext` per row from
  exactly the fields that CSV actually has (`signal`, `strategy`, `session`, `market_regime`,
  `rr_ratio`, `quality_score`, `brain_score`); every other `DecisionContext` field is left at its
  own dataclass default (legitimate "no evidence" state, not a fabricated value). It then
  compares FAIE's `top_scenario.direction` against the direction actually traded (`signal`) as a
  **proxy** for "what the real decision was" — there is no stored `unified_decide()` result to
  compare against directly. **This is a real, stated limitation, not a hidden one** — read the
  module's own docstring before treating any number from this report as more precise than it is.
- **Real result, generated in this session** against the full 642-row `data/history/trades.csv`:
  0 rows skipped, 642 evaluated, **agreement_rate = 89.3%** (573 agreements, 69 opposite
  disagreements, 0 neutral calls), 33 historical losing trades FAIE's lean would have avoided,
  36 historical winning trades it would have missed. See "A real finding worth a human's
  attention" below for a follow-up observation from the same data.
- **Tests:** `tests/test_faie_backtest.py` (16 tests) — row-to-context mapping (valid/missing
  signal/invalid signal/missing strategy/unknown strategy/malformed numeric field), no-data and
  insufficient-data statuses, agreement-rate bounds and count consistency, OPEN-trade exclusion
  from win/loss lists, mixed skip/valid row counting, disagreement-case capping, never-raises on
  malformed rows, JSON shape, and an integration smoke test against the real
  `data/history/trades.csv` file.

### 6. §4 Self Audit — 🟡 DONE
- **New file:** `certification/self_audit.py` — `detect_bias()`, `detect_drift()`,
  `detect_overfitting()`, plus `load_shadow_log_decisions()`, `split_recent_vs_baseline()`,
  `build_self_audit_report()`, and `write_self_audit_report()` (→
  `data/analytics/self_audit_<date>.json`, matching `certification/framework.py`'s
  `STATUS_JSON` convention).
- **New runner:** `run_faie_self_audit.py` — loads whatever `data/faie/shadow_log.jsonl` history
  exists (real accumulated decisions from §5's call site) for bias/drift, and
  `testing.faie_backtest.run_faie_backtest_by_period()` over `data/history/trades.csv` for
  overfitting (this doesn't need the shadow log at all, so it's usable immediately, unlike
  bias/drift).
- **`detect_bias`** implements the spec's exact bias signature: flags when
  `top_scenario.direction` is skewed ≥70% toward one side *while*
  `fused_evidence.net_score`'s sign is <60% one-sided over the same window — decision skew not
  matched by evidence skew, the spec's own definition of "a scenario-engine bug, not market
  truth." A synchronized skew (both direction and net_score lean the same way) is correctly
  **not** flagged, since that's what a real trend looks like.
- **`detect_drift`** compares two independent signals per analyst between an older and newer
  window, computed only where both windows actually have data for that analyst (skipped
  entirely otherwise, never fabricated): mean `net_score` shift beyond 25 points, and a ≥30
  percentage-point jump in how often that analyst reports `partial` — the spec's own named
  signature of "an analyst that's stopped reporting real evidence and defaulted to NEUTRAL."
- **`detect_overfitting`** compares any two periods' worth of numeric metrics
  (`win_rate`/`profit_factor`/`agreement_rate`/...), flagging ≥20% relative degradation from the
  first period to the last. Stated limitation in the docstring: assumes "higher is better" for
  every metric passed in — a "lower is better" metric like `max_drawdown` needs separate
  handling, not blind trust in its `flagged` value.
- **Real result, generated in this session:** with only two periods derived from
  `data/history/trades.csv` (`in_sample` = first half, `out_of_sample` = second half),
  agreement_rate dropped from **96.3% → 82.2%** (14.6% relative degradation — under the 20%
  flag threshold, so correctly *not* flagged, but worth a human's attention; see below).
  Bias/drift correctly returned `INSUFFICIENT_DATA` — `data/faie/shadow_log.jsonl` doesn't exist
  yet because `FAIE_SHADOW_LOGGING_ENABLED` has never run in the live loop. **This is the
  correct behavior, not a bug**: the spec explicitly requires `INSUFFICIENT_DATA` over a
  false-confidence conclusion.
- **Tests:** `tests/test_self_audit.py` (20 tests) — bias insufficient-data floor, flagging a
  synthetic bug signature, not flagging a genuine synchronized trend, accepting real `Decision`
  objects via `.to_dict()`; drift insufficient-data floor, flagging a large mean shift, not
  flagging a stable analyst, flagging a broken-analyst partial-rate jump, skipping (not
  fabricating) an analyst missing from one window; overfitting insufficient-data floor,
  flagging real degradation, not flagging stable metrics, skipping non-numeric metrics;
  chronological split correctness; shadow-log loading (missing file, malformed lines skipped);
  combined report building and JSON persistence.

### A real finding worth a human's attention (not an implementation task)

The backtest harness and self-audit's overfitting check, run against the same 642-row history in
this session, independently point at the same thing: FAIE's directional agreement with what was
actually traded is meaningfully higher in the first half of the available history (96.3%) than
the second half (82.2%, and 89.3% overall). This is exactly the kind of pattern §4's overfitting
check exists to surface — and it surfaced it correctly, on the first real run, without needing
any tuning. It sits just under the 20% flag threshold used in this pass, so it was **not** auto-
flagged, but it's the kind of number a human reviewing `docs/FAIE/PHASE_2_SPECIFICATION.md §7`'s
gate conditions before Paper Trading should look at directly rather than only trusting the
boolean `flagged` field. No code change is being proposed here — this is exactly the kind of
judgment call §7 reserves for a human, not an AI session.



### 7. §3.2 Institutional Session Engine (upgrade) — 🟡 DONE
- **New analyst:** `brain/faie/analysts.py::SessionAnalyst` — FAIE's 10th analyst, registered in
  `DEFAULT_ANALYSTS`. Thin adapter over the existing, unmodified `core/session_intelligence.py`
  (`detect_session_phase`, `get_phase_modifiers`) — no re-implementation.
- **Deviation from the spec's assumed data availability, and why:** the spec assumed
  `DecisionContext` already carries enough to call `detect_session_phase(hour, minute)` directly.
  It didn't — `DecisionContext` only had a coarse `session` string (`'ASIA'`/`'LONDON'`/...), no
  `hour`/`minute` at all. Rather than guess "now" for every context (wrong for historical
  replay) or skip the fine-grained read entirely (wrong for live trading, where a real hour is
  genuinely available), `DecisionContext` gained two new optional fields —
  `hour: Optional[int] = None` and `minute: int = 0`, both backward-compatible defaults, every
  existing caller unaffected. `core/unified_bridge.py::build_decision_context()` (the live-loop
  factory `main.py` actually calls) now defaults `hour`/`minute` to the real current UTC time
  when the caller doesn't pass one explicitly — genuinely correct there, since that factory is
  only ever called for "right now." `testing/faie_backtest.py`'s historical-row loader
  deliberately leaves `hour` as `None`, since a past trade's exact minute was never stored.
- **`SessionAnalyst` behavior:** with a real `ctx.hour`, calls `detect_session_phase()` for a
  genuine sub-window read (e.g. `LONDON_SWEEP`, confidence 65). Without one, falls back to a
  coarse mapping from `ctx.session` alone at visibly lower confidence (30) and a note flagging
  it as a degraded read — never silently claims precision it doesn't have. Reports a 0-100
  "liquidity window strength" score as `NEUTRAL`-direction evidence (window quality, not a
  directional lean — same established pattern as `RiskOfficer`/`PsychologyAnalyst`; NEUTRAL
  evidence always nets to 0 in fusion by design, so this never moves `top_scenario.direction`
  on its own, only informs `notes`/explainability/future consumers).
- **Fusion weights rebalanced:** `brain/faie/fusion.py::DEFAULT_WEIGHTS` and every profile in
  `brain/faie/personality.py::PERSONALITY_PROFILES` gained a `SessionAnalyst` entry (all still
  sum to 1.0). XAUUSD weighted it highest (0.10) given gold's session-liquidity sensitivity;
  GBPUSD/EURUSD lower (0.06), consistent with the rationale already documented in
  `personality.py`.
- **Tests:** `tests/faie/test_session_analyst.py` (14 tests) — registration/weight-sum checks
  across all profiles, real-hour fine-grained phase + tags, weak-window flagging, always-NEUTRAL
  bias across all 24 hours, zero net-score contribution by design, coarse fallback without an
  hour, lower confidence on the fallback, unknown-session graceful handling, never-guesses-now
  guarantee, and `ChiefDecisionOfficer`/backtest-harness integration. Plus
  `tests/test_unified_bridge_session.py` (4 tests) for `build_decision_context()`'s new
  hour/minute wiring specifically (explicit override, real-UTC-now default, minute defaulting,
  end-to-end usability by `SessionAnalyst`).

### 8. Explainability reconciliation — investigated, documented, not merged
- **New file:** `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md` — the deliverable for this item.
- **What was found, after actually reading `fer3on_masr/`:** it is not a stale duplicate of
  FAIE's explainability layer — it's a separate, self-contained, still-actively-developed
  prototype application (`fer3on_masr/app.py` / `run_masr.py`, its own kernel, agents, director,
  learning center) that runs standalone (`python3 -m fer3on_masr.app`) against `rates` passed in
  directly, producing a demo JSON output. It is explicitly documented in the repo's own
  `IMPLEMENTATION_STATUS_MASR.md` as not connected to live trading. Its `ExplainabilityService`
  explains a completely different data model (`ExecutionPlan`/`StrategyDecision`) than FAIE's
  `Decision` object, and **the two never run against the same decision in the same process.**
- **Why no code merge was performed:** merging them would require picking a winner between two
  independently-developed, independently-tested architectures (`fer3on_masr/`'s broader
  "clean-room" kernel rewrite vs. FAIE's narrower layer built directly on the existing, certified
  `core/` pipeline) — an architectural call about `fer3on_masr/`'s actual future (promoted,
  kept as a lab environment, or retired) that this session has no basis to make unilaterally.
  Forcing an adapter between them today would add a dependency between two systems that don't
  currently need each other, for no functional benefit.
- **What this deliverable actually contains:** a full comparison table (ownership, entry point,
  data model, live-data status, test coverage) and a concrete list of what a real merge would
  need to decide, so whichever human makes that call later has a ready starting map instead of
  having to re-derive it.



## Shadow logging enabled — explicit human decision, 2026-07-09

The account owner reviewed everything above and approved turning shadow logging on by default,
specifically to start accumulating real decision history for `certification/self_audit.py`'s
bias/drift checks (which cannot report anything beyond `INSUFFICIENT_DATA` without it).

**What changed:** `core/settings.py::FAIE_SHADOW_LOGGING_ENABLED` default flipped from `'False'`
to `'True'` (one line, still env-overridable — set `FAIE_SHADOW_LOGGING_ENABLED=False` to turn
it back off for any run without editing the file). Verified end-to-end in this session: with
the flag on, a real `decide_trade()` cycle followed by the same `log_faie_shadow_decision()` call
`main.py`'s sidecar makes produces a correctly-shaped line in `data/faie/shadow_log.jsonl`.

**What this does and does not mean:**
- Does: start writing one advisory `Decision` per real decision cycle to
  `data/faie/shadow_log.jsonl`, purely for later review.
- Does not: change sizing, gating, or execution in any way — same guarantees as §5's original
  design (never raises, never blocks, never read back into the real decision).
- Does not: constitute approval for Paper Trading or live execution influence — those remain
  separate, explicitly human-approved steps per Volume 1's constitution and Phase-2 spec §7.

**Recommended review cadence (agreed with the account owner):** run `run_faie_self_audit.py`
weekly once the bot has been running with this enabled, and review the bias/drift sections in
particular — they'll go from `INSUFFICIENT_DATA` to real numbers once
`MIN_DECISIONS_FOR_BIAS`/`MIN_DECISIONS_FOR_DRIFT` worth of history accumulates (see
`certification/self_audit.py`). A minimum of a few weeks of real operation was suggested before
treating any single self-audit report as conclusive, same reasoning as the backtest harness's
own confidence floor.

## What was deliberately NOT done across these passes, and why

Per §8's own suggested order, some items were held rather than built speculatively, and one
item was deliberately investigated-and-documented rather than coded:

- **§2.1 Elliott Wave Engine / §2.2 Correlation Engine** — held. The spec explicitly says "hold
  until a decision on Elliott's inherent ambiguity and Correlation's data source is made; don't
  build speculatively." Neither decision has been made across any of these passes.
- **§2.3 Real Volume/Order-Flow Engine** — not a coding task; blocked on whether the running
  MT5 environment actually has tick-volume/order-flow data available, which is a broker/account
  question for whoever owns that connection.
- **`fer3on_masr/`'s explainability service was not merged into FAIE's** — see item 8 above and
  `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md`. Investigated fully; merging would require an
  architectural decision about `fer3on_masr/`'s future that belongs to a human.
- **§7 Phases 8-10 (Paper Trading, Live, Full Rollout)** — explicitly human-gated, not coding
  tasks; nothing across any of these passes moves any of those gates, and nothing in these
  passes is capable of moving them on its own (the shadow-logging call site only ever appends a
  log line; the backtest/self-audit reports are inputs to a human's Paper Trading go/no-go, not
  a decision made on their own).

## Test status after this pass

- New/updated FAIE + analytics tests across all four passes: 101 total —
  `tests/faie/` = 45 (personality 8, shadow logging 8, master-brain + RiskOfficer/Portfolio
  Intelligence integration 15, session analyst 14), `tests/test_execution_quality.py` = 7,
  `tests/test_portfolio_intelligence.py` = 9, `tests/test_faie_backtest.py` = 16,
  `tests/test_self_audit.py` = 20, `tests/test_unified_bridge_session.py` = 4 — all passing.
- Full existing suite regression check: **433 passed, 1 skipped** (pre-existing, unrelated to
  this work), 17 subtests passed — no pre-existing test was modified to make it pass; all
  failures that would have indicated a real regression were absent.
- `main.py`, `core/trade_executor.py`, `core/unified_bridge.py`, and every new/modified module
  were also verified to import cleanly (`python3 -c "import ..."`) with
  `FAIE_SHADOW_LOGGING_ENABLED` both unset and explicitly enabled, confirming the sidecar is a
  true no-op when disabled.
- `run_faie_shadow.py`, `run_faie_backtest.py`, and `run_faie_self_audit.py` were all run
  end-to-end against real repo data at least once each across these passes — see the "Real
  result" notes above for what those runs actually produced, including after `SessionAnalyst`
  was added (backtest agreement rate unchanged at 89.3%, as expected for a `NEUTRAL`-only
  analyst that by design never moves `top_scenario.direction`).
- `run_faie_shadow.py`, `run_faie_backtest.py`, and `run_faie_self_audit.py` were all run
  end-to-end against real repo data (not just unit tests) at least once each in this session —
  see the "Real result" notes in sections 5 and 6 above for what those runs actually produced.

# FAIE — Roadmap (adapted to actual current state)

The original 10-step rollout plan assumed starting from an unstabilized codebase. This
roadmap documents the earlier V3.5+++ stabilization stage and maps the same 10 steps onto
the architecture that preceded the FER3ON-V100 package.

| # | Original step | Status here |
|---|---|---|
| 1 | Stabilize current architecture without breaking it | **DONE** — this is what V3.5 already is (Portfolio Risk Authority split, `core/settings.py` single source of truth, 242+ passing tests) |
| 2 | Introduce the Master Market Brain | **DONE** — `brain/faie/` — additive, shadow-mode only |
| 3 | Wire old engines into the new brain | **DONE, ENABLED — human-approved 2026-07-09** (Phase-2 spec §5) — `core/fer3on_decision_authority.py::decide_trade()` (the actual single "Single Decision Authority" call site used by `main.py`, not the four per-strategy sites originally guessed) now runs `ChiefDecisionOfficer` on the same `DecisionContext` and appends the advisory `Decision` to `data/faie/shadow_log.jsonl` via `brain/faie/shadow_logging.py`. Gated behind `FAIE_SHADOW_LOGGING_ENABLED` in `core/settings.py`, **now defaulting to `True` per the account owner's explicit decision** (see `docs/FAIE/PHASE_2_PROGRESS.md`) — still logging-only, never read back into the real decision, never raises into the real decision loop. |
| 4 | Add the new institutional engines | **DONE, except deliberately-held items** — Evidence Fusion, Contradiction Resolver, Scenario Engine, Market Personality Engine (`brain/faie/personality.py`), Execution Quality Engine (`analytics/execution_quality.py`), Portfolio Intelligence (`analytics/portfolio_intelligence.py`), Institutional Session Engine (`brain/faie/analysts.py::SessionAnalyst`) all done. Still open, held on purpose: Elliott Wave Engine, Correlation/Intermarket Engine (held per spec §8 — "don't build speculatively"), real Volume/Order-Flow Engine (blocked on a broker data-feed decision, not a coding task) — see `GAP_ANALYSIS.md`. |
| 5 | Activate the evidence fusion layer | **DONE**, in shadow mode |
| 6 | Activate the reasoning/explainability layer | **DONE**, in shadow mode |
| 7 | Full historical backtest | **DONE for FAIE** (Phase-2 spec §6) — `testing/faie_backtest.py::run_faie_backtest()` replays `data/history/trades.csv` through `ChiefDecisionOfficer` and compares its directional lean against what was actually traded. **Important limitation, stated honestly:** no historical `DecisionContext` or `unified_decide()` result was ever persisted — only the final trade outcome — so this is a best-effort partial-context replay compared against a proxy "real decision" (the direction actually traded), not a full internal-state replay. See that module's docstring and `docs/FAIE/PHASE_2_PROGRESS.md` before trusting a number from it in isolation. Legacy `testing/backtester.py` (OHLC-replay, unrelated to `DecisionContext`) is untouched. |
| 8 | Paper trading | **NOT DONE for FAIE** — the legacy pipeline appears to already support this (`BACKTEST_VALIDITY_NOTICE.md`, `test_mode_status.md`). Gate condition (Phase-2 spec §7): §6's backtest report reviewed (done — row 7) plus a human-decided minimum period of `FAIE_SHADOW_LOGGING_ENABLED=True` running in the live loop — **now in progress** as of 2026-07-09 (see `docs/FAIE/PHASE_2_PROGRESS.md`); recommended minimum observation period (a few weeks, reviewed weekly via `run_faie_self_audit.py`) has not elapsed yet, so Paper Trading remains not-yet-approved. |
| 9 | Small-risk live account with full monitoring | **NOT APPLICABLE YET** — blocked on 7 and 8, and requires a new, separately-reviewed code change per spec §7 (not an on-by-default flag) |
| 10 | Gradual transition to full institutional version | **NOT APPLICABLE YET** |

## Concrete next steps, in order

1. ~~**Market Personality Engine**~~ — **DONE**: `brain/faie/personality.py`, wired into
   `run_faie_shadow.py` and `brain/faie/shadow_logging.py`.
2. ~~**Phase 3 shadow-logging call site**~~ — **DONE**: see row 3 above. Still needs real
   operating time accumulated (`FAIE_SHADOW_LOGGING_ENABLED=True`) before it's useful as
   backtest/self-audit input.
3. ~~**Execution Quality Engine (post-trade)**~~ / ~~**Portfolio Intelligence**~~ — **DONE**:
   `analytics/execution_quality.py` (wired into `core/trade_executor.py::execute_trade`'s
   fill/reject paths) and `analytics/portfolio_intelligence.py` (wired into
   `brain/faie/analysts.py::RiskOfficer`'s existing notes field).
4. ~~**Backtest harness for FAIE**~~ — **DONE**: `testing/faie_backtest.py`. Real run against
   `data/history/trades.csv` (642 rows, 0 skipped): **89.3% agreement rate** between FAIE's
   directional lean and what was actually traded, flagging 33 historical losing trades FAIE
   would have leaned away from and 36 winning trades it would have missed — see
   `docs/FAIE/PHASE_2_PROGRESS.md` for the full run and its stated limitations (this is a
   best-effort partial-context replay compared against a proxy "real decision", not a full
   `unified_decide()` internal-state replay — no historical `DecisionContext` was ever
   persisted, only final trade outcomes).
5. ~~**Self Audit**~~ — **DONE**: `certification/self_audit.py` (`detect_bias`, `detect_drift`,
   `detect_overfitting`), runnable via `run_faie_self_audit.py`. Bias/drift correctly report
   `INSUFFICIENT_DATA` until `FAIE_SHADOW_LOGGING_ENABLED` has actually run in the live loop and
   accumulated decisions in `data/faie/shadow_log.jsonl` — that's the spec's own required
   failure mode (§4), not a gap. Overfitting detection works today against
   `data/history/trades.csv` via `testing.faie_backtest.run_faie_backtest_by_period()` and
   currently shows a real, not-yet-flagged-but-worth-watching drop in agreement rate between
   the first and second half of history (96.3% → 82.2%).
6. ~~**Reconcile the two explainability paths**~~ — **INVESTIGATED, documented, not merged**:
   `fer3on_masr/explainability/service.py` belongs to a separate, standalone prototype app
   (`run_masr.py` / `fer3on_masr/app.py`) that never runs against the same decision as
   `brain/faie/explainability.py` — they explain two different data models
   (`ExecutionPlan`/`StrategyDecision` vs. FAIE's `Decision`) in two systems that don't share a
   runtime today. Merging them would mean picking a winner between two independently-developed
   architectures, which is a human architectural call, not something resolved by writing an
   adapter. See `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md` for the full comparison and what a
   real merge would actually require if a human decides to pursue one.
7. ~~**§3.2 Institutional Session Engine upgrade**~~ — **DONE**: `brain/faie/analysts.py::
   SessionAnalyst`, a 10th analyst, thin adapter over the existing `core/session_intelligence.py`
   (unchanged). Reports `NEUTRAL`-direction "liquidity window strength" evidence — real
   sub-window precision (e.g. `LONDON_SWEEP`) when a real clock hour is available on the
   `DecisionContext` (now true end-to-end for the live loop, via `core/unified_bridge.py::
   build_decision_context()` defaulting to real UTC "now"), honest coarser/lower-confidence
   fallback from `ctx.session` alone otherwise (e.g. `testing/faie_backtest.py`'s historical
   replay, which has no real hour for a past trade and correctly never guesses one).
8. ~~Propose running `FAIE_SHADOW_LOGGING_ENABLED=True`~~ — **DONE, approved by the account
   owner on 2026-07-09**: the default in `core/settings.py` is now `True` (still env-overridable
   to `False` for any single run). This is still logging-only and does not by itself authorize
   Paper Trading — the recommended next step is a weekly `run_faie_self_audit.py` review over a
   few weeks of real operation before treating `certification/self_audit.py`'s bias/drift output
   as conclusive (see `docs/FAIE/PHASE_2_PROGRESS.md`). Everything else remaining (Elliott/
   Correlation/Volume engines, the explainability architectural call, Paper Trading → Live →
   Full Rollout) is a human decision, not an open coding task — see `GAP_ANALYSIS.md`'s bottom
   line.

## What was deliberately NOT done in this pass, and why

- **No changes to how `main.py` sizes, gates, or sends any order.** `FAIE_SHADOW_LOGGING_ENABLED`
  is now `True` by default (human-approved), but the call site it gates only ever appends a JSON
  log line — it cannot influence `runtime_decision`, `snapshot`, or any execution call. Volume 1
  rule 7 —
  staged rollout, never a big-bang cutover.
- **No fabricated Volume/Elliott/Correlation engines.** Building a fake-looking engine that
  produces numbers with no real data behind them would be worse than not having it; it was
  left as an explicit, tracked gap instead (see `GAP_ANALYSIS.md` and Phase-2 spec §2.1/§2.2).
- **No forced merge of `fer3on_masr/`'s explainability service into FAIE's.** They're two
  independently-runnable systems that don't share a runtime today (see
  `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md`) — merging them would mean making an
  architectural call about `fer3on_masr/`'s future that belongs to a human, not this session.
- **No attempt to implement all remaining volumes in one pass.** That would not be reviewable,
  testable, or safe to reason about for a live-money trading system. What was built across all
  four passes is scoped, tested, and runnable end-to-end — see `docs/FAIE/PHASE_2_PROGRESS.md`
  for the full accounting of what changed and the current full-suite test count.

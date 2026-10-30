# FAIE — Gap Analysis

Historical mapping of the 10-volume institutional vision against what existed in
`FER3ON-MASR-complete` at the time of this pass. This analysis predates the FER3ON-V100
package. Status legend: **EXISTS** (already implemented and
in the current pipeline), **PARTIAL** (implemented but not in the shape the vision describes,
or not wired end-to-end), **NEW-DONE** (built in this pass, additive, not yet wired live),
**MISSING** (not built anywhere yet).

| Volume | Vision | Current state | Status |
|---|---|---|---|
| 1. Project Constitution | Written rules no module may break | `README.md` / `README_MASR.md` already state "Single Decision Authority", "No engine deletion"; formalized in `docs/FAIE/VOLUME_1_CONSTITUTION.md` | **PARTIAL → NEW-DONE** |
| 2. System Architecture | Full box diagram, responsibilities/interfaces per box | `PROJECT_STRUCTURE.md`, `README_MASR.md` describe layout; no single formal per-module interface/failure-handling spec | **PARTIAL** |
| 3. Master Market Brain (analysts write reports, nobody executes, Chief Decision Officer synthesizes) | `brain/master_brain.py` (533 lines) computes composite scores directly — it *is* a scoring engine, not an analyst/report/CDO separation | `brain/faie/analysts.py` + `chief_decision_officer.py` — 9 analysts producing `Evidence`, none execute, `ChiefDecisionOfficer` synthesizes | **NEW-DONE** (runs alongside `master_brain.py`, does not replace it) |
| 4. Analysis Engines (Trend/SMC/Liquidity/Volume/Pattern/Elliott/Fib/Momentum/Session/Macro/News/Correlation/Volatility/Behavior + Fusion) | Most already exist: `core/trend_confluence.py`, `core/smc_advanced.py`, `core/session_intelligence.py`, `core/synthetic_orderflow.py`, `core/market_regime.py`, `brain/news_memory.py`. **No real Volume/tick-flow engine, no Elliott engine, no dedicated Correlation/Intermarket engine.** | Reused via `DecisionContext` fields in `brain/faie/analysts.py`; gaps marked honestly (`VolumeAnalyst` is `partial=True`) | **PARTIAL** |
| 5. Decision Engine (Evidence Graph, Decision Graph, Contradiction Graph, Scenario Ranking, Adaptive Weighting) | `core/unified_decision.py` (794 lines) is threshold/composite-score based, not evidence-graph based | `brain/faie/evidence.py` (Evidence Graph), `contradiction.py` (Contradiction Resolver), `scenario.py` (Scenario Engine), `fusion.py` (adaptive re-normalized weighting) | **NEW-DONE** |
| 6. Learning Architecture (Long/Short/Pattern/Trade/Market/Strategy memory, Adaptive Confidence not Adaptive Rules) | Extensive: `brain/trade_dna.py`, `core/market_memory.py`, `core/contextual_memory.py`, `core/dynamic_confidence.py`, `fer3on_masr/learning/{evolution,knowledge_graph,history_loader,center}.py` | Already covers most of this volume | **EXISTS** |
| 7. Risk Constitution (max risk/exposure/correlation/daily loss/etc., protections) | `risk/hard_risk_cap.py`, `core/portfolio_risk_authority.py`, `core/settings.py` (single source of truth per README V3.5), `core/loss_pause_guard.py`, `core/account_protection.py` | Strong existing coverage; `RiskOfficer` (FAIE) reads this read-only rather than duplicating it | **EXISTS** |
| 8. Explainability (human + machine explanation, rejected alternatives, trade review) | `fer3on_masr/explainability/service.py` — belongs to the separate `fer3on_masr/` standalone prototype app (`run_masr.py`), not connected to live trading | `brain/faie/explainability.py::ExplanationBuilder` — human + machine explanation with rejected scenarios, built directly on the new Decision object, wired into the real (optional, logging-only) live decision cycle | **NEW-DONE for FAIE; investigated, not merged, for `fer3on_masr`** — see `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md`: these two never run against the same decision (different data models, different runtimes), so merging them would mean picking a winner between two independently-developed systems — an architectural call reserved for a human, not resolved here. |
| 9. Self Audit (daily/weekly/monthly review, bias/overfitting/drift detection) | `certification/framework.py` + `certification_status.md` track win rate / profit factor / drawdown / Sharpe against 100/200-trade certification targets. No explicit bias/overfitting/drift detector yet. | Not touched in this pass | **PARTIAL** |
| 10. Live Trading Constitution (data integrity / broker ready / rollback / emergency stop gates before allowing live) | `risk/hard_risk_cap.py` (emergency stop), `core/data_integrity.py`, `core/watchdog.py`, `PHASE_1_ACCEPTANCE.md`, `PHASE_2_SAFETY_BOUNDARY.md`, `BACKTEST_VALIDITY_NOTICE.md` already gate phases explicitly | Not touched in this pass; FAIE is explicitly excluded from anything live per Volume 1 rule 7 | **EXISTS** (for the current pipeline) / **N/A for FAIE**, by design |

## New additions called out in the original plan

| Addition | Status |
|---|---|
| Evidence Fusion Engine | **NEW-DONE** — `brain/faie/fusion.py` |
| Scenario Engine | **NEW-DONE** — `brain/faie/scenario.py` |
| Contradiction Resolver | **NEW-DONE** — `brain/faie/contradiction.py` |
| Market Personality Engine (per-asset profiles/weights) | **NEW-DONE** — `brain/faie/personality.py` (Phase-2 spec §3.1); wired into `run_faie_shadow.py` and `brain/faie/shadow_logging.py` via `ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))`. |
| Institutional Session Engine | **NEW-DONE** — `brain/faie/analysts.py::SessionAnalyst` (Phase-2 spec §3.2), a thin adapter over the existing `core/session_intelligence.py` (unchanged). Reads a real `ctx.hour`/`ctx.minute` when the live loop provides one (now wired end-to-end: `core/unified_bridge.py::build_decision_context()` defaults to real UTC "now" for live callers) for a fine-grained sub-window read (e.g. `LONDON_SWEEP`), and degrades honestly to a coarser, lower-confidence read from `ctx.session` alone when no real clock time is available (e.g. `testing/faie_backtest.py`'s historical replay) — never guesses "now" for a context that isn't actually now. Reports `NEUTRAL`-direction evidence by design (window quality, not a directional lean), same established pattern as `RiskOfficer`/`PsychologyAnalyst`. |
| Execution Quality Engine (slippage/delay/rejection tracking feeding performance) | **NEW-DONE** — `analytics/execution_quality.py` (Phase-2 spec §3.3): `record_execution_outcome()` wired into `core/trade_executor.py::execute_trade()`'s fill and rejection paths; `summarize_execution_quality()` available for `certification/framework.py` or a future `RiskOfficer` evidence input (not yet consumed there — tracking only so far). |
| Portfolio Intelligence (correlated-risk accumulation across trades) | **NEW-DONE** — `analytics/portfolio_intelligence.py` (Phase-2 spec §3.4): `assess_correlated_exposure()` reads `core.portfolio_risk_authority.get_portfolio_state().open_trades` read-only and surfaces an informational note through `brain/faie/analysts.py::RiskOfficer`'s existing `notes` field. Does not gate or resize anything — `core.portfolio_risk_authority`'s existing diversification-vs-conflict rule is unchanged. |
| Shadow-logging call site (wiring FAIE next to the real decision loop) | **NEW-DONE, ENABLED** — `brain/faie/shadow_logging.py` (Phase-2 spec §5), called from `core/fer3on_decision_authority.py::decide_trade()` (the actual single decision-authority facade `main.py` uses, not the four per-strategy sites the spec initially guessed). Gated behind `FAIE_SHADOW_LOGGING_ENABLED` in `core/settings.py`, **defaulting to `True` since 2026-07-09 per the account owner's explicit approval** (see `docs/FAIE/PHASE_2_PROGRESS.md`). Logging-only; never raises into and never influences the real decision. |
| Elliott Wave Engine | **MISSING, held on purpose** — Phase-2 spec §2.1. Deliberately not built speculatively: wave counting is inherently ambiguous and the spec requires it not ship as non-partial until a backtest harness exists to validate it. |
| Correlation / Intermarket Engine | **MISSING, held on purpose** — Phase-2 spec §2.2. Needs a data-feed decision (DXY/US10Y/indices subscription in the running MT5 environment) before it can be built honestly rather than simulated. |
| Real Volume/Order-Flow Engine | **MISSING** — Phase-2 spec §2.3. Blocked on broker tick-volume/order-flow data availability, which is a data-availability question for whoever owns the broker connection, not a coding task. |
| Self Audit (bias/drift/overfitting) | **NEW-DONE** — `certification/self_audit.py` (Phase-2 spec §4): `detect_bias()`, `detect_drift()`, `detect_overfitting()`, runnable end-to-end via `run_faie_self_audit.py`. Bias/drift honestly report `INSUFFICIENT_DATA` until `data/faie/shadow_log.jsonl` has accumulated real decisions (the shadow-logging call site above makes that possible, but it hasn't run anywhere yet); overfitting detection already works today against `data/history/trades.csv` via `testing.faie_backtest.run_faie_backtest_by_period()`. |
| FAIE Backtest Harness | **NEW-DONE** — `testing/faie_backtest.py` (Phase-2 spec §6): `run_faie_backtest()` replayed `data/history/trades.csv` (642 rows) end-to-end, agreement_rate 89.3%. **Read the module's docstring before trusting this number in isolation** — no historical `DecisionContext` or `unified_decide()` result was ever persisted, only final trade outcomes, so this compares FAIE's directional lean against a *proxy* for "the real decision" (the direction actually traded), not a full replay of `unified_decide()`'s internal state. |

## Bottom line

This codebase is **not** starting from zero against the 10-volume vision — Volumes 6, 7, and
(mostly) 10 are already solidly built, tested (242+ existing tests), and running through a
Phase-1-certified pipeline. The genuinely new, missing pieces were concentrated in **Volume 3
and Volume 5** (the report → evidence → contradiction → scenario → decision chain), which an
earlier pass built, plus 3 of the 7 "new addition" engines.

A subsequent pass, following `docs/FAIE/PHASE_2_SPECIFICATION.md`, closed 4 more of the
remaining gaps: the **Market Personality Engine**, **Execution Quality Engine**, **Portfolio
Intelligence**, and the **§5 shadow-logging call site** (disabled by default) are now all
**NEW-DONE**. A third pass then closed the two largest remaining items: the **FAIE Backtest
Harness** (§6) and **Self Audit** (§4) — both **NEW-DONE**, with real results already generated
against `data/history/trades.csv` (89.3% agreement rate; a real, not-yet-flagged drop in
agreement rate between the first and second half of history worth a human's attention). A fourth
pass closed the **Institutional Session Engine upgrade** (§3.2, `SessionAnalyst`, now a 10th
analyst wired into live decisions with real clock-time awareness) and investigated the
explainability-reconciliation item — finding that the two "explainability paths" belong to two
independently-runnable systems that never share a runtime today, so no code merge was performed;
see `docs/FAIE/EXPLAINABILITY_RECONCILIATION.md`. See `docs/FAIE/PHASE_2_PROGRESS.md` for the
full accounting of all four passes. What remains: held deliberately, not speculatively built —
the **Elliott Wave**, **Correlation/Intermarket**, and **real Volume/Order-Flow** engines
(§2.1-§2.3), each blocked on either a data-source decision or an inherent-ambiguity decision
that only a human should make — and the human-gated rollout phases (§7: Paper Trading → Live →
Full Rollout), which no coding session can move on its own.

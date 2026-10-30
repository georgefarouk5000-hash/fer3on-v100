# PHASE 2 SAFETY BOUNDARY

**FER3ON V3+++ — Performance Intelligence Layer**
**Status: ACTIVE (Analytics-Only Mode)**

---

## The Golden Rule

> Phase 2 is a **read-only analytics sidecar**.
> It reads from the Truth Layer. It writes to `data/analytics/phase2/` only.
> It has **zero runtime influence**.

---

## What Phase 2 CAN do

| Action | Permitted |
|--------|-----------|
| Read from `analytics/truth_layer.py` | ✅ |
| Read closed decision snapshots (read-only) | ✅ |
| Write to `data/analytics/phase2/**` | ✅ |
| Generate JSON / Markdown reports | ✅ |
| Display results in dashboard (read-only tabs) | ✅ |
| Run offline via `tools/generate_performance_intelligence_reports.py` | ✅ |

---

## What Phase 2 CANNOT do

| Action | Forbidden |
|--------|-----------|
| Write to `data/analytics/adaptive_state.json` | ❌ FORBIDDEN |
| Write to `data/analytics/adaptive_trades.jsonl` | ❌ FORBIDDEN |
| Call `tune_thresholds()` | ❌ FORBIDDEN |
| Call `record_trade_outcome()` for Phase 2 purposes | ❌ FORBIDDEN |
| Import `core.session_intelligence` to alter behaviour | ❌ FORBIDDEN |
| Import `core.market_regime` to alter live labels | ❌ FORBIDDEN |
| Import `core.risk_manager` | ❌ FORBIDDEN |
| Import `core.unified_decision` | ❌ FORBIDDEN |
| Import `core.adaptive_learning` | ❌ FORBIDDEN |
| Set `PHASE2_RUNTIME_INFLUENCE = True` | ❌ FORBIDDEN |
| Set `activated = True` on any CalibrationCandidate | ❌ FORBIDDEN |

---

## Files NEVER to touch in Phase 2

```
main.py
core/unified_decision.py
core/risk_manager.py
core/portfolio_risk_authority.py
core/session_intelligence.py
core/market_regime.py
core/adaptive_learning.py
core/adaptive_floor.py
core/confidence_engine.py
core/adaptive_weighting.py
core/trade_executor.py
core/strategy_runners.py
```

---

## Files that MAY be lightly modified (additive only)

```
analytics/truth_layer.py     → helper read functions only, no metric changes
core/settings.py             → Phase 2 path/flag constants only
dashboard.py                 → read-only display tabs only
core/decision_snapshot.py    → logging enrichment only (no decision changes)
```

---

## Settings guarding this boundary

```python
PHASE2_RUNTIME_INFLUENCE       = False   # NEVER flip to True
PHASE2_SHADOW_CALIBRATION_ONLY = True    # shadow = no activation
```

Both are asserted on import in `analytics/adaptive_shadow_prep.py` and
`analytics/performance_repository.py`. Any attempt to set `PHASE2_RUNTIME_INFLUENCE = True`
will raise an `AssertionError` before any analysis runs.

---

## Output directories

```
data/analytics/phase2/reports/          → portfolio_statistics.json, phase2_summary.md
data/analytics/phase2/rankings/         → session_edge_ranking.json, regime_edge_ranking.json
data/analytics/phase2/contributions/    → module_contribution_report.json
data/analytics/phase2/shadow/           → shadow_state.json, shadow_calibration_candidates.json
```

All `calibration_candidates` objects carry `activated=False` and `advisory_only=True`.

---

## When to promote Phase 2 outputs to live influence

**Only after:**
1. Minimum 100 real trades per bucket (not test data)
2. Wilson CI on win rate < ±8%
3. Manual human review and explicit approval
4. Separate Phase 3 implementation with proper activation flags
5. Full regression test suite passing

**Not before.**

---

*Last updated: Phase 2 initial implementation*
*Author: FER3ON engineering*

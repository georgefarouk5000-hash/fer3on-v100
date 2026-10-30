# FAIE — Volume 1: Project Constitution

**Applies to:** everything under `brain/faie/`, `run_faie_shadow.py`, and any future FAIE volume.
**Status:** binding. No PR/patch touching this codebase may violate these rules, and CI (see
`tests/faie/test_faie_master_brain.py::TestConstitutionalSafety`) enforces rule 1 automatically.

## 1. No unilateral execution

No module inside `brain/faie/` may import, call, or reference anything capable of sending,
modifying, or cancelling a broker order (`trade_executor`, `execution_optimizer_v2`,
`MetaTrader5`, `order_send`, `order_close`, `place_order`, etc.). Every analyst produces a
**report**. Only `ChiefDecisionOfficer` synthesizes reports into a **Decision** — and that
Decision is advisory. It is enforced mechanically by a source-scan unit test, not just by
convention.

## 2. No engine deletion

This mirrors a rule the existing codebase already lives by (see `README.md`: *"No engine
deletion"*, and `README_MASR.md`: *"بدون حذف المحركات الأصلية"*). FAIE is a pure add-on layer.
It reads from `core.unified_decision.DecisionContext` — the project's own canonical input
struct — instead of re-implementing trend/SMC/liquidity/session logic that already exists in
`core/`, `brain/`, and `analytics/`.

## 3. Evidence before opinion

Every claim an analyst makes is an `Evidence` object with an explicit `direction`, `strength`,
`confidence`, `timeframe`, and `source` (a dotted path back to the exact existing field it came
from). Nothing is a bare number with an implied meaning.

## 4. Honesty about gaps

Where the current codebase does not yet expose a real signal (for example: no true tick/volume
feed on `DecisionContext` today), the corresponding analyst (`VolumeAnalyst`) must mark itself
`partial=True` and abstain (NEUTRAL, no evidence) rather than fabricate a plausible-looking
number. `EvidenceFusionEngine` re-normalizes weights to exclude partial analysts automatically,
so an honest gap doesn't silently get treated as a confident zero.

## 5. Disagreement must surface, not disappear

`ContradictionResolver` runs before any confidence number is produced. Averaging away
disagreement between analysts without reporting it is a constitution violation. The
`Decision.confidence` value is explicitly a function of *how much the leading scenario beats
the runner-up*, not just raw evidence volume.

## 6. Everything is reproducible and inspectable

`Decision.to_dict()` (machine explanation) must contain the full evidence graph, every analyst
report, the fused score, the contradiction report, and every scenario considered — including
the ones that were **not** chosen (`rejected_scenarios`). See Volume 8.

## 7. Staged rollout, never a big-bang cutover

FAIE runs in shadow mode (`run_faie_shadow.py`) until a human explicitly wires it into the live
loop. It never modifies `main.py`, `run_masr.py`, or anything in `core/unified_decision.py`.
See `docs/FAIE/ROADMAP.md` for the phase gate that has to be cleared before that happens.

## 8. Risk Officer is read-only inside FAIE

`RiskOfficer` (the FAIE analyst) only *reports* the existing `core.portfolio_risk_authority`
state (`get_portfolio_state()`, a read-only call). It never calls `evaluate_risk`,
`record_trade_open`, or anything else that mutates portfolio state. Sizing and hard-blocking
remain exclusively the job of the existing Portfolio Risk Authority, per the architecture this
project has already committed to:

```
Strategies -> Independent Evaluation -> Unified Decision -> Portfolio Risk Authority -> Execution
```

FAIE sits *beside* this pipeline as an explainability/second-opinion layer, not inside it,
until Phase 3 of the roadmap is explicitly approved and re-tested.

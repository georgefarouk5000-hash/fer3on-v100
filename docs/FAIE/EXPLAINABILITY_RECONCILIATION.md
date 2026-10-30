# FAIE — Explainability Reconciliation (§ ROADMAP item 6)

**Status: investigated and documented. No code merge performed — see "Why no merge" below.**

This document is the deliverable for the ROADMAP.md item "reconcile the two explainability
paths." Same principle as `docs/FAIE/PHASE_2_SPECIFICATION.md` §1 (Volume 2): where the honest
answer is a mapping and a documented decision rather than new code, the mapping *is* the
deliverable.

## What actually exists

| | `brain/faie/explainability.py` | `fer3on_masr/explainability/service.py` |
|---|---|---|
| Belongs to | FAIE (`brain/faie/`, `core/fer3on_decision_authority.py`) | `fer3on_masr/` — a separate package with its own kernel, agents, and director |
| Entry point | `core.fer3on_decision_authority.decide_trade()` → `main.py`'s live loop (optionally, behind `FAIE_SHADOW_LOGGING_ENABLED`) | `python3 -m fer3on_masr.app` / `run_masr.py` — a standalone process, run manually |
| Data model it explains | `brain.faie.chief_decision_officer.Decision` (Evidence → Scenario → Contradiction → Decision) | `fer3on_masr.kernel.models.ExecutionPlan` / `StrategyDecision` (its own `ExecutiveDirector`'s output) |
| Runs against real MT5 data? | Yes — same `DecisionContext` the real decision cycle uses | No — takes `rates: list[dict]` passed in directly; produces `data/fer3on_masr_demo_output.json` when run standalone (see `README_MASR.md`) |
| Test coverage | `tests/faie/` | `tests/fer3on_masr/` (5 files, referenced as "40 tests" in `README_MASR.md`) |
| Connected to live trading? | Logging-only today (§5), but wired into the real `DecisionContext` | Not connected to `main.py` / MT5 at all — explicitly documented as a demo/expansion layer in `IMPLEMENTATION_STATUS_MASR.md` ("ليست إعادة بناء مؤسسية مكتملة 100%... لكنها نسخة تطوير كاملة قابلة للتحميل") |

## The actual finding

**These two explainability services never run in the same process against the same decision.**
`fer3on_masr/` is not a competing explanation of what `main.py` decided — it's a separate,
self-contained prototype application (its own agents, its own director, its own learning
center) that a human runs manually and that produces its own demo output. `brain/faie/` is the
one wired (optionally) into the actual live decision loop.

So "reconciling" them by merging code would mean forcing two independently-tested,
independently-runnable systems — with genuinely different data models (`Decision` vs
`ExecutionPlan`/`StrategyDecision`) — into one, on the assumption that only one "real"
explainability layer should exist. That assumption isn't obviously true: `fer3on_masr` looks
like an earlier, broader "clean room" rewrite attempt (its own kernel/registry/event-bus/plugin
manager), while FAIE is a narrower, additive layer built directly on top of the existing,
certified `core/` pipeline. They may simply be two different experiments with different futures,
not two versions of the same thing.

## Why no merge was performed here

A real merge requires a decision this session has no basis to make on its own:

1. **Is `fer3on_masr/` meant to become the production pipeline eventually, stay a standalone lab
   environment, or be retired?** `README_MASR.md`'s own "Real-Data Activation" update shows it's
   still being actively developed as its own thing, with its own real-data wiring
   (`fer3on_masr/learning/history_loader.py` reading the same `data/history/trades.csv` FAIE's
   backtest harness reads) — it is not a dead prototype.
2. **If it's meant to converge with FAIE eventually, which data model wins** — `Decision`
   (Evidence/Scenario/Contradiction graph) or `ExecutionPlan`/`StrategyDecision`? Picking one
   silently would mean rewriting the other system's internals, which is a large, high-risk change
   for a live-money-adjacent codebase to make without an explicit human decision — exactly the
   kind of unilateral architectural call Volume 1's constitution reserves for a human.
3. **Forcing an adapter between the two today** (e.g. having `fer3on_masr`'s
   `ExplainabilityService` also accept a FAIE `Decision`, or vice versa) would create a
   dependency between two systems that currently don't need each other, for no functional
   benefit — nothing today reads both outputs together, so there is nothing to actually
   reconcile at the data level yet.

## Recommendation

Leave both as they are until a human makes an explicit call on `fer3on_masr/`'s future (promote
it, keep it as a parallel lab/prototype environment, or retire it). If/when that call is made,
this document is the starting map for whichever direction is chosen — the two data models above
are the actual translation surface a real merge would need to bridge, not the explainability
`build()`/`human_explanation()` methods themselves (those are thin, ~25-55 line adapters over
each system's own decision object; the real work in a merge would be upstream of them).

No code was changed for this item. `ROADMAP.md` and `GAP_ANALYSIS.md` are updated to point here
instead of listing this as an open "reconcile" coding task.

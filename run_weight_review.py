#!/usr/bin/env python3
# =============================================================================
# FER3ON — Weight Review Runner (manual, report-only, with shadow P&L sim)
# =============================================================================
# [FER3ON-FIX-2026-08-20] Revision 2 of the staged plan to (eventually) wire
# self_optimizer.py / adaptive_weighting.py into the live decision. Revision
# 1 just printed both engines' "changes" list. This revision incorporates
# two findings from reviewing that output:
#
#  1. self_optimizer.py and adaptive_weighting.py independently compute the
#     SAME 5 live knobs (SCALP/SMC/DAILY/SWING_threshold, min_rr) with
#     different sample-size gates (5 vs 10 trades), different win-rate bands
#     (40%/65% vs 35%/68%), and different min_rr formulas (adaptive_weighting
#     requires avg_rr AND profit_factor to both be weak; self_optimizer only
#     checks avg_rr). Running both as live sources would fight over the same
#     values. self_optimizer.py is therefore FROZEN here: shown for
#     reference/comparison only, its own state file is deliberately NOT
#     written (no _save_state call — see run_frozen_self_optimizer_reference
#     below), and adaptive_weighting.py is treated as the sole candidate
#     source for any future wiring.
#
#  2. A win-rate-driven threshold suggestion can look statistically correct
#     while quietly discarding net-profitable trades (raising a quality
#     floor to fix a win rate can filter out low-frequency, high-R:R winners
#     just as easily as it filters out losers). So instead of just printing
#     "changes", this script re-walks the SAME sample of already-executed,
#     build-filtered trades adaptive_weighting analyzed and asks: which of
#     them would have passed the OLD threshold vs the NEW one, and what was
#     their combined real P&L under each? That is a genuine, if partial,
#     answer to "does this suggestion make or lose money" — see the caveat
#     printed at the end of the shadow section for what it does NOT model.
#
# Still report-only: nothing here is applied to the live decision path.
# adaptive_weighting.py still only writes its own state file
# (data/analytics/adaptive_weights.json); nothing else in the repo reads it
# yet (see the CHANGELOG / conversation this script came out of).
#
# Usage:
#   PYTHONPATH=. python3 run_weight_review.py
# =============================================================================

from __future__ import annotations

import sys

from core.ai_memory import load_memory_records
from core.build_scope import filter_current_build_rows
from core.self_optimizer import _analyze_trades, _adjust_weights, get_optimizer_weights, CYCLE_SIZE
from core.adaptive_weighting import (
    _deep_analyze,
    _compute_new_weights,
    get_adaptive_weights,
    run_adaptive_weighting,
    MIN_TRADES_FOR_ADAPT,
)

# session name -> the multiplier key adaptive_weighting.py adjusts for it
_SESSION_MULT_KEYS = {
    "LONDON": "london_mult",
    "NEWYORK": "ny_mult",
    "ASIA": "asia_mult",
    "OFF_HOURS": "off_mult",
}
_MULT_KEY_TO_SESSION = {v: k for k, v in _SESSION_MULT_KEYS.items()}
_METADATA_KEYS = {"_version", "_last_update", "_cycle", "_total_trades"}


def _fmt_money(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):.2f}"


# -----------------------------------------------------------------------
# Section 1: self_optimizer.py — FROZEN, reference only, read-only
# -----------------------------------------------------------------------
def run_frozen_self_optimizer_reference() -> dict:
    """
    Mirrors run_self_optimization()'s own gate logic exactly, but calls
    _analyze_trades()/_adjust_weights() directly and never calls
    _save_state() — self_optimizer.py's cycle/history/total_analyzed stay
    untouched. This is intentionally read-only: it exists so you can see
    what the older, looser engine would have suggested, for comparison
    against adaptive_weighting.py, without it advancing its own state as
    if it were still an active decision source.
    """
    stats = _analyze_trades(CYCLE_SIZE)
    if not stats or stats.get("total", 0) < 10:
        return {"ran": False, "reason": "INSUFFICIENT_DATA"}
    current_weights = get_optimizer_weights()
    new_weights, changes = _adjust_weights(stats, current_weights)
    return {"ran": True, "stats": stats, "changes": changes, "new_weights": new_weights}


def _print_self_optimizer_section(result: dict) -> None:
    print("-" * 70)
    print("1) core/self_optimizer.py — FROZEN / reference only (state NOT saved)")
    print("-" * 70)
    if not result.get("ran"):
        print(f"NOT RUN — {result.get('reason')}")
        return
    stats = result["stats"]
    print(f"sample={stats.get('total')} trades (wins={stats.get('wins')}, "
          f"losses={stats.get('losses')}, winrate={stats.get('winrate')}%, "
          f"avg_rr={stats.get('avg_rr')})")
    print("Would have suggested (for comparison against section 2 only):")
    if result["changes"]:
        for c in result["changes"]:
            print(f"   • {c}")
    else:
        print("   (no changes)")


# -----------------------------------------------------------------------
# Section 2: adaptive_weighting.py — the sole candidate source
# -----------------------------------------------------------------------
def _print_adaptive_weighting_section(result: dict) -> None:
    print("-" * 70)
    print("2) core/adaptive_weighting.py :: run_adaptive_weighting(force=True)")
    print("   (sole candidate source — state file IS saved, as designed)")
    print("-" * 70)
    if not result.get("ran"):
        extra = f"  (new_trades={result['new_trades']})" if "new_trades" in result else ""
        print(f"NOT RUN — {result.get('reason')}{extra}")
        return
    analysis = result["analysis"]
    print(f"cycle #{result.get('cycle')}  |  sample={analysis.get('total')} trades "
          f"(winrate={analysis.get('winrate')}%, avg_rr={analysis.get('avg_rr')}, "
          f"profit_factor={analysis.get('profit_factor')})")
    print("Suggested weight changes:")
    if result["changes"]:
        for c in result["changes"]:
            print(f"   • {c}")
    else:
        print("   (no changes — current weights already look optimal)")


# -----------------------------------------------------------------------
# Section 3: shadow P&L simulation of adaptive_weighting's changes
# -----------------------------------------------------------------------
def _simulate_threshold(rows: list, strategy: str, old_t: float, new_t: float) -> dict:
    strat_rows = [r for r in rows if str(r.get("strategy", "")).upper() == strategy.upper()]

    def _kept(threshold):
        kept = []
        for r in strat_rows:
            try:
                q = float(r.get("quality_score", 0) or 0)
            except Exception:
                q = 0.0
            if q >= threshold:
                kept.append(r)
        return kept

    def _pnl(kept):
        return sum(float(r.get("profit", 0) or 0) for r in kept)

    old_kept, new_kept = _kept(old_t), _kept(new_t)
    old_tickets = {r.get("ticket") for r in old_kept}
    new_tickets = {r.get("ticket") for r in new_kept}
    dropped = [r for r in old_kept if r.get("ticket") not in new_tickets]
    added = [r for r in new_kept if r.get("ticket") not in old_tickets]
    return {
        "sample_size": len(strat_rows),
        "old_threshold": old_t, "new_threshold": new_t,
        "old_kept": len(old_kept), "old_pnl": _pnl(old_kept),
        "new_kept": len(new_kept), "new_pnl": _pnl(new_kept),
        "dropped_count": len(dropped), "dropped_pnl": _pnl(dropped),
        "added_count": len(added), "added_pnl": _pnl(added),
    }


def _simulate_min_rr(rows: list, old_t: float, new_t: float) -> dict:
    def _kept(threshold):
        kept = []
        for r in rows:
            try:
                rr = float(r.get("rr_ratio", 0) or 0)
            except Exception:
                rr = 0.0
            if rr >= threshold:
                kept.append(r)
        return kept

    def _pnl(kept):
        return sum(float(r.get("profit", 0) or 0) for r in kept)

    old_kept, new_kept = _kept(old_t), _kept(new_t)
    old_tickets = {r.get("ticket") for r in old_kept}
    new_tickets = {r.get("ticket") for r in new_kept}
    dropped = [r for r in old_kept if r.get("ticket") not in new_tickets]
    return {
        "old_threshold": old_t, "new_threshold": new_t,
        "old_kept": len(old_kept), "old_pnl": _pnl(old_kept),
        "new_kept": len(new_kept), "new_pnl": _pnl(new_kept),
        "dropped_count": len(dropped), "dropped_pnl": _pnl(dropped),
    }


def _simulate_session_mult(rows: list, session: str, old_mult: float, new_mult: float) -> dict:
    # Multipliers scale position size, not accept/reject — approximate by
    # linearly scaling each trade's realised P&L by (new_mult/old_mult).
    # This assumes P&L scales linearly with lot size, which holds for a
    # pure position-size multiplier but ignores any broker minimum-lot
    # rounding at the edges.
    sess_rows = [r for r in rows if str(r.get("session", "")).upper() == session.upper()]
    actual_pnl = sum(float(r.get("profit", 0) or 0) for r in sess_rows)
    ratio = (new_mult / old_mult) if old_mult else 1.0
    simulated_pnl = actual_pnl * ratio
    return {
        "sample_size": len(sess_rows), "old_mult": old_mult, "new_mult": new_mult,
        "actual_pnl": actual_pnl, "simulated_pnl": simulated_pnl,
    }


def run_shadow_simulation(old_weights: dict, new_weights: dict, rows: list) -> None:
    print("-" * 70)
    print("3) SHADOW P&L SIMULATION — same sample, old vs new weights")
    print("-" * 70)
    changed_keys = [
        k for k in new_weights
        if k not in _METADATA_KEYS and old_weights.get(k) != new_weights.get(k)
    ]
    if not changed_keys:
        print("No weight changed this cycle — nothing to simulate.")
        return

    for key in changed_keys:
        old_v, new_v = old_weights.get(key), new_weights.get(key)
        if key.endswith("_threshold"):
            strategy = key[: -len("_threshold")]
            sim = _simulate_threshold(rows, strategy, old_v, new_v)
            print(f"\n{key}: {old_v} -> {new_v}  (quality_score gate, {strategy} trades, n={sim['sample_size']})")
            print(f"   OLD kept {sim['old_kept']} trades -> net {_fmt_money(sim['old_pnl'])}")
            print(f"   NEW kept {sim['new_kept']} trades -> net {_fmt_money(sim['new_pnl'])}")
            if sim["dropped_count"]:
                verdict = "would have GIVEN UP" if sim["dropped_pnl"] > 0 else "would have AVOIDED"
                print(f"   -> {sim['dropped_count']} trades newly excluded, "
                      f"combined {_fmt_money(sim['dropped_pnl'])}: {verdict} this money")
            if sim["added_count"]:
                print(f"   -> {sim['added_count']} trades newly included, "
                      f"combined {_fmt_money(sim['added_pnl'])}")
        elif key == "min_rr":
            sim = _simulate_min_rr(rows, old_v, new_v)
            print(f"\nmin_rr: {old_v} -> {new_v}  (rr_ratio gate, all strategies)")
            print(f"   OLD kept {sim['old_kept']} trades -> net {_fmt_money(sim['old_pnl'])}")
            print(f"   NEW kept {sim['new_kept']} trades -> net {_fmt_money(sim['new_pnl'])}")
            if sim["dropped_count"]:
                verdict = "would have GIVEN UP" if sim["dropped_pnl"] > 0 else "would have AVOIDED"
                print(f"   -> {sim['dropped_count']} trades newly excluded, "
                      f"combined {_fmt_money(sim['dropped_pnl'])}: {verdict} this money")
        elif key in _MULT_KEY_TO_SESSION:
            session = _MULT_KEY_TO_SESSION[key]
            sim = _simulate_session_mult(rows, session, old_v, new_v)
            print(f"\n{key} ({session}): {old_v} -> {new_v}  "
                  f"(position-size multiplier, n={sim['sample_size']}, LINEAR APPROXIMATION)")
            print(f"   Actual P&L at old size:    {_fmt_money(sim['actual_pnl'])}")
            print(f"   Simulated P&L at new size: {_fmt_money(sim['simulated_pnl'])}")
        else:
            print(f"\n{key}: {old_v} -> {new_v}")
            print("   (no P&L simulation — this is a scoring-component weight, not an "
                  "accept/reject filter or size multiplier; simulating it would mean "
                  "re-scoring every trade with the new weights, not just refiltering "
                  "recorded outcomes)")

    print("\nCAVEAT: this only re-filters/re-scales trades that were ALREADY taken.")
    print("It does not model trades the bot might have taken instead under a looser")
    print("threshold, or skipped under a stricter one, nor any change in exposure")
    print("timing. Treat it as a sanity check on the suggestion, not a backtest.")


def main() -> int:
    current_build_trades = len(filter_current_build_rows(load_memory_records()))

    print("=" * 70)
    print("FER3ON — WEIGHT REVIEW (manual, report-only, force=True)")
    print("=" * 70)
    print(f"Current-build trades available: {current_build_trades}")
    print("Both engines require a minimum sample even with force=True "
          "(self_optimizer: 10, adaptive_weighting: 20).")
    print("Reminder: even if a suggestion below looks good, nothing currently")
    print("reads adaptive_weights.json live, and the one place that COULD")
    print("(core/quality_score.py::evaluate_quality_gate's optimizer_weights=")
    print("param) is separately bypassed right now by QUALITY_SCORE_TRUST_ENABLED")
    print("=False (quality_score inversion bug, unrelated FER3ON-FIX-2026-08-19).")

    opt_result = run_frozen_self_optimizer_reference()
    _print_self_optimizer_section(opt_result)

    old_weights = get_adaptive_weights()
    adapt_result = run_adaptive_weighting(force=True)
    _print_adaptive_weighting_section(adapt_result)

    if adapt_result.get("ran"):
        rows = filter_current_build_rows(load_memory_records())[-MIN_TRADES_FOR_ADAPT:]
        run_shadow_simulation(old_weights, adapt_result["new_weights"], rows)

    print("=" * 70)
    print("Nothing above was applied to the live decision path. "
          "self_optimizer.py stayed frozen (no state written); "
          "adaptive_weighting.py wrote data/analytics/adaptive_weights.json "
          "as the sole candidate source, but nothing else in the repo reads "
          "it yet. To act on a suggestion, change the corresponding live "
          "constant by hand.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

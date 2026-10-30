#!/usr/bin/env python3
# =============================================================================
# FAIE — Shadow Mode Runner
# =============================================================================
# Runs the new Master Market Brain (brain/faie) on a DecisionContext and
# writes an explainable Decision to data/faie/decisions/. This script is
# DELIBERATELY separate from main.py / run_masr.py: it does not touch the
# live decision or execution path. This is the safe way to observe what
# FAIE would say, in parallel with the existing system, before Phase 3 of
# the roadmap ("wire old engines into the new brain") is approved.
#
# Usage:
#   PYTHONPATH=. python3 run_faie_shadow.py
#
# In real operation, replace `build_sample_context()` with whatever already
# builds a DecisionContext in your live loop (core.unified_decision is
# already fed by the existing engines — reuse that same object here).
# =============================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

from core.unified_decision import DecisionContext
from brain.faie import ChiefDecisionOfficer, ExplanationBuilder, get_profile


def build_sample_context() -> DecisionContext:
    """Illustrative context only — replace with a real one in production."""
    return DecisionContext(
        strategy="SMC",
        signal="BUY",
        symbol="XAUUSD",
        market_regime="TRENDING",
        session="LONDON",
        trend_strength=62.0,
        market_structure="BULLISH_BOS",
        mtf_alignment_mode="ALIGNED",
        smc_strength=7.2,
        smc_entry_confirmed=True,
        sweep_probability=58.0,
        liquidity_strength=61.0,
        liquidity_alignment=59.0,
        candle_trigger_confirmed=True,
        candle_bonus=4.0,
        candle_penalty=0.0,
        spread_ratio=0.12,
        atr_sufficient=True,
        rr_ratio=1.8,
    )


def main() -> int:
    ctx = build_sample_context()

    # §3.1 Market Personality Engine — per-symbol fusion weight profile
    # instead of the flat DEFAULT_WEIGHTS every symbol used before.
    cdo = ChiefDecisionOfficer(fusion_weights=get_profile(ctx.symbol))
    decision = cdo.decide(ctx)

    explainer = ExplanationBuilder()
    human = explainer.human_explanation(decision)
    machine = explainer.machine_explanation(decision)

    out_dir = Path("data/faie/decisions")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"decision_{stamp}.json"
    out_path.write_text(json.dumps(machine, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 70)
    print("FAIE SHADOW DECISION (advisory only — not wired to execution)")
    print("=" * 70)
    print(human)
    print("-" * 70)
    print(f"Full machine explanation written to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

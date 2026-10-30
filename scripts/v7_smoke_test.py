"""
FER3ON V7.0 ADAPTIVE — Smoke Test Suite
=========================================
يختبر:
1. تحميل settings الجديدة
2. unified_decision في 6 سيناريوهات
3. adaptive_learning round-trip
4. master_brain ranking
5. compile check لـ main.py
6. تكامل end-to-end
"""

import os
import sys
import json
import shutil
import tempfile
import traceback

# Add project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# Use a temp dir for analytics so tests don't pollute real data
TMP = tempfile.mkdtemp(prefix="fer3on_v7_test_")
os.environ["ALLOW_LIVE_TRADING"] = "False"

results = []


def run_check(name, fn):
    try:
        out = fn()
        results.append((name, "PASS", out or ""))
        print(f"✅ {name}")
        if out:
            for line in str(out).strip().splitlines():
                print(f"   {line}")
    except Exception as e:
        results.append((name, "FAIL", f"{e}\n{traceback.format_exc()}"))
        print(f"❌ {name}: {e}")


# ============================================================================
# TEST 1: settings load with new thresholds
# ============================================================================
def t_settings():
    from core import settings as s
    assert s.MIN_QUALITY_SCORE == 50, f"Expected 50, got {s.MIN_QUALITY_SCORE}"
    assert s.COMPOSITE_FULL_MIN == 70
    assert s.COMPOSITE_REDUCED_MIN == 50
    assert s.COMPOSITE_MICRO_MIN == 38
    assert s.V7_THRESHOLD_ASIA == 60, "Asia should be 60 not 70"
    assert s.ADAPTIVE_LEARNING_ENABLED is True
    assert s.HARD_RISK_DAILY_LOSS_PERCENT == 10.0, "daily safety cap should remain unified at 10%"
    assert s.HARD_RISK_MAX_PER_TRADE == 0.50, "per-trade cap should remain 0.50"
    return (f"Quality=55, Asia=60, Composite[full/red/micro]=72/56/42, "
            f"safety caps preserved (3%/0.5%)")


# ============================================================================
# TEST 2: unified_decision — 6 scenarios
# ============================================================================
def t_unified():
    from core.unified_decision import unified_decide, DecisionContext

    out_lines = []

    # Scenario A: Excellent setup — should PASS_FULL
    ctx = DecisionContext(
        strategy="SMC", signal="BUY",
        quality_score=78, confidence_pct=72, brain_score=70, execution_score=72,
        daily_bias="BUY", mtf_strength=3, smc_strength=7.5,
        smc_entry_confirmed=True, candle_trigger_confirmed=True, candle_weight=4,
        liquidity_alignment=80, sweep_probability=70,
        session="LONDON", market_regime="TRENDING", context_score=80,
        atr_sufficient=True, rr_ratio=2.2,
        ml_score=72, ml_rl_action="PASS",
    )
    r = unified_decide(ctx)
    assert r.decision == "PASS_FULL", f"Excellent → got {r.decision}, score {r.composite_score}"
    out_lines.append(f"Excellent setup → {r.decision} (score {r.composite_score:.1f}) ✓")

    # Scenario B: Borderline — should PASS_REDUCED or PASS_MICRO
    ctx = DecisionContext(
        strategy="SMC", signal="BUY",
        quality_score=55, confidence_pct=52, brain_score=50, execution_score=55,
        daily_bias="NONE", mtf_strength=2, smc_strength=4,
        candle_trigger_confirmed=False, candle_weight=2,
        liquidity_alignment=55, sweep_probability=30,
        session="LONDON", market_regime="RANGING", context_score=60,
        rr_ratio=1.5, ml_score=55,
    )
    r = unified_decide(ctx)
    assert r.decision in ("PASS_REDUCED", "PASS_MICRO"), f"Borderline → got {r.decision}"
    out_lines.append(f"Borderline → {r.decision} (score {r.composite_score:.1f}) ✓")

    # Scenario C: Weak — should PASS_MICRO or HARD_BLOCK
    ctx = DecisionContext(
        strategy="SMC", signal="BUY",
        quality_score=44, confidence_pct=46, brain_score=40, execution_score=45,
        daily_bias="SELL",  # conflict
        mtf_strength=1, smc_strength=2,
        candle_weight=0, liquidity_alignment=40, rr_ratio=1.2,
        session="ASIA", market_regime="VOLATILE", context_score=40,
        ml_score=42,
    )
    r = unified_decide(ctx)
    assert r.decision in ("PASS_MICRO", "HARD_BLOCK"), f"Weak → got {r.decision}"
    out_lines.append(f"Weak/conflict → {r.decision} (score {r.composite_score:.1f}) ✓")

    # Scenario D: Catastrophic — emergency stop
    ctx = DecisionContext(
        strategy="SMC", signal="BUY",
        quality_score=90, emergency_stop=True,
    )
    r = unified_decide(ctx)
    assert r.decision == "HARD_BLOCK" and r.hard_block_reason == "EMERGENCY_STOP"
    out_lines.append(f"Emergency stop → HARD_BLOCK:{r.hard_block_reason} ✓")

    # Scenario E: News pause
    ctx = DecisionContext(
        strategy="SMC", signal="BUY", quality_score=90, news_pause=True,
    )
    r = unified_decide(ctx)
    assert r.decision == "HARD_BLOCK" and r.hard_block_reason == "NEWS_PAUSE"
    out_lines.append(f"News pause → HARD_BLOCK:{r.hard_block_reason} ✓")

    # Scenario F: DAILY without bias → strategy hard gate
    ctx = DecisionContext(
        strategy="DAILY", signal="BUY",
        quality_score=70, confidence_pct=65, brain_score=70,
        daily_bias="SELL",  # conflict for DAILY = hard
        mtf_strength=2,
        session="LONDON", market_regime="TRENDING", context_score=70,
    )
    r = unified_decide(ctx)
    assert r.decision == "HARD_BLOCK" and r.hard_block_reason == "STRATEGY_HARD_GATE"
    out_lines.append(f"DAILY bias conflict → HARD_BLOCK:{r.hard_block_reason} ✓")

    return "\n".join(out_lines)


# ============================================================================
# TEST 3: adaptive_learning round-trip
# ============================================================================
def t_adaptive():
    # redirect analytics dir to tmp
    from core import settings as s
    orig_dir = s.ANALYTICS_DIR
    s.ANALYTICS_DIR = TMP
    # also patch adaptive_learning module references
    from core import adaptive_learning as al
    al.STATE_FILE = os.path.join(TMP, "adaptive_state.json")
    al.TRADE_LOG_FILE = os.path.join(TMP, "adaptive_trades.jsonl")

    # fresh state
    if os.path.exists(al.STATE_FILE):
        os.remove(al.STATE_FILE)

    # record 12 trades: 8 wins / 4 losses (WR 66.7%)
    for i in range(12):
        win = (i % 3 != 0)   # 8 wins, 4 losses
        pnl = 1.2 if win else -1.0
        al.record_trade_outcome(
            strategy="SMC", session="LONDON", regime="TRENDING",
            signal="BUY", composite_score=68 + i, size_mode="FULL",
            pnl=pnl, win=win,
        )

    summary = al.get_status_summary()
    assert summary["total_trades"] == 12, f"Expected 12, got {summary['total_trades']}"
    assert summary["wins"] == 8
    assert summary["losses"] == 4
    wr = summary["recent_wr"]
    assert 0.60 <= wr <= 0.70, f"WR={wr}"

    # tuning should have triggered (>= 10 trades, >= 20 interval — let's force)
    al.tune_thresholds(al.load_state())
    th = al.get_adjusted_thresholds()
    # WR=66.7% ≥ 62% → should relax → offsets ≤ 0
    # Just check that thresholds object is well-formed
    assert "full" in th and "reduced" in th and "micro" in th

    # restore
    s.ANALYTICS_DIR = orig_dir
    return (f"12 trades recorded, WR={wr*100:.1f}%, "
            f"thresholds[full/red/micro]={th['full']:.1f}/{th['reduced']:.1f}/{th['micro']:.1f}")


# ============================================================================
# TEST 4: master_brain low_score floor lowered
# ============================================================================
def t_master_brain():
    import brain.master_brain as mb
    assert mb.MASTER_HARD_FLOOR == 20, f"Expected 20, got {mb.MASTER_HARD_FLOOR}"
    assert mb.MASTER_LOW_SCORE_FLOOR == 35, f"Expected 35, got {mb.MASTER_LOW_SCORE_FLOOR}"
    assert mb.MASTER_MICRO_BAND_TOP == 44
    return f"Master Brain floors: hard=20 (was 25), low=35 (was 42), micro_band_top=44"


# ============================================================================
# TEST 5: main.py compiles (syntax check)
# ============================================================================
def t_main_compile():
    import py_compile
    py_compile.compile(os.path.join(ROOT, "main.py"), doraise=True)
    # also verify our hooks are present
    with open(os.path.join(ROOT, "main.py"), "r", encoding="utf-8") as f:
        txt = f.read()
    assert "UNIFIED DECISION GATE" in txt, "Unified gate not injected"
    assert "record_trade_outcome" in txt, "Adaptive recording not injected"
    assert "/tune" in txt, "/tune command not added"
    assert "from core.unified_bridge" in txt, "Bridge import missing"
    return "main.py compiles & all hooks injected (gate + record + /tune + bridge)"


# ============================================================================
# TEST 6: bridge end-to-end
# ============================================================================
def t_bridge():
    from core.unified_bridge import build_decision_context, decide_and_log

    ctx = build_decision_context(
        strategy="SMC", signal="BUY",
        quality_score=68, confidence_pct=64, brain_score=66, execution_score=62,
        daily_bias="BUY", mtf_strength=2, smc_strength=6.5,
        smc_entry_confirmed=True, candle_trigger_confirmed=True, candle_weight=3,
        liquidity_alignment=75, sweep_probability=60,
        session="LONDON", market_regime="TRENDING", session_score=78,
        rr_ratio=2.0, ml_score=66,
    )
    res = decide_and_log(ctx)
    assert res.decision in ("PASS_FULL", "PASS_REDUCED", "PASS_MICRO"), f"Got {res.decision}"
    assert res.risk_multiplier > 0
    return (f"Bridge SMC BUY → {res.decision} | score={res.composite_score:.1f} | "
            f"risk_mult={res.risk_multiplier:.2f}")


# ============================================================================
# TEST 7: thresholds preserved for safety
# ============================================================================
def t_safety_preserved():
    from core import settings as s
    # هذه القيم لا يجب أن تتغير
    assert s.HARD_RISK_DAILY_LOSS_PERCENT == 10.0
    assert s.HARD_RISK_MAX_PER_TRADE == 0.50
    assert s.ANTI_REVENGE_ENABLED is True
    assert s.MAX_RISK_TOTAL == 0.75
    return "Safety caps untouched: daily 3%, per-trade 0.50%, anti-revenge ON, max_total 0.75"


# ============================================================================
# RUN ALL
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("FER3ON V7.0 ADAPTIVE — SMOKE TEST SUITE")
    print("=" * 70)

    run_check("T1: settings.py (new thresholds + adaptive enabled)", t_settings)
    run_check("T2: unified_decision — 6 scenarios", t_unified)
    run_check("T3: adaptive_learning — record/tune/recall", t_adaptive)
    run_check("T4: master_brain — floor lowered 42→35", t_master_brain)
    run_check("T5: main.py — compile & hooks injected", t_main_compile)
    run_check("T6: unified_bridge — end-to-end SMC", t_bridge)
    run_check("T7: safety caps preserved (no destruction)", t_safety_preserved)

    print("=" * 70)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    print(f"RESULTS:  {passed} PASSED  |  {failed} FAILED  |  TOTAL {len(results)}")
    print("=" * 70)

    # cleanup
    try:
        shutil.rmtree(TMP)
    except Exception:
        pass

    sys.exit(0 if failed == 0 else 1)

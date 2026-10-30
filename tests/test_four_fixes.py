"""
اختبارات التحقق من الإصلاحات الأربعة:
    1) Liquidity Sweep متوصّل فعلياً بـ FAIE.
    2) Order Flow متوصّل عبر OrderFlowIntelligence (شفاف عن كونه synthetic).
    3) Anchored VWAP حقيقي (typical price + volume weighting).
    4) Volume Profile حقيقي (POC/VAH/VAL/HVN/LVN).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if ROOT.as_posix() not in sys.path:
    sys.path.insert(0, ROOT.as_posix())


def _sample_rates(n: int = 60):
    return [
        {
            "open": 100 + i * 0.5,
            "high": 101 + i * 0.5,
            "low": 99 + i * 0.5,
            "close": 100.5 + i * 0.5,
            "tick_volume": 100 + i * 3,
            "real_volume": 0,
            "time": 1_700_000_000 + i * 3600,
        }
        for i in range(n)
    ]


# ---------- Fix 3: Anchored VWAP ----------

def test_anchored_vwap_is_real():
    from core.anchored_vwap import compute_anchored_vwap

    rates = _sample_rates()
    result = compute_anchored_vwap(rates, anchor="day_open", lookback=40)
    assert result["valid"] is True
    assert result["vwap"] > 0
    assert result["upper_band_1sd"] > result["vwap"] >= result["lower_band_1sd"]
    assert result["upper_band_2sd"] > result["upper_band_1sd"]
    assert result["source"] in {"real_volume", "tick_volume", "uniform", "mixed"}


def test_anchored_vwap_matches_manual_calc():
    from core.anchored_vwap import compute_anchored_vwap

    rates = _sample_rates(20)
    result = compute_anchored_vwap(rates, anchor="index", index=0, include_bands=False)
    # حساب يدوي لـ VWAP = Σ(TP*V)/ΣV
    cum_vp = 0.0
    cum_v = 0.0
    for r in rates:
        tp = (r["high"] + r["low"] + r["close"]) / 3.0
        v = r["tick_volume"]
        cum_vp += tp * v
        cum_v += v
    expected = cum_vp / cum_v
    assert abs(result["vwap"] - expected) < 1e-6


# ---------- Fix 4: Volume Profile ----------

def test_volume_profile_is_real():
    from core.volume_profile import compute_volume_profile

    rates = _sample_rates()
    vp = compute_volume_profile(rates, bins=12, lookback=40)
    assert vp["valid"] is True
    assert vp["poc"] > 0
    assert vp["vah"] > vp["val"]
    assert vp["val"] >= vp["low"]
    assert vp["vah"] <= vp["high"]
    assert len(vp["hist"]) == vp["bins"]
    # POC يجب أن يكون داخل منطقة القيمة
    assert vp["val"] <= vp["poc"] <= vp["vah"]


def test_volume_profile_price_context():
    from core.volume_profile import compute_volume_profile, price_context_vs_profile

    rates = _sample_rates()
    vp = compute_volume_profile(rates)
    ctx = price_context_vs_profile(vp, rates[-1]["close"])
    assert ctx["position"] in {"ABOVE_VALUE_AREA", "BELOW_VALUE_AREA", "INSIDE_VALUE_AREA"}
    assert ctx["acceptance"] in {"STRONG_ACCEPTANCE", "MODERATE_ACCEPTANCE", "REJECTION_ZONE"}


# ---------- Fix 2: Order Flow ----------

def test_orderflow_analyst_wired_and_honest():
    from fer3on_masr.intelligence.orderflow import OrderFlowIntelligence

    of = OrderFlowIntelligence()
    report = of.analyze(_sample_rates(), snapshot={"spread": 20.0})
    assert report.name == "Order Flow Engine"
    # الشفافية عن كونه اصطناعياً
    assert report.details["source"] == "synthetic_orderflow"
    assert report.details["is_real_dom"] is False
    assert "inputs" in report.details


# ---------- Fix 1: Liquidity Sweep integration ----------

def test_liquidity_analyst_reads_sweep_probability():
    from fer3on_masr.intelligence.liquidity import LiquidityIntelligence

    li = LiquidityIntelligence()
    snap = {
        "sweep_probability": 72.5,
        "sweep_direction": "SELL",
        "sweep_confidence_bonus": 5.0,
        "equal_highs": [],
        "equal_lows": [100.1, 100.15],
        "liquidity_pools": [],
        "session": "LONDON",
    }
    prof = li.profile(_sample_rates(), snapshot=snap)
    # الآن FAIE بيقرأ sweep_probability فعلياً (ليس تجاهله)
    assert prof.details["sweep_probability"] == 72.5
    assert prof.details["sweep_direction"] == "SELL"
    # best_target يجب أن يُوجَّه نحو sell-side بسبب قوة السويب
    assert "sell-side low" in prof.details["best_target_reason"]


# ---------- End-to-end: FAIE run_cycle uses all 4 fixes ----------

def test_faie_run_cycle_exposes_all_four_fixes():
    from fer3on_masr.app import Fer3onMasrApp, build_sample_rates

    app = Fer3onMasrApp(ROOT)
    result = app.run_cycle(build_sample_rates())

    for key in (
        "liquidity_intelligence",
        "orderflow_intelligence",
        "volume_profile_intelligence",
        "anchored_vwap_intelligence",
    ):
        assert key in result, f"missing key {key}"

    # SMC agent يقرأ الأدلة الجديدة
    smc = next((d for d in result["strategy_ai"] if d["name"] == "SMC AI"), None)
    assert smc is not None
    rationale = " | ".join(smc["rationale"])
    # واحد على الأقل من الأدلة الأربعة يظهر في السبب
    assert any(
        kw in rationale
        for kw in ("sweep_probability", "anchored_vwap", "volume_profile", "orderflow")
    ), f"SMC AI not consuming new evidence: {rationale}"


# ---------- Regression: old misleading name fully removed ----------

def test_vwap_reclaim_alias_removed():
    """detect_vwap_reclaim_candle was a backward-compat alias for the
    correctly-named detect_midpoint_reclaim_candle (the old name was
    misleading -- the calculation has nothing to do with VWAP). Per the
    repo cleanup recommendation, the alias has been removed now that no
    production code references the old name; this test guards against it
    quietly reappearing.
    """
    import core.candle_patterns as candle_patterns

    assert hasattr(candle_patterns, "detect_midpoint_reclaim_candle")
    assert not hasattr(candle_patterns, "detect_vwap_reclaim_candle")


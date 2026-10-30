# =========================================
# FER3ON V5.1 — ADAPTIVE WEIGHTING ENGINE
# =========================================

import json
import os
from datetime import datetime, timezone

from core.ai_memory import load_memory_records
from core.build_scope import filter_current_build_rows

ADAPTIVE_FILE = "data/analytics/adaptive_weights.json"
MIN_TRADES_FOR_ADAPT = 100
ADAPT_INTERVAL = 100

DEFAULT_WEIGHTS = {
    "trend": 20,
    "liquidity": 15,
    "smc": 25,
    "session": 10,
    "news": 5,
    "dna": 8,
    "choch": 15,
    "liq_map": 10,
    "SMC_threshold": 65,
    "DAILY_threshold": 60,
    "min_rr": 1.5,
    "max_risk_pct": 1.0,
    "quality_lot_boost": 1.0,
    "london_mult": 1.20,
    "ny_mult": 1.20,
    "asia_mult": 0.80,
    "off_mult": 0.60,
    "_version": "V5.5",
    "_last_update": None,
    "_cycle": 0,
    "_total_trades": 0,
}


def _load_weights():
    if os.path.exists(ADAPTIVE_FILE):
        try:
            with open(ADAPTIVE_FILE, "r", encoding="utf-8") as f:
                weights = json.load(f)
            for k, v in DEFAULT_WEIGHTS.items():
                weights.setdefault(k, v)
            return weights
        except Exception:
            pass
    return DEFAULT_WEIGHTS.copy()


def _save_weights(weights):
    os.makedirs(os.path.dirname(ADAPTIVE_FILE), exist_ok=True)
    with open(ADAPTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, ensure_ascii=False)


def _deep_analyze(n=MIN_TRADES_FOR_ADAPT):
    # [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] إعادة وزن المكونات (trend/smc/dna/...)
    # كانت بتتحسب من آخر 100 صفقة من كل النسخ مخلوطة. التحليل دلوقتي من
    # صفقات البيلد الحالي فقط؛ وقلة العينة ترجع {} فتبقى الأوزان الافتراضية.
    rows = filter_current_build_rows(load_memory_records())
    if len(rows) < 20:
        return {}
    recent = rows[-n:]

    analysis = {
        "total": len(recent),
        "wins": 0,
        "losses": 0,
        "winrate": 0,
        "avg_rr": 0,
        "profit_factor": 0,
        "by_strategy": {},
        "by_session": {},
        "by_regime": {},
        "by_quality": {},
        "confidence_avg": 0,
        "component_attribution": {},
    }

    win_rr = []
    loss_rr = []
    confidence_values = []

    for row in recent:
        result = str(row.get("result", "")).upper()
        strat = row.get("strategy", "UNKNOWN")
        sess = row.get("session", "UNKNOWN")
        regime = row.get("market_regime", "UNKNOWN")
        try:
            qual = float(row.get("quality_score", 0) or 0)
        except Exception:
            qual = 0
        try:
            conf = float(row.get("confidence_pct", row.get("confidence_score", 0)) or 0)
        except Exception:
            conf = 0
        confidence_values.append(conf)

        if qual >= 90:
            q_band = "90+"
        elif qual >= 80:
            q_band = "80-90"
        elif qual >= 70:
            q_band = "70-80"
        else:
            q_band = "<70"

        is_win = result == "WIN"
        if is_win:
            analysis["wins"] += 1
        elif result == "LOSS":
            analysis["losses"] += 1

        try:
            rr = float(row.get("rr_ratio", 0) or 0)
            if rr > 0:
                (win_rr if is_win else loss_rr).append(rr)
        except Exception:
            pass

        for dim_key, dim_val in [
            ("by_strategy", strat),
            ("by_session", sess),
            ("by_regime", regime),
            ("by_quality", q_band),
        ]:
            bucket = analysis[dim_key].setdefault(dim_val, {"wins": 0, "losses": 0})
            if is_win:
                bucket["wins"] += 1
            elif result == "LOSS":
                bucket["losses"] += 1

        for comp_key in ["liq_map_score", "confidence_pct", "quality_score", "rr_ratio", "mtf_strength"]:
            try:
                comp_val = float(row.get(comp_key, 0) or 0)
            except Exception:
                comp_val = 0
            bucket = analysis["component_attribution"].setdefault(comp_key, {"win_sum": 0.0, "loss_sum": 0.0, "wins": 0, "losses": 0})
            if is_win:
                bucket["win_sum"] += comp_val
                bucket["wins"] += 1
            elif result == "LOSS":
                bucket["loss_sum"] += comp_val
                bucket["losses"] += 1

    total = analysis["total"]
    if total > 0:
        analysis["winrate"] = round(analysis["wins"] / total * 100, 1)
    if win_rr:
        analysis["avg_rr"] = round(sum(win_rr) / len(win_rr), 2)
    total_win = sum(win_rr) if win_rr else 0
    total_loss = len(loss_rr) * 1.0
    if total_loss > 0:
        analysis["profit_factor"] = round(total_win / total_loss, 2)
    if confidence_values:
        analysis["confidence_avg"] = round(sum(confidence_values) / len(confidence_values), 2)
    return analysis


def _compute_new_weights(analysis, current_weights):
    new_w = current_weights.copy()
    changes = []

    for strat, data in analysis.get("by_strategy", {}).items():
        total = data["wins"] + data["losses"]
        if total < 10:
            continue
        wr = data["wins"] / total
        key = f"{strat}_threshold"
        new_w.setdefault(key, 65)
        old_val = new_w[key]
        if wr < 0.35:
            new_w[key] = min(old_val + 5, 88)
            changes.append(f"↑ {strat}_threshold {old_val}→{new_w[key]} (WR={wr:.0%}, n={total})")
        elif wr > 0.68 and old_val > 55:
            new_w[key] = max(old_val - 3, 55)
            changes.append(f"↓ {strat}_threshold {old_val}→{new_w[key]} (WR={wr:.0%}, n={total})")

    for sess, mult_key in {"LONDON": "london_mult", "NEWYORK": "ny_mult", "ASIA": "asia_mult", "OFF_HOURS": "off_mult"}.items():
        data = analysis.get("by_session", {}).get(sess)
        if not data:
            continue
        total = data["wins"] + data["losses"]
        if total < 8:
            continue
        wr = data["wins"] / total
        old_val = new_w.get(mult_key, 1.0)
        if wr < 0.35 and old_val > 0.5:
            new_w[mult_key] = round(max(old_val - 0.1, 0.5), 2)
            changes.append(f"↓ {mult_key} {old_val}→{new_w[mult_key]} (WR={wr:.0%})")
        elif wr > 0.65 and old_val < 1.5:
            new_w[mult_key] = round(min(old_val + 0.05, 1.5), 2)
            changes.append(f"↑ {mult_key} {old_val}→{new_w[mult_key]} (WR={wr:.0%})")

    avg_rr = analysis.get("avg_rr", 0)
    pf = analysis.get("profit_factor", 0)
    old_rr = new_w.get("min_rr", 1.5)
    if avg_rr > 0:
        if avg_rr < 1.5 and pf < 1.5:
            new_w["min_rr"] = round(min(old_rr + 0.1, 2.5), 1)
            changes.append(f"↑ min_rr {old_rr}→{new_w['min_rr']} (avg_rr={avg_rr})")
        elif avg_rr > 2.5 and pf > 2.0 and old_rr > 1.5:
            new_w["min_rr"] = round(max(old_rr - 0.1, 1.5), 1)
            changes.append(f"↓ min_rr {old_rr}→{new_w['min_rr']} (avg_rr={avg_rr})")

    for comp_key, weight_key in [("liq_map_score", "liq_map"), ("confidence_pct", "dna"), ("quality_score", "smc")]:
        comp = analysis.get("component_attribution", {}).get(comp_key)
        if not comp or comp.get("wins", 0) < 5 or comp.get("losses", 0) < 5:
            continue
        win_avg = comp["win_sum"] / max(1, comp["wins"])
        loss_avg = comp["loss_sum"] / max(1, comp["losses"])
        old = new_w.get(weight_key, DEFAULT_WEIGHTS[weight_key])
        if win_avg > loss_avg * 1.15:
            new_w[weight_key] = min(old + 1, DEFAULT_WEIGHTS[weight_key] + 5)
            changes.append(f"↑ {weight_key} {old}→{new_w[weight_key]} ({comp_key} helps wins)")
        elif loss_avg > win_avg * 1.15:
            new_w[weight_key] = max(old - 1, max(1, DEFAULT_WEIGHTS[weight_key] - 5))
            changes.append(f"↓ {weight_key} {old}→{new_w[weight_key]} ({comp_key} weak in losses)")

    q90 = analysis.get("by_quality", {}).get("90+")
    if q90:
        total = q90["wins"] + q90["losses"]
        if total >= 10:
            q90_wr = q90["wins"] / total
            old_boost = new_w.get("quality_lot_boost", 1.0)
            if q90_wr > 0.70:
                new_w["quality_lot_boost"] = round(min(old_boost + 0.05, 1.30), 2)
                changes.append(f"↑ quality_lot_boost {old_boost}→{new_w['quality_lot_boost']} (Q90 WR={q90_wr:.0%})")
            elif q90_wr < 0.50 and old_boost > 1.0:
                new_w["quality_lot_boost"] = round(max(old_boost - 0.05, 1.0), 2)
                changes.append(f"↓ quality_lot_boost {old_boost}→{new_w['quality_lot_boost']} (Q90 WR={q90_wr:.0%})")

    return new_w, changes


def run_adaptive_weighting(force=False):
    weights = _load_weights()
    # [BRAIN-SCOPE] فترة الـ 100 صفقة بين دورات التكيّف تُحسب من صفقات
    # البيلد الحالي فقط — صفقات النسخ القديمة لا تسرّع الدورة ولا تغذيها.
    rows_count = len(filter_current_build_rows(load_memory_records()))
    prev_total = weights.get("_total_trades", 0)
    new_trades = rows_count - prev_total

    if not force and new_trades < ADAPT_INTERVAL:
        return {"ran": False, "reason": f"Need {ADAPT_INTERVAL - new_trades} more trades (anti-overfitting)", "new_trades": new_trades}

    print(f"\n🧬 ADAPTIVE WEIGHTING: Analyzing {MIN_TRADES_FOR_ADAPT} trades...")
    analysis = _deep_analyze(MIN_TRADES_FOR_ADAPT)
    if not analysis or analysis.get("total", 0) < 20:
        return {"ran": False, "reason": "INSUFFICIENT_DATA"}

    new_weights, changes = _compute_new_weights(analysis, weights)
    cycle = weights.get("_cycle", 0) + 1
    new_weights["_cycle"] = cycle
    new_weights["_last_update"] = datetime.now(timezone.utc).isoformat()
    new_weights["_total_trades"] = rows_count
    new_weights["_version"] = "V5.5"
    _save_weights(new_weights)

    print(f"\n✅ ADAPTIVE WEIGHTING CYCLE #{cycle}")
    print(f"   WinRate:{analysis['winrate']}%")
    print(f"   AvgRR:{analysis['avg_rr']}")
    print(f"   ProfitFactor:{analysis['profit_factor']}")
    if changes:
        print("   Changes:")
        for c in changes:
            print(f"     • {c}")
    else:
        print("   No changes needed — weights optimal")

    return {"ran": True, "cycle": cycle, "analysis": analysis, "changes": changes, "new_weights": new_weights}


def get_adaptive_weights():
    return _load_weights()


def get_weight(key, default=None):
    weights = _load_weights()
    if default is None:
        default = DEFAULT_WEIGHTS.get(key, 1.0)
    return weights.get(key, default)

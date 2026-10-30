# =========================================
# FER3ON AI V1.5 — TRADE DNA V2
# =========================================

import json
import os
from datetime import datetime, timezone

from core.ai_memory import load_memory_records
from core.build_scope import filter_current_build_rows

try:
    from core.settings import BUILD_ID as _BUILD_ID
except Exception:
    _BUILD_ID = None

try:
    from core.account_scope import get_cached_account_id as _get_account_id
except Exception:
    def _get_account_id():
        return ""

DNA_FILE = "data/trade_dna.json"
DNA_V2 = "data/trade_dna_v2.json"
ML_FEATURE_SCHEMA_VERSION = 2


def initialize_trade_dna():
    os.makedirs("data", exist_ok=True)
    for f in [DNA_FILE, DNA_V2]:
        if not os.path.exists(f):
            with open(f, "w", encoding="utf-8") as fh:
                json.dump([], fh, indent=2, ensure_ascii=False)

    try:
        with open(DNA_V2, "r", encoding="utf-8") as f:
            current = json.load(f)
    except Exception:
        current = []

    if current:
        return

    # [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] الـ bootstrap كان بيعيد بناء الـ DNA
    # من آخر 200 صف في ai_memory.csv بدون فلترة — يعني حتى لو اتمسح الملف كان
    # بيتملى تاني بصفقات النسخ الفاشلة. دلوقتي الـ bootstrap من صفقات البيلد
    # الحالي فقط؛ لو مفيش، الملف يفضل فاضي و get_trade_dna_score يرجع prior.
    boot = []
    for row in filter_current_build_rows(load_memory_records())[-200:]:
        profit = round(float(row.get("profit", 0) or 0), 2)
        boot.append({
            "timestamp": row.get("date") or datetime.now(timezone.utc).isoformat(),
            "ticket": row.get("ticket", ""),
            "strategy": row.get("strategy", "UNKNOWN"),
            "signal": row.get("signal", "NONE"),
            "decision": row.get("decision", "UNKNOWN"),
            "mode": row.get("mode", "UNKNOWN"),
            "result": row.get("result", "UNKNOWN"),
            "profit": profit,
            "market_regime": row.get("market_regime", "UNKNOWN"),
            "session": row.get("session", "UNKNOWN"),
            "hour": int(float(row.get("hour", 0) or 0)),
            "atr": round(float(row.get("atr", 0) or 0), 2),
            "quality_score": float(row.get("quality_score", 0) or 0),
            "confidence_score": float(row.get("confidence_score", 0) or 0),
            "confidence_pct": float(row.get("confidence_pct", 0) or 0),
            "composite_score": float(row.get("composite_score", 0) or 0),
            "risk_percent": float(row.get("risk_percent", 0) or 0),
            "duration_minutes": float(row.get("duration_minutes", 0) or 0),
            "choch_state": row.get("choch_state", "NONE"),
            "choch_strength": row.get("choch_strength", "WEAK"),
            "liq_map_score": float(row.get("liq_map_score", 0) or 0),
            "liq_map_dir": row.get("liq_map_dir", "NEUTRAL"),
            "exec_grade": row.get("exec_grade", "B"),
            "fill_quality": row.get("fill_quality", row.get("exec_grade", "B")),
            "execution_latency_ms": float(row.get("latency_ms", 0) or 0),
            "slippage_pts": float(row.get("slippage_pts", 0) or 0),
            "rr_ratio": float(row.get("rr_ratio", 0) or 0),
            "spread_pts": float(row.get("spread", 0) or 0),
            "sl_dist": float(row.get("sl_dist", 0) or 0),
            "tp_dist": float(row.get("tp_dist", 0) or 0),
            "mtf_strength": float(row.get("mtf_strength", 0) or 0),
            "mtf_structural": str(row.get("mtf_structural", "")).lower() in ("1", "true", "yes"),
            "entry_price": float(row.get("entry_price", 0) or 0),
            "exit_price": float(row.get("exit_price", 0) or 0),
            "entry_time": row.get("entry_time", ""),
            "exit_time": row.get("exit_time", ""),
            "dist_pdh": 0,
            "dist_pdl": 0,
            "decision_snapshot_id": row.get("decision_snapshot_id", ""),
        })

    if boot:
        with open(DNA_V2, "w", encoding="utf-8") as f:
            json.dump(boot, f, indent=2, ensure_ascii=False)


def load_trade_dna():
    initialize_trade_dna()
    try:
        with open(DNA_V2, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_trade_dna(data):
    with open(DNA_V2, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def record_trade_dna(
    strategy,
    market_regime,
    session,
    signal,
    atr,
    result,
    profit,
    confidence_score=0,
    confidence_pct=0,
    choch_state="NONE",
    choch_strength="WEAK",
    liq_map_score=0,
    liq_map_dir="NEUTRAL",
    exec_grade="B",
    quality_score=0,
    rr_ratio=0,
    spread_pts=0,
    sl_dist=0,
    tp_dist=0,
    mtf_strength=0,
    mtf_structural=False,
    pdh=0,
    pdl=0,
    distance_to_pdh=0,
    distance_to_pdl=0,
    hour=0,
    entry_price=0,
    exit_price=0,
    ticket="",
    decision_snapshot_id="",
    decision="UNKNOWN",
    composite_score=0,
    risk_percent=0,
    mode="UNKNOWN",
    entry_time="",
    exit_time="",
    duration_minutes=0,
    execution_latency_ms=0,
    slippage_pts=0,
    fill_quality="",
):
    data = load_trade_dna()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # [BRAIN-SCOPE] وسم كل سجل جديد بالبيلد عشان الفلترة تعتمد على
        # build_id مباشرة بدل الاستنتاج من التاريخ.
        "build_id": _BUILD_ID or "",
        # [FER3ON-FIX-2026-08-28] نفس منطق build_id بالظبط، بس لمحور الحساب
        # مش الكود — يحمي من اختلاط بيانات حساب MT5 قديم لو الحساب اتغيّر
        # من غير ما البيلد يتغيّر (build_scope.py وحدها مش كفاية لده).
        "account_id": _get_account_id(),
        "ticket": ticket,
        "strategy": strategy,
        "signal": signal,
        "decision": decision,
        "mode": mode,
        "result": result,
        "profit": round(float(profit or 0), 2),
        "market_regime": market_regime,
        "session": session,
        "hour": hour,
        "atr": round(float(atr or 0), 2),
        "quality_score": quality_score,
        "confidence_score": confidence_score,
        "confidence_pct": round(float(confidence_pct or 0), 1),
        "composite_score": round(float(composite_score or 0), 2),
        "risk_percent": round(float(risk_percent or 0), 4),
        "duration_minutes": round(float(duration_minutes or 0), 2),
        "choch_state": choch_state,
        "choch_strength": choch_strength,
        "liq_map_score": liq_map_score,
        "liq_map_dir": liq_map_dir,
        "exec_grade": exec_grade,
        "fill_quality": fill_quality or exec_grade,
        "execution_latency_ms": round(float(execution_latency_ms or 0), 2),
        "slippage_pts": round(float(slippage_pts or 0), 2),
        "rr_ratio": round(float(rr_ratio or 0), 2),
        "spread_pts": round(float(spread_pts or 0), 1),
        "sl_dist": round(float(sl_dist or 0), 2),
        "tp_dist": round(float(tp_dist or 0), 2),
        "entry_price": round(float(entry_price or 0), 2),
        "exit_price": round(float(exit_price or 0), 2),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "mtf_strength": mtf_strength,
        "mtf_structural": mtf_structural,
        "pdh": round(float(pdh or 0), 2),
        "pdl": round(float(pdl or 0), 2),
        "dist_pdh": round(float(distance_to_pdh or 0), 2),
        "dist_pdl": round(float(distance_to_pdl or 0), 2),
        "decision_snapshot_id": decision_snapshot_id,
    }
    data.append(record)
    save_trade_dna(data)
    return record


def find_similar_trades(strategy, market_regime, session, min_score=0):
    # [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] dna_score (35% من master_score) كان
    # بيقرا trade_dna_v2.json كاملًا بكل النسخ. التشابه دلوقتي محسوب من سجلات
    # البيلد الحالي فقط (السجلات القديمة تفضل في الملف كأرشيف).
    matches = []
    for t in filter_current_build_rows(load_trade_dna(), date_field="timestamp"):
        score = 0
        if t.get("strategy") == strategy:
            score += 1
        if t.get("market_regime") == market_regime:
            score += 1
        if t.get("session") == session:
            score += 1
        if score >= 2 and float(t.get("quality_score", 0) or 0) >= min_score:
            matches.append(t)
    return matches


def calculate_trade_dna_score(trades):
    if not trades:
        return 0.0

    wins = sum(1 for t in trades if str(t.get("result", "")).upper() == "WIN")
    win_rate = wins / len(trades)

    profit_factor = 0.0
    positive = sum(float(t.get("profit", 0) or 0) for t in trades if float(t.get("profit", 0) or 0) > 0)
    negative = abs(sum(float(t.get("profit", 0) or 0) for t in trades if float(t.get("profit", 0) or 0) < 0))
    if negative > 0:
        profit_factor = positive / negative

    recovery_factor = 0.0
    if negative > 0:
        recovery_factor = positive / negative if negative > 0 else 0.0

    recent_accuracy = 0.0
    recent_trades = trades[-5:]
    if recent_trades:
        recent_accuracy = sum(1 for t in recent_trades if str(t.get("result", "")).upper() == "WIN") / len(recent_trades)

    quality = sum(float(t.get("quality_score", 0) or 0) for t in trades) / max(1, len(trades))
    confidence = sum(float(t.get("confidence_pct", 0) or 0) for t in trades) / max(1, len(trades))

    score = (
        win_rate * 0.35
        + min(max(profit_factor, 0.0), 3.0) / 3.0 * 0.20
        + min(max(recovery_factor, 0.0), 3.0) / 3.0 * 0.15
        + recent_accuracy * 0.20
        + min(max(quality / 100.0, 0.0), 1.0) * 0.05
        + min(max(confidence / 100.0, 0.0), 1.0) * 0.05
    ) * 100.0

    return round(max(0.0, min(100.0, score)), 2)


def get_trade_dna_score(strategy, market_regime, session):
    trades = find_similar_trades(strategy, market_regime, session)
    if not trades:
        # [BRAIN-SCOPE] لا توجد صفقات مشابهة من البيلد الحالي → prior محايد
        # متحفظ (25 = بداية band الـ LEARNING) بدل 0 (عمى يسحق master_score)
        # أو درجة محسوبة من بيانات النسخة الفاشلة — نفس فلسفة edge gate.
        return 25.0
    if len(trades) < 5:
        return round(25.0 + min(20.0, len(trades) * 5.0), 2)
    return calculate_trade_dna_score(trades)


def get_trade_dna_display(trade_count, dna_score):
    if int(trade_count or 0) < 20:
        return "LEARNING"
    if int(trade_count or 0) < 50:
        return str(int(dna_score or 0))
    return str(int(dna_score or 0))


def rank_strategies(min_trades=3):
    # [BRAIN-SCOPE] ترتيب الاستراتيجيات من أداء البيلد الحالي فقط
    rows = filter_current_build_rows(load_trade_dna(), date_field="timestamp")
    grouped = {}
    for row in rows:
        strat = str(row.get("strategy", "UNKNOWN")).upper()
        g = grouped.setdefault(strat, {"trades": 0, "wins": 0, "profit": 0.0})
        g["trades"] += 1
        if str(row.get("result", "")).upper() == "WIN":
            g["wins"] += 1
        g["profit"] += float(row.get("profit", 0) or 0)
    ranking = []
    for strat, g in grouped.items():
        if g["trades"] < min_trades:
            continue
        wr = g["wins"] / g["trades"] if g["trades"] else 0
        score = (wr * 70.0) + (max(-1000.0, min(1000.0, g["profit"])) * 0.03)
        ranking.append({
            "strategy": strat,
            "trades": g["trades"],
            "win_rate": round(wr * 100.0, 2),
            "profit": round(g["profit"], 2),
            "score": round(score, 2),
        })
    ranking.sort(key=lambda x: (x["score"], x["profit"], x["win_rate"]), reverse=True)
    return ranking


def get_ml_features(record):
    regime_map = {"TRENDING": 1, "RANGING": 2, "VOLATILE": 3, "CRISIS": 4, "UNKNOWN": 0}
    session_map = {"LONDON": 1, "NEWYORK": 2, "ASIA": 3, "OVERLAP": 4, "OFF_HOURS": 0}
    signal_map = {"BUY": 1, "SELL": -1, "NONE": 0}
    choch_map = {
        "CHOCH_BULLISH": 2,
        "CHOCH_BEARISH": -2,
        "BULLISH_STRUCTURE": 2,
        "TRANSITION_BULLISH": 1,
        "BEARISH_STRUCTURE": -2,
        "TRANSITION_BEARISH": -1,
        "RANGING": 0,
        "UNKNOWN": 0,
        "NONE": 0,
    }
    exec_map = {"ELITE": 5, "A+": 4, "A": 3, "B": 2, "C": 1, "REJECT": 0}
    strat_map = {"SCALP": 1, "DAILY": 2, "SWING": 3, "SMC": 4}

    return [
        strat_map.get(record.get("strategy", ""), 0),
        signal_map.get(record.get("signal", ""), 0),
        regime_map.get(record.get("market_regime", ""), 0),
        session_map.get(record.get("session", ""), 0),
        float(record.get("quality_score", 0)),
        float(record.get("confidence_pct", 0)),
        choch_map.get(record.get("choch_state", "NONE"), 0),
        float(record.get("liq_map_score", 0)),
        exec_map.get(record.get("exec_grade", "B"), 2),
        float(record.get("rr_ratio", 0)),
        float(record.get("spread_pts", 0)),
        float(record.get("mtf_strength", 0)),
        int(record.get("mtf_structural", False)),
        float(record.get("atr", 0)),
        float(record.get("hour", 0)),
        float(record.get("dist_pdh", 0)),
        float(record.get("dist_pdl", 0)),
        # These are post-entry/outcome values or unavailable in live inference.
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
    ]


FEATURE_NAMES = [
    "strategy", "signal", "market_regime", "session",
    "quality_score", "confidence_pct", "choch_state",
    "liq_map_score", "exec_grade", "rr_ratio", "spread_pts",
    "mtf_strength", "mtf_structural", "atr", "hour",
    "dist_pdh", "dist_pdl", "composite_score", "risk_percent",
    "duration_minutes", "execution_latency_ms", "slippage_pts",
]

# =========================================
# FER3ON V5 — CONFIDENCE ENGINE V2
# المرحلة 2: تفصيل كامل لكل مكوّن
# Trend + Liquidity + SMC + Session + News + DNA
# =========================================

import csv
import os
from datetime import datetime, timezone

from core.adaptive_ai import get_strategy_confidence as adaptive_get_strategy_confidence
from core.build_scope import is_current_build_row

MEMORY_FILE = "data/memory/ai_memory.csv"


def get_strategy_confidence(strategy):
    return adaptive_get_strategy_confidence(strategy)


# =========================================
# COMPONENT SCORES (الأوزان الجديدة)
# =========================================

WEIGHTS = {
    "trend":     20,   # اتجاه السوق الهيكلي
    "liquidity": 15,   # تحليل السيولة
    "smc":       25,   # Smart Money Concepts
    "session":   10,   # جودة الجلسة
    "news":       5,   # حالة الأخبار
    "dna":        8,   # تاريخ الأداء الشخصي
}

MAX_TOTAL = sum(WEIGHTS.values())   # 83


# =========================================
# SUB-SCORERS
# =========================================

def score_trend(market_regime, mtf_direction, mtf_strength, signal):
    """
    Trend score (0-20):
      - TRENDING + اتجاه موافق  → 20
      - TRENDING + محايد         → 14
      - RANGING                  → 10
      - VOLATILE                 →  6
      - تعارض مع الاتجاه         →  0
    """
    base = {
        "TRENDING": 16,
        "RANGING":  10,
        "VOLATILE":  6,
        "CRISIS":    0,
        "UNKNOWN":   8
    }.get(market_regime, 8)

    # مطابقة اتجاه MTF
    if mtf_direction == signal:
        base = min(base + 4, 20)
    elif mtf_direction not in ("NONE", None) and mtf_direction != signal:
        base = max(base - 8, 0)

    return min(base, 20)


def score_liquidity(liquidity_bias, signal, asian_data=None):
    """
    Liquidity score (0-15):
      - Bias موافق + منطقة سيولة قريبة → 15
      - Bias موافق فقط                 → 10
      - محايد                          →  7
      - تعارض                          →  2
    """
    if liquidity_bias == signal:
        base = 10
        if asian_data and asian_data.get("near_zone"):
            base = 15
    elif liquidity_bias == "NEUTRAL":
        base = 7
    elif liquidity_bias == "NONE":
        base = 5
    else:
        base = 2   # تعارض — خصم

    return min(base, 15)


def score_smc(smc_strength, entry_grade):
    """
    SMC score (0-25) بعد إعادة المعايرة:
      - B+ يجب أن تبقى فعلياً في band قوي
      - الخصم من smc_strength يكون محدوداً
      - لا يتم سحق SMC بالكامل بسبب تعارض واحد
    """
    grade_map = {"A+": 25, "A": 23, "B+": 19, "B": 15, "C": 9, "NONE": 0}
    base = grade_map.get(entry_grade, 0)

    smc_strength = float(smc_strength or 0)
    if smc_strength >= 8:
        base = min(base + 2, 25)
    elif smc_strength >= 6:
        base = min(base + 1, 25)
    elif smc_strength <= 2:
        base = max(base - 2, 0)

    return min(base, 25)


def score_session(session_score, session_name):
    """
    Session score (0-10):
      - London/NY peak hours        → 10
      - Good winrate history        → 8-10
      - Off-hours                   → 3
    """
    session_base = {
        "LONDON":    9,
        "NEWYORK":   9,
        "ASIA":      5,
        "OFF_HOURS": 3
    }.get(session_name, 5)

    # تعديل من winrate تاريخي
    history_adj = round((session_score - 50) / 50 * 3)
    return min(max(session_base + history_adj, 0), 10)


def score_news(is_news_time, news_impact="LOW"):
    """
    News score (0-5):
      - لا أخبار مهمة   → 5
      - أخبار متوسطة    → 3
      - أخبار عالية     → 0
    """
    if is_news_time:
        return 0
    impact_map = {"LOW": 5, "MEDIUM": 3, "HIGH": 0}
    return impact_map.get(news_impact, 3)


def score_dna(strategy, market_regime, session, current_hour):
    """
    DNA score (0-8):
      يحسب أداء البوت التاريخي في نفس الظروف
    """
    if not os.path.exists(MEMORY_FILE):
        return 4   # neutral default

    total = wins = 0

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] مكوّن DNA كان يحسب
                # الـ winrate من كل صفقات النسخ القديمة. صفقات البيلد الحالي
                # فقط؛ والعينة الصغيرة (total<5 أدناه) ترجع القيمة المحايدة 4.
                if not is_current_build_row(row):
                    continue
                match = 0
                if row.get("strategy") == strategy:
                    match += 1
                if row.get("market_regime", "") == market_regime:
                    match += 1
                try:
                    hour = int(row.get("hour", 0))
                    if abs(hour - current_hour) <= 1:
                        match += 1
                except Exception:
                    pass

                if match >= 2:
                    total += 1
                    if row.get("result") == "WIN":
                        wins += 1
    except Exception:
        return 4

    if total < 5:
        return 4

    wr = wins / total
    if wr >= 0.75:
        return 8
    elif wr >= 0.60:
        return 6
    elif wr >= 0.45:
        return 4
    elif wr >= 0.30:
        return 2
    else:
        return 0


# =========================================
# MASTER CONFIDENCE — يجمع كل المكونات
# =========================================

def get_confidence_v2(
    strategy,
    signal,
    market_regime,
    mtf_direction,
    mtf_strength,
    smc_strength,
    entry_grade,
    session_name,
    session_score,
    liquidity_bias,
    is_news,
    news_impact="LOW",
    asian_data=None
):
    """
    يُعيد:
      total_score  : 0-83+ (لكن SMC أصبحت أكثر اتساقاً مع band التقييم)
      breakdown    : dict بتفاصيل كل مكوّن
      label        : EXCELLENT | GOOD | ACCEPTABLE | WEAK
      explanation  : نص شرح القرار كاملاً
    """
    current_hour = datetime.now(timezone.utc).hour

    # --- حساب كل مكوّن ---
    t_score = score_trend(market_regime, mtf_direction, mtf_strength, signal)
    l_score = score_liquidity(liquidity_bias, signal, asian_data)
    s_score = score_smc(smc_strength, entry_grade)
    ss_score = score_session(session_score, session_name)
    n_score = score_news(is_news, news_impact)
    d_score = score_dna(strategy, market_regime, session_name, current_hour)

    total = t_score + l_score + s_score + ss_score + n_score + d_score

    breakdown = {
        "Trend":     {"score": t_score,  "max": WEIGHTS["trend"],     "pct": round(t_score  / WEIGHTS["trend"]     * 100)},
        "Liquidity": {"score": l_score,  "max": WEIGHTS["liquidity"], "pct": round(l_score  / WEIGHTS["liquidity"] * 100)},
        "SMC":       {"score": s_score,  "max": WEIGHTS["smc"],       "pct": round(s_score  / WEIGHTS["smc"]       * 100)},
        "Session":   {"score": ss_score, "max": WEIGHTS["session"],   "pct": round(ss_score / WEIGHTS["session"]   * 100)},
        "News":      {"score": n_score,  "max": WEIGHTS["news"],      "pct": round(n_score  / WEIGHTS["news"]      * 100)},
        "DNA":       {"score": d_score,  "max": WEIGHTS["dna"],       "pct": round(d_score  / WEIGHTS["dna"]       * 100)},
    }

    # Label
    pct = total / MAX_TOTAL * 100
    if pct >= 85:
        label = "EXCELLENT ✨"
    elif pct >= 70:
        label = "GOOD 👍"
    elif pct >= 55:
        label = "ACCEPTABLE ✅"
    else:
        label = "WEAK ⚠️"

    # Human-readable explanation
    explanation = _build_explanation(breakdown, total, label, entry_grade)

    print(
        f"🧠 CONFIDENCE V2 | "
        f"Trend:{t_score}/{WEIGHTS['trend']} "
        f"Liq:{l_score}/{WEIGHTS['liquidity']} "
        f"SMC:{s_score}/{WEIGHTS['smc']} "
        f"Sess:{ss_score}/{WEIGHTS['session']} "
        f"News:{n_score}/{WEIGHTS['news']} "
        f"DNA:{d_score}/{WEIGHTS['dna']} "
        f"→ TOTAL:{total}/{MAX_TOTAL} [{label}]"
    )

    return {
        "total":       total,
        "max":         MAX_TOTAL,
        "breakdown":   breakdown,
        "label":       label,
        "explanation": explanation,
        "pct":         round(pct, 1)
    }


# =========================================
# EXPLANATION BUILDER
# =========================================

def _build_explanation(breakdown, total, label, entry_grade):
    lines = [f"📊 CONFIDENCE REPORT — {total}/{MAX_TOTAL} [{label}]", ""]

    for component, data in breakdown.items():
        bar = "█" * (data["pct"] // 10) + "░" * (10 - data["pct"] // 10)
        lines.append(
            f"  {component:<10} [{bar}] {data['score']}/{data['max']} ({data['pct']}%)"
        )

    lines.append("")
    lines.append(f"  Entry Grade : {entry_grade}")

    weakest = min(breakdown, key=lambda k: breakdown[k]["pct"])
    lines.append(f"  Weak Point  : {weakest} ({breakdown[weakest]['score']}/{breakdown[weakest]['max']})")

    return "\n".join(lines)


# =========================================
# V5.1 ADDITION — CHOCH + LIQUIDITY MAP + ADAPTIVE WEIGHTS
# =========================================

def get_confidence_v51(
    strategy,
    signal,
    market_regime,
    mtf_direction,
    mtf_strength,
    smc_strength,
    entry_grade,
    session_name,
    session_score,
    liquidity_bias,
    is_news,
    news_impact="LOW",
    asian_data=None,
    choch_data=None,
    liq_map=None,
    adaptive_weights=None
):
    """
    V5.1: Confidence Engine الكامل مع:
      - كل مكونات V5
      - CHOCH Score (جديد)
      - Liquidity Map Score (جديد)
      - Adaptive Weights (جديد)
    """
    from core.choch_engine import get_choch_score

    # استخدام الأوزان التكيفية إذا توفرت
    w = adaptive_weights or WEIGHTS.copy()

    # الحساب الأساسي من V5
    base_result = get_confidence_v2(
        strategy=strategy,
        signal=signal,
        market_regime=market_regime,
        mtf_direction=mtf_direction,
        mtf_strength=mtf_strength,
        smc_strength=smc_strength,
        entry_grade=entry_grade,
        session_name=session_name,
        session_score=session_score,
        liquidity_bias=liquidity_bias,
        is_news=is_news,
        news_impact=news_impact,
        asian_data=asian_data
    )

    bonus = 0
    extra_breakdown = {}

    # ——— CHOCH BONUS (0-15) ———
    choch_bonus = 0
    if choch_data:
        choch_bonus = get_choch_score(choch_data, signal)
        extra_breakdown["CHOCH"] = {
            "score": max(choch_bonus, 0),
            "max": 15,
            "pct": round(max(choch_bonus, 0) / 15 * 100)
        }
        bonus += choch_bonus

    # ——— LIQUIDITY MAP BONUS (0-10) ———
    liq_map_bonus = 0
    if liq_map and liq_map.get("liquidity_score", 0) >= 5:
        liq_score = liq_map["liquidity_score"]
        liq_dir   = liq_map.get("direction", "NEUTRAL")

        if (signal == "BUY"  and liq_dir == "UP") or \
           (signal == "SELL" and liq_dir == "DOWN"):
            liq_map_bonus = min(round(liq_score * 0.5), 10)
        elif liq_dir not in ("NEUTRAL",):
            liq_map_bonus = -5

        extra_breakdown["LiqMap"] = {
            "score": max(liq_map_bonus, 0),
            "max": 10,
            "pct": round(max(liq_map_bonus, 0) / 10 * 100)
        }
        bonus += liq_map_bonus

    total_v51  = base_result["total"] + bonus
    max_v51    = base_result["max"] + 25   # 83 + 25 = 108
    pct_v51    = total_v51 / max_v51 * 100

    if pct_v51 >= 88:
        label_v51 = "INSTITUTIONAL ✨✨"
    elif pct_v51 >= 78:
        label_v51 = "EXCELLENT ✨"
    elif pct_v51 >= 65:
        label_v51 = "GOOD 👍"
    elif pct_v51 >= 52:
        label_v51 = "ACCEPTABLE ✅"
    else:
        label_v51 = "WEAK ⚠️"

    # دمج الـ breakdown
    full_breakdown = {**base_result["breakdown"], **extra_breakdown}

    print(
        f"🧠 CONFIDENCE V5.1 | Base:{base_result['total']}"
        f" + CHOCH:{choch_bonus}"
        f" + LiqMap:{liq_map_bonus}"
        f" = TOTAL:{total_v51}/{max_v51}"
        f" [{label_v51}]"
    )

    from core.dynamic_confidence import get_dynamic_confidence_threshold
    from core.settings import V7_ENABLED

    current_hour = datetime.now(timezone.utc).hour
    dynamic_threshold = get_dynamic_confidence_threshold(
        session_name, market_regime, current_hour
    ) if V7_ENABLED else {"threshold": None, "enabled": False}

    return {
        "total":       total_v51,
        "max":         max_v51,
        "base_total":  base_result["total"],
        "choch_bonus": choch_bonus,
        "liq_bonus":   liq_map_bonus,
        "breakdown":   full_breakdown,
        "label":       label_v51,
        "pct":         round(pct_v51, 1),
        "explanation": base_result["explanation"] + f"\n  CHOCH:+{choch_bonus} | LiqMap:+{liq_map_bonus}",
        "dynamic_threshold": dynamic_threshold.get("threshold"),
        "dynamic_threshold_detail": dynamic_threshold,
    }

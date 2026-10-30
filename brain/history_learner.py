# =========================================
# FER3ON V5.8 — HISTORY LEARNER / REPLAY MEMORY
# Uses actual trade outcomes instead of naive forward-close count
# [FER3ON-FIX-2026-08-19 BRAIN-SCOPE] يتعلّم من صفقات البيلد الحالي فقط
# =========================================

from core.ai_memory import load_memory_records
from core.build_scope import filter_current_build_rows, MIN_LEARNING_SAMPLE
from core.outcome_learning import build_outcome_stats


def analyze_history(symbol=None):
    # [BRAIN-SCOPE] history_score كان بيتغذى بأكتر من 1700 صف من كل النسخ
    # مخلوطة (بما فيها صفقات النسخة الفاشلة). دلوقتي زي expected_edge_gate:
    # صفقات البيلد الحالي فقط، والعينة الصغيرة ترجع قيمة محايدة.
    rows = filter_current_build_rows(load_memory_records())
    if not rows:
        return {
            "bullish_probability": 50.0,
            "bearish_probability": 50.0,
            "replay_scenarios": 0,
            "best_scenario": None,
            "worst_scenario": None,
        }

    buy_wins = buy_total = 0
    sell_wins = sell_total = 0

    for row in rows:
        signal = str(row.get("signal", "NONE")).upper()
        result = str(row.get("result", "")).upper()
        profit = float(row.get("profit", 0) or 0)
        is_win = result == "WIN" or (result not in ("WIN", "LOSS") and profit > 0)
        if signal == "BUY":
            buy_total += 1
            if is_win:
                buy_wins += 1
        elif signal == "SELL":
            sell_total += 1
            if is_win:
                sell_wins += 1

    # [BRAIN-SCOPE] عينة أصغر من MIN_LEARNING_SAMPLE = احتمال محايد 50%
    # بدل نسبة مضللة من صفقة أو اتنين (نفس منطق الـ prior المحافظ).
    bullish = round((buy_wins / buy_total) * 100, 2) if buy_total >= MIN_LEARNING_SAMPLE else 50.0
    bearish = round((sell_wins / sell_total) * 100, 2) if sell_total >= MIN_LEARNING_SAMPLE else 50.0

    scenario_stats = build_outcome_stats(rows=rows, min_samples=5)
    best_scenario = None
    worst_scenario = None
    if scenario_stats:
        ranked = sorted(
            scenario_stats.items(),
            key=lambda kv: (kv[1].get("winrate", 0), kv[1].get("avg_rr", 0), kv[1].get("count", 0)),
            reverse=True,
        )
        best_scenario = {"scenario": ranked[0][0], **ranked[0][1]}
        worst_scenario = {"scenario": ranked[-1][0], **ranked[-1][1]}

    return {
        "bullish_probability": bullish,
        "bearish_probability": bearish,
        "replay_scenarios": len(scenario_stats),
        "best_scenario": best_scenario,
        "worst_scenario": worst_scenario,
    }


def get_history_score():
    return analyze_history("XAUUSD")

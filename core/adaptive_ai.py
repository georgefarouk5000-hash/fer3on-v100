# =========================================
# FER3ON V4 — ADAPTIVE AI + SELF OPTIMIZATION
# =========================================

from core.ai_memory import load_memory_records


# Compatibility shims for startup validation

def market_is_safe():
    rows = load_memory_records()
    if len(rows) < 10:
        return True

    last_10 = rows[-10:]
    losses = sum(1 for r in last_10 if str(r.get("result", "")).upper() == "LOSS")
    if losses >= 7:
        print(f"⛔ MARKET UNSAFE: {losses}/10 recent trades lost")
        return False
    return True


def get_strategy_confidence(strategy):
    rows = [r for r in load_memory_records() if str(r.get("strategy", "")).upper() == strategy.upper()][-20:]
    if len(rows) < 3:
        return 1.0

    wins = sum(1 for r in rows if str(r.get("result", "")).upper() == "WIN")
    winrate = wins / len(rows)

    if winrate >= 0.70:
        confidence = 1.20
    elif winrate >= 0.60:
        confidence = 1.10
    elif winrate >= 0.50:
        confidence = 1.00
    elif winrate >= 0.40:
        confidence = 0.80
    else:
        confidence = 0.60

    print(f"🤖 {strategy} CONFIDENCE: WR={round(winrate * 100, 1)}% → mult={confidence}")
    return confidence


# =========================================
# SELF OPTIMIZATION REPORT
# =========================================

_optimization_log = {}


def self_optimize():
    rows = load_memory_records()
    if len(rows) < 20 or len(rows) % 20 != 0:
        return

    print("\n" + "=" * 45)
    print("🤖 SELF OPTIMIZATION REPORT")
    print("=" * 45)

    for strategy in ["DAILY", "SMC"]:
        strat_rows = [r for r in rows if str(r.get("strategy", "")).upper() == strategy]
        if len(strat_rows) < 5:
            continue

        profits = []
        for r in strat_rows:
            try:
                profits.append(float(r.get("profit", 0) or 0))
            except Exception:
                profits.append(0.0)

        total = len(strat_rows)
        wins = sum(1 for r in strat_rows if str(r.get("result", "")).upper() == "WIN")
        wr = round(wins / total * 100, 1)
        pnl = round(sum(profits), 2)
        avg_w = round(sum(p for p in profits if p > 0) / max(1, wins), 2)
        avg_l = round(abs(sum(p for p in profits if p < 0)) / max(1, total - wins), 2)

        if wr < 40:
            rec = "⛔ أوقف هذه الاستراتيجية مؤقتاً"
        elif wr < 50:
            rec = "⚠️ قلل المخاطرة 50%"
        elif wr >= 65 and avg_w > avg_l:
            rec = "🚀 زد الثقة — أداء ممتاز"
        else:
            rec = "✅ استمر كما أنت"

        print(f"  {strategy:5s}: {total}T WR:{wr}% PnL:{pnl}$ → {rec}")
        _optimization_log[strategy] = {"winrate": wr, "pnl": pnl, "rec": rec}

    print("=" * 45 + "\n")


def get_optimization_summary():
    return _optimization_log

from core.ai_memory import load_memory_records

MEMORY_FILE = "data/memory/ai_memory.csv"


def load_memory():
    return load_memory_records()


def get_hour_stats():
    trades = load_memory()
    stats = {}
    for row in trades:
        hour = str(row.get("hour", ""))
        if hour == "":
            continue
        try:
            profit = float(row.get("profit", 0) or 0)
        except Exception:
            profit = 0.0
        stats.setdefault(hour, {"trades": 0, "wins": 0, "profit": 0.0})
        stats[hour]["trades"] += 1
        stats[hour]["profit"] += profit
        if profit > 0:
            stats[hour]["wins"] += 1
    for hour, data in stats.items():
        data["winrate"] = round((data["wins"] / data["trades"]) * 100, 2) if data["trades"] > 0 else 0
    return stats


def get_regime_stats():
    trades = load_memory()
    stats = {}
    for row in trades:
        regime = row.get("market_regime", "UNKNOWN")
        try:
            profit = float(row.get("profit", 0) or 0)
        except Exception:
            profit = 0.0
        stats.setdefault(regime, {"trades": 0, "wins": 0, "profit": 0.0})
        stats[regime]["trades"] += 1
        stats[regime]["profit"] += profit
        if profit > 0:
            stats[regime]["wins"] += 1
    for regime, data in stats.items():
        data["winrate"] = round((data["wins"] / data["trades"]) * 100, 2) if data["trades"] > 0 else 0
    return stats


def get_best_regime():
    stats = get_regime_stats()
    return max(stats, key=lambda r: stats[r]["profit"]) if stats else None


def get_worst_regime():
    stats = get_regime_stats()
    return min(stats, key=lambda r: stats[r]["profit"]) if stats else None


def hour_allowed(current_hour):
    stats = get_hour_stats()
    current_hour = str(current_hour)
    if current_hour not in stats or stats[current_hour]["trades"] < 5:
        return True
    return stats[current_hour]["winrate"] >= 40


def regime_allowed(regime):
    stats = get_regime_stats()
    if regime not in stats or stats[regime]["trades"] < 5:
        return True
    return stats[regime]["winrate"] >= 40

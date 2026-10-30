# =========================================
# FER3ON V5.8 — OUTCOME LEARNING + REPLAY MEMORY
# Learns from actual trade outcomes and scenario repetition
# =========================================

from collections import defaultdict

from core.ai_memory import load_memory_records


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _quality_band(value):
    value = _safe_float(value)
    if value >= 90:
        return "Q90+"
    if value >= 80:
        return "Q80"
    if value >= 70:
        return "Q70"
    return "Q<70"


def _scenario_key(row):
    return (
        str(row.get("strategy", "UNKNOWN")),
        str(row.get("signal", "NONE")),
        str(row.get("session", "UNKNOWN")),
        str(row.get("market_regime", "UNKNOWN")),
        _quality_band(row.get("quality_score", 0)),
        str(row.get("exec_grade", "B")),
    )


def build_outcome_stats(rows=None, min_samples=5):
    rows = rows or load_memory_records()
    buckets = defaultdict(lambda: {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "profit": 0.0,
        "rr_sum": 0.0,
        "rr_count": 0,
        "confidence_sum": 0.0,
    })

    for row in rows:
        key = _scenario_key(row)
        bucket = buckets[key]
        bucket["count"] += 1
        profit = _safe_float(row.get("profit", 0))
        rr_ratio = _safe_float(row.get("rr_ratio", 0))
        conf = _safe_float(row.get("confidence_pct", row.get("confidence_score", 0)))
        bucket["profit"] += profit
        bucket["confidence_sum"] += conf
        if rr_ratio > 0:
            bucket["rr_sum"] += rr_ratio
            bucket["rr_count"] += 1
        if str(row.get("result", "")).upper() == "WIN" or profit > 0:
            bucket["wins"] += 1
        else:
            bucket["losses"] += 1

    cooked = {}
    for key, raw in buckets.items():
        count = raw["count"]
        if count < min_samples:
            continue
        cooked[key] = {
            "count": count,
            "wins": raw["wins"],
            "losses": raw["losses"],
            "winrate": round(raw["wins"] / count * 100, 2),
            "avg_profit": round(raw["profit"] / count, 2),
            "avg_rr": round(raw["rr_sum"] / raw["rr_count"], 2) if raw["rr_count"] else 0.0,
            "avg_confidence": round(raw["confidence_sum"] / count, 2),
        }
    return cooked


def get_replay_memory(strategy, signal, session, market_regime, quality_score=0, exec_grade="B", min_samples=5):
    key = (
        str(strategy),
        str(signal),
        str(session),
        str(market_regime),
        _quality_band(quality_score),
        str(exec_grade),
    )
    stats = build_outcome_stats(min_samples=min_samples)
    exact = stats.get(key)
    if exact:
        return {
            "scenario": key,
            **exact,
            "matched": "exact",
        }

    fallback_pool = []
    for candidate_key, data in stats.items():
        similarity = 0
        if candidate_key[0] == strategy:
            similarity += 1
        if candidate_key[1] == signal:
            similarity += 1
        if candidate_key[2] == session:
            similarity += 1
        if candidate_key[3] == market_regime:
            similarity += 1
        if candidate_key[4] == _quality_band(quality_score):
            similarity += 1
        if candidate_key[5] == exec_grade:
            similarity += 1
        if similarity >= 4:
            fallback_pool.append((similarity, candidate_key, data))

    if not fallback_pool:
        return {
            "scenario": key,
            "count": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 50.0,
            "avg_profit": 0.0,
            "avg_rr": 0.0,
            "avg_confidence": 50.0,
            "matched": "none",
        }

    fallback_pool.sort(key=lambda x: (x[0], x[2].get("count", 0), x[2].get("winrate", 0)), reverse=True)
    similarity, candidate_key, best = fallback_pool[0]
    return {
        "scenario": candidate_key,
        **best,
        "matched": f"fallback:{similarity}/6",
    }


def get_probability_distribution(signal, replay_stats, base_confidence=50):
    replay_wr = _safe_float(replay_stats.get("winrate", 50))
    sample_boost = min(_safe_float(replay_stats.get("count", 0)) / 100.0, 1.0) * 10.0
    confidence = _safe_float(base_confidence, 50)

    directional = max(5.0, min(92.0, replay_wr * 0.72 + confidence * 0.28 + sample_boost))
    no_trade = max(5.0, 100.0 - directional - 12.0)
    opposite = max(3.0, 100.0 - directional - no_trade)

    if signal == "BUY":
        return {
            "BUY": round(directional, 1),
            "SELL": round(opposite, 1),
            "NO_TRADE": round(no_trade, 1),
        }
    if signal == "SELL":
        return {
            "BUY": round(opposite, 1),
            "SELL": round(directional, 1),
            "NO_TRADE": round(no_trade, 1),
        }
    return {
        "BUY": 25.0,
        "SELL": 25.0,
        "NO_TRADE": 50.0,
    }

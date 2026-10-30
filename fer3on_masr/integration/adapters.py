from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone

from core.atr_manager import calculate_atr
from core.market_regime import detect_market_regime
from core.session_intelligence import get_session


def _cf(rate: Any, key: str, default: float = 0.0) -> float:
    try:
        if isinstance(rate, dict):
            v = rate.get(key, default)
        else:
            v = getattr(rate, key, default)
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _detect_equal_levels(rates: List[Any], side: str, tolerance_ratio: float = 0.0005) -> List[float]:
    """
    يرصد المستويات المتساوية (equal highs/lows) بتسامح نسبي.
    side: "high" أو "low".
    """
    if not rates or len(rates) < 5:
        return []
    prices = [_cf(r, side, 0.0) for r in rates[-30:] if _cf(r, side, 0.0) > 0]
    if not prices:
        return []
    ref = sum(prices) / len(prices)
    tol = ref * tolerance_ratio
    clusters: List[List[float]] = []
    for p in prices:
        placed = False
        for c in clusters:
            if abs(c[0] - p) <= tol:
                c.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])
    equal_levels = [sum(c) / len(c) for c in clusters if len(c) >= 2]
    return sorted(equal_levels)


def _liquidity_pools(rates: List[Any], current_price: float) -> List[Dict[str, Any]]:
    if not rates:
        return []
    highs = _detect_equal_levels(rates, "high")
    lows = _detect_equal_levels(rates, "low")
    pools: List[Dict[str, Any]] = []
    for h in highs:
        pools.append({"price": h, "side": "above" if h > current_price else "below", "type": "equal_high"})
    for l in lows:
        pools.append({"price": l, "side": "above" if l > current_price else "below", "type": "equal_low"})
    return pools


def _compute_sweep_bundle(rates: List[Any], session: str) -> Dict[str, Any]:
    """
    يحسب sweep_probability و sweep_direction بأمان — يعتمد على
    core/sweep_predictor.py الحقيقي بدل التقدير الثنائي القديم في main.py.
    """
    if not rates:
        return {
            "sweep_probability": 0.0,
            "sweep_direction": "NONE",
            "sweep_confidence_bonus": 0.0,
            "equal_highs": [],
            "equal_lows": [],
            "liquidity_pools": [],
            "distance_next_pool": None,
            "sweep_enabled": False,
        }

    equal_highs = _detect_equal_levels(rates, "high")
    equal_lows = _detect_equal_levels(rates, "low")
    price = _cf(rates[-1], "close", 0.0)
    pools = _liquidity_pools(rates, price)

    # أقرب برك سيولة (فوق أو تحت)
    distances = []
    for p in pools:
        try:
            distances.append(abs(float(p["price"]) - price))
        except (TypeError, ValueError, KeyError):
            continue
    distance_next_pool = min(distances) if distances else None

    # نجرّب كلا الاتجاهين ونختار الأقوى.
    best_prob = 0.0
    best_dir = "NONE"
    best_bonus = 0.0
    sweep_enabled = True
    try:
        from core.sweep_predictor import compute_sweep_probability
        for signal in ("BUY", "SELL"):
            res = compute_sweep_probability(
                signal=signal,
                equal_highs=equal_highs,
                equal_lows=equal_lows,
                liquidity_pools=pools,
                current_price=price,
                session=session,
                distance_to_pool=distance_next_pool,
            )
            if not res.get("enabled", True):
                sweep_enabled = False
                break
            prob = float(res.get("sweep_probability", 0.0) or 0.0)
            if prob > best_prob:
                best_prob = prob
                best_dir = signal
                best_bonus = float(res.get("confidence_bonus", 0.0) or 0.0)
    except Exception:
        # fallback آمن: نبني تقديرًا خفيفًا من كثرة equal levels وقرب السعر
        combined = len(equal_highs) + len(equal_lows)
        best_prob = min(60.0, combined * 12.0)
        if equal_highs and (not equal_lows or equal_highs[-1] > price):
            best_dir = "BUY"
        elif equal_lows:
            best_dir = "SELL"

    return {
        "sweep_probability": round(best_prob, 2),
        "sweep_direction": best_dir,
        "sweep_confidence_bonus": round(best_bonus, 2),
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "liquidity_pools": pools,
        "distance_next_pool": distance_next_pool,
        "sweep_enabled": sweep_enabled,
    }


class LegacyBridge:
    """
    Bridge بين المحرك القديم في core/ وطبقة FAIE.

    توسعات هذه النسخة (لسد الفجوات الأربع):
      1) sweep_probability + sweep_direction فعليان من core/sweep_predictor.py
         بدل التقدير الثنائي القديم (0 أو 100).
      2) equal_highs / equal_lows / liquidity_pools محسوبة من نفس rates
         بدل تركها فارغة.
      3) session_hint موحّد يستخدمه sweep_predictor.
      4) news_bias يبقى NEUTRAL افتراضيًا حتى يصل مصدر أخبار حقيقي —
         لكنه لم يعد افتراضًا خفيًا؛ الكود يعلن ذلك في details.source.
    """

    def build_snapshot(self, rates: List[Any], symbol: str = "XAUUSD") -> Dict[str, Any]:
        atr = calculate_atr(rates) if rates else 0.0
        regime = detect_market_regime(rates) if rates else "UNKNOWN"
        session = get_session(datetime.now(timezone.utc).hour)

        sweep_bundle = _compute_sweep_bundle(rates, session)

        snapshot: Dict[str, Any] = {
            "symbol": symbol,
            "rates": rates,
            "atr": atr,
            "market_regime": regime,
            "session": session,
            "spread": 18.0,
            "volume": len(rates or []),
            "news_bias": "NEUTRAL",
            "news_bias_source": "default_no_feed_connected",
        }
        snapshot.update(sweep_bundle)
        return snapshot

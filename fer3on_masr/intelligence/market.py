from __future__ import annotations

from statistics import mean
from typing import Any

from fer3on_masr.kernel.models import MarketEngineReport


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_closes(rates: list[Any]) -> list[float]:
    closes: list[float] = []
    for rate in rates or []:
        if isinstance(rate, dict):
            closes.append(_safe_float(rate.get("close", 0.0)))
        else:
            closes.append(_safe_float(getattr(rate, "close", 0.0)))
    return [c for c in closes if c > 0]


class MarketIntelligenceLayer:
    ENGINE_NAMES = (
        "trend",
        "liquidity",
        "structure",
        "volatility",
        "volume",
        "momentum",
        "session",
        "news",
        "sentiment",
        "spread",
    )

    def analyze(self, snapshot: dict[str, Any]) -> list[MarketEngineReport]:
        rates = snapshot.get("rates", []) or []
        closes = _extract_closes(rates)
        if len(closes) < 5:
            closes = closes or [1.0, 1.1, 1.2, 1.15, 1.25]

        recent = closes[-20:]
        base = mean(recent)
        last = recent[-1]
        first = recent[0]
        delta = last - first
        direction = "BUY" if delta >= 0 else "SELL"
        confidence = min(95.0, 50.0 + abs(delta) / max(base, 1e-6) * 1000.0)
        atr = _safe_float(snapshot.get("atr", 0.0), 0.0)
        spread = _safe_float(snapshot.get("spread", 0.0), 0.0)
        volume_hint = _safe_float(snapshot.get("volume", len(recent)), float(len(recent)))
        regime = str(snapshot.get("market_regime", "UNKNOWN"))
        session = str(snapshot.get("session", "UNKNOWN"))

        reports = [
            MarketEngineReport("Trend Engine", direction, confidence, confidence, {"delta": delta, "base": base}),
            MarketEngineReport("Liquidity Engine", direction, max(35.0, confidence - 5), max(35.0, confidence - 5), {"atr": atr}),
            MarketEngineReport("Structure Engine", direction, max(30.0, confidence - 3), max(30.0, confidence - 3), {"regime": regime}),
            MarketEngineReport("Volatility Engine", "HIGH" if atr > 0 else "NORMAL", min(90.0, 40.0 + atr * 10), min(90.0, 40.0 + atr * 10), {"atr": atr}),
            MarketEngineReport("Volume Engine", direction, min(88.0, 35.0 + volume_hint), min(88.0, 35.0 + volume_hint), {"volume_hint": volume_hint}),
            MarketEngineReport("Momentum Engine", direction, confidence, confidence, {"last": last}),
            MarketEngineReport("Session Engine", session, 70.0, 70.0, {"session": session}),
            MarketEngineReport("News Engine", snapshot.get("news_bias", "NEUTRAL"), 50.0, 50.0, {"news_bias": snapshot.get("news_bias", "NEUTRAL")}),
            MarketEngineReport("Sentiment Engine", direction, max(35.0, confidence - 7), max(35.0, confidence - 7), {"sentiment_source": "price_action"}),
            MarketEngineReport("Spread Engine", "WIDE" if spread > 30 else "NORMAL", max(20.0, 80.0 - spread), max(20.0, 80.0 - spread), {"spread": spread}),
        ]
        return reports

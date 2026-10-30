from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fer3on_masr.kernel.models import StrategyDecision

# =============================================================================
# STRATEGY AI AGENTS — REAL PER-AGENT DIFFERENTIATION
# =============================================================================
# النسخة القديمة: كل الوكلاء (Daily/Swing/Scalp/SMC/Micro/News/Recovery) كانوا
# ينفّذون نفس evaluate() الواحد، ويقرؤون فقط context["market_bias"] (نفس
# اتجاه Trend Engine الوحيد) — الفارق الوحيد بينهم كان confidence_bias ثابت
# يُضاف/يُطرح. عمليًا: 7 "وكلاء" لكن صوت تحليلي واحد فقط مكرر 7 مرات.
#
# هذه النسخة تجعل كل وكيل يقرأ مصدر بيانات مختلف فعليًا من context الغني
# (الذي يبنيه الآن fer3on_masr/app.py من TimeframeIntelligence/LiquidityIntelligence/
# CandleIntelligence/history_loader بدل قيمة واحدة مشتركة):
#   - Daily AI   -> تقرير D1 (+ تأكيد W1)
#   - Swing AI   -> مزيج H4/H1
#   - Scalp AI   -> M1/M5 + تأكيد نمط الشمعة الحالي
#   - SMC AI     -> ملف السيولة (buy/sell side, sweep zones) + Structure Engine
#   - Micro AI   -> M1 مع فلتر تقلّب (ATR) وتفضيل صريح لنظام RANGING
#                   (يطابق REGIME_STRATEGY_FIT في core/market_regime.py)
#   - News AI    -> news_bias الفعلي من اللقطة (snapshot)، صوت دفاعي عند الأخبار
#   - Recovery AI-> إحصاءات سجل حقيقي (history_stats: سلسلة خسائر حقيقية) —
#                   لا يُضاعف الحجم بعد خسائر (anti-martingale)، بل يُقلّصه
#
# أي حقل غير متوفر في context (مثلًا لا يوجد تقرير D1) يُرجع الوكيل احتياطيًا
# إلى market_bias العام مع الإفصاح الصريح عن ذلك في rationale، بدل اختلاق قيمة.


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _tf(context: dict[str, Any], name: str) -> dict[str, Any] | None:
    return (context.get("timeframes") or {}).get(name)


_BULLISH_CANDLES = {
    "Bullish Engulfing", "Hammer", "Bullish Marubozu", "Morning Star",
    "Three White Soldiers", "Piercing Line", "Dragonfly Doji", "Tweezer Bottom",
    "Three Inside Up", "Bullish Harami",
}
_BEARISH_CANDLES = {
    "Bearish Engulfing", "Shooting Star", "Hanging Man", "Bearish Marubozu",
    "Evening Star", "Three Black Crows", "Dark Cloud Cover", "Gravestone Doji",
    "Tweezer Top", "Three Inside Down", "Bearish Harami",
}

# النتيجة المُرجَعة من كل دالة: (action, confidence, risk_fraction, lot_fraction, rationale)
# risk_fraction/lot_fraction نسبة من risk_cap/lot_cap العامين للحساب (وليست قيمًا
# مطلقة)، لتبقى محكومة دومًا بسقف الحساب بغض النظر عن منطق الوكيل الداخلي.
SignalResult = tuple[str, float, float, float, list[str]]


def _daily_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    d1 = _tf(context, "D1")
    w1 = _tf(context, "W1")
    if not d1:
        fallback = str(context.get("market_bias", agent.default_action)).upper()
        return (
            fallback,
            _safe_float(context.get("base_confidence"), 60.0),
            1.0, 1.0,
            ["D1 report unavailable -> fallback to overall market_bias"],
        )
    action = d1["trend"]
    confidence = float(d1["confidence"])
    rationale = [f"D1 trend={d1['trend']} confidence={d1['confidence']} momentum={d1.get('momentum')}"]
    if w1:
        if w1["trend"] == action:
            confidence = _clamp(confidence + 6.0, 0.0, 97.0)
            rationale.append(f"W1 confirms D1 direction ({w1['trend']}) -> +6 confidence")
        else:
            confidence = _clamp(confidence - 10.0, 0.0, 97.0)
            rationale.append(f"W1 disagrees with D1 ({w1['trend']} vs {action}) -> -10 confidence")
    return action, confidence, 1.0, 1.05, rationale


def _swing_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    h4 = _tf(context, "H4")
    h1 = _tf(context, "H1")
    reports = [r for r in (h4, h1) if r]
    if not reports:
        fallback = str(context.get("market_bias", agent.default_action)).upper()
        return (
            fallback,
            _safe_float(context.get("base_confidence"), 60.0),
            0.9, 0.9,
            ["H4/H1 reports unavailable -> fallback to overall market_bias"],
        )
    buys = sum(1 for r in reports if r["trend"] == "BUY")
    action = "BUY" if buys >= (len(reports) - buys) else "SELL"
    confidence = sum(float(r["confidence"]) for r in reports) / len(reports)
    rationale = [f"{r['timeframe']} trend={r['trend']} confidence={r['confidence']}" for r in reports]
    if h4 and h1 and h4["trend"] != h1["trend"]:
        confidence = _clamp(confidence - 5.0, 0.0, 95.0)
        rationale.append("H4/H1 disagree -> blended vote, -5 confidence")
    return action, confidence, 0.85, 0.9, rationale


def _scalp_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    base_tf = _tf(context, "M1") or _tf(context, "M5")
    candles = context.get("candles") or []
    top_candle = candles[0] if candles else None
    if not base_tf:
        fallback = str(context.get("market_bias", agent.default_action)).upper()
        return (
            fallback,
            _safe_float(context.get("base_confidence"), 55.0),
            0.5, 0.4,
            ["M1/M5 reports unavailable -> fallback to overall market_bias"],
        )
    action = base_tf["trend"]
    confidence = float(base_tf["confidence"])
    rationale = [f"{base_tf['timeframe']} trend={base_tf['trend']} confidence={base_tf['confidence']}"]
    if top_candle:
        label = str(top_candle.get("label", ""))
        prob = _safe_float(top_candle.get("probability"), 0.0)
        if label in _BULLISH_CANDLES and action == "BUY":
            confidence = _clamp(confidence + prob * 0.15, 0.0, 97.0)
            rationale.append(f"candle confirms direction: {label} ({prob}%) -> +confidence")
        elif label in _BEARISH_CANDLES and action == "SELL":
            confidence = _clamp(confidence + prob * 0.15, 0.0, 97.0)
            rationale.append(f"candle confirms direction: {label} ({prob}%) -> +confidence")
        elif label in _BULLISH_CANDLES or label in _BEARISH_CANDLES:
            confidence = _clamp(confidence - prob * 0.10, 0.0, 97.0)
            rationale.append(f"candle contradicts direction: {label} ({prob}%) -> -confidence")
    rationale.append("scalp profile: tight risk envelope, intended for high trade frequency (frequency itself governed elsewhere, e.g. MAX_DAILY_TRADES)")
    return action, confidence, 0.55, 0.35, rationale


def _smc_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    liquidity = context.get("liquidity") or {}
    buy_side = liquidity.get("buy_side", [])
    sell_side = liquidity.get("sell_side", [])
    best_target = _safe_float(liquidity.get("best_target"), 0.0)
    structure_bias = str(context.get("structure_bias", agent.default_action)).upper()
    structure_confidence = _safe_float(context.get("structure_confidence"), 60.0)

    # === NEW: real sweep probability evidence (was ignored in old version) ===
    sweep_probability = _safe_float(context.get("sweep_probability"), 0.0)
    sweep_direction = str(context.get("sweep_direction", "NONE") or "NONE").upper()
    sweep_bonus = _safe_float(context.get("sweep_confidence_bonus"), 0.0)

    # === NEW: order flow evidence ===
    orderflow = context.get("orderflow") or {}
    of_bias = str(orderflow.get("bias", "NEUTRAL") or "NEUTRAL").upper()
    of_aggression = _safe_float((orderflow.get("details") or {}).get("aggression_pressure"), 0.0)

    # === NEW: anchored VWAP evidence ===
    vwap = context.get("anchored_vwap") or {}
    vwap_bias_val = str(vwap.get("bias", "NEUTRAL") or "NEUTRAL").upper()

    # === NEW: volume profile evidence ===
    vp = context.get("volume_profile") or {}
    vp_bias = str(vp.get("bias", "NEUTRAL") or "NEUTRAL").upper()

    if best_target in buy_side:
        liquidity_bias = "BUY"
    elif best_target in sell_side:
        liquidity_bias = "SELL"
    else:
        liquidity_bias = structure_bias

    rationale = [
        f"liquidity best_target={best_target} draws {liquidity_bias}-side liquidity",
        f"structure_bias={structure_bias} (Structure Engine)",
    ]
    action = structure_bias
    if liquidity_bias == structure_bias:
        confidence = _clamp(structure_confidence + 8.0, 0.0, 97.0)
        rationale.append("liquidity draw agrees with structure -> +8 confidence")
    else:
        confidence = _clamp(structure_confidence - 6.0, 0.0, 97.0)
        rationale.append("liquidity draw conflicts with structure -> -6 confidence (watch for a sweep before reversal)")

    # Sweep probability integration (real, was completely ignored before)
    if sweep_probability >= 70.0:
        if sweep_direction == action:
            confidence = _clamp(confidence + min(sweep_bonus, 8.0), 0.0, 97.0)
            rationale.append(f"sweep_probability={sweep_probability:.1f} direction={sweep_direction} aligns with action -> +{min(sweep_bonus, 8.0):.1f} confidence")
        elif sweep_direction in ("BUY", "SELL") and sweep_direction != action:
            confidence = _clamp(confidence - 5.0, 0.0, 97.0)
            rationale.append(f"sweep_probability={sweep_probability:.1f} points {sweep_direction} against our {action} -> -5 confidence (potential reversal setup)")
    elif sweep_probability >= 55.0:
        rationale.append(f"sweep_probability={sweep_probability:.1f} elevated but below strong threshold -> watch only")

    # Order Flow integration
    if of_bias == action and of_aggression >= 0.4:
        confidence = _clamp(confidence + 4.0, 0.0, 97.0)
        rationale.append(f"orderflow bias={of_bias} aggression={of_aggression:.2f} confirms action -> +4 confidence (source: synthetic)")
    elif of_bias in ("BUY", "SELL") and of_bias != action:
        confidence = _clamp(confidence - 3.0, 0.0, 97.0)
        rationale.append(f"orderflow bias={of_bias} disagrees with action={action} -> -3 confidence (source: synthetic)")

    # Anchored VWAP integration
    if vwap_bias_val == action:
        confidence = _clamp(confidence + 3.0, 0.0, 97.0)
        rationale.append(f"anchored_vwap bias={vwap_bias_val} confirms action -> +3 confidence")
    elif vwap_bias_val in ("BUY", "SELL") and vwap_bias_val != action:
        confidence = _clamp(confidence - 2.0, 0.0, 97.0)
        rationale.append(f"anchored_vwap bias={vwap_bias_val} disagrees -> -2 confidence")

    # Volume Profile integration
    if vp_bias == action:
        confidence = _clamp(confidence + 3.0, 0.0, 97.0)
        rationale.append(f"volume_profile bias={vp_bias} confirms action -> +3 confidence")
    elif vp_bias in ("BUY", "SELL") and vp_bias != action:
        confidence = _clamp(confidence - 2.0, 0.0, 97.0)
        rationale.append(f"volume_profile bias={vp_bias} disagrees -> -2 confidence")

    traps = liquidity.get("traps") or []
    if traps:
        rationale.append(f"active trap watch: {', '.join(traps)}")
    return action, confidence, 1.0, 1.0, rationale


def _micro_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    m1 = _tf(context, "M1")
    m5 = _tf(context, "M5")
    regime = str(context.get("market_regime", "UNKNOWN")).upper()
    if not m1:
        fallback = str(context.get("market_bias", agent.default_action)).upper()
        return (
            fallback,
            _safe_float(context.get("base_confidence"), 50.0),
            0.3, 0.15,
            ["M1 report unavailable -> fallback to overall market_bias"],
        )
    action = m1["trend"]
    confidence = float(m1["confidence"])
    rationale = [f"M1 trend={m1['trend']} confidence={m1['confidence']}"]

    if regime == "RANGING":
        confidence = _clamp(confidence + 7.0, 0.0, 95.0)
        rationale.append("RANGING regime fits micro-scalping (+7 confidence, matches core/market_regime.py REGIME_STRATEGY_FIT)")
    elif regime == "TRENDING":
        confidence = _clamp(confidence - 10.0, 0.0, 95.0)
        rationale.append("TRENDING regime doesn't fit micro-scalping well (-10 confidence)")

    m1_atr = _safe_float(m1.get("atr"), 0.0)
    m5_atr = _safe_float(m5.get("atr") if m5 else 0.0, 0.0)
    if m1_atr > 0 and m5_atr > 0 and m1_atr > m5_atr * 1.3:
        confidence = _clamp(confidence - 8.0, 0.0, 95.0)
        rationale.append("M1 ATR spiking relative to M5 -> likely noise, reduced confidence")

    return action, confidence, 0.25, 0.12, rationale


def _news_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    news_bias = str(context.get("news_bias", "NEUTRAL")).upper()
    market_bias = str(context.get("market_bias", agent.default_action)).upper()
    base_confidence = _safe_float(context.get("base_confidence"), 60.0)

    if news_bias == "NEUTRAL":
        rationale = ["no active news bias detected -> weak deferential vote to overall market_bias"]
        return market_bias, _clamp(base_confidence - 15.0, 0.0, 90.0), 0.4, 0.25, rationale

    action = news_bias if news_bias in {"BUY", "SELL"} else "HOLD"
    rationale = [f"news_bias={news_bias} -> defensive stance around active news catalyst"]
    confidence = _clamp(base_confidence + 10.0, 0.0, 95.0)
    return action, confidence, 0.2, 0.1, rationale


def _recovery_signal(agent: "StrategyAgent", context: dict[str, Any]) -> SignalResult:
    stats = context.get("history_stats") or {}
    sample_size = int(stats.get("sample_size", 0) or 0)
    streak = int(stats.get("current_losing_streak", 0) or 0)
    market_bias = str(context.get("market_bias", agent.default_action)).upper()
    base_confidence = _safe_float(context.get("base_confidence"), 60.0)
    regime = str(context.get("market_regime", "UNKNOWN")).upper()

    if sample_size == 0:
        rationale = ["no real trade history yet -> conservative default, no streak data available"]
        return market_bias, _clamp(base_confidence - 10.0, 0.0, 90.0), 0.5, 0.4, rationale

    if streak >= 2:
        rationale = [f"current real losing streak={streak} -> defensive HOLD, size is reduced not increased (anti-martingale)"]
        confidence = _clamp(55.0 + streak * 3.0, 0.0, 85.0)
        if regime == "CRISIS":
            confidence = _clamp(confidence + 5.0, 0.0, 90.0)
            rationale.append("CRISIS regime matches legacy core/market_regime.py RECOVERY mapping -> defensive stance reinforced")
        return "HOLD", confidence, 0.15, 0.08, rationale

    win_rate = stats.get("win_rate")
    rationale = [f"no active losing streak (win_rate={win_rate}%, sample={sample_size}) -> conservative participation"]
    return market_bias, _clamp(base_confidence - 5.0, 0.0, 90.0), 0.45, 0.3, rationale


_SIGNAL_HANDLERS: dict[str, Callable[["StrategyAgent", dict[str, Any]], SignalResult]] = {
    "daily": _daily_signal,
    "swing": _swing_signal,
    "scalp": _scalp_signal,
    "smc": _smc_signal,
    "micro": _micro_signal,
    "news": _news_signal,
    "recovery": _recovery_signal,
}


@dataclass(slots=True)
class StrategyAgent:
    name: str
    kind: str
    default_action: str
    memory: list[dict[str, Any]] = field(default_factory=list)
    confidence_bias: float = 0.0

    def evaluate(self, context: dict[str, Any], weight: float = 1.0) -> StrategyDecision:
        handler = _SIGNAL_HANDLERS.get(self.kind)
        if handler is None:
            action = str(context.get("market_bias", self.default_action)).upper()
            confidence = _safe_float(context.get("base_confidence"), 60.0)
            risk_fraction, lot_fraction = 1.0, 1.0
            rationale = [f"unknown kind '{self.kind}' -> generic fallback"]
        else:
            action, confidence, risk_fraction, lot_fraction, rationale = handler(self, context)

        confidence = _clamp(confidence + self.confidence_bias, 5.0, 97.0)
        risk_cap = _safe_float(context.get("risk_cap"), 0.42)
        lot_cap = _safe_float(context.get("lot_cap"), 0.18)
        risk_pct = _clamp(risk_cap * _clamp(risk_fraction, 0.05, 1.2), 0.02, 0.55)
        lot = _clamp(lot_cap * _clamp(lot_fraction, 0.05, 1.2), 0.01, 0.35)

        full_rationale = list(rationale) + [f"weight={weight:.3f}", f"memory_size={len(self.memory)}"]
        decision = StrategyDecision(
            name=self.name,
            action=action,
            confidence=round(confidence, 2),
            weight=round(weight, 4),
            risk_pct=round(risk_pct, 4),
            suggested_lot=round(lot * weight, 4),
            rationale=full_rationale,
            details={"kind": self.kind, "memory": self.memory[-3:]},
        )
        self.memory.append({"action": action, "confidence": decision.confidence, "weight": decision.weight})
        self.memory = self.memory[-200:]
        return decision


class StrategyAgentFactory:
    # (name, kind, default_action_fallback, confidence_bias)
    DEFAULTS = (
        ("Daily AI", "daily", "BUY", 6.0),
        ("Swing AI", "swing", "BUY", 3.5),
        ("Scalp AI", "scalp", "BUY", -2.0),
        ("SMC AI", "smc", "SELL", 1.0),
        ("Micro AI", "micro", "BUY", -4.0),
        ("News AI", "news", "BUY", -1.0),
        ("Recovery AI", "recovery", "BUY", -3.0),
    )

    @classmethod
    def build_default_agents(cls) -> list[StrategyAgent]:
        return [
            StrategyAgent(name=name, kind=kind, default_action=action, confidence_bias=bias)
            for name, kind, action, bias in cls.DEFAULTS
        ]

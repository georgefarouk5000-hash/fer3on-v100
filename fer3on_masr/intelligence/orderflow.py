from __future__ import annotations

from typing import Any, Dict, List

from fer3on_masr.kernel.models import MarketEngineReport

# نستخدم المنطق الموجود فعليًا في core/synthetic_orderflow.py — لا نُكرر الحساب.
# ملاحظة الشفافية: هذا Order Flow اصطناعي (Synthetic) وليس مقروءًا من Level 2 / DOM.
# يبني تقريبًا معقولًا من: سرعة الشمعة، عدوانية الذيل، سلوك السبريد، تمدد الفوليوم
# (المتاح، غالبًا tick_volume)، والزخم. هذه الحقيقة معلنة في details.source.
from core.synthetic_orderflow import analyze_orderflow


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


def _last_n(rates: List[Any], n: int) -> List[Any]:
    if not rates:
        return []
    return rates[-max(1, int(n)):]


def _candle_velocity(rates: List[Any]) -> float:
    window = _last_n(rates, 5)
    if len(window) < 2:
        return 0.0
    closes = [_cf(r, "close") for r in window]
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg = sum(diffs) / len(diffs) if diffs else 0.0
    ref = max(1e-9, abs(closes[-1]))
    return max(-1.0, min(1.0, avg / (ref * 0.002)))


def _wick_aggression(rates: List[Any]) -> float:
    window = _last_n(rates, 3)
    if not window:
        return 0.0
    scores = []
    for r in window:
        h = _cf(r, "high")
        l = _cf(r, "low")
        o = _cf(r, "open")
        c = _cf(r, "close")
        rng = max(1e-9, h - l)
        body = abs(c - o)
        wicks = max(0.0, (rng - body))
        scores.append(min(1.0, wicks / rng))
    return sum(scores) / len(scores)


def _volume_expansion(rates: List[Any]) -> float:
    window = _last_n(rates, 20)
    if len(window) < 5:
        return 0.0
    vols = []
    for r in window:
        v = _cf(r, "real_volume") or _cf(r, "tick_volume") or _cf(r, "volume")
        vols.append(v)
    vols = [v for v in vols if v > 0]
    if len(vols) < 3:
        return 0.0
    baseline = sum(vols[:-1]) / max(1, len(vols) - 1)
    if baseline <= 0:
        return 0.0
    ratio = vols[-1] / baseline
    return max(0.0, min(1.0, (ratio - 1.0)))


def _imbalance(rates: List[Any]) -> float:
    window = _last_n(rates, 10)
    if not window:
        return 0.0
    ups = 0.0
    downs = 0.0
    for r in window:
        c = _cf(r, "close")
        o = _cf(r, "open")
        if c > o:
            ups += (c - o)
        elif c < o:
            downs += (o - c)
    total = ups + downs
    if total <= 0:
        return 0.0
    return max(-1.0, min(1.0, (ups - downs) / total))


def _momentum_acceleration(rates: List[Any]) -> float:
    window = _last_n(rates, 8)
    if len(window) < 4:
        return 0.0
    closes = [_cf(r, "close") for r in window]
    half = len(closes) // 2
    slope_recent = closes[-1] - closes[-half]
    slope_prior = closes[-half] - closes[0]
    diff = slope_recent - slope_prior
    ref = max(1e-9, abs(closes[-1]))
    return max(-1.0, min(1.0, diff / (ref * 0.003)))


def _spread_behavior(snapshot: Dict[str, Any] | None) -> float:
    if not snapshot:
        return 0.0
    spread = float(snapshot.get("spread", 0.0) or 0.0)
    # نطبق تطبيعًا لينًا: 0 spread -> 0.0، 30 نقطة -> 0.5، 60+ -> 1.0
    return max(0.0, min(1.0, spread / 60.0))


class OrderFlowIntelligence:
    """
    OrderFlowAnalyst — تحليل تدفق الأوامر الاصطناعي (Synthetic) داخل FAIE.

    مصدر البيانات:
      - أسعار OHLC + tick_volume (أو real_volume إن توفر) من نفس الشموع.
      - قيمة spread من snapshot (إن وُجدت).

    الشفافية: يعلن في details.source أن التحليل Synthetic وليس من Level 2 / DOM.
    القرار الحقيقي للـ Real Order Flow لسه محتاج ربط API بروكر يوفّر real volume/DOM.
    """

    def analyze(self, rates: List[Any], snapshot: Dict[str, Any] | None = None) -> MarketEngineReport:
        if not rates or len(rates) < 3:
            return MarketEngineReport(
                name="Order Flow Engine",
                bias="NEUTRAL",
                confidence=0.0,
                score=0.0,
                details={
                    "source": "synthetic_orderflow",
                    "reason": "insufficient_rates",
                    "is_real_dom": False,
                },
            )

        cv = _candle_velocity(rates)
        wa = _wick_aggression(rates)
        sb = _spread_behavior(snapshot)
        ve = _volume_expansion(rates)
        im = _imbalance(rates)
        ma = _momentum_acceleration(rates)

        result = analyze_orderflow(
            candle_velocity=cv,
            wick_aggression=wa,
            spread_behavior=sb,
            volume_expansion=ve,
            imbalance=im,
            momentum_acceleration=ma,
        )

        raw_bias = str(result.get("orderflow_bias", "NEUTRAL")).upper()
        bias = {"BULLISH": "BUY", "BEARISH": "SELL"}.get(raw_bias, "NEUTRAL")

        aggression = float(result.get("aggression_pressure", 0.0))
        exhaustion = float(result.get("exhaustion_probability", 0.0))
        # ثقة أساسية 40، تُعزَّز بالضغط العدواني في اتجاه واضح وتُخفَّض بالإرهاق.
        base_conf = 40.0 + (aggression * 45.0) - (exhaustion * 15.0)
        if bias == "NEUTRAL":
            base_conf = min(base_conf, 45.0)
        confidence = max(5.0, min(95.0, base_conf))
        score = round(aggression * 100.0, 2)

        details = dict(result)
        details.update({
            "source": "synthetic_orderflow",
            "is_real_dom": False,
            "inputs": {
                "candle_velocity": round(cv, 4),
                "wick_aggression": round(wa, 4),
                "spread_behavior": round(sb, 4),
                "volume_expansion": round(ve, 4),
                "imbalance": round(im, 4),
                "momentum_acceleration": round(ma, 4),
            },
        })

        return MarketEngineReport(
            name="Order Flow Engine",
            bias=bias,
            confidence=round(confidence, 2),
            score=score,
            details=details,
        )

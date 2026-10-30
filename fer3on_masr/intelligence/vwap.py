from __future__ import annotations

from typing import Any, Dict, List, Optional

from fer3on_masr.kernel.models import MarketEngineReport

from core.anchored_vwap import (
    compute_anchored_vwap,
    vwap_bias,
    vwap_reclaim_signal,
)


class AnchoredVWAPIntelligence:
    """
    Anchored VWAP Analyst — VWAP الحقيقي داخل FAIE.

    شفافية:
      - Typical Price = (H+L+C)/3
      - الحجم: real_volume إن وُجد، وإلا tick_volume، وإلا وزن موحّد.
      - المرساة الافتراضية: session_open (بداية الجلسة الحالية UTC).
      - القيم المعادة تشمل النطاقات ±1σ و ±2σ لاستخدامها في اتخاذ القرار.
    """

    def __init__(self, default_anchor: str = "session_open") -> None:
        self.default_anchor = default_anchor

    def analyze(
        self,
        rates: List[Any],
        anchor: Optional[str] = None,
        lookback: int = 60,
        index: Optional[int] = None,
    ) -> MarketEngineReport:
        anchor = anchor or self.default_anchor
        result = compute_anchored_vwap(
            rates,
            anchor=anchor,
            lookback=lookback,
            index=index,
            include_bands=True,
        )
        if not result.get("valid"):
            return MarketEngineReport(
                name="Anchored VWAP Engine",
                bias="NEUTRAL",
                confidence=0.0,
                score=0.0,
                details={
                    "source": result.get("source", "none"),
                    "reason": result.get("reason", "invalid_vwap"),
                    "anchor": anchor,
                    "valid": False,
                },
            )

        bias = vwap_bias(result)
        reclaim = vwap_reclaim_signal(rates, result)
        price = float(result.get("price", 0.0))
        vwap = float(result.get("vwap", 0.0))
        sd = float(result.get("stdev", 0.0))

        # ثقة أساسية 55، تُعزَّز عند تجاوز ±1σ ومع reclaim مؤكد.
        confidence = 55.0
        if sd > 0:
            deviations = abs(price - vwap) / sd
            confidence += min(25.0, deviations * 10.0)
        if reclaim != "NONE" and reclaim == bias:
            confidence = min(95.0, confidence + 10.0)
        confidence = max(5.0, min(95.0, confidence))

        return MarketEngineReport(
            name="Anchored VWAP Engine",
            bias=bias,
            confidence=round(confidence, 2),
            score=round(abs(price - vwap), 4),
            details={
                "source": result.get("source"),
                "anchor": result.get("anchor"),
                "anchor_index": result.get("anchor_index"),
                "vwap": vwap,
                "upper_band_1sd": result.get("upper_band_1sd"),
                "lower_band_1sd": result.get("lower_band_1sd"),
                "upper_band_2sd": result.get("upper_band_2sd"),
                "lower_band_2sd": result.get("lower_band_2sd"),
                "stdev": sd,
                "distance_from_price": result.get("distance_from_price"),
                "price": price,
                "vwap_reclaim_signal": reclaim,
                "sample_size": result.get("sample_size"),
                "is_real_volume": result.get("source") == "real_volume",
                "valid": True,
            },
        )

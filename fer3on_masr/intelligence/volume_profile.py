from __future__ import annotations

from typing import Any, Dict, List

from fer3on_masr.kernel.models import MarketEngineReport

# نستخدم الحساب الحقيقي من core/volume_profile.py (POC/VAH/VAL/HVN/LVN)
from core.volume_profile import compute_volume_profile, price_context_vs_profile


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


class VolumeProfileIntelligence:
    """
    Volume Profile Analyst — بروفايل الحجم الحقيقي داخل FAIE.

    شفافية: مصدر الحجم هو real_volume إن توفّر، وإلا tick_volume، وإلا وزن موحّد
    (time-weighted). الحقيقة تُصرَّح في details.source.
    """

    def analyze(
        self,
        rates: List[Any],
        bins: int = 24,
        lookback: int = 120,
        value_area_pct: float = 0.70,
    ) -> MarketEngineReport:
        profile = compute_volume_profile(
            rates,
            bins=bins,
            lookback=lookback,
            value_area_pct=value_area_pct,
        )
        if not profile.get("valid"):
            return MarketEngineReport(
                name="Volume Profile Engine",
                bias="NEUTRAL",
                confidence=0.0,
                score=0.0,
                details={
                    "source": profile.get("source", "none"),
                    "reason": profile.get("reason", "invalid_profile"),
                    "valid": False,
                },
            )

        last_price = _cf(rates[-1], "close", 0.0) if rates else 0.0
        ctx = price_context_vs_profile(profile, last_price)

        # bias: فوق منطقة القيمة => BUY (استمرار)، تحتها => SELL، داخلها => NEUTRAL
        pos = ctx.get("position", "UNKNOWN")
        if pos == "ABOVE_VALUE_AREA":
            bias = "BUY"
            base_conf = 65.0
        elif pos == "BELOW_VALUE_AREA":
            bias = "SELL"
            base_conf = 65.0
        elif pos == "INSIDE_VALUE_AREA":
            bias = "NEUTRAL"
            base_conf = 45.0
        else:
            bias = "NEUTRAL"
            base_conf = 30.0

        # تعزيز إذا كان قبول قوي عند POC
        if ctx.get("acceptance") == "STRONG_ACCEPTANCE":
            base_conf = max(base_conf - 5.0, 30.0)  # قبول قوي => احتمال ارتداد أقل، ثقة توجيه أقل
        elif ctx.get("acceptance") == "REJECTION_ZONE":
            base_conf = min(base_conf + 10.0, 90.0)

        return MarketEngineReport(
            name="Volume Profile Engine",
            bias=bias,
            confidence=round(base_conf, 2),
            score=round(min(100.0, (profile.get("total_volume", 0.0) or 0.0)), 2),
            details={
                "source": profile.get("source"),
                "poc": profile.get("poc"),
                "vah": profile.get("vah"),
                "val": profile.get("val"),
                "hvn": profile.get("hvn"),
                "lvn": profile.get("lvn"),
                "bin_size": profile.get("bin_size"),
                "bins": profile.get("bins"),
                "lookback_used": profile.get("lookback_used"),
                "price_context": ctx,
                "is_real_volume": profile.get("source") == "real_volume",
                "valid": True,
            },
        )

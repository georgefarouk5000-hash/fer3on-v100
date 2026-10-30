from __future__ import annotations

from typing import Any, Dict, List, Optional

from fer3on_masr.kernel.models import LiquidityProfile


class LiquidityIntelligence:
    """
    LiquidityAnalyst — بروفايل السيولة الحقيقي داخل FAIE.

    الإصلاح المهم في هذه النسخة:
    ---------------------------------
    النسخة السابقة كانت تتجاهل كليًا `sweep_probability` و`sweep_direction`
    الآتية من core/sweep_predictor.py + core/liquidity_intelligence.py،
    رغم أن main.py يحسبها ويضعها في ctx فعلًا. المنطق كان يقرأ بس
    liquidity_strength / liquidity_alignment. البيانات كانت موجودة بس
    FAIE ما بيبني evidence منها — فجوة إدماج، مش قرار متعمّد.

    هذه النسخة:
      - تقبل snapshot اختياري من LegacyBridge يحمل sweep_probability و
        sweep_direction و equal_highs / equal_lows و liquidity_pools.
      - تدمجها فعليًا داخل LiquidityProfile.details.
      - تحدّد best_target بناءً على sweep_direction حين تتوفر أدلة قوية
        (بدل تقدير أعمى من طول القوائم فقط).
    """

    @staticmethod
    def _high(rate: Any) -> float:
        if isinstance(rate, dict):
            return float(rate.get("high", 0.0) or 0.0)
        return float(getattr(rate, "high", 0.0) or 0.0)

    @staticmethod
    def _low(rate: Any) -> float:
        if isinstance(rate, dict):
            return float(rate.get("low", 0.0) or 0.0)
        return float(getattr(rate, "low", 0.0) or 0.0)

    def profile(
        self,
        rates: List[Any],
        snapshot: Optional[Dict[str, Any]] = None,
    ) -> LiquidityProfile:
        highs = [self._high(rate) for rate in rates or [] if self._high(rate) > 0]
        lows = [self._low(rate) for rate in rates or [] if self._low(rate) > 0]
        if not highs or not lows:
            highs = [1.3, 1.35, 1.4]
            lows = [1.0, 1.05, 1.1]
        buy_side = sorted(highs[-5:])
        sell_side = sorted(lows[-5:])

        # --------- Sweep evidence integration (real fix) ---------
        sweep_probability = 0.0
        sweep_direction = "NONE"
        sweep_bonus = 0.0
        equal_highs: List[float] = []
        equal_lows: List[float] = []
        liquidity_pools: List[Dict[str, Any]] = []
        distance_next_pool: Optional[float] = None
        session_hint = "UNKNOWN"

        if snapshot:
            sweep_probability = float(snapshot.get("sweep_probability", 0.0) or 0.0)
            sweep_direction = str(snapshot.get("sweep_direction", "NONE") or "NONE").upper()
            sweep_bonus = float(snapshot.get("sweep_confidence_bonus", 0.0) or 0.0)
            equal_highs = list(snapshot.get("equal_highs") or [])
            equal_lows = list(snapshot.get("equal_lows") or [])
            liquidity_pools = list(snapshot.get("liquidity_pools") or [])
            distance_next_pool = snapshot.get("distance_next_pool")
            session_hint = str(snapshot.get("session", "UNKNOWN") or "UNKNOWN").upper()

        # اختيار الهدف الأمثل:
        #   - إن كان sweep_probability >= 65 و sweep_direction محدّد،
        #     نُوجّه best_target ناحية جانب السيولة المستهدف.
        #   - وإلا نستخدم المنطق القديم (أطول قائمة يفوز).
        if sweep_probability >= 65.0 and sweep_direction in ("BUY", "UP", "HIGH"):
            best_target = buy_side[-1]
            best_target_reason = f"sweep_probability={sweep_probability:.1f} bullish -> target buy-side high"
        elif sweep_probability >= 65.0 and sweep_direction in ("SELL", "DOWN", "LOW"):
            best_target = sell_side[0]
            best_target_reason = f"sweep_probability={sweep_probability:.1f} bearish -> target sell-side low"
        else:
            best_target = buy_side[-1] if len(buy_side) >= len(sell_side) else sell_side[0]
            best_target_reason = "no strong sweep evidence -> pick side with more liquidity levels"

        # فخاخ: نستخدم الأدلة الفعلية إن توفّرت، وإلا نضيف أسماء عامة كمرجع.
        traps: List[str] = []
        if sweep_probability >= 55.0:
            traps.append(f"Session Sweep Watch ({sweep_direction or 'unknown'})")
        if equal_highs:
            traps.append(f"Equal Highs Cluster ({len(equal_highs)})")
        if equal_lows:
            traps.append(f"Equal Lows Cluster ({len(equal_lows)})")
        if not traps:
            traps = ["False Breakout Trap", "Liquidity Vacuum"]

        sweep_zones = [buy_side[0], sell_side[-1]]
        if liquidity_pools:
            # إضافة مواقع أول 3 برك سيولة قريبة كمناطق سويب محتملة.
            for pool in liquidity_pools[:3]:
                if isinstance(pool, dict):
                    px = pool.get("price") or pool.get("level")
                    if px:
                        try:
                            sweep_zones.append(float(px))
                        except (TypeError, ValueError):
                            pass

        details: Dict[str, Any] = {
            "buy_count": len(buy_side),
            "sell_count": len(sell_side),
            "sweep_probability": sweep_probability,
            "sweep_direction": sweep_direction,
            "sweep_confidence_bonus": sweep_bonus,
            "equal_highs_count": len(equal_highs),
            "equal_lows_count": len(equal_lows),
            "liquidity_pools_count": len(liquidity_pools),
            "distance_next_pool": distance_next_pool,
            "session": session_hint,
            "best_target_reason": best_target_reason,
        }

        return LiquidityProfile(
            buy_side=buy_side,
            sell_side=sell_side,
            traps=traps,
            sweep_zones=sweep_zones,
            best_target=best_target,
            details=details,
        )

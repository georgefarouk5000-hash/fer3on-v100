# =============================================================================
# FER3ON FINAL [SLTP-4]: single, authoritative SL/TP finalization pipeline.
# =============================================================================
# Before this module existed, three different places independently
# re-derived the "final" SL/TP that would actually reach the broker:
#
#   1. main.py::_build_order_request
#   2. core/trade_executor.py::execute_trade          (the ONE place that
#      actually sends the order, retries on stops-too-close, and records
#      the trade to the DB / AI-memory)
#
# Each of them applied its own subset of the rules — SL floor + account-size
# cap, TP floor, an ATR-based sanity ceiling — in a slightly different order,
# and #2 always ran AFTER #1 using the RAW (pre-builder) sl_dist/tp_dist
# it was passed as separate function arguments, not the request dict #1
# had already adjusted. That is exactly how the earlier bugs happened:
# whatever #1 computed (e.g. an ATR-capped TP) was silently discarded,
# because #2 recomputed everything from scratch with looser rules and that
# recomputation is what actually got sent to the broker.
#
# Now there is ONE function — `finalize_sl_tp` — used with the SAME raw inputs
# (the adaptive engine's own sl_distance/tp_distance,
# before any floor/cap has touched them). Being a pure, deterministic
# function of those inputs, every caller now agrees by construction: there
# is no "builder computed X but the executor sent Y" possible anymore,
# because there is only one place the computation happens.
#
# Pipeline (always in this order):
#   1. SL: broker-min-stop floor, then MAX_SL_DISTANCE_DOLLARS account-size
#      cap (see settings.py for the full reasoning).
#   2. TP: rescaled to preserve the risk:reward ratio the adaptive engine
#      actually chose (tp_dist_raw / sl_dist_raw), reapplied to the REAL
#      (post-cap) SL. This is what keeps TP proportional to what is truly
#      at risk instead of a stop distance that got capped away.
#   3. TP: optional secondary ATR sanity ceiling, per-strategy
#      (get_tp_cap_multiplier / get_tp_sl_multiplier). Runs AFTER step 2's
#      rescale, on top of it — belt-and-suspenders against a pathological
#      RR (e.g. a corrupted higher-timeframe structure target), never the
#      primary mechanism and never allowed to push TP below the real SL.
#   4. tp_tiers (the TP1/TP2/TP3 multi-TP ladder): each tier already carries
#      its own fixed `rr` from MULTI_TP_PROFILE, so its distance/price are
#      recomputed directly from that `rr` and the FINAL sl — not scaled by
#      an approximate factor. Informational/analytics only today (nothing
#      in this codebase places broker-side partial-TP orders from it), but
#      it must still reflect the real SL so logs/DB/dashboard aren't
#      misleading.
# =============================================================================
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.settings import (
    MAX_SL_DISTANCE_DOLLARS,
    get_tp_cap_multiplier,
    get_tp_sl_multiplier,
)


def finalize_sl_tp(
    symbol: str,
    sl_dist_raw: Optional[float],
    tp_dist_raw: Optional[float],
    point: float = 0.01,
    strategy: Optional[str] = None,
    atr: Optional[float] = None,
    tp_tiers_raw: Optional[List[Dict[str, Any]]] = None,
    entry_price: Optional[float] = None,
    signal: Optional[str] = None,
    market_regime: Optional[str] = None,
    confidence: Any = 1.0,
    exposure_modifier: float = 1.0,
) -> Dict[str, Any]:
    """Compute the final SL/TP distances (raw price units) that should
    actually be sent to the broker, plus a rescaled tp_tiers ladder for
    logging/analytics. This is the single source of truth — every caller
    that builds an order request, and execute_trade itself, must call this
    instead of re-deriving SL/TP independently.
    """
    # Local import to match the existing pattern in this codebase (avoids an
    # import-time MT5 dependency / circular import at module load).
    from core.trade_executor import (
        _enforce_min_stop_distance,
        _enforce_min_tp_distance,
        _required_min_stop_distance,
    )

    try:
        sl_dist_raw = float(sl_dist_raw) if sl_dist_raw is not None else None
        tp_dist_raw = float(tp_dist_raw) if tp_dist_raw is not None else None
    except (TypeError, ValueError):
        sl_dist_raw = None
        tp_dist_raw = None
    if sl_dist_raw is not None and not math.isfinite(sl_dist_raw):
        sl_dist_raw = None
    if tp_dist_raw is not None and not math.isfinite(tp_dist_raw):
        tp_dist_raw = None

    confidence_value = confidence
    if isinstance(confidence, dict):
        confidence_value = confidence.get("pct", confidence.get("value", 0.5))
        try:
            confidence_value = float(confidence_value)
            if confidence_value > 1.0:
                confidence_value /= 100.0
        except (TypeError, ValueError):
            confidence_value = 0.5

    # Preserve the raw values for RR and diagnostics before applying policy.
    original_sl_dist_raw = sl_dist_raw

    # STEP 1 — SL: apply the active strategy's context-aware cap before
    # broker enforcement.
    effective_sl_cap = float(MAX_SL_DISTANCE_DOLLARS)
    if sl_dist_raw is not None and strategy:
        from core.sl_risk_policy import resolve_sl_cap
        strategy_cap = resolve_sl_cap(
            strategy=strategy,
            market_regime=market_regime,
            confidence=confidence_value,
            exposure_modifier=exposure_modifier,
        )["effective_cap"]
        effective_sl_cap = min(effective_sl_cap, float(strategy_cap))
        sl_dist_for_enforcement = min(sl_dist_raw, effective_sl_cap)
    else:
        sl_dist_for_enforcement = sl_dist_raw
    required_minimum = _required_min_stop_distance(symbol, point)
    stop_valid = sl_dist_raw is not None and sl_dist_raw > 0
    stop_reason = None if stop_valid else "INVALID_SL_DISTANCE"
    tp_valid = tp_dist_raw is not None and tp_dist_raw > 0
    if not tp_valid and stop_valid:
        stop_reason = "INVALID_TP_DISTANCE"
    if required_minimum > effective_sl_cap:
        stop_valid = False
        stop_reason = "BROKER_MINIMUM_EXCEEDS_SL_CAP"
    sl_dist_final = _enforce_min_stop_distance(
        symbol,
        sl_dist_for_enforcement if sl_dist_for_enforcement is not None else 0.0,
        point,
    )
    if sl_dist_final > effective_sl_cap:
        if stop_valid:
            stop_valid = False
            stop_reason = stop_reason or "FINAL_SL_EXCEEDS_POLICY_CAP"

    # STEP 2 — TP: RR-preserving rescale against the REAL, enforced SL.
    tp_dist_final = _enforce_min_tp_distance(
        sl_dist_final=sl_dist_final,
        tp_dist=tp_dist_raw if tp_dist_raw is not None else 0.0,
        strategy=strategy or "",
        sl_dist_original=original_sl_dist_raw or 0.0,
    )

    # STEP 3 — secondary ATR sanity ceiling (defense-in-depth only).
    tp_was_atr_capped = False
    if atr is not None and float(atr) > 0 and strategy and tp_dist_final is not None:
        try:
            mult_atr = float(get_tp_cap_multiplier(strategy))
            mult_sl = float(get_tp_sl_multiplier(strategy))
            atr_ceiling = max(sl_dist_final * mult_sl, float(atr) * mult_atr)
            if tp_dist_final > atr_ceiling:
                new_tp = max(atr_ceiling, sl_dist_final)
                print(
                    f'🛡 TP_ATR_CEILING | strategy={strategy} '
                    f'was={tp_dist_final:.2f} → capped={new_tp:.2f} '
                    f'(atr={atr:.2f}, atr_mult={mult_atr}, sl_mult={mult_sl})'
                )
                tp_dist_final = new_tp
                tp_was_atr_capped = True
        except Exception as exc:
            print(f'⚠️ TP_ATR_CEILING_FAILED (non-fatal, cap skipped): {exc}')

    # STEP 4 — rescale tp_tiers to the FINAL sl, using each tier's own rr.
    tp_tiers_final = None
    if tp_tiers_raw:
        tp_tiers_final = []
        direction = str(signal or "").upper()
        for tier in tp_tiers_raw:
            tier = dict(tier)  # never mutate the caller's original list
            rr = float(tier.get("rr", 0) or 0)
            if rr > 0:
                new_distance = round(sl_dist_final * rr, 2)
            else:
                new_distance = tier.get("price_distance")
            tier["price_distance"] = new_distance
            if entry_price is not None and new_distance is not None:
                if direction in {"BUY", "0"}:
                    tier["price"] = round(float(entry_price) + new_distance, 5)
                elif direction in {"SELL", "1"}:
                    tier["price"] = round(float(entry_price) - new_distance, 5)
            tp_tiers_final.append(tier)

    return {
        "sl_dist": sl_dist_final,
        "tp_dist": tp_dist_final,
        "tp_tiers": tp_tiers_final,
        "rr": round(tp_dist_final / sl_dist_final, 2) if sl_dist_final else 0.0,
        "sl_cap": effective_sl_cap,
        "required_minimum_sl": round(required_minimum, 5),
        "stop_valid": stop_valid,
        "stop_reason": stop_reason,
        "valid": stop_valid and tp_valid,
        "sl_was_capped": (
            original_sl_dist_raw is None
            or round(sl_dist_final, 6) != round(original_sl_dist_raw, 6)
        ),
        "tp_was_rescaled": (
            tp_dist_raw is None or tp_dist_final is None
            or abs(tp_dist_final - tp_dist_raw) > 1e-6
        ),
        "tp_was_atr_capped": tp_was_atr_capped,
    }

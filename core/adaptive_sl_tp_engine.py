from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.settings import (
    ATR_SL_DAILY,
    ATR_SL_MULT,
    ATR_SL_SMC,
    ATR_TP_DAILY,
    ATR_TP_MULT,
    ATR_TP_SMC,
    MIN_SL_DISTANCE,
    MULTI_TP_ENABLED,
    MULTI_TP_PROFILE,
    MULTI_TP_STRATEGY_ENABLED,
    SLTP_MODE,
    SLTP_MODE_FIXED_ATR,
    get_tp_cap_multiplier,
    get_tp_sl_multiplier,
)


def _to_ratio(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
    except (TypeError, ValueError):
        return default
    if value > 1.0:
        return value / 100.0
    return max(0.0, min(1.0, value))


def _normalize(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def _structure_levels(context: Dict[str, Any], key: str) -> List[float]:
    sequence_key = "swing_lows" if key == "swing_low" else "swing_highs"
    levels: List[float] = []
    sequence = context.get(sequence_key) or []
    if isinstance(sequence, (list, tuple)):
        for item in sequence:
            value = item.get("price") if isinstance(item, dict) else item
            if value is None:
                continue
            try:
                level = float(value)
            except (TypeError, ValueError):
                continue
            if level > 0:
                levels.append(level)

    for name in (f"last_{key}", key):
        try:
            level = float(context.get(name) or 0.0)
        except (TypeError, ValueError):
            continue
        if level > 0:
            levels.append(level)
    return list(dict.fromkeys(levels))


def _structure_anchor(context: Dict[str, Any], key: str, price: float) -> Dict[str, Any]:
    sequence_key = "swing_lows" if key == "swing_low" else "swing_highs"
    for item in context.get(sequence_key) or []:
        if not isinstance(item, dict):
            continue
        raw_price = item.get("price")
        if raw_price is None:
            continue
        try:
            if abs(float(raw_price) - price) <= 1e-8:
                return {
                    "price": price,
                    "index": item.get("index"),
                    "label": item.get("label"),
                    "kind": item.get("kind"),
                }
        except (TypeError, ValueError):
            continue
    return {"price": price, "index": None, "label": None, "kind": None}


def _strategy_factor(strategy: Optional[str]) -> float:
    key = str(strategy or "").upper()
    if key in {"SMC"}:
        return 1.05
    if key == "DAILY":
        return 1.15
    return 1.0


def _regime_factor(market_regime: Optional[str]) -> float:
    key = str(market_regime or "").upper()
    mapping = {
        "TRENDING": 0.95,
        "RANGING": 1.00,
        "VOLATILE": 1.18,
        "CRISIS": 1.28,
        "UNKNOWN": 1.05,
    }
    return mapping.get(key, 1.00)


def _session_factor(session: Optional[str]) -> float:
    key = str(session or "").upper()
    mapping = {
        "LONDON": 1.00,
        "NEWYORK": 0.98,
        "OVERLAP": 0.94,
        "ASIA": 1.06,
        "OFF_HOURS": 1.08,
    }
    return mapping.get(key, 1.00)


def _execution_factor(execution_grade: Optional[str]) -> float:
    key = str(execution_grade or "").upper()
    mapping = {
        "ELITE": 0.92,
        "A+": 0.94,
        "A": 0.96,
        "B": 1.00,
        "C": 1.08,
        "REJECT": 1.14,
    }
    return mapping.get(key, 1.00)


def _lot_factor(lot: float) -> float:
    lot_value = max(0.0, float(lot or 0.0))
    if lot_value <= 0:
        return 1.0
    normalized = lot_value / 0.20
    return 1.0 + (0.35 * (normalized ** 0.85))


def _structure_atr_buffer(
    atr_value: float,
    volatility_ratio: float,
    spread_pct: float,
    session_scale: float,
    execution_scale: float,
    regime_scale: float,
    structure_ratio: float,
) -> float:
    base = atr_value * (0.35 + (volatility_ratio * 0.45) + min(spread_pct / 100.0, 0.4))
    base *= 1.0 + ((session_scale - 1.0) * 0.08)
    base *= 1.0 + ((execution_scale - 1.0) * 0.10)
    base *= 1.0 + ((regime_scale - 1.0) * 0.06)
    base *= 1.0 + max(-0.10, min(0.20, (0.40 - structure_ratio * 0.30)))
    return max(atr_value * 0.10, min(base, atr_value * 1.75))


def calculate_adaptive_sl_tp(
    *,
    atr: float,
    strategy: Optional[str] = None,
    lot: float = 0.01,
    confidence: float = 0.5,
    quality_score: float = 50.0,
    market_regime: Optional[str] = None,
    session: Optional[str] = None,
    structure_strength: float = 0.5,
    liquidity: float = 0.5,
    volatility: float = 0.5,
    spread: float = 0.0,
    execution_grade: Optional[str] = None,
    broker_stop_level: float = 0.0,
    broker_stop_fallback: float = 0.0,
    min_sl: float = 0.0,
    max_sl: float = 1500.0,
    entry_price: Optional[float] = None,
    signal: Optional[str] = None,
    structure_context: Optional[Dict[str, Any]] = None,
    structure_analysis: Optional[Dict[str, Any]] = None,
    final_brain: Optional[Any] = None,
    strategy_dna: Optional[Any] = None,
    exposure_modifier: float = 1.0,
) -> Dict[str, Any]:
    """Return structure-anchored SL/TP with an ATR buffer and fallback.

    Confirmed pivots are used when valid; otherwise the ATR-based stop and RR
    target remain available. Policy and broker constraints are fail-closed.
    """

    atr_value = max(0.0, float(atr or 0.0))
    if atr_value <= 0:
        return {
            "sl_distance": 0.0,
            "tp_distance": 0.0,
            "risk_reward": 0.0,
            "stop_distance": 0.0,
            "dynamic_rr": 0.0,
            "reason": "ATR_INVALID",
            "stop_valid": False,
            "stop_reason": "ATR_INVALID",
        }

    confidence_ratio = _to_ratio(confidence, 0.5)
    quality_ratio = _to_ratio(quality_score, 0.5)
    structure_ratio = _to_ratio(structure_strength, 0.5)
    liquidity_ratio = _to_ratio(liquidity, 0.5)
    volatility_ratio = _to_ratio(volatility, 0.5)
    spread_ratio = max(0.0, float(spread or 0.0))

    brain_value = 0.0
    if isinstance(final_brain, (int, float)):
        brain_value = float(final_brain)
    elif isinstance(final_brain, dict):
        brain_value = float(final_brain.get("final_score", final_brain.get("score", 0)) or 0)
    brain_ratio = _to_ratio(brain_value, 0.5)

    dna_value = 0.0
    if isinstance(strategy_dna, (int, float)):
        dna_value = float(strategy_dna)
    elif isinstance(strategy_dna, dict):
        dna_value = float(strategy_dna.get("score", strategy_dna.get("dna_score", 0)) or 0)
    dna_ratio = _to_ratio(dna_value, 0.5)

    strategy_scale = _strategy_factor(strategy)
    regime_scale = _regime_factor(market_regime)
    session_scale = _session_factor(session)
    execution_scale = _execution_factor(execution_grade)
    lot_scale = _lot_factor(lot)

    quality_bias = 0.96 + (quality_ratio * 0.12)
    confidence_bias = 0.96 + (confidence_ratio * 0.12)
    structure_bias = 0.95 + (structure_ratio * 0.14)
    liquidity_bias = 0.92 + (liquidity_ratio * 0.16)
    volatility_bias = 1.00 + (volatility_ratio * 0.70)
    spread_bias = 1.00 + (spread_ratio / 100.0) * 0.45

    # [FER3ON-FIX-2026-08-19] TIGHTER SL - real data proved avg_loss > avg_win.
    # Base 6.0 -> 4.5, secondary coefficients reduced. Range 6.0-11.3 -> 4.5-8.5 (~25% tighter).
    adaptive_sl_multiplier = (
        4.5
        + (quality_ratio * 1.2)
        + (confidence_ratio * 0.8)
        + (structure_ratio * 0.6)
        + (liquidity_ratio * 0.5)
        + (volatility_ratio * 0.6)
        + (0.25 if str(market_regime or "").upper() in {"VOLATILE", "CRISIS"} else 0.0)
        + (0.15 if str(market_regime or "").upper() == "TRENDING" else 0.0)
        + (0.20 if str(strategy or "").upper() == "DAILY" else 0.0)
        + (0.15 if str(execution_grade or "").upper() in {"A", "A+", "ELITE"} else 0.0)
        + (lot_scale * 0.30)
        + (brain_ratio * 0.25)
        + (dna_ratio * 0.20)
    )

    fixed_atr_profiles = {
        "SMC": (float(ATR_SL_SMC), float(ATR_TP_SMC)),
        "DAILY": (float(ATR_SL_DAILY), float(ATR_TP_DAILY)),
    }
    fixed_sl_multiplier, fixed_tp_multiplier = fixed_atr_profiles.get(
        str(strategy or "").upper(),
        (float(ATR_SL_MULT), float(ATR_TP_MULT)),
    )
    is_fixed_atr = SLTP_MODE == SLTP_MODE_FIXED_ATR
    sl_multiplier = fixed_sl_multiplier if is_fixed_atr else adaptive_sl_multiplier
    sl_distance = atr_value * sl_multiplier

    safety_floor = float(min_sl or 0.0)
    if safety_floor <= 0:
        # Standalone callers still receive the canonical broker-distance
        # floor; the old 100-dollar fallback flattened every ATR result.
        safety_floor = float(MIN_SL_DISTANCE) * 0.01

    if max_sl is None:
        max_sl = 1500.0
    from core.sl_risk_policy import resolve_sl_cap
    sl_policy = resolve_sl_cap(
        strategy=strategy,
        market_regime=market_regime,
        confidence=confidence,
        exposure_modifier=exposure_modifier,
    )
    # A missing min_sl means a legacy standalone calculation. Keep its
    # historical fallback behaviour; production callers pass min_sl.
    policy_max_sl = sl_policy["effective_cap"] if min_sl else float(max_sl)
    configured_sl_cap = min(float(max_sl), policy_max_sl)
    max_sl_value = configured_sl_cap

    structure_candidates: Dict[str, float] = {}
    base_context = structure_context or {}
    if structure_analysis:
        base_context = {**base_context, **structure_analysis}
    signal_dir = str(signal or "").upper()
    entry = float(entry_price or 0.0)
    selected_swing = None
    target_price = None
    target_source = "rr_fallback"
    stop_valid = True
    stop_reason = None
    selected_anchor: Dict[str, Any] = {}
    stop_selection_reason = "ATR_FALLBACK"

    selected_source = "fixed_atr" if is_fixed_atr else "atr"
    selected_distance = sl_distance
    buffer_distance = _structure_atr_buffer(
        atr_value=atr_value,
        volatility_ratio=volatility_ratio,
        spread_pct=spread_ratio,
        session_scale=session_scale,
        execution_scale=execution_scale,
        regime_scale=regime_scale,
        structure_ratio=structure_ratio,
    )

    if base_context and not is_fixed_atr and entry > 0 and signal_dir in {"BUY", "SELL"}:
        protective_key = "swing_low" if signal_dir == "BUY" else "swing_high"
        protective_levels = _structure_levels(base_context, protective_key)
        eligible_levels = [
            level for level in protective_levels
            if (level < entry if signal_dir == "BUY" else level > entry)
        ]
        if eligible_levels:
            nearest_swing = (
                max(eligible_levels) if signal_dir == "BUY" else min(eligible_levels)
            )
            protected_key = "protected_low" if signal_dir == "BUY" else "protected_high"
            protected = base_context.get(protected_key) or {}
            raw_protected_price = (
                protected.get("price") if isinstance(protected, dict) else None
            )
            if raw_protected_price is None:
                protected_price = 0.0
            else:
                try:
                    protected_price = float(raw_protected_price)
                except (TypeError, ValueError):
                    protected_price = 0.0
            protected_eligible = (
                protected_price in eligible_levels
            )
            protected_distance = abs(entry - protected_price) + buffer_distance
            nearest_distance = abs(entry - nearest_swing) + buffer_distance

            if protected_eligible and (
                protected_distance <= configured_sl_cap
                or nearest_distance > configured_sl_cap
            ):
                selected_swing = protected_price
                selected_anchor = {
                    "price": protected_price,
                    "index": protected.get("index") if isinstance(protected, dict) else None,
                    "label": protected.get("label") if isinstance(protected, dict) else None,
                    "kind": protected.get("kind") if isinstance(protected, dict) else None,
                }
                stop_selection_reason = str(
                    (protected.get("reason") if isinstance(protected, dict) else None)
                    or ("PROTECTED_HL" if signal_dir == "BUY" else "PROTECTED_LH")
                )
            else:
                selected_swing = nearest_swing
                selected_anchor = _structure_anchor(
                    base_context, protective_key, nearest_swing
                )
                stop_selection_reason = (
                    "PROTECTED_SWING_EXCEEDS_SL_CAP_USE_NEAREST_CONFIRMED_SWING"
                    if protected_eligible
                    else "NEAREST_CONFIRMED_SWING_NO_PROTECTED_SWING"
                )

            structure_candidates["swing"] = abs(entry - selected_swing)

    if not is_fixed_atr and structure_candidates and selected_swing is not None:
        selected_source = "structure"
        if signal_dir == "BUY":
            selected_distance = entry - (selected_swing - buffer_distance)
        else:
            selected_distance = (selected_swing + buffer_distance) - entry
        if selected_distance <= 0:
            selected_source = "atr"
            selected_distance = sl_distance
            selected_swing = None
            selected_anchor = {}
            stop_selection_reason = "INVALID_STRUCTURE_ANCHOR_ATR_FALLBACK"
            structure_candidates.clear()

    if broker_stop_level and float(broker_stop_level) > 0:
        selected_distance = max(selected_distance, float(broker_stop_level))
        if (
            selected_distance == float(broker_stop_level)
            and selected_source not in {"structure", "fixed_atr"}
        ):
            selected_source = "broker"

    # [FER3ON-FIX-2026-08-19] CORE FIX: actual R:R 0.67-0.93 -> forced 1.5-3.2
    # Base 1.20 -> 1.60, positive coeffs increased, negatives reduced.
    # Range floor 1.15 -> 1.5 (matches new tp1_rr); ceiling 2.2 -> 3.2.
    rr_base = 1.60
    rr_base += confidence_ratio * 0.85
    rr_base += quality_ratio * 0.75
    rr_base += liquidity_ratio * 0.30
    rr_base += structure_ratio * 0.30
    rr_base += (0.20 if str(execution_grade or "").upper() in {"A", "A+", "ELITE"} else 0.0)
    rr_base -= volatility_ratio * 0.12
    rr_base -= (0.15 if str(market_regime or "").upper() == "CRISIS" else 0.0)
    rr_base += (0.10 if str(strategy or "").upper() == "DAILY" else 0.0)
    rr_base += (lot_scale - 1.0) * 0.30
    rr_base += brain_ratio * 0.25
    rr_base += dna_ratio * 0.15

    # HARD FLOOR at 1.5 to prevent avg_win < avg_loss inversion; ceiling raised to 3.2
    risk_reward = (
        fixed_tp_multiplier / fixed_sl_multiplier
        if is_fixed_atr and fixed_sl_multiplier > 0
        else _normalize(rr_base, 1.5, 3.2)
    )

    if broker_stop_level and float(broker_stop_level) > 0:
        safety_floor = max(safety_floor, float(broker_stop_level))
    elif safety_floor <= 0 and broker_stop_fallback and float(broker_stop_fallback) > 0:
        safety_floor = float(broker_stop_fallback)

    if safety_floor > configured_sl_cap:
        stop_valid = False
        stop_reason = "BROKER_MINIMUM_EXCEEDS_SL_CAP"
        max_sl_value = safety_floor
    if (
        selected_distance > max_sl_value
        and selected_source == "structure"
        and stop_valid
    ):
        stop_valid = False
        stop_reason = "STRUCTURAL_STOP_EXCEEDS_SL_CAP"

    selected_distance = _normalize(selected_distance, safety_floor, max_sl_value)
    sl_distance = _normalize(selected_distance, safety_floor, max_sl_value)

    min_structural_rr = 1.5
    max_structural_rr = 3.2
    tp_cap = max(
        sl_distance * float(get_tp_sl_multiplier(strategy or "")),
        atr_value * float(get_tp_cap_multiplier(strategy or "")),
    )
    tp_cap = min(tp_cap, sl_distance * max_structural_rr)
    target_levels = []
    if not is_fixed_atr and entry > 0 and signal_dir in {"BUY", "SELL"}:
        target_key = "swing_high" if signal_dir == "BUY" else "swing_low"
        for level in _structure_levels(base_context, target_key):
            if (level > entry if signal_dir == "BUY" else level < entry):
                target_levels.append(level)
        target_key_plural = "equal_highs" if signal_dir == "BUY" else "equal_lows"
        for level in base_context.get(target_key_plural, []) or []:
            try:
                target_level = float(level)
            except (TypeError, ValueError):
                continue
            if (
                target_level > entry
                if signal_dir == "BUY"
                else 0 < target_level < entry
            ):
                target_levels.append(target_level)

    target_distances = sorted({
        round(abs(level - entry), 8)
        for level in target_levels
        if min_structural_rr * sl_distance <= abs(level - entry) <= tp_cap
    })
    if target_distances and stop_valid:
        tp_distance = target_distances[0]
        risk_reward = tp_distance / sl_distance if sl_distance else risk_reward
        target_price = entry + tp_distance if signal_dir == "BUY" else entry - tp_distance
        target_source = "structure"
    else:
        tp_distance = sl_distance * risk_reward

    def _build_tp_tiers(
        strategy: Optional[str],
        sl_distance_value: float,
        tp_distance_value: float,
        risk_reward_value: float,
        entry_price_value: Optional[float],
        signal_value: Optional[str],
    ) -> list[Dict[str, Any]]:
        strat_key = str(strategy or "").upper()
        tiers: list[Dict[str, Any]] = []
        if (
            MULTI_TP_ENABLED
            and MULTI_TP_STRATEGY_ENABLED.get(strat_key, True)
            and strat_key in MULTI_TP_PROFILE
        ):
            profile = MULTI_TP_PROFILE[strat_key]
            for i in range(1, 4):
                pct = float(profile.get(f"tp{i}_pct", 0) or 0)
                rr = float(profile.get(f"tp{i}_rr", 0) or 0)
                if pct <= 0 or rr <= 0:
                    continue
                distance = round(sl_distance_value * rr, 2)
                price = None
                if entry_price_value is not None:
                    direction = str(signal_value or "").upper()
                    if direction in {"BUY", "0"}:
                        price = round(float(entry_price_value) + distance, 5)
                    elif direction in {"SELL", "1"}:
                        price = round(float(entry_price_value) - distance, 5)
                tiers.append({
                    "label": f"TP{i}",
                    "close_pct": pct,
                    "rr": rr,
                    "price_distance": distance,
                    "price": price,
                })
        if not tiers:
            price = None
            if entry_price_value is not None:
                direction = str(signal_value or "").upper()
                if direction in {"BUY", "0"}:
                    price = round(float(entry_price_value) + tp_distance_value, 5)
                elif direction in {"SELL", "1"}:
                    price = round(float(entry_price_value) - tp_distance_value, 5)
            tiers = [
                {
                    "label": "TP1",
                    "close_pct": 1.0,
                    "rr": round(risk_reward_value, 2),
                    "price_distance": round(tp_distance_value, 2),
                    "price": price,
                }
            ]
        return tiers

    tp_tiers = _build_tp_tiers(
        strategy=strategy,
        sl_distance_value=sl_distance,
        tp_distance_value=tp_distance,
        risk_reward_value=risk_reward,
        entry_price_value=entry_price,
        signal_value=signal,
    )

    diagnostics = {
        "sl_distance": round(sl_distance, 2),
        "tp_distance": round(tp_distance, 2),
        "tp_tiers": tp_tiers,
        "risk_reward": round(risk_reward, 2),
        "stop_distance": round(sl_distance, 2),
        "dynamic_rr": round(risk_reward, 2),
        "reason": (
            "FIXED_ATR_PROFILE" if is_fixed_atr
            else "STRUCTURE_STOP" if selected_source == "structure"
            else "ADAPTIVE_ATR"
        ),
        "sltp_mode": SLTP_MODE,
        "selected_stop_source": selected_source,
        "selected_swing": round(selected_swing, 5) if selected_swing is not None else None,
        "selected_stop_anchor": selected_anchor,
        "stop_selection_reason": stop_selection_reason,
        "structure_buffer": round(buffer_distance, 5) if selected_source == "structure" else 0.0,
        "stop_valid": stop_valid,
        "stop_reason": stop_reason,
        "target_source": target_source,
        "target_price": round(target_price, 5) if target_price is not None else None,
        "structure_candidates": structure_candidates,
        "atr_distance": round(atr_value * sl_multiplier, 2),
        "regime_factor": round(_regime_factor(market_regime), 3),
        "quality_factor": round(quality_bias, 3),
        "confidence_factor": round(confidence_bias, 3),
        "lot_factor": round(lot_scale, 3),
        "session_factor": round(_session_factor(session), 3),
        "execution_factor": round(_execution_factor(execution_grade), 3),
        "atr": round(atr_value, 2),
        "market_regime": str(market_regime or "UNKNOWN"),
        "strategy": str(strategy or "UNKNOWN"),
        "session": str(session or "UNKNOWN"),
        "quality_score": round(float(quality_score or 0.0), 2),
        "confidence": round(float(confidence or 0.0), 2),
        "lot": round(float(lot or 0.0), 2),
        "structure_strength": round(float(structure_strength or 0.0), 2),
        "liquidity": round(float(liquidity or 0.0), 2),
        "volatility": round(float(volatility or 0.0), 2),
        "spread": round(float(spread or 0.0), 2),
        "execution_grade": str(execution_grade or "UNKNOWN"),
        "brain_factor": round(brain_ratio, 3),
        "dna_factor": round(dna_ratio, 3),
        "broker_stop_level": round(float(broker_stop_level or 0.0), 2),
        "broker_stop_fallback": round(float(broker_stop_fallback or 0.0), 2),
        "safety_floor": round(float(safety_floor), 2),
        "sl_policy": sl_policy,
    }
    print(
        "📐 ADAPTIVE SL ENGINE"
        f" | Mode={diagnostics['sltp_mode']}"
        f" | ATR={diagnostics['atr']}"
        f" | Regime={diagnostics['market_regime']}"
        f" | Quality={diagnostics['quality_score']}"
        f" | Confidence={diagnostics['confidence']}"
        f" | Lot={diagnostics['lot']}"
        f" | Structure={diagnostics['structure_strength']}"
        f" | SelectedStop={diagnostics['selected_stop_source']}"
        f" | FinalSL={diagnostics['sl_distance']}"
        f" | DynamicRR={diagnostics['risk_reward']}"
        f" | FinalTP={diagnostics['tp_distance']}"
    )
    return diagnostics

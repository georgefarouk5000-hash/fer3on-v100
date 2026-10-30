# =========================================
# FER3ON V6.2 — ADAPTIVE CANDLE TRIGGER AI
# Smart weighted execution instead of hard blocking
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.candle_engine import analyze_candle_context, strength_to_weight
from core.candle_patterns import detect_candle_pattern_full
from core.candle_gate_v3 import evaluate_candle_gate, get_closed_candle


class AggregateResult(dict):
    """Dict result that also supports legacy tuple unpacking.

    Order when unpacked: confirmed, weight, reasons, score
    """

    def __iter__(self):
        return iter((self["confirmed"], self["weight"], self["reasons"], self["score"]))


# =========================================
# HELPERS
# =========================================

def _body(candle):
    return abs(candle["close"] - candle["open"])


def _range(candle):
    return candle["high"] - candle["low"]


def _micro_pattern(rates, context=None):
    if rates is None or len(rates) < 2:
        return ("NONE", "NONE", 0)

    prev = rates[-2]
    last = rates[-1]

    rng = _range(last)

    if rng <= 0:
        return ("NONE", "NONE", 0)

    body = _body(last)
    body_ratio = body / rng if rng > 0 else 0

    upper = last["high"] - max(last["open"], last["close"])
    lower = min(last["open"], last["close"]) - last["low"]

    ctx = context or {}

    vol_spike = bool(ctx.get("volume_spike", False))
    liquidity_sweep = bool(ctx.get("liquidity_sweep", False))
    atr_expansion = bool(ctx.get("atr_expansion", False))

    breakout_strength = int(ctx.get("breakout_strength", 0) or 0)

    # =========================================
    # MOMENTUM BREAKOUT
    # =========================================

    if (
        last["close"] > last["open"]
        and last["close"] > prev["high"]
        and body_ratio >= 0.50
    ):

        weight = (
            1
            + int(vol_spike)
            + int(liquidity_sweep)
            + int(atr_expansion)
            + int(breakout_strength >= 2)
        )

        return ("MOMENTUM_BREAKOUT", "BUY", max(1, min(4, weight)))

    if (
        last["close"] < last["open"]
        and last["close"] < prev["low"]
        and body_ratio >= 0.50
    ):

        weight = (
            1
            + int(vol_spike)
            + int(liquidity_sweep)
            + int(atr_expansion)
            + int(breakout_strength >= 2)
        )

        return ("MOMENTUM_BREAKOUT", "SELL", max(1, min(4, weight)))

    # =========================================
    # REJECTION CANDLES
    # =========================================

    if (
        lower >= body * 1.5
        and last["close"] > last["open"]
        and body_ratio >= 0.18
    ):

        weight = 1 + int(liquidity_sweep) + int(atr_expansion)

        return ("REJECTION_BUY", "BUY", max(1, min(4, weight)))

    if (
        upper >= body * 1.5
        and last["close"] < last["open"]
        and body_ratio >= 0.18
    ):

        weight = 1 + int(liquidity_sweep) + int(atr_expansion)

        return ("REJECTION_SELL", "SELL", max(1, min(4, weight)))

    return ("NONE", "NONE", 0)


# =========================================
# ANALYZE SINGLE TF
# =========================================

def _analyze_tf(rates, tf_name, signal=None, context=None, verbose=True):

    enriched = analyze_candle_context(
        rates,
        signal=signal,
        context=context
    )

    pattern_name = enriched.get("pattern", "NONE")
    direction = enriched.get("direction", "NONE")
    weight = enriched.get("weight", 0)
    strength = enriched.get("strength", 0)

    # =========================================
    # MICRO PATTERN FALLBACK
    # =========================================

    if pattern_name == "NONE":

        pattern_name, direction, micro_weight = _micro_pattern(
            rates,
            context=context
        )

        if direction != "NONE":

            strength = max(35, micro_weight * 20 + 20)
            weight = strength_to_weight(strength)

        else:

            weight = 0
            strength = 0

    if verbose:
        print(
            f"🕯️ CANDLE TF:{tf_name}"
            f" | Pattern:{pattern_name}"
            f" | Dir:{direction}"
            f" | Strength:{strength}"
            f" | Weight:{weight}"
        )

    return pattern_name, direction, weight, strength


# =========================================
# SMART WEIGHTED ARBITRATION
# =========================================

def _aggregate_weights(
    signal,
    m5_data,
    m15_data,
    strategy="SMC"
):

    score = 0.0
    reasons = []

    strategy_key = str(strategy or "SMC").upper()

    # =========================================
    # STRATEGY BONUSES
    # =========================================

    bonus_map = {
        "SMC": (4, 2),
        "DAILY": (1, 5),
    }

    if strategy_key in bonus_map:
        m5_bonus, m15_bonus = bonus_map[strategy_key]
    else:
        m5_bonus, m15_bonus = (1, 5)

    # =========================================
    # THRESHOLDS
    # =========================================

    if strategy_key == "SMC":

        confirmed_threshold = 1.4
        penalty = 0.40

    else:

        confirmed_threshold = 2.5
        penalty = 0.60

    # =========================================
    # TF PROCESSING
    # =========================================

    for tf_name, data, bonus in (
        ("M5", m5_data, m5_bonus),
        ("M15", m15_data, m15_bonus),
    ):

        pattern_name, direction, weight, strength = data

        normalized = (float(strength or 0) / 100.0) * 4.0

        # =========================================
        # CONFIRMING SIGNAL
        # =========================================

        if direction == signal:

            tf_score = normalized + weight + (bonus / 6.0)

            score += tf_score

            reasons.append(
                f"{tf_name}:{pattern_name}(+{tf_score:.1f}|s={strength})"
            )

        # =========================================
        # CONFLICTING SIGNAL
        # =========================================

        elif direction not in ("NONE", None):

            adaptive_penalty = penalty

            # تخفيف العقوبات الذكي
            if "REJECTION" in str(pattern_name):
                adaptive_penalty *= 0.45

            elif "MOMENTUM" in str(pattern_name):
                adaptive_penalty *= 0.65

            elif "CROWS" in str(pattern_name):
                adaptive_penalty *= 0.55

            score -= adaptive_penalty

            reasons.append(
                f"{tf_name}:{pattern_name}"
                f"(-{adaptive_penalty:.1f}|s={strength})"
            )

    # =========================================
    # EXECUTION STATES
    # =========================================

    if score >= 6.0:

        execution_mode = "FULL_ENTRY"
        final_weight = 4
        confirmed = True

    elif score >= 3.5:

        execution_mode = "REDUCED_ENTRY"
        final_weight = 3
        confirmed = True

    elif score >= confirmed_threshold:

        execution_mode = "MICRO_PROBE"
        final_weight = 2
        confirmed = True

    elif score >= -0.8:

        execution_mode = "LIGHT_PROBE"
        final_weight = 1
        confirmed = True

    else:

        execution_mode = "WAIT"
        final_weight = 0
        confirmed = False

    return AggregateResult({
        "confirmed": confirmed,
        "weight": final_weight,
        "score": round(score, 2),
        "execution_mode": execution_mode,
        "reasons": reasons,
    })


# =========================================
# MAIN API
# =========================================

def check_candle_trigger(
    symbol,
    signal,
    strategy,
    rates=None,
    rates_m15=None,
    verbose=True,
    deduplicate_closed_candles=True,
):

    rates_m5 = rates

    if rates_m5 is None:
        rates_m5 = mt5.copy_rates_from_pos(
            symbol,
            mt5.TIMEFRAME_M5,
            0,
            12
        )

    if rates_m15 is None:
        rates_m15 = mt5.copy_rates_from_pos(
            symbol,
            mt5.TIMEFRAME_M15,
            0,
            12
        )

    if rates_m5 is None or len(rates_m5) < 3:
        return {
            "confirmed": False,
            "pattern": "NO_DATA_M5",
            "weight": 0,
            "execution_mode": "WAIT",
            "score": -99,
        }

    if rates_m15 is None or len(rates_m15) < 3:
        rates_m15 = rates_m5

    context = {
        "trend_bias": signal,
        "strategy": strategy,
    }

    m5_data = _analyze_tf(
        rates_m5,
        "M5",
        signal=signal,
        context=context,
        verbose=verbose,
    )

    m15_data = _analyze_tf(
        rates_m15,
        "M15",
        signal=signal,
        context=context,
        verbose=verbose,
    )

    result = _aggregate_weights(
        signal,
        m5_data,
        m15_data,
        strategy=strategy
    )

    pattern_summary = f"M5:{m5_data[0]}|M15:{m15_data[0]}"

    # =========================================
    # V3.0 CANDLE INTELLIGENCE GATE
    # Implements: Tier weights, strength multipliers,
    # bonus engine, opposite-candle penalty, MTF alignment,
    # hard-block conditions, closed-candle duplicate guard.
    # =========================================

    # Closed-candle time stamps for duplicate guard
    if deduplicate_closed_candles:
        _m5_closed, _m5_dup = get_closed_candle(rates_m5, symbol, "M5")
        _m15_closed, _m15_dup = get_closed_candle(rates_m15, symbol, "M15")
    else:
        _m5_closed, _m15_closed = None, None

    gate = evaluate_candle_gate(
        signal         = signal,
        m5_pattern     = m5_data[0],
        m5_direction   = m5_data[1],
        m5_strength    = float(m5_data[3] or 0),
        m15_pattern    = m15_data[0],
        m15_direction  = m15_data[1],
        m15_strength   = float(m15_data[3] or 0),
        base_score     = float(result["score"] or 0),
        # structure_confidence passed as 100 here; callers with SMC context
        # can call evaluate_candle_gate() directly with the real value.
        structure_confidence = 100.0,
        closed_m5_time  = _m5_closed.get("time")  if _m5_closed  else None,
        closed_m15_time = _m15_closed.get("time") if _m15_closed else None,
        symbol          = symbol,
    )

    if verbose:
        print(gate["log_line"])

    # =========================================
    # HARD BLOCK — only when ALL 4 spec conditions met
    # =========================================

    if gate["hard_block"]:
        if verbose:
            print(
                f"🛑 CANDLE_HARD_BLOCK"
                f" | Signal:{signal}"
                f" | OppPattern:{m5_data[0] if gate['m5_opposite'] else m15_data[0]}"
                f" | composite_delta={gate['composite_delta']:+.1f}"
            )
        return {
            "confirmed": False,
            "pattern": pattern_summary,
            "weight": 0,
            "execution_mode": "HARD_BLOCK",
            "score": gate["final_score"],
            # V3.0 gate fields
            "gate_v3": gate,
            "candle_bonus":   gate["candle_bonus"],
            "candle_penalty": gate["candle_penalty"],
            "hard_warning":   gate["hard_warning"],
            "mtf_bonus":      gate["mtf_bonus"],
            "composite_delta": gate["composite_delta"],
        }

    # =========================================
    # APPLY GATE DELTA TO AGGREGATE SCORE
    # =========================================

    # Composite score from V3.0 gate (base + bonus − penalty + mtf)
    composite_score = gate["final_score"]

    # Recalculate confirmed / weight using composite score so that
    # the gate delta actually influences execution mode.
    if composite_score >= 6.0:
        gate_mode   = "FULL_ENTRY"
        gate_weight = 4
        gate_conf   = True
    elif composite_score >= 3.5:
        gate_mode   = "REDUCED_ENTRY"
        gate_weight = 3
        gate_conf   = True
    elif composite_score >= 1.0:
        gate_mode   = "MICRO_PROBE"
        gate_weight = 2
        gate_conf   = True
    elif composite_score >= -0.8:
        gate_mode   = "LIGHT_PROBE"
        gate_weight = 1
        gate_conf   = True
    else:
        gate_mode   = "WAIT"
        gate_weight = 0
        gate_conf   = False

    # Hard-warning: force REDUCED if we were at FULL_ENTRY
    if gate["hard_warning"] and gate_mode == "FULL_ENTRY":
        gate_mode   = "REDUCED_ENTRY"
        gate_weight = min(gate_weight, 3)

    # candle_gate_v3 is the authoritative classification. Keep this public
    # result aligned with it so logs cannot report FULL while the gate says
    # REDUCED because of opposite MTF context or structure confidence.
    gate_mode_map = {
        "FULL_ENTRY": ("FULL_ENTRY", 4),
        "REDUCED": ("REDUCED_ENTRY", 3),
        "BLOCKED": ("HARD_BLOCK", 0),
        "NEUTRAL": ("WAIT", 0),
    }
    if gate["execution_mode"] in gate_mode_map:
        gate_mode, gate_weight = gate_mode_map[gate["execution_mode"]]
        gate_conf = gate_weight > 0

    if verbose:
        print(
            f"🕯️ CANDLE TRIGGER"
            f" | Signal:{signal}"
            f" | RawScore:{result['score']:.2f}"
            f" | GateScore:{composite_score:.2f}"
            f" | Bonus:{gate['candle_bonus']:+.1f}"
            f" | Penalty:{gate['candle_penalty']:+.1f}"
            f" | MTF:{gate['mtf_bonus']:+d}"
            f" | Weight:{gate_weight}"
            f" | Mode:{gate_mode}"
            f" | HardWarn:{gate['hard_warning']}"
        )

    # =========================================
    # SMART EXECUTION
    # =========================================

    if not gate_conf:

        if verbose:
            print(
                f"⏸ WAITING CANDLE TRIGGER"
                f" | Mode:{gate_mode}"
            )

        return {
            "confirmed": False,
            "pattern": pattern_summary,
            "weight": 0,
            "execution_mode": "WAIT",
            "score": composite_score,
            "gate_v3": gate,
            "candle_bonus":   gate["candle_bonus"],
            "candle_penalty": gate["candle_penalty"],
            "hard_warning":   gate["hard_warning"],
            "mtf_bonus":      gate["mtf_bonus"],
            "composite_delta": gate["composite_delta"],
        }

    if verbose:
        print(
            f"✅ CANDLE CONFIRMED"
            f" | Mode:{gate_mode}"
            f" | Pattern:{pattern_summary}"
            f" | Signal:{signal}"
            f" | Weight:{gate_weight}"
        )

    return {
        "confirmed": True,
        "pattern": pattern_summary,
        "weight": gate_weight,
        "execution_mode": gate_mode,
        "score": composite_score,
        # V3.0 gate fields exposed for downstream consumers
        "gate_v3": gate,
        "candle_bonus":   gate["candle_bonus"],
        "candle_penalty": gate["candle_penalty"],
        "hard_warning":   gate["hard_warning"],
        "mtf_bonus":      gate["mtf_bonus"],
        "composite_delta": gate["composite_delta"],
        "aligned":        gate["aligned"],
    }


# =========================================
# REQUIREMENT LOGIC
# =========================================

def candle_trigger_required(strategy):
    return str(strategy or "").upper() in ("SMC", "DAILY")

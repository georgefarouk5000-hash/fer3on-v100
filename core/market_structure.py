# =========================================
# FER3ON V6.3 — ADAPTIVE MARKET STRUCTURE AI
# Smart weighted structure engine
# No hard rejection — adaptive penalties only
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.choch_engine import get_full_structure_analysis


# =========================================
# SWING POINTS
# =========================================

def find_swing_points(rates, left=3, right=3):

    highs = []
    lows = []

    n = len(rates)

    for i in range(left, n - right):

        # SWING HIGH
        if (
            all(
                rates[i]["high"] >= rates[i - k]["high"]
                for k in range(1, left + 1)
            )
            and
            all(
                rates[i]["high"] >= rates[i + k]["high"]
                for k in range(1, right + 1)
            )
        ):

            highs.append((i, rates[i]["high"]))

        # SWING LOW
        if (
            all(
                rates[i]["low"] <= rates[i - k]["low"]
                for k in range(1, left + 1)
            )
            and
            all(
                rates[i]["low"] <= rates[i + k]["low"]
                for k in range(1, right + 1)
            )
        ):

            lows.append((i, rates[i]["low"]))

    return highs, lows


# =========================================
# STRUCTURE CLASSIFICATION
# =========================================

def classify_structure(highs, lows, lookback=4):

    if len(highs) < 2 or len(lows) < 2:
        return "RANGING", [], 0.0

    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # =========================================
    # HIGH ANALYSIS
    # =========================================

    hh_count = sum(
        1
        for i in range(1, len(recent_highs))
        if recent_highs[i][1] > recent_highs[i - 1][1]
    )

    lh_count = sum(
        1
        for i in range(1, len(recent_highs))
        if recent_highs[i][1] < recent_highs[i - 1][1]
    )

    # =========================================
    # LOW ANALYSIS
    # =========================================

    hl_count = sum(
        1
        for i in range(1, len(recent_lows))
        if recent_lows[i][1] > recent_lows[i - 1][1]
    )

    ll_count = sum(
        1
        for i in range(1, len(recent_lows))
        if recent_lows[i][1] < recent_lows[i - 1][1]
    )

    labels = []

    # =========================================
    # LABEL GENERATION
    # =========================================

    if len(recent_highs) >= 2:

        for i in range(1, len(recent_highs)):

            if recent_highs[i][1] > recent_highs[i - 1][1]:
                labels.append("HH")
            else:
                labels.append("LH")

    if len(recent_lows) >= 2:

        for i in range(1, len(recent_lows)):

            if recent_lows[i][1] > recent_lows[i - 1][1]:
                labels.append("HL")
            else:
                labels.append("LL")

    n = max(len(recent_highs), len(recent_lows)) - 1

    if n <= 0:
        return "RANGING", labels, 0.0

    bull_score = (hh_count + hl_count) / (n * 2)
    bear_score = (lh_count + ll_count) / (n * 2)

    confidence = max(bull_score, bear_score)

    # =========================================
    # STRUCTURE STATES
    # =========================================

    if bull_score >= 0.70:

        return (
            "BULLISH_STRUCTURE",
            labels,
            round(confidence * 100, 2)
        )

    elif bear_score >= 0.70:

        return (
            "BEARISH_STRUCTURE",
            labels,
            round(confidence * 100, 2)
        )

    elif bull_score > bear_score and "HH" in labels[-2:]:

        return (
            "TRANSITION_BULLISH",
            labels,
            round(confidence * 100, 2)
        )

    elif bear_score > bull_score and "LL" in labels[-2:]:

        return (
            "TRANSITION_BEARISH",
            labels,
            round(confidence * 100, 2)
        )

    return ("RANGING", labels, round(confidence * 100, 2))


# =========================================
# PENALTY ENGINE
# =========================================

def calculate_structure_penalty(
    signal,
    final_bias,
    confidence,
    choch_confirm
):

    signal = str(signal or "").upper()
    final_bias = str(final_bias or "").upper()

    # =========================================
    # ALIGNED
    # =========================================

    if signal == final_bias:

        return {
            "penalty": 0.0,
            "allow_trade": True,
            "mode": "FULL_ALIGNMENT",
        }

    # =========================================
    # TRANSITION MARKET
    # =========================================

    if "TRANSITION" in final_bias:

        return {
            "penalty": -0.8,
            "allow_trade": True,
            "mode": "TRANSITION_PROBE",
        }

    # =========================================
    # STRONG CHOCH
    # =========================================

    if choch_confirm == "STRONG":

        return {
            "penalty": -1.2,
            "allow_trade": True,
            "mode": "CHOCH_REVERSAL",
        }

    # =========================================
    # COUNTER TREND
    # =========================================

    if confidence < 75:

        return {
            "penalty": -1.5,
            "allow_trade": True,
            "mode": "COUNTER_TREND",
        }

    # =========================================
    # STRONG STRUCTURE
    # =========================================

    return {
        "penalty": -2.5,
        "allow_trade": True,
        "mode": "HIGH_RISK_COUNTER",
    }


# =========================================
# MAIN STRUCTURE ENGINE
# =========================================

def get_market_structure(symbol, *, rates_h1=None, rates_h4=None):
    if rates_h1 is None:
        rates_h1 = mt5.copy_rates_from_pos(
            symbol,
            mt5.TIMEFRAME_H1,
            0,
            80
        )
    if rates_h4 is None:
        rates_h4 = mt5.copy_rates_from_pos(
            symbol,
            mt5.TIMEFRAME_H4,
            0,
            60
        )

    if rates_h1 is None:

        return {
            "structure": "UNKNOWN",
            "bias": "NEUTRAL",
            "labels_h1": [],
            "labels_h4": [],
            "mtf_aligned": False,
            "confidence": 0.0,
        }

    # =========================================
    # H1
    # =========================================

    highs_h1, lows_h1 = find_swing_points(
        rates_h1,
        left=3,
        right=3
    )

    struct_h1, lbl_h1, conf_h1 = classify_structure(
        highs_h1,
        lows_h1,
        lookback=4
    )

    # =========================================
    # H4
    # =========================================

    struct_h4 = "RANGING"
    lbl_h4 = []
    conf_h4 = 0.0

    if rates_h4 is not None and len(rates_h4) > 10:

        highs_h4, lows_h4 = find_swing_points(
            rates_h4,
            left=2,
            right=2
        )

        struct_h4, lbl_h4, conf_h4 = classify_structure(
            highs_h4,
            lows_h4,
            lookback=3
        )

    # =========================================
    # BIAS
    # =========================================

    bull_structs = (
        "BULLISH_STRUCTURE",
        "TRANSITION_BULLISH",
    )

    bear_structs = (
        "BEARISH_STRUCTURE",
        "TRANSITION_BEARISH",
    )

    if struct_h1 in bull_structs:

        bias = "BUY"

    elif struct_h1 in bear_structs:

        bias = "SELL"

    else:

        bias = "NEUTRAL"

    # =========================================
    # MTF ALIGNMENT
    # =========================================

    mtf_aligned = (
        (
            struct_h1 in bull_structs
            and
            struct_h4 in bull_structs
        )
        or
        (
            struct_h1 in bear_structs
            and
            struct_h4 in bear_structs
        )
    )

    # =========================================
    # FINAL STRUCTURE
    # =========================================

    final_struct = struct_h1

    if (
        struct_h4 in bull_structs
        and
        struct_h1 == "RANGING"
    ):

        final_struct = "TRANSITION_BULLISH"
        bias = "BUY"

    elif (
        struct_h4 in bear_structs
        and
        struct_h1 == "RANGING"
    ):

        final_struct = "TRANSITION_BEARISH"
        bias = "SELL"

    confidence = max(conf_h1, conf_h4)

    recent_labels = (
        lbl_h1[-4:]
        if len(lbl_h1) >= 4
        else lbl_h1
    )

    print(
        f"🏗 STRUCTURE"
        f" | H1:{struct_h1}"
        f" | H4:{struct_h4}"
        f" | BIAS:{bias}"
        f" | CONF:{confidence:.1f}"
        f" | MTF_ALIGN:{mtf_aligned}"
        f" | Labels:{recent_labels}"
    )

    return {
        "structure": final_struct,
        "bias": bias,
        "labels_h1": lbl_h1,
        "labels_h4": lbl_h4,
        "mtf_aligned": mtf_aligned,
        "h1": struct_h1,
        "h4": struct_h4,
        "confidence": confidence,
    }


# =========================================
# V6.3 — CHOCH + ADAPTIVE AI
# =========================================

def get_market_structure_v63(symbol, signal=None):

    base = get_market_structure(symbol)

    choch_data = get_full_structure_analysis(symbol)

    final_bias = base["bias"]

    # =========================================
    # CHOCH OVERRIDE
    # =========================================

    if choch_data["confirmation"] == "STRONG":

        final_bias = choch_data["bias"]

    elif (
        choch_data["confirmation"] == "MODERATE"
        and
        base["bias"] == "NEUTRAL"
    ):

        final_bias = choch_data["bias"]

    # =========================================
    # STRUCTURE PENALTY
    # =========================================

    structure_ai = calculate_structure_penalty(
        signal=signal,
        final_bias=final_bias,
        confidence=base["confidence"],
        choch_confirm=choch_data["confirmation"],
    )

    combined = {**base}

    combined["choch"] = choch_data
    combined["choch_bias"] = choch_data["bias"]

    combined["choch_confirm"] = choch_data["confirmation"]

    combined["final_bias"] = final_bias

    combined["bos_level"] = choch_data.get(
        "bos_level",
        0
    )

    combined["choch_level"] = choch_data.get(
        "choch_level",
        0
    )

    combined["entry_precision"] = choch_data.get(
        "entry_precision",
        "NORMAL"
    )

    combined["structure_penalty"] = structure_ai["penalty"]

    combined["allow_counter_trend"] = structure_ai["allow_trade"]

    combined["execution_mode"] = structure_ai["mode"]

    print(
        f"🏗 STRUCTURE V6.3"
        f" | BASE:{base['structure']}"
        f" | CHOCH:{choch_data['choch_h4']}"
        f"({choch_data['confirmation']})"
        f" | FINAL_BIAS:{final_bias}"
        f" | PENALTY:{structure_ai['penalty']}"
        f" | MODE:{structure_ai['mode']}"
        f" | CONF:{base['confidence']:.1f}"
    )

    return combined


# =========================================
# BACKWARD COMPATIBILITY
# =========================================

get_market_structure_v51 = get_market_structure

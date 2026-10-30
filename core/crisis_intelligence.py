from core.mt5_compat import mt5, MT5_AVAILABLE


# =========================================
# ATR SPIKE
# =========================================

def atr_spike_detected(
    current_atr,
    average_atr
):

    if average_atr <= 0:
        return False

    return (
        current_atr >
        average_atr * 2
    )


# =========================================
# SPREAD SPIKE
# =========================================

def spread_spike_detected(
    symbol
):

    tick = mt5.symbol_info_tick(
        symbol
    )

    if tick is None:
        return False

    spread = (
        tick.ask -
        tick.bid
    )

    return spread > 1.0


# =========================================
# FLASH CRASH
# =========================================

def flash_crash_detected(
    current_atr,
    average_atr,
    symbol
):

    if atr_spike_detected(
        current_atr,
        average_atr
    ):

        return True

    if spread_spike_detected(
        symbol
    ):

        return True

    return False


# =========================================
# CRISIS MULTIPLIER
# =========================================

def get_crisis_multiplier(
    current_atr,
    average_atr,
    symbol
):

    if flash_crash_detected(
        current_atr,
        average_atr,
        symbol
    ):

        return 0

    if current_atr > (
        average_atr * 1.5
    ):

        return 0.50

    if current_atr > (
        average_atr * 1.2
    ):

        return 0.75

    return 1.0


# =========================================
# CRISIS REPORT
# =========================================

def get_crisis_state(
    current_atr,
    average_atr,
    symbol
):

    multiplier = (
        get_crisis_multiplier(
            current_atr,
            average_atr,
            symbol
        )
    )

    if multiplier == 0:

        return {
            "state": "FREEZE",
            "risk": 0
        }

    elif multiplier < 1:

        return {
            "state": "REDUCED",
            "risk": multiplier
        }

    return {
        "state": "NORMAL",
        "risk": 1
    }
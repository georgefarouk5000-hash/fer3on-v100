# =========================================
# FER3ON V3 — AI SCORING ENGINE
# يحسب نقاط جودة الإشارة 0–10
# =========================================


def calculate_trade_score(
    ema_trend,
    rsi,
    candle_signal,
    current_price,
    support,
    resistance,
    daily_bias=None,
    mtf_direction=None,
    mtf_strength=0
):
    score   = 0
    reasons = []

    # ===================================
    # 1. EMA TREND (0–2)
    # ===================================
    if ema_trend in ("BUY", "SELL"):
        score += 2
        reasons.append(f"EMA:{ema_trend}")

    # ===================================
    # 2. RSI — مناطق أوضح (0–2)
    # ===================================
    if ema_trend == "BUY":
        if 55 <= rsi <= 75:
            score += 2
            reasons.append("RSI:BUY_ZONE")
        elif rsi > 75:
            score -= 1
            reasons.append("RSI:OVERBOUGHT")
        elif 45 <= rsi < 55:
            score += 1
            reasons.append("RSI:NEUTRAL_BUY")

    elif ema_trend == "SELL":
        if 25 <= rsi <= 45:
            score += 2
            reasons.append("RSI:SELL_ZONE")
        elif rsi < 25:
            score -= 1
            reasons.append("RSI:OVERSOLD")
        elif 45 < rsi <= 55:
            score += 1
            reasons.append("RSI:NEUTRAL_SELL")

    # ===================================
    # 3. CANDLE PATTERN (−2 → +2)
    # ===================================
    if candle_signal == ema_trend:
        score += 2
        reasons.append("CANDLE:CONFIRM")
    elif candle_signal == "NONE":
        pass  # محايد
    else:
        score -= 2
        reasons.append("CANDLE:CONFLICT")

    # ===================================
    # 4. DAILY BIAS (−2 → +1)
    # ===================================
    if daily_bias is not None and daily_bias != "NONE":
        if daily_bias == ema_trend:
            score += 1
            reasons.append("DAILY_BIAS:CONFIRM")
        else:
            score -= 2
            reasons.append("DAILY_BIAS:CONFLICT")

    # ===================================
    # 5. MTF CONSENSUS (0 → +2)
    # ===================================
    if mtf_direction is not None and mtf_direction != "NONE":
        if mtf_direction == ema_trend:
            if mtf_strength == 3:
                score += 2
                reasons.append("MTF:FULL_ALIGN")
            elif mtf_strength == 2:
                score += 1
                reasons.append("MTF:H1H4_ALIGN")
        else:
            score -= 1
            reasons.append("MTF:PARTIAL_CONFLICT")

    # ===================================
    # 6. SUPPORT / RESISTANCE (0–1)
    # ===================================
    price_range = resistance - support
    if price_range > 0:
        position = (current_price - support) / price_range

        if ema_trend == "BUY" and position < 0.40:
            score += 1
            reasons.append("S/R:NEAR_SUPPORT")
        elif ema_trend == "SELL" and position > 0.60:
            score += 1
            reasons.append("S/R:NEAR_RESISTANCE")
        elif ema_trend == "BUY" and position > 0.80:
            score -= 1
            reasons.append("S/R:NEAR_RESISTANCE")
        elif ema_trend == "SELL" and position < 0.20:
            score -= 1
            reasons.append("S/R:NEAR_SUPPORT")

    return score, reasons

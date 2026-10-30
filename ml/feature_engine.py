# =========================================
# FER3ON V5.2 — ML FEATURE ENGINE
# تحويل بيانات السوق إلى features للـ ML
# =========================================

import numpy as np
from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone


# =========================================
# EXTRACT FEATURES من بيانات السوق الحية
# =========================================

def extract_live_features(
    symbol,
    strategy,
    signal,
    market_regime,
    session,
    quality_score,
    confidence_pct,
    choch_state,
    liq_map_score,
    exec_grade,
    rr_ratio,
    spread_pts,
    mtf_strength,
    mtf_structural,
    atr,
    key_levels=None,
    current_price=None,
    as_of=None,
):
    """
    يُنتج feature vector كامل من بيانات اللحظة.
    يُستخدم لتمرير الصفقات إلى نماذج ML.
    """
    from brain.trade_dna import get_ml_features

    if current_price is None:
        tick = mt5.symbol_info_tick(symbol)
        current_price = ((tick.ask + tick.bid)/2) if tick else 0

    pdh = key_levels.get("PDH", 0) if key_levels else 0
    pdl = key_levels.get("PDL", 0) if key_levels else 0
    dist_pdh = abs(current_price - pdh) if pdh else 0
    dist_pdl = abs(current_price - pdl) if pdl else 0

    if as_of is None:
        hour = datetime.now(timezone.utc).hour
    else:
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        hour = as_of.astimezone(timezone.utc).hour

    record = {
        "strategy":       strategy,
        "signal":         signal,
        "market_regime":  market_regime,
        "session":        session,
        "quality_score":  quality_score,
        "confidence_pct": confidence_pct,
        "choch_state":    choch_state,
        "liq_map_score":  liq_map_score,
        "exec_grade":     exec_grade,
        "rr_ratio":       rr_ratio,
        "spread_pts":     spread_pts,
        "mtf_strength":   mtf_strength,
        "mtf_structural": mtf_structural,
        "atr":            atr,
        "hour":           hour,
        "dist_pdh":       dist_pdh,
        "dist_pdl":       dist_pdl,
    }

    return np.array(get_ml_features(record), dtype=np.float32), record


# =========================================
# TECHNICAL INDICATORS لـ Backtesting
# =========================================

def compute_indicator_features(rates, idx):
    """
    يحسب indicators من rates array عند index معيّن.
    يُستخدم في backtesting لتوليد features تاريخية.
    """
    if idx < 50:
        return None

    window  = rates[max(0,idx-50):idx+1]
    closes  = np.array([c["close"] for c in window])
    highs   = np.array([c["high"]  for c in window])
    lows    = np.array([c["low"]   for c in window])
    from core.micro_trigger import candle_value

    volumes = np.array(
        [float(candle_value(c, "tick_volume", candle_value(c, "real_volume", 0)) or 0) for c in window],
        dtype=float,
    )

    n = len(closes)

    # EMA
    def ema(arr, p):
        k = 2/(p+1)
        e = arr[0]
        for v in arr[1:]:
            e = v*k + e*(1-k)
        return e

    ema9  = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)

    # ATR
    tr_list = []
    for i in range(1, n):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        tr_list.append(tr)
    atr14 = np.mean(tr_list[-14:]) if tr_list else 1

    # RSI
    gains  = [max(closes[i]-closes[i-1],0) for i in range(1,n)]
    losses = [max(closes[i-1]-closes[i],0) for i in range(1,n)]
    ag = np.mean(gains[-14:]) if gains else 0.001
    al = np.mean(losses[-14:]) if losses else 0.001
    rsi = 100-(100/(1+ag/al)) if al>0 else 50

    # Bollinger
    sma20 = np.mean(closes[-20:])
    std20 = np.std(closes[-20:])
    bb_pct = (closes[-1]-sma20)/(2*std20+0.001)

    # Momentum
    mom10 = (closes[-1]-closes[-10])/closes[-10]*100 if closes[-10]>0 else 0

    # Volume ratio
    vol_ratio = volumes[-1]/np.mean(volumes[-20:]) if np.mean(volumes[-20:])>0 else 1

    # Price position in recent range
    h20 = np.max(highs[-20:])
    l20 = np.min(lows[-20:])
    pos = (closes[-1]-l20)/(h20-l20+0.001)

    return {
        "ema9":      ema9,
        "ema21":     ema21,
        "ema50":     ema50,
        "ema_diff":  (ema9-ema50)/closes[-1]*100,
        "atr14":     atr14,
        "rsi":       rsi,
        "bb_pct":    bb_pct,
        "mom10":     mom10,
        "vol_ratio": vol_ratio,
        "pos20":     pos,
        "spread_atr": 0,
        "close":     closes[-1],
        "n":         n,
    }

# =========================================
# FER3ON V5.2 — LIQUIDITY MAP ENGINE
# PDH/PDL + Weekly High/Low + Equal H/L
# خريطة السيولة الكاملة المؤسسية
# =========================================

from core.mt5_compat import mt5, MT5_AVAILABLE
from datetime import datetime, timezone


# =========================================
# PDH / PDL — Previous Day High/Low
# أهم أهداف السيولة اليومية
# =========================================

def get_pdh_pdl(symbol):
    """
    يجلب:
      PDH  : Previous Day High
      PDL  : Previous Day Low
      PWH  : Previous Week High
      PWL  : Previous Week Low
      ODH  : Today's Open
    """
    rates_d1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 10)
    rates_w1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 5)

    result = {"PDH":0,"PDL":0,"PWH":0,"PWL":0,"ODH":0,"ODL":0}

    if rates_d1 is not None and len(rates_d1) >= 2:
        yesterday       = rates_d1[-2]
        today           = rates_d1[-1]
        result["PDH"]   = round(float(yesterday["high"]),  2)
        result["PDL"]   = round(float(yesterday["low"]),   2)
        result["ODH"]   = round(float(today["high"]),      2)
        result["ODL"]   = round(float(today["low"]),       2)

    if rates_w1 is not None and len(rates_w1) >= 2:
        prev_week       = rates_w1[-2]
        result["PWH"]   = round(float(prev_week["high"]),  2)
        result["PWL"]   = round(float(prev_week["low"]),   2)

    return result


# =========================================
# EQUAL HIGHS / LOWS
# =========================================

def _extract_equal_levels(rates, tolerance_pct=0.015, label="H4"):
    """يكتشف Equal Highs / Lows (نسبة tolerance كنسبة مئوية من السعر)"""
    pools = []
    n     = len(rates)
    highs = [c["high"]  for c in rates]
    lows  = [c["low"]   for c in rates]
    avg   = sum(highs) / len(highs)
    tol   = avg * tolerance_pct / 100

    for i in range(n):
        for j in range(i+1, min(i+20, n)):
            if abs(highs[i]-highs[j]) <= tol:
                lvl = (highs[i]+highs[j])/2
                pools.append({"price":round(lvl,2),"type":"EQH","tf":label,"strength":"MEDIUM"})
                break
    for i in range(n):
        for j in range(i+1, min(i+20, n)):
            if abs(lows[i]-lows[j]) <= tol:
                lvl = (lows[i]+lows[j])/2
                pools.append({"price":round(lvl,2),"type":"EQL","tf":label,"strength":"MEDIUM"})
                break

    # Swing Highs / Lows الكبيرة
    for i in range(3, n-3):
        if all(highs[i]>=highs[i-k] for k in range(1,4)) and all(highs[i]>=highs[i+k] for k in range(1,4)):
            pools.append({"price":round(highs[i],2),"type":"SWING_H","tf":label,"strength":"HIGH"})
        if all(lows[i] <=lows[i-k]  for k in range(1,4)) and all(lows[i] <=lows[i+k]  for k in range(1,4)):
            pools.append({"price":round(lows[i],2), "type":"SWING_L","tf":label,"strength":"HIGH"})

    # إزالة تكرار
    seen, unique = [], []
    for p in pools:
        if not any(abs(p["price"]-s) < tol*2 for s in seen):
            unique.append(p); seen.append(p["price"])
    return unique


# =========================================
# FULL LIQUIDITY MAP V5.2
# =========================================

def build_liquidity_map(symbol, current_price=None):
    """
    V5.2 — خريطة السيولة الكاملة:
      TIER-1 (أعلى أولوية): PDH / PDL / PWH / PWL
      TIER-2: Swing Highs / Lows على H4
      TIER-3: Equal Highs / Lows على H1
    """
    rates_h4 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 100)
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 80)

    if rates_h4 is None:
        return _empty_map()

    tick = mt5.symbol_info_tick(symbol)
    if current_price is None and tick:
        current_price = (tick.ask + tick.bid) / 2
    if not current_price:
        return _empty_map()

    # ————————————————————————
    # TIER-1: PDH/PDL/PWH/PWL (أولوية قصوى)
    # ————————————————————————
    key_levels = get_pdh_pdl(symbol)
    tier1_pools = []
    for k, v in key_levels.items():
        if v > 0:
            tier1_pools.append({
                "price":    v,
                "type":     k,
                "tf":       "D1/W1",
                "strength": "CRITICAL",
                "priority": 1
            })

    # ————————————————————————
    # TIER-2: H4 Swing Points
    # ————————————————————————
    tier2_pools = _extract_equal_levels(rates_h4, tolerance_pct=0.02, label="H4")
    for p in tier2_pools:
        p["priority"] = 2

    # ————————————————————————
    # TIER-3: H1 Equal Levels
    # ————————————————————————
    tier3_pools = []
    if rates_h1 is not None:
        tier3_pools = _extract_equal_levels(rates_h1, tolerance_pct=0.01, label="H1")
        for p in tier3_pools:
            p["priority"] = 3

    all_pools = tier1_pools + tier2_pools + tier3_pools

    if not all_pools:
        return _empty_map()

    # ————————————————————————
    # تصنيف فوق / تحت السعر
    # ————————————————————————
    above = sorted([p for p in all_pools if p["price"] > current_price + 1],
                   key=lambda x: (x["priority"], x["price"]))
    below = sorted([p for p in all_pools if p["price"] < current_price - 1],
                   key=lambda x: (x["priority"], -x["price"]))

    direction = _determine_direction(rates_h1, current_price)

    # ————————————————————————
    # اختيار الأهداف بحسب الاتجاه
    # ————————————————————————
    if direction == "UP":
        # الأهداف فوق — رتبها بالقرب أولاً، مع تفضيل TIER-1
        targets     = sorted(above, key=lambda x: x["price"])[:4]
        next_target  = targets[0]["price"] if targets else current_price + 10
        final_target = targets[-1]["price"] if targets else current_price + 20
        current_pool = below[0]["price"] if below else current_price - 5

    elif direction == "DOWN":
        targets     = sorted(below, key=lambda x: -x["price"])[:4]
        next_target  = targets[0]["price"] if targets else current_price - 10
        final_target = targets[-1]["price"] if targets else current_price - 20
        current_pool = above[0]["price"] if above else current_price + 5

    else:
        targets      = (above[:1]+below[:1]) if (above or below) else []
        next_target  = above[0]["price"] if above else (below[0]["price"] if below else current_price)
        final_target = next_target
        current_pool = current_price

    distance_next  = round(abs(current_price-next_target),  2)
    distance_final = round(abs(current_price-final_target), 2)

    # ————————————————————————
    # نقاط القوة
    # ————————————————————————
    liq_score = _score_map(direction, targets, tier1_pools, above, below, distance_next)

    # أهم المستويات فوق/تحت
    critical_above = [p for p in above  if p.get("strength")=="CRITICAL"][:3]
    critical_below = [p for p in below  if p.get("strength")=="CRITICAL"][:3]

    print(
        f"🗺  LIQ-MAP V5.2 | Dir:{direction}"
        f" | PDH:{key_levels['PDH']} PDL:{key_levels['PDL']}"
        f" | Next:{next_target:.2f} ({distance_next:.1f}pts)"
        f" | Final:{final_target:.2f}"
        f" | Score:{liq_score}/25"
        f" | Pools:{len(all_pools)}"
    )

    return {
        "direction":        direction,
        "current_price":    round(current_price, 2),
        "current_pool":     round(current_pool, 2),
        "next_target":      round(next_target, 2),
        "final_target":     round(final_target, 2),
        "distance_next":    distance_next,
        "distance_final":   distance_final,
        "liquidity_score":  liq_score,
        "targets":          targets,
        "pools_above":      [p["price"] for p in above[:5]],
        "pools_below":      [p["price"] for p in below[:5]],
        "critical_above":   [p["price"] for p in critical_above],
        "critical_below":   [p["price"] for p in critical_below],
        "key_levels":       key_levels,
        "tier1_count":      len(tier1_pools),
        "total_pools":      len(all_pools),
    }


def _determine_direction(rates_h1, current_price):
    if rates_h1 is None or len(rates_h1) < 10:
        return "NEUTRAL"
    closes = [c["close"] for c in rates_h1[-10:]]
    h1 = sum(closes[:5])/5
    h2 = sum(closes[5:])/5
    pct = (h2-h1)/h1*100
    return "UP" if pct>0.1 else ("DOWN" if pct<-0.1 else "NEUTRAL")


def _score_map(direction, targets, tier1, above, below, dist_next):
    score = 0
    if direction != "NEUTRAL":   score += 5
    if tier1:                     score += min(len(tier1)*3, 9)
    if targets:                   score += min(len(targets)*2, 6)
    if 5 <= dist_next <= 60:      score += 5
    return min(score, 25)


def validate_trade_with_map(liq_map, signal, sl_dist, current_price):
    if liq_map.get("liquidity_score", 0) < 5:
        return True, "MAP_WEAK_SKIP", 0
    direction  = liq_map.get("direction", "NEUTRAL")
    dist_next  = liq_map.get("distance_next", 0)
    aligned = (signal=="BUY" and direction=="UP") or (signal=="SELL" and direction=="DOWN")
    if not aligned:
        return False, f"MAP_CONFLICT: sig={signal} dir={direction}", -10
    if dist_next >= sl_dist*3: return True, "EXCELLENT_RANGE", 12
    if dist_next >= sl_dist*2: return True, "GOOD_RANGE", 8
    return True, "ACCEPTABLE_RANGE", 4


def _empty_map():
    return {
        "direction":"NEUTRAL","current_price":0,"current_pool":0,
        "next_target":0,"final_target":0,"distance_next":0,
        "distance_final":0,"liquidity_score":0,"targets":[],
        "pools_above":[],"pools_below":[],"critical_above":[],
        "critical_below":[],"key_levels":{},"tier1_count":0,"total_pools":0
    }

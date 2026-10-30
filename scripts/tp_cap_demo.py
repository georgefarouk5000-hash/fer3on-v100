"""Demo script: show adaptive SL/TP for active strategies.

Run with: python scripts/tp_cap_demo.py
"""
from core.adaptive_sl_tp_engine import calculate_adaptive_sl_tp
from core.settings import (
    TP_ATR_CAP_MULT_PER_STRAT,
    TP_SL_MULT_PER_STRAT,
)

SCENARIOS = [
    {
        'strategy': 'DAILY',
        'atr': 0.5,
        'quality_score': 55,
        'session': 'LONDON',
    },
    {
        'strategy': 'SMC',
        'atr': 25.0,
        'quality_score': 70,
        'session': 'NEWYORK',
    },
]

for s in SCENARIOS:
    strat = s['strategy']
    atr = s['atr']
    print('\n---')
    print(f"Strategy={strat} ATR={atr}")
    adaptive = calculate_adaptive_sl_tp(
        atr=atr,
        strategy=strat,
        lot=0.01,
        confidence=0.5,
        quality_score=s['quality_score'],
        market_regime='UNKNOWN',
        session=s['session'],
        structure_strength=0.6,
        liquidity=0.6,
        volatility=0.5,
        execution_grade='B',
        broker_stop_level=0.0,
        broker_stop_fallback=0.0,
        min_sl=5.0,
    )

    raw_sl = adaptive['sl_distance']
    raw_tp = adaptive['tp_distance']

    mult_atr = TP_ATR_CAP_MULT_PER_STRAT.get(strat.upper(), None)
    mult_sl = TP_SL_MULT_PER_STRAT.get(strat.upper(), None)

    print(f"Adaptive SL={raw_sl:.2f} TP={raw_tp:.2f}")
    if mult_atr is not None and mult_sl is not None:
        cap_atr = atr * mult_atr
        cap_sl = raw_sl * mult_sl
        capped_tp = min(raw_tp, max(cap_atr, cap_sl))
        print(f"Per-strat caps: ATR*{mult_atr}={cap_atr:.2f}, SL*{mult_sl}={cap_sl:.2f}")
        print(f"Final TP after cap = {capped_tp:.2f}")
    else:
        print("No per-strategy caps configured; no capping applied.")

print('\nDemo complete.')

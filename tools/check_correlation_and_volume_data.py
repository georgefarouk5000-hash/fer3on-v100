#!/usr/bin/env python3
# =============================================================================
# FAIE data-availability diagnostic (Phase-2 spec §2.2 / §2.3 pre-checks)
# =============================================================================
# Answers the two open questions blocking the Correlation Engine (§2.2) and
# the real Volume/Order-Flow Engine (§2.3), WITHOUT building either engine
# speculatively (see docs/FAIE/GAP_ANALYSIS.md and PHASE_2_SPECIFICATION.md
# §8 — "hold until a decision on ... Correlation's data source is made;
# don't build speculatively").
#
# RUN THIS ON THE ACTUAL MACHINE WHERE THE MT5 TERMINAL IS INSTALLED AND
# LOGGED INTO THE BROKER ACCOUNT — it will not produce a real answer
# anywhere else (a stub result on a non-Windows/no-MT5 machine is expected
# and clearly labeled as such below, not a real answer).
#
# Usage:
#   python3 tools/check_correlation_and_volume_data.py [SYMBOL]
#   (SYMBOL defaults to XAUUSD, the symbol this codebase already assumes
#   almost everywhere else — see core/settings.py)
# =============================================================================

from __future__ import annotations

import sys

from core.mt5_compat import mt5, MT5_AVAILABLE

# Common broker-naming variants for each correlation-relevant instrument.
# Brokers rename these constantly (suffixes like 'm', '.a', '_i', or a
# completely different ticker) — this is a best-effort pattern search over
# whatever mt5.symbols_get() actually returns, not a fixed exact-name list.
CANDIDATE_PATTERNS = {
    "US Dollar Index (DXY)": ["DXY", "USDX", "USDOLLAR", "DOLLAR", "DXUSD", "USDIDX"],
    "US 10Y Treasury Yield": ["US10Y", "T10Y", "TNX", "USTBOND", "US10YR", "BOND10"],
    "US Treasury Bonds (futures-style)": ["USTBOND", "TBOND", "ZN", "ZB"],
    "S&P 500 index": ["US500", "SPX", "SP500", "USA500", "SPX500"],
    "Nasdaq 100 index": ["US100", "NAS100", "USTEC", "NDX"],
}


def find_candidate_symbols():
    """Search every symbol the broker actually offers (not just what's
    already in Market Watch) for names that look like a correlation-
    relevant instrument. Never assumes a symbol exists — reports exactly
    what matched, or that nothing did."""
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return {}

    names = [s.name for s in all_symbols]
    found = {}
    for label, patterns in CANDIDATE_PATTERNS.items():
        matches = [n for n in names if any(p in n.upper() for p in patterns)]
        if matches:
            found[label] = sorted(set(matches))
    return found


def check_volume_kind(symbol: str, bars: int = 200):
    """Pull recent candles for `symbol` and check whether real_volume is
    ever nonzero. If real_volume is always 0 across a real sample of bars,
    the broker/feed is only providing tick_volume for this symbol — that's
    normal for most retail accounts, not a bug, but it means a real Volume/
    Order-Flow engine (§2.3) would have nothing genuine to read."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, bars)
    if rates is None or len(rates) == 0:
        return {
            "symbol": symbol, "bars_checked": 0, "has_real_volume": None,
            "note": f"could not read any rates for {symbol} — check the symbol name and that it's in Market Watch",
        }

    try:
        real_volumes = [r["real_volume"] for r in rates]
        tick_volumes = [r["tick_volume"] for r in rates]
    except (KeyError, IndexError, TypeError):
        return {
            "symbol": symbol, "bars_checked": len(rates), "has_real_volume": None,
            "note": "this MT5 build's rates array has no real_volume field at all",
        }

    nonzero_real = sum(1 for v in real_volumes if v)
    return {
        "symbol": symbol,
        "bars_checked": len(rates),
        "has_real_volume": nonzero_real > 0,
        "nonzero_real_volume_bars": nonzero_real,
        "avg_tick_volume": sum(tick_volumes) / len(tick_volumes),
        "note": (
            f"{nonzero_real} of {len(rates)} bars had nonzero real_volume"
            if nonzero_real else
            "real_volume was 0 on every bar checked — this feed is tick_volume only"
        ),
    }


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"

    print("=" * 70)
    print("FAIE data-availability diagnostic")
    print("=" * 70)

    if not MT5_AVAILABLE or getattr(mt5, "is_stub", False):
        print(
            "MetaTrader5 package/terminal not available in this environment.\n"
            "This is expected if you're running this somewhere other than the\n"
            "Windows machine with the MT5 terminal installed and logged in —\n"
            "run it there instead for a real answer."
        )
        return 1

    if not mt5.initialize():
        print("mt5.initialize() failed — is the MT5 terminal open and logged in?")
        return 1

    try:
        print("\n--- 1. Correlation-relevant symbols available at your broker ---\n")
        found = find_candidate_symbols()
        if not found:
            print(
                "No obvious matches found by name. This does not necessarily mean\n"
                "nothing is available — some brokers use non-obvious tickers. Open\n"
                "MT5 -> View -> Symbols (Ctrl+U), search manually for 'dollar',\n"
                "'index', '10y', 'bond', and check what's actually listed there."
            )
        else:
            for label, matches in found.items():
                print(f"  {label}: {', '.join(matches)}")

        print(f"\n--- 2. Volume data kind for {symbol} ---\n")
        vol_report = check_volume_kind(symbol)
        for k, v in vol_report.items():
            print(f"  {k}: {v}")

        print("\n" + "-" * 70)
        print("Send this whole output back — it's exactly what's needed to decide")
        print("whether the Correlation Engine (§2.2) and real Volume Engine (§2.3)")
        print("are buildable against your actual account, or should stay held.")
    finally:
        mt5.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())

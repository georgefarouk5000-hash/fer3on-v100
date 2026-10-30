#!/usr/bin/env python3
"""
Check Currently Open Trades

Quick script to display all currently open positions on XAUUSD
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 module not installed")
    sys.exit(1)

from core.settings import SYMBOL

# Initialize MT5
if not mt5.initialize():
    print(f"ERROR: Failed to initialize MT5. Error: {mt5.last_error()}")
    sys.exit(1)

print("\n" + "="*80)
print("CURRENTLY OPEN TRADES")
print("="*80)

# Get all open positions
positions = mt5.positions_get(symbol=SYMBOL)

if not positions:
    print("\nNo open trades found.")
else:
    print(f"\nTotal Open Positions: {len(positions)}\n")
    
    for i, pos in enumerate(positions, 1):
        pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        
        print(f"Trade #{i}:")
        print(f"  Ticket:       {pos.ticket}")
        print(f"  Type:         {pos_type}")
        print(f"  Volume:       {pos.volume} lot")
        print(f"  Open Price:   ${pos.price_open:.2f}")
        print(f"  Current Price: ${pos.price_current:.2f}")
        
        if pos_type == "BUY":
            profit_loss = (pos.price_current - pos.price_open) * pos.volume * 100
            profit_pct = ((pos.price_current - pos.price_open) / pos.price_open * 100) if pos.price_open > 0 else 0
        else:
            profit_loss = (pos.price_open - pos.price_current) * pos.volume * 100
            profit_pct = ((pos.price_open - pos.price_current) / pos.price_open * 100) if pos.price_open > 0 else 0
        
        print(f"  SL:           ${pos.sl:.2f}" if pos.sl > 0 else f"  SL:           None")
        print(f"  TP:           ${pos.tp:.2f}" if pos.tp > 0 else f"  TP:           None")
        print(f"  Profit/Loss:  ${profit_loss:.2f} ({profit_pct:+.2f}%)")
        print(f"  Open Time:    {pos.time}")
        print(f"  Magic:        {pos.magic}")
        print()

mt5.shutdown()

print("="*80)

#!/usr/bin/env python3
import sys
from core.mt5_compat import mt5, MT5_AVAILABLE, connect_mt5


def main():
    print('FER3ON MT5 connectivity check')
    print(f'MT5 package available: {MT5_AVAILABLE}')
    if not MT5_AVAILABLE:
        print('MT5 package is not installed in this environment; using compatibility mode.')
        print('On Windows, install requirements then open MetaTrader 5 and rerun this file if you want live connectivity.')
        return 0
    if not connect_mt5():
        print('MT5 initialize failed; continuing in compatibility mode.')
        return 0
    account = mt5.account_info()
    term = mt5.terminal_info()
    print('MT5 initialize: OK')
    print(f'Account available: {account is not None}')
    print(f'Terminal connected: {bool(term)}')
    mt5.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

from core.demo_execution import demo_execution_status
from core.mt5_compat import MT5_AVAILABLE, mt5
from core.trade_identity import strategy_from_magic


def _is_daily_position(position):
    return (
        strategy_from_magic(
            getattr(position, "magic", None),
            default="UNKNOWN",
        )
        == "DAILY"
    )


def manage_daily_positions(symbol):
    if not MT5_AVAILABLE or mt5 is None:
        return

    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        print("[DAILY_POSITION_MANAGER] Position state unavailable; no updates made")
        return

    daily_positions = [position for position in positions if _is_daily_position(position)]
    if not daily_positions:
        return

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3)
    if rates is None or len(rates) < 2:
        print("[DAILY_POSITION_MANAGER] Closed D1 candle unavailable; no updates made")
        return

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    if tick is None or symbol_info is None:
        print("[DAILY_POSITION_MANAGER] Price or symbol metadata unavailable; no updates made")
        return

    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    if point <= 0:
        print("[DAILY_POSITION_MANAGER] Invalid symbol point; no updates made")
        return

    minimum_distance = max(
        0,
        int(getattr(symbol_info, "trade_stops_level", 0) or 0),
    ) * point
    closed_candle = rates[-2]
    allowed, reason = demo_execution_status()
    if not allowed:
        print(f"🛑 DAILY_POSITION_ORDER_BLOCKED | {reason}")
        return

    for position in daily_positions:
        position_type = getattr(position, "type", None)
        current_sl = float(getattr(position, "sl", 0.0) or 0.0)
        take_profit = float(getattr(position, "tp", 0.0) or 0.0)
        if position_type == mt5.POSITION_TYPE_BUY:
            new_sl = float(closed_candle["low"])
            market_price = float(getattr(tick, "bid", 0.0) or 0.0)
            improves_protection = current_sl <= 0 or new_sl > current_sl
            valid_side = market_price > 0 and new_sl < market_price - minimum_distance
        elif position_type == mt5.POSITION_TYPE_SELL:
            new_sl = float(closed_candle["high"])
            market_price = float(getattr(tick, "ask", 0.0) or 0.0)
            improves_protection = current_sl <= 0 or new_sl < current_sl
            valid_side = market_price > 0 and new_sl > market_price + minimum_distance
        else:
            continue

        if new_sl <= 0 or not improves_protection or not valid_side:
            continue

        digits = int(getattr(symbol_info, "digits", 2) or 2)
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": int(position.ticket),
            "sl": round(new_sl, digits),
            "tp": take_profit,
        }
        result = mt5.order_send(request)
        if result is not None and getattr(result, "retcode", None) == mt5.TRADE_RETCODE_DONE:
            print(f"🌍 DAILY SL UPDATED | Ticket: {position.ticket} | New SL: {request['sl']}")
        else:
            print(
                f"❌ DAILY SL UPDATE FAILED | Ticket: {position.ticket} "
                f"| retcode={getattr(result, 'retcode', None)}"
            )

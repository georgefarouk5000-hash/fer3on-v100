"""Read the current trading day's XAUUSD PnL directly from MetaTrader 5."""

from __future__ import annotations

from datetime import datetime, time, timezone
import logging
import math
import time as time_module
from typing import Any, Dict, Optional

from core.mt5_compat import MT5_AVAILABLE, mt5
from core.settings import SYMBOL

MT5_READ_ATTEMPTS = 3
MT5_RETRY_DELAY_SEC = 0.25
_LOGGER = logging.getLogger(__name__)


def _amount(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid MT5 PnL value: {value!r}") from exc
    if not math.isfinite(amount):
        raise ValueError(f"Non-finite MT5 PnL value: {value!r}")
    return amount


def get_daily_loss_status(
    symbol: str = SYMBOL,
    *,
    now: Optional[datetime] = None,
    mt5_client: Any = None,
) -> Dict[str, float]:
    """Return realized/current PnL and the largest observed loss for today.

    Closed MT5 deals are processed chronologically so a later recovery does
    not erase an intraday loss-limit breach. Current floating PnL is included
    when checking the live loss.
    """
    client = mt5_client if mt5_client is not None else mt5
    if client is None or (
        mt5_client is None
        and (not MT5_AVAILABLE or getattr(client, "is_stub", False))
    ):
        raise RuntimeError("MT5_DAILY_PNL_UNAVAILABLE")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current_time = current_time.astimezone(timezone.utc)
    day_start = datetime.combine(current_time.date(), time.min, tzinfo=timezone.utc)

    last_error = None
    for attempt in range(1, MT5_READ_ATTEMPTS + 1):
        read_stage = "history"
        try:
            deals = client.history_deals_get(day_start, current_time)
            if deals is None:
                raise RuntimeError("MT5_DEAL_HISTORY_UNAVAILABLE")

            read_stage = "positions"
            positions = client.positions_get(symbol=symbol)
            if positions is None:
                raise RuntimeError("MT5_POSITION_STATE_UNAVAILABLE")
            break
        except Exception as exc:
            last_error = exc
            reason = (
                "MT5_POSITION_STATE_UNAVAILABLE"
                if read_stage == "positions"
                else "MT5_DEAL_HISTORY_UNAVAILABLE"
            )
            if attempt == MT5_READ_ATTEMPTS:
                _LOGGER.error(
                    "MT5 daily PnL unavailable after %s attempts: %s",
                    MT5_READ_ATTEMPTS,
                    exc,
                )
                raise RuntimeError(reason) from exc
            _LOGGER.warning(
                "MT5 daily PnL read failed (attempt %s/%s); retrying in %.2fs: %s",
                attempt,
                MT5_READ_ATTEMPTS,
                MT5_RETRY_DELAY_SEC,
                exc,
            )
            time_module.sleep(MT5_RETRY_DELAY_SEC)
    else:
        raise RuntimeError("MT5_DAILY_PNL_UNAVAILABLE") from last_error

    symbol_deals = [
        deal for deal in deals
        if str(getattr(deal, "symbol", "") or "").upper() == symbol.upper()
    ]
    symbol_deals.sort(
        key=lambda deal: (
            int(getattr(deal, "time_msc", 0) or 0),
            int(getattr(deal, "time", 0) or 0),
            int(getattr(deal, "ticket", 0) or 0),
        )
    )

    realized_pnl = 0.0
    worst_realized_pnl = 0.0
    for deal in symbol_deals:
        realized_pnl += sum(
            _amount(getattr(deal, field, 0.0))
            for field in ("profit", "commission", "swap", "fee")
        )
        worst_realized_pnl = min(worst_realized_pnl, realized_pnl)

    floating_pnl = sum(
        _amount(getattr(position, "profit", 0.0))
        + _amount(getattr(position, "swap", 0.0))
        for position in positions
    )
    current_pnl = realized_pnl + floating_pnl
    daily_loss = max(0.0, -worst_realized_pnl, -current_pnl)
    return {
        "realized_pnl": round(realized_pnl, 2),
        "floating_pnl": round(floating_pnl, 2),
        "daily_pnl": round(current_pnl, 2),
        "daily_loss": round(daily_loss, 2),
    }

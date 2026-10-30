import os
from datetime import datetime, timezone

from core.data_integrity import (
    AI_MEMORY_COLUMNS,
    AI_MEMORY_FILE,
    append_csv_row,
    dump_rows,
    ensure_csv_schema,
    read_csv_records,
)
from core.account_scope import get_cached_account_id


# =========================================
# INIT MEMORY
# =========================================

def initialize_memory():
    ensure_csv_schema(
        AI_MEMORY_FILE,
        AI_MEMORY_COLUMNS
    )


_UNSET = object()  # sentinel: distinguishes "caller didn't pass this" from
                   # "caller explicitly passed 0 / 'UNKNOWN' / etc." — see
                   # save_trade_memory() for why this matters.


def _upsert_memory_row(row):
    ticket = str(row.get("ticket", "") or "")
    if not ticket:
        append_csv_row(AI_MEMORY_FILE, AI_MEMORY_COLUMNS, row)
        return row

    rows = read_csv_records(AI_MEMORY_FILE, AI_MEMORY_COLUMNS)
    updated = False
    merged_rows = []
    for existing in rows:
        if str(existing.get("ticket", "") or "") == ticket:
            merged = dict(existing)
            for key, value in row.items():
                if value not in (None, ""):
                    merged[key] = value
            if str(merged.get("result", "")).upper() == "OPEN" and str(row.get("result", "")).upper() in {"WIN", "LOSS", "BREAKEVEN"}:
                merged["result"] = row.get("result")
            merged_rows.append(merged)
            updated = True
        else:
            merged_rows.append(existing)

    if not updated:
        merged_rows.append(row)

    dump_rows(AI_MEMORY_FILE, AI_MEMORY_COLUMNS, merged_rows)
    return row


# =========================================
# SAVE MEMORY
# =========================================

def save_trade_memory(
    ticket,
    strategy,
    signal,
    result,
    profit,
    atr=_UNSET,
    market_regime=_UNSET,
    spread=_UNSET,
    session=_UNSET,
    quality_score=_UNSET,
    final_score=_UNSET,
    execution_mode=_UNSET,
    recovery_state=_UNSET,
    confidence=_UNSET,
    candle_weight=_UNSET,
    liquidity_bias=_UNSET,
    structure_bias=_UNSET,
    choch_bias=_UNSET,
    regime_score=_UNSET,
    latency_ms=_UNSET,
    spread_score=_UNSET,
    ai_override=_UNSET,
    notes=_UNSET,
    **extra,
):

    initialize_memory()

    now = datetime.now(timezone.utc)

    hour = extra.get("hour", now.hour)

    # ENRICHMENT FIX: these params used to have concrete Python defaults
    # (atr=0, market_regime="UNKNOWN", quality_score=50, ...), so every
    # call — including one that only meant to update the outcome, like the
    # MT5 close-sync recording a result — silently wrote those defaults
    # into the row. _upsert_memory_row() treats any non-None/non-empty
    # value as authoritative and overwrites the merged row with it, so a
    # later call could wipe out real data recorded at open time (atr,
    # quality_score, choch/liquidity fields via **extra, etc.) with a
    # "nobody told me, so assume 0/UNKNOWN" default. _UNSET now
    # distinguishes "caller didn't pass this" from "caller explicitly
    # passed 0/UNKNOWN" — unset fields are defaulted only when this is the
    # first record for a ticket, and simply omitted (left untouched by the
    # merge) on a later update to an existing ticket.
    ticket_key = str(ticket or "")
    is_new_record = not (ticket_key and deal_exists(ticket_key))

    _field_defaults = {
        "atr": 0,
        "market_regime": "UNKNOWN",
        "spread": 0,
        "session": "UNKNOWN",
        "quality_score": 50,
        "final_score": 50,
        "execution_mode": "NORMAL",
        "recovery_state": "NORMAL",
        "confidence": 50,
        "candle_weight": 0,
        "liquidity_bias": "NONE",
        "structure_bias": "NONE",
        "choch_bias": "NONE",
        "regime_score": 50,
        "latency_ms": 0,
        "spread_score": 0,
        "ai_override": False,
        "notes": "",
    }
    _field_values = {
        "atr": atr,
        "market_regime": market_regime,
        "spread": spread,
        "session": session,
        "quality_score": quality_score,
        "final_score": final_score,
        "execution_mode": execution_mode,
        "recovery_state": recovery_state,
        "confidence": confidence,
        "candle_weight": candle_weight,
        "liquidity_bias": liquidity_bias,
        "structure_bias": structure_bias,
        "choch_bias": choch_bias,
        "regime_score": regime_score,
        "latency_ms": latency_ms,
        "spread_score": spread_score,
        "ai_override": ai_override,
        "notes": notes,
    }
    _numeric_fields = {
        "atr", "spread", "quality_score", "final_score",
        "confidence", "regime_score", "latency_ms", "spread_score",
    }

    row = {
        "date": extra.get("date", now.isoformat()),
        "ticket": ticket,
        "strategy": strategy,
        "signal": signal,
        "result": result,
        "profit": round(float(profit or 0), 2),
        "hour": hour,
        "account_id": get_cached_account_id(),
    }

    for field, value in _field_values.items():
        if value is _UNSET:
            if not is_new_record:
                continue  # don't clobber an existing merged value
            value = _field_defaults[field]
        if field in _numeric_fields:
            value = round(float(value or 0), 2)
        elif field == "ai_override":
            value = bool(value)
        row[field] = value

    row.update(extra)

    _upsert_memory_row(row)

    return row


# =========================================
# COMPAT WRAPPER
# =========================================

def store_memory(*args, **kwargs):
    """Compatibility wrapper required by startup integrity validation."""
    return save_trade_memory(*args, **kwargs)


# =========================================
# DEAL EXISTS
# =========================================

def deal_exists(ticket):

    if not os.path.exists(
        AI_MEMORY_FILE
    ):
        return False

    ticket = str(ticket)

    for row in read_csv_records(
        AI_MEMORY_FILE
    ):

        if str(
            row.get("ticket", "")
        ) == ticket:

            return True

    return False


# =========================================
# LOAD MEMORY
# =========================================

def load_memory_records():

    initialize_memory()

    return read_csv_records(
        AI_MEMORY_FILE,
        AI_MEMORY_COLUMNS
    )


# =========================================
# ANALYZE MEMORY
# =========================================

def analyze_memory():

    rows = load_memory_records()

    if not rows:
        return {}

    trades = len(rows)

    wins = 0
    losses = 0

    total_profit = 0.0

    for row in rows:

        try:
            profit = float(
                row.get("profit", 0) or 0
            )
        except Exception:
            profit = 0.0

        total_profit += profit

        result = str(
            row.get("result", "")
        ).upper()

        if result == "WIN" or (
            result not in ("WIN", "LOSS")
            and profit >= 0
        ):

            wins += 1

        elif result == "LOSS" or profit < 0:

            losses += 1

    winrate = (
        (wins / trades) * 100
        if trades > 0
        else 0
    )

    return {

        "trades":
            trades,

        "wins":
            wins,

        "losses":
            losses,

        "profit":
            round(total_profit, 2),

        "winrate":
            round(winrate, 2),
    }


# =========================================
# FALSE SIGNAL RATE
# =========================================

def get_false_signal_rate(
    strategy=None
):

    rows = load_memory_records()

    if not rows:
        return 0.0

    total = 0
    false_signals = 0

    for row in rows:

        if strategy:

            if row.get(
                "strategy"
            ) != strategy:

                continue

        total += 1

        result = str(
            row.get("result", "")
        ).upper()

        if result == "LOSS":

            quality = float(
                row.get(
                    "quality_score",
                    50
                ) or 50
            )

            if quality >= 70:
                false_signals += 1

    if total == 0:
        return 0.0

    return round(
        (
            false_signals / total
        ) * 100,
        2
    )


# =========================================
# BEST SESSION
# =========================================

def get_best_session():

    rows = load_memory_records()

    stats = {}

    for row in rows:

        session = row.get(
            "session",
            "UNKNOWN"
        )

        if session not in stats:

            stats[session] = {
                "wins": 0,
                "total": 0
            }

        stats[session]["total"] += 1

        if str(
            row.get("result")
        ).upper() == "WIN":

            stats[session]["wins"] += 1

    best = None
    best_wr = 0

    for session, data in stats.items():

        if data["total"] < 5:
            continue

        wr = (
            data["wins"] /
            data["total"]
        )

        if wr > best_wr:

            best_wr = wr
            best = session

    return best, round(
        best_wr * 100,
        2
    )


# =========================================
# REGIME PERFORMANCE
# =========================================

def get_regime_performance():

    rows = load_memory_records()

    regimes = {}

    for row in rows:

        regime = row.get(
            "market_regime",
            "UNKNOWN"
        )

        if regime not in regimes:

            regimes[regime] = {

                "wins": 0,

                "losses": 0,

                "profit": 0,

                "trades": 0,
            }

        profit = float(
            row.get("profit", 0) or 0
        )

        regimes[regime]["profit"] += profit

        regimes[regime]["trades"] += 1

        if profit >= 0:
            regimes[regime]["wins"] += 1
        else:
            regimes[regime]["losses"] += 1

    return regimes


# =========================================
# STRATEGY MATRIX
# =========================================

def get_strategy_matrix():

    rows = load_memory_records()

    matrix = {}

    for row in rows:

        strategy = row.get(
            "strategy",
            "UNKNOWN"
        )

        if strategy not in matrix:

            matrix[strategy] = {

                "wins": 0,

                "losses": 0,

                "profit": 0,

                "trades": 0,
            }

        matrix[strategy]["trades"] += 1

        profit = float(
            row.get("profit", 0) or 0
        )

        matrix[strategy]["profit"] += profit

        if profit >= 0:
            matrix[strategy]["wins"] += 1
        else:
            matrix[strategy]["losses"] += 1

    return matrix


# =========================================
# CONFIDENCE FEEDBACK
# =========================================

def get_confidence_feedback():

    rows = load_memory_records()

    if not rows:
        return 0.0

    high_conf_total = 0
    high_conf_losses = 0

    for row in rows:

        score = float(
            row.get(
                "final_score",
                0
            ) or 0
        )

        if score >= 80:

            high_conf_total += 1

            profit = float(
                row.get(
                    "profit",
                    0
                ) or 0
            )

            if profit < 0:
                high_conf_losses += 1

    if high_conf_total == 0:
        return 0.0

    error_rate = (
        high_conf_losses /
        high_conf_total
    ) * 100

    return round(
        error_rate,
        2
    )


# =========================================
# MARKET PERSONALITY
# =========================================

def detect_market_personality():

    regimes = get_regime_performance()

    if not regimes:
        return "UNKNOWN"

    best_regime = None
    best_profit = -999999

    for regime, data in regimes.items():

        profit = float(
            data.get("profit", 0)
        )

        if profit > best_profit:

            best_profit = profit
            best_regime = regime

    return best_regime or "UNKNOWN"


# =========================================
# BUILD MEMORY INTELLIGENCE
# =========================================

def build_memory_intelligence():

    analysis = analyze_memory()

    best_session = get_best_session()

    strategy_matrix = get_strategy_matrix()

    regime_performance = (
        get_regime_performance()
    )

    false_signal_rate = (
        get_false_signal_rate()
    )

    confidence_error = (
        get_confidence_feedback()
    )

    market_personality = (
        detect_market_personality()
    )

    return {

        "memory":
            analysis,

        "best_session":
            best_session,

        "strategy_matrix":
            strategy_matrix,

        "regime_performance":
            regime_performance,

        "false_signal_rate":
            false_signal_rate,

        "confidence_error":
            confidence_error,

        "market_personality":
            market_personality,
    }


# =========================================
# MEMORY DASHBOARD
# =========================================

def print_memory_dashboard():

    intel = build_memory_intelligence()

    mem = intel["memory"]

    print(
        f"[MEMORY AI]"
        f" Trades={mem.get('trades',0)}"
        f" | WR={mem.get('winrate',0)}%"
        f" | Profit={mem.get('profit',0)}"
        f" | FALSE={intel['false_signal_rate']}%"
        f" | CONF_ERR={intel['confidence_error']}%"
        f" | MARKET={intel['market_personality']}"
    )
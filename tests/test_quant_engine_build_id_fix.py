"""
Regression test for a live-risk-affecting bug found while reviewing a real
burn-in log of FER3ON-FINAL-build1: evaluate_strategy_health() (consumed by
core/trade_executor.py for lot-sizing and core/unified_decision.py for entry
scoring) computed its verdict from load_all_trades() with NO build_id filter
-- so a strategy's health tier / risk_multiplier was silently blended from
retired pre-merge strategy versions together with this build's real trades
(observed live: "QUANT_HEALTH | SMC | tier=POOR | n=82" while this build only
had a couple dozen real SMC trades at the time).

Fix: filter_trades() now accepts build_id, and evaluate_strategy_health()
passes BUILD_ID through it.
"""
import json

from analytics.truth_layer import TradeRecord, append_trade, __test_reset__
from analytics.quant_engine import evaluate_strategy_health
from core.settings import BUILD_ID


def _make_trade(i, build_id, profit):
    return TradeRecord(
        ticket=i,
        strategy="SMC",
        direction="BUY",
        session="LONDON",
        regime="TRENDING",
        open_time=f"2026-07-01T00:{i:02d}:00+00:00",
        close_time=f"2026-07-01T00:{i:02d}:30+00:00",
        profit=profit,
        is_win=profit > 0,
        build_id=build_id,
    )


def test_health_ignores_other_build_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    __test_reset__()

    # 25 retired-version SMC trades, mostly losing -> would read as POOR
    # if blended in.
    for i in range(25):
        append_trade(_make_trade(i, "SOME_OLDER_BUILD", -10 if i % 3 else 15))

    # Only 5 real current-build trades -- below QUANT_MIN_TRADES_FOR_HEALTH.
    for i in range(25, 30):
        append_trade(_make_trade(i, BUILD_ID, 20))

    health = evaluate_strategy_health("SMC")

    # Must NOT compute a tier from the blended 30; must see only the 5 real
    # current-build trades and correctly report an insufficient sample.
    assert health.sample_size == 5, (
        f"Expected only the 5 current-build trades, got sample_size="
        f"{health.sample_size} -- retired-build trades leaked back in."
    )
    assert health.health_tier == "UNKNOWN"
    assert health.risk_multiplier == 1.0


def test_health_uses_current_build_once_enough_samples(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    __test_reset__()

    for i in range(15):
        append_trade(_make_trade(i, "SOME_OLDER_BUILD", -10))

    for i in range(15, 40):
        append_trade(_make_trade(i, BUILD_ID, 20 if i % 2 else -5))

    health = evaluate_strategy_health("SMC")
    assert health.sample_size == 25

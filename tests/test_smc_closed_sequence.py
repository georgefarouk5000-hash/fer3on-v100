from unittest.mock import Mock, call, patch


def _details(**overrides):
    details = {
        "sweep": False,
        "bos": False,
        "fvg": False,
        "ob": False,
        "mitigation": False,
        "breaker": False,
        "premium_discount_aligned": False,
        "retest": False,
    }
    details.update(overrides)
    return details


def test_smc_entry_requires_retest_but_accepts_either_structural_trigger():
    from core.smc_entry_engine import _grade_smc

    confirmed, grade, _ = _grade_smc(
        _details(sweep=True, fvg=True, retest=False)
    )

    assert not confirmed
    assert grade == "C"

    confirmed, grade, _ = _grade_smc(
        _details(bos=True, fvg=True, retest=True)
    )

    assert confirmed
    assert grade == "B+"


def test_smc_entry_allows_premium_discount_confluence_after_retest():
    from core.smc_entry_engine import _grade_smc

    confirmed, grade, _ = _grade_smc(
        _details(fvg=True, premium_discount_aligned=True, retest=True)
    )

    assert confirmed
    assert grade == "B"


def test_live_smc_rates_are_requested_from_last_closed_candle():
    import core.smc_entry_engine as engine

    fake_mt5 = Mock()
    fake_mt5.TIMEFRAME_H1 = 1
    fake_mt5.TIMEFRAME_M5 = 5
    fake_mt5.TIMEFRAME_M15 = 15
    fake_mt5.copy_rates_from_pos.return_value = [
        {"time": index, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0}
        for index in range(60)
    ]

    with (
        patch.object(engine, "mt5", fake_mt5),
        patch.object(engine, "detect_liquidity_sweep", return_value="NONE"),
        patch.object(engine, "detect_bos", return_value="NONE"),
        patch.object(engine, "detect_fvg", return_value=("NONE", None)),
        patch.object(engine, "detect_order_block", return_value=("NONE", None)),
        patch.object(
            engine,
            "analyze_smc_advanced",
            return_value={
                "premium_discount": {"zone": "NEUTRAL"},
                "mitigation": {"type": "NONE"},
                "breaker": {"type": "NONE"},
                "buy_score": 0,
                "sell_score": 0,
            },
        ),
    ):
        engine.check_smc_entry_sequence("XAUUSD", "BUY", verbose=False)

    assert fake_mt5.copy_rates_from_pos.call_args_list == [
        call("XAUUSD", 1, 1, 60),
        call("XAUUSD", 5, 1, 120),
        call("XAUUSD", 15, 1, 60),
    ]


def test_fvg_must_precede_the_candle_used_to_confirm_its_retest():
    from core.smart_money import detect_fvg

    rates = [
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 10.8, "high": 12.0, "low": 10.8, "close": 11.0},
    ]

    assert detect_fvg(rates, lookback=5) == ("NONE", None)


def test_advanced_fvg_must_precede_the_candle_used_to_confirm_its_retest():
    from core.smc_advanced import detect_real_fvg

    rates = [
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 9.5, "high": 10.0, "low": 9.0, "close": 9.7},
        {"open": 10.0, "high": 14.0, "low": 10.0, "close": 14.0},
        {"open": 11.0, "high": 12.0, "low": 10.8, "close": 11.5},
    ]

    assert detect_real_fvg(rates, lookback=5)["type"] == "NONE"

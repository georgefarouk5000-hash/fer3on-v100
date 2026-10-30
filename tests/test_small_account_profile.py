import importlib
from unittest.mock import MagicMock, patch


def test_frozen_profile_respects_explicit_balance_env(monkeypatch):
    """BASE_ACCOUNT_BALANCE still reads ACCOUNT_BALANCE_USD when set -- the
    3-tier account-size system was replaced with a single frozen profile
    (build spec [SETTINGS-1] / [SLTP-2]) calibrated for the confirmed
    $200-$1000 real account range, but this env-var passthrough is still the
    mechanism that lets the operator tell the bot its actual live balance."""
    monkeypatch.setenv("ACCOUNT_BALANCE_USD", "350")
    monkeypatch.setenv("ACCOUNT_MODE", "REAL")

    import core.settings as settings
    settings = importlib.reload(settings)

    assert settings.BASE_ACCOUNT_BALANCE == 350.0


def test_frozen_profile_absolute_ceilings_hold(monkeypatch):
    """Regardless of balance, the FINAL build's absolute safety ceilings
    (build spec Action Plan #4/#5) must never be exceeded."""
    monkeypatch.delenv("ACCOUNT_BALANCE_USD", raising=False)
    monkeypatch.setenv("ACCOUNT_MODE", "DEMO")

    import core.settings as settings
    settings = importlib.reload(settings)

    assert settings.MAX_LOT <= 0.10
    assert settings.MAX_RISK_PER_DAY_PERCENT <= 10.0
    assert settings.MAX_SL_DISTANCE_DOLLARS > 0


def test_small_account_is_protected_by_min_lot_risk_guard():
    """The 3-tier settings.py system (tiny RISK_PER_TRADE_PERCENT for small
    balances) has been replaced by a functional guard: on a $200 account,
    core.risk_manager.calculate_smart_lot must either (a) size the trade so
    the MIN_LOT-implied dollar risk stays within MIN_LOT_RISK_MULTIPLE_CAP
    of the intended risk_amount, or (b) skip the trade (lot=0.0) rather than
    silently open an oversized-relative-risk position. See build spec
    [SLTP-2] for the full reasoning (XAUUSD's 0.01 MIN_LOT combined with a
    realistic ATR-based stop can otherwise imply 15-45% single-trade risk
    on a $200 balance)."""
    import core.risk_manager as rm
    from core.settings import (
        MIN_LOT, MAX_SL_DISTANCE_DOLLARS, MIN_LOT_RISK_MULTIPLE_CAP,
        RISK_PER_TRADE_PERCENT,
    )

    fake_sym_info = MagicMock()
    fake_sym_info.trade_tick_value = 1.0
    fake_sym_info.volume_step = 0.01
    fake_sym_info.point = 0.01

    balance = 200.0
    risk_amount = balance * (RISK_PER_TRADE_PERCENT / 100.0)

    with patch.object(rm, "mt5") as fake_mt5:
        fake_mt5.symbol_info.return_value = fake_sym_info
        with patch.object(
            rm, "get_loss_limits_status",
            return_value={"daily_used": 0, "daily_limit": 999,
                          "weekly_used": 0, "weekly_limit": 999},
        ):
            with patch.object(rm, "cooldown_active", return_value=False):
                # A wide, realistic ATR-based stop that exceeds the account's
                # comfortable risk budget at MIN_LOT.
                lot, raw_lot, adjustments = rm.calculate_smart_lot(
                    balance=balance,
                    risk_percent=RISK_PER_TRADE_PERCENT,
                    sl_dist=50.0,
                    symbol="XAUUSD",
                    quality_score=75,
                    session="LONDON",
                    exec_grade="A",
                )

    if lot > 0:
        implied_risk = lot * (min(50.0, MAX_SL_DISTANCE_DOLLARS) / 0.01) * 1.0
        assert implied_risk <= risk_amount * MIN_LOT_RISK_MULTIPLE_CAP + 1e-6
    else:
        # Guard correctly chose to skip rather than force an oversized trade.
        assert any("GUARD" in a for a in adjustments)

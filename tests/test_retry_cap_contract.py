from core.settings import MAX_SL_DISTANCE_DOLLARS
from core.trade_executor import _cap_retry_growth


def test_retry_growth_never_exceeds_finalizer_account_cap():
    growth = _cap_retry_growth(10.0, MAX_SL_DISTANCE_DOLLARS / 2.0)
    assert growth <= 2.0


def test_retry_growth_preserves_requested_growth_below_cap():
    assert _cap_retry_growth(1.2, 5.0) == 1.2


def test_retry_growth_respects_contextual_strategy_cap():
    assert _cap_retry_growth(2.0, 5.0, sl_cap=8.0) == 1.3
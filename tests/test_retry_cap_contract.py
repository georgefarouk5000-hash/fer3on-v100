from types import SimpleNamespace

from core.settings import MAX_SL_DISTANCE_DOLLARS
import core.trade_executor as te
from core.trade_executor import _cap_retry_growth


def test_retry_growth_never_exceeds_finalizer_account_cap():
    growth = _cap_retry_growth(10.0, MAX_SL_DISTANCE_DOLLARS / 2.0)
    assert growth <= 2.0


def test_retry_growth_preserves_requested_growth_below_cap():
    assert _cap_retry_growth(1.2, 5.0) == 1.2


def test_retry_growth_respects_contextual_strategy_cap():
    assert _cap_retry_growth(2.0, 5.0, sl_cap=8.0) == 1.3


def test_structural_stop_retry_does_not_widen_stop_or_target(monkeypatch, tmp_path):
    sent_requests = []
    rejected = SimpleNamespace(retcode=10016, comment="invalid stops")

    class FakeMT5:
        TRADE_RETCODE_DONE = 10009

        @staticmethod
        def order_check(request):
            return SimpleNamespace(retcode=0)

        @staticmethod
        def order_send(request):
            sent_requests.append(dict(request))
            return rejected

    monkeypatch.setattr(te, "mt5", FakeMT5)
    monkeypatch.setattr(te, "get_filling_fallback_sequence", lambda _: [1])
    monkeypatch.setattr(te, "_is_unsupported_filling", lambda _: False)
    monkeypatch.setattr(te, "_is_stops_too_close_rejection", lambda _: True)
    monkeypatch.setattr(te, "ORDER_RETRY_ON_STOPS_REJECTION_ENABLED", True)
    monkeypatch.setattr(te, "ORDER_RETRY_MAX_ATTEMPTS", 5)

    from core import trade_event_ledger

    monkeypatch.setattr(
        trade_event_ledger,
        "TRADE_EVENTS_FILE",
        str(tmp_path / "events.jsonl"),
    )
    result, final_sl, final_tp = te._send_order_with_stops_retry(
        request={
            "symbol": "XAUUSD",
            "type": 0,
            "type_filling": 1,
            "price": 2000.0,
        },
        symbol="XAUUSD",
        point=0.01,
        sl_dist=25.0,
        tp_dist=55.0,
        price=2000.0,
        signal="BUY",
        decision_id="decision-1",
        strategy="TSM",
        preserve_structural_stop=True,
    )

    assert result is rejected
    assert final_sl == 25.0
    assert final_tp == 55.0
    assert len(sent_requests) == 1
    assert sent_requests[0]["sl"] == 1975.0
    assert sent_requests[0]["tp"] == 2055.0
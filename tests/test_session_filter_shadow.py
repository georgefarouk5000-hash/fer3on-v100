from dataclasses import dataclass, field
from typing import Any, Dict

from analytics.session_filter_shadow import replay_session_hard_filter


@dataclass
class _FakeTrade:
    ticket: int
    strategy: str = "SMC"
    direction: str = "BUY"
    session: str = "ASIA"
    regime: str = "TRENDING"
    profit: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


def _ranking(sessions):
    return {"generated_at": "now", "total_trades_analysed": 0, "sessions": sessions}


def test_no_ranking_file_degrades_gracefully(monkeypatch, tmp_path):
    import analytics.session_filter_shadow as shadow
    monkeypatch.setattr(shadow, "_RANKING_PATH", str(tmp_path / "missing.json"))
    result = replay_session_hard_filter(trades=[_FakeTrade(ticket=1)], ranking=None)
    assert result["status"] == "NO_RANKING_FILE"


def test_blocks_only_confirmed_low_pf_sessions():
    ranking = _ranking([
        {"session": "ASIA", "sample_label": "EDGE_CONFIRMED", "profit_factor": 0.7},
        {"session": "LONDON", "sample_label": "EDGE_CONFIRMED", "profit_factor": 1.8},
        {"session": "OVERLAP", "sample_label": "INSUFFICIENT_SAMPLE", "profit_factor": 0.2},
    ])
    trades = [
        _FakeTrade(ticket=1, session="ASIA", profit=-30.0),
        _FakeTrade(ticket=2, session="LONDON", profit=50.0),
        _FakeTrade(ticket=3, session="OVERLAP", profit=10.0),
    ]
    result = replay_session_hard_filter(trades=trades, ranking=ranking)
    assert result["status"] == "OK"
    assert result["blocked_sessions"] == ["ASIA"]
    # OVERLAP not blocked despite low PF because sample is insufficient
    assert result["trades_that_would_be_blocked"] == 1
    assert result["pnl_of_blocked_trades"] == -30.0
    assert result["capital_effect_of_filter"] == "would have avoided a net loss"


def test_verdict_when_blocked_trades_were_net_positive():
    ranking = _ranking([{"session": "ASIA", "sample_label": "EDGE_CONFIRMED", "profit_factor": 0.9}])
    trades = [_FakeTrade(ticket=1, session="ASIA", profit=40.0)]
    result = replay_session_hard_filter(trades=trades, ranking=ranking)
    assert result["capital_effect_of_filter"] == "would ALSO have blocked net-positive trades"

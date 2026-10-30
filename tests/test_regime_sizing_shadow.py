from dataclasses import dataclass, field
from typing import Any, Dict

from analytics.regime_sizing_shadow import (
    multiplier_for_regime,
    replay_regime_aware_sizing,
)


@dataclass
class _FakeTrade:
    ticket: int
    strategy: str = "SMC"
    direction: str = "BUY"
    session: str = "LONDON"
    regime: str = "TRENDING"
    profit: float = 0.0
    lot: float = 0.01
    extra: Dict[str, Any] = field(default_factory=dict)


def _ranking(regimes):
    return {"generated_at": "now", "total_trades_analysed": 0, "regimes": regimes}


def test_multiplier_neutral_when_insufficient_sample():
    ranking = _ranking([{"regime": "TRENDING", "sample_label": "INSUFFICIENT_SAMPLE", "profit_factor": 3.0}])
    info = multiplier_for_regime("TRENDING", ranking)
    assert info["multiplier"] == 1.0


def test_multiplier_scales_with_profit_factor_when_confirmed():
    ranking = _ranking([{"regime": "TRENDING", "sample_label": "EDGE_CONFIRMED", "profit_factor": 3.0}])
    info = multiplier_for_regime("TRENDING", ranking)
    # pf/reference = 3.0/1.5 = 2.0, clamped to max 1.5
    assert info["multiplier"] == 1.5


def test_multiplier_never_below_floor():
    ranking = _ranking([{"regime": "CRISIS", "sample_label": "EDGE_CONFIRMED", "profit_factor": 0.1}])
    info = multiplier_for_regime("CRISIS", ranking)
    assert info["multiplier"] == 0.5


def test_replay_no_ranking_file_degrades_gracefully(monkeypatch, tmp_path):
    import analytics.regime_sizing_shadow as shadow
    monkeypatch.setattr(shadow, "_RANKING_PATH", str(tmp_path / "missing.json"))
    result = replay_regime_aware_sizing(trades=[_FakeTrade(ticket=1)], ranking=None)
    assert result["status"] in ("NO_RANKING_FILE",)


def test_replay_sums_actual_and_shadow_pnl():
    ranking = _ranking([{"regime": "TRENDING", "sample_label": "EDGE_CONFIRMED", "profit_factor": 3.0}])
    trades = [
        _FakeTrade(ticket=1, regime="TRENDING", profit=100.0),
        _FakeTrade(ticket=2, regime="TRENDING", profit=-50.0),
    ]
    result = replay_regime_aware_sizing(trades=trades, ranking=ranking)
    assert result["status"] == "OK"
    assert result["total_actual_pnl"] == 50.0
    # multiplier 1.5 -> shadow = 150 - 75 = 75
    assert result["total_shadow_pnl_if_regime_aware"] == 75.0
    assert result["per_regime"]["TRENDING"]["trades"] == 2

from datetime import datetime, timezone
from unittest.mock import patch


def _candles(count, step=0.1):
    rates = []
    for index in range(count):
        close = 100 + index * step
        rates.append({
            "time": index * 60,
            "open": close - step / 2,
            "high": close + step,
            "low": close - step,
            "close": close,
            "tick_volume": 10,
        })
    return rates


def _timed_candles(count, start, step=0.1, interval_seconds=300):
    rates = _candles(count, step)
    for index, candle in enumerate(rates):
        candle["time"] = start + index * interval_seconds
    return rates


def test_smc_entry_sequence_accepts_historical_rates_without_mt5():
    from core.smc_entry_engine import check_smc_entry_sequence

    with patch(
        "core.smc_entry_engine.mt5.copy_rates_from_pos",
        side_effect=AssertionError("historical replay must not fetch live rates"),
    ):
        confirmed, grade, details = check_smc_entry_sequence(
            "XAUUSD",
            "BUY",
            rates_h1=_candles(60),
            rates_m5=_candles(120),
            rates_m15=_candles(60),
            verbose=False,
        )

    assert isinstance(confirmed, bool)
    assert isinstance(grade, str)
    assert "grade_score" in details


def test_candle_trigger_accepts_historical_m15_rates_without_mt5():
    from core.candle_trigger import check_candle_trigger

    with patch(
        "core.candle_trigger.mt5.copy_rates_from_pos",
        side_effect=AssertionError("historical replay must not fetch live rates"),
    ):
        result = check_candle_trigger(
            "XAUUSD",
            "BUY",
            "SMC",
            rates=_candles(20),
            rates_m15=_candles(20, step=0.2),
            verbose=False,
            deduplicate_closed_candles=False,
        )

    assert "confirmed" in result
    assert "execution_mode" in result


def test_market_structure_and_regime_accept_historical_rates_without_mt5():
    from core.market_regime import detect_market_regime
    from core.market_structure import get_market_structure

    h1 = _candles(80)
    h4 = _candles(60, step=0.3)
    m15 = _candles(100, step=0.05)

    with (
        patch(
            "core.market_structure.mt5.copy_rates_from_pos",
            side_effect=AssertionError("must use supplied H1/H4 rates"),
        ),
        patch(
            "core.market_regime.mt5.copy_rates_from_pos",
            side_effect=AssertionError("must use supplied M15/H1 rates"),
        ),
    ):
        structure = get_market_structure("XAUUSD", rates_h1=h1, rates_h4=h4)
        regime = detect_market_regime("XAUUSD", rates_m15=m15, rates_h1=h1)

    assert structure["bias"] in {"BUY", "SELL", "NEUTRAL"}
    assert regime in {"TRENDING", "RANGING", "VOLATILE", "CRISIS", "UNKNOWN"}


def test_historical_liquidity_uses_as_of_time_and_supplied_rates():
    from core.liquidity_intelligence import get_liquidity_bias

    utc_midnight = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())
    m15 = _timed_candles(96, utc_midnight, interval_seconds=15 * 60)
    for candle in m15[:32]:
        candle["high"] = 105
        candle["low"] = 95
    m5 = _timed_candles(20, utc_midnight + 9 * 60 * 60, interval_seconds=5 * 60)
    for candle in m5:
        candle["high"] = 104
        candle["low"] = 99
        candle["close"] = 101
    m5[-1].update({"high": 106, "low": 100, "close": 104})
    h1 = _timed_candles(50, utc_midnight, interval_seconds=60 * 60)

    with patch(
        "core.liquidity_intelligence.mt5.copy_rates_from_pos",
        side_effect=AssertionError("historical liquidity must not fetch MT5 rates"),
    ), patch(
        "core.liquidity_intelligence.mt5.symbol_info_tick",
        side_effect=AssertionError("historical liquidity must use supplied price"),
    ):
        result = get_liquidity_bias(
            "XAUUSD",
            rates_m15=m15,
            rates_m5=m5,
            rates_h1=h1,
            current_price=104,
            as_of=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        )

    assert result["sweep"] == "LONDON_SWEEP_HIGH"
    assert result["bias"] == "SELL"


def test_asof_frame_selection_excludes_unclosed_and_future_candles():
    import pandas as pd

    from testing.smc_historical_replay import _rates_asof

    frame = pd.DataFrame({
        "Date": pd.to_datetime([
            "2026-01-01 00:00",
            "2026-01-01 00:05",
            "2026-01-01 00:10",
        ]),
        "Open": [1.0, 2.0, 3.0],
        "High": [1.5, 2.5, 3.5],
        "Low": [0.5, 1.5, 2.5],
        "Close": [1.1, 2.1, 3.1],
        "Volume": [1.0, 1.0, 1.0],
    })

    selected, end = _rates_asof(
        frame,
        [0, 300, 600],
        decision_time=600,
        timeframe_seconds=300,
    )

    assert end == 2
    assert [candle["close"] for candle in selected] == [1.1, 2.1]


def test_same_candle_stop_and_target_is_labeled_as_loss():
    from testing.smc_historical_replay import _outcome

    result, _, exit_price = _outcome(
        [{"open": 100, "high": 103, "low": 97}],
        first_bar=0,
        signal="BUY",
        entry=100,
        sl_distance=2,
        tp_distance=2,
    )

    assert result == "LOSS"
    assert exit_price == 98


def test_live_feature_extractor_accepts_replay_price_and_timestamp_without_mt5():
    import numpy as np

    from brain.trade_dna import get_ml_features
    from ml.feature_engine import extract_live_features

    as_of = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    with patch(
        "ml.feature_engine.mt5.symbol_info_tick",
        side_effect=AssertionError("explicit historical price must bypass MT5"),
    ):
        features, record = extract_live_features(
            symbol="XAUUSD",
            strategy="SMC",
            signal="SELL",
            market_regime="TRENDING",
            session="LONDON",
            quality_score=80,
            confidence_pct=65,
            choch_state="BEARISH_STRUCTURE",
            liq_map_score=12,
            exec_grade="B",
            rr_ratio=2,
            spread_pts=0,
            mtf_strength=3,
            mtf_structural=1,
            atr=8,
            key_levels={"PDH": 110, "PDL": 90},
            current_price=100,
            as_of=as_of,
        )

    assert record["hour"] == 10
    assert features.dtype == np.float32
    assert features.tolist() == get_ml_features(record)
    assert features[6] == -2


def test_outcome_dependent_trade_fields_do_not_change_ml_features():
    from brain.trade_dna import get_ml_features

    before_exit = {
        "strategy": "SMC",
        "signal": "BUY",
        "market_regime": "TRENDING",
        "session": "LONDON",
        "duration_minutes": 5,
        "execution_latency_ms": 100,
        "slippage_pts": 2,
        "composite_score": 75,
        "risk_percent": 0.5,
    }
    after_exit = {
        **before_exit,
        "duration_minutes": 120,
        "execution_latency_ms": 900,
        "slippage_pts": 12,
        "composite_score": 15,
        "risk_percent": 5,
    }

    assert get_ml_features(before_exit) == get_ml_features(after_exit)
    assert get_ml_features(after_exit)[17:] == [0.0] * 5


def test_legacy_nn_feature_schema_fails_closed(tmp_path, monkeypatch):
    import pickle

    import ml.neural_network as neural_network

    artifact = tmp_path / "nn.pkl"
    artifact.write_bytes(pickle.dumps({
        "model": object(),
        "scaler": object(),
        "feature_count": 22,
    }))
    monkeypatch.setattr(neural_network, "NN_MODEL_FILE", str(artifact))

    predictor = neural_network.NeuralPredictor()

    assert predictor.trained is False
    assert predictor.model is None


def test_legacy_gbm_feature_schema_fails_closed(tmp_path, monkeypatch):
    import joblib

    import ml.xgboost_model as xgboost_model

    model_path = tmp_path / "model.pkl"
    scaler_path = tmp_path / "scaler.pkl"
    joblib.dump({"model": object(), "feature_count": 22}, model_path)
    joblib.dump({"scaler": object(), "feature_count": 22}, scaler_path)
    monkeypatch.setattr(xgboost_model, "MODEL_FILE", str(model_path))
    monkeypatch.setattr(xgboost_model, "SCALER_FILE", str(scaler_path))
    monkeypatch.setattr(xgboost_model, "LEGACY_MODEL_FILE", str(tmp_path / "missing-model.pkl"))
    monkeypatch.setattr(xgboost_model, "LEGACY_SCALER_FILE", str(tmp_path / "missing-scaler.pkl"))

    predictor = xgboost_model.GBMPredictor()

    assert predictor.trained is False
    assert predictor.model is None

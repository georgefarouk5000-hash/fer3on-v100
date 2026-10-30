import json

from tools.development_readiness_gate import (
    _check_data_quality,
    _check_real_backtest,
    _check_trading_sample,
    _check_market_diversity,
    run_readiness_check,
)


def _row(**overrides):
    base = {
        "date": "2026-07-01T10:00:00+00:00",
        "ticket": "1",
        "result": "WIN",
        "atr": "1.5",
        "choch_strength": "STRONG",
        "liq_map_score": "64",
        "liq_map_dir": "UP",
        "mtf_structural": "1",
        "market_regime": "TRENDING",
    }
    base.update(overrides)
    return base


# ---------------------------- data_quality ----------------------------

def test_data_quality_insufficient_sample():
    result = _check_data_quality([_row(ticket=str(i)) for i in range(3)])
    assert result["status"] == "INSUFFICIENT_SAMPLE"


def test_data_quality_pass_with_full_enrichment():
    rows = [_row(ticket=str(i)) for i in range(10)]
    result = _check_data_quality(rows)
    assert result["status"] == "PASS"
    assert result["coverage"] == 1.0


def test_data_quality_fail_with_no_enrichment():
    rows = [
        _row(ticket=str(i), atr="0", choch_strength="", liq_map_score="",
             liq_map_dir="", mtf_structural="")
        for i in range(10)
    ]
    result = _check_data_quality(rows)
    assert result["status"] == "FAIL"
    assert result["coverage"] == 0.0


def test_data_quality_ignores_open_trades():
    rows = [_row(ticket=str(i), result="OPEN", atr="", choch_strength="") for i in range(10)]
    result = _check_data_quality(rows)
    assert result["status"] == "INSUFFICIENT_SAMPLE"  # OPEN trades don't count as closed


# ---------------------------- real_backtest ----------------------------

def test_real_backtest_fail_when_missing(tmp_path):
    path = str(tmp_path / "missing.json")
    result = _check_real_backtest(path)
    assert result["status"] == "FAIL"


def test_real_backtest_warn_when_synthetic_only(tmp_path):
    path = str(tmp_path / "baseline.json")
    with open(path, "w") as fh:
        json.dump({"expectancy": 42.0, "csv": None}, fh)
    result = _check_real_backtest(path)
    assert result["status"] == "WARN"


def test_real_backtest_pass_when_real_csv_recorded(tmp_path):
    path = str(tmp_path / "baseline.json")
    with open(path, "w") as fh:
        json.dump({"expectancy": 42.0, "csv": "data/backtest_data/real.csv"}, fh)
    result = _check_real_backtest(path)
    assert result["status"] == "PASS"


# ---------------------------- trading_sample ----------------------------

def test_trading_sample_fail_when_no_closed_trades():
    result = _check_trading_sample([_row(ticket="1", result="OPEN")])
    assert result["status"] == "FAIL"
    assert result["trade_count"] == 0


def test_trading_sample_pass_with_enough_trades_and_span():
    rows = [
        _row(ticket=str(i), date=f"2026-06-{(i % 28) + 1:02d}T10:00:00+00:00")
        for i in range(40)
    ]
    result = _check_trading_sample(rows)
    assert result["status"] == "PASS"
    assert result["trade_count"] == 40


def test_trading_sample_warn_with_few_trades():
    rows = [
        _row(ticket=str(i), date=f"2026-06-{(i % 20) + 1:02d}T10:00:00+00:00")
        for i in range(15)
    ]
    result = _check_trading_sample(rows)
    assert result["status"] == "WARN"


# ---------------------------- market_diversity ----------------------------

def test_market_diversity_insufficient_when_all_unknown():
    rows = [_row(ticket=str(i), market_regime="UNKNOWN") for i in range(5)]
    result = _check_market_diversity(rows)
    assert result["status"] == "INSUFFICIENT_SAMPLE"


def test_market_diversity_pass_with_two_regimes():
    rows = (
        [_row(ticket=f"t{i}", market_regime="TRENDING") for i in range(5)]
        + [_row(ticket=f"r{i}", market_regime="RANGING") for i in range(5)]
    )
    result = _check_market_diversity(rows)
    assert result["status"] == "PASS"
    assert result["distinct_regimes"] == 2


# ---------------------------- overall verdict ----------------------------

def test_run_readiness_check_ready_when_all_gates_pass(tmp_path, monkeypatch):
    good_rows = [
        _row(ticket=str(i), date=f"2026-06-{(i % 28) + 1:02d}T10:00:00+00:00",
             market_regime="TRENDING" if i % 2 else "RANGING")
        for i in range(40)
    ]
    monkeypatch.setattr("tools.development_readiness_gate.load_memory_records", lambda: good_rows)

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps({"expectancy": 10.0, "csv": "real.csv"}))
    monkeypatch.setattr("tools.development_readiness_gate.CI_BASELINE_PATH", str(baseline_path))
    monkeypatch.setattr(
        "tools.development_readiness_gate._check_real_backtest",
        lambda baseline_path=str(baseline_path): {"status": "PASS", "message": "ok"},
    )

    report = run_readiness_check()
    assert report["verdict"] == "READY"


def test_run_readiness_check_not_ready_on_any_fail(monkeypatch):
    monkeypatch.setattr("tools.development_readiness_gate.load_memory_records", lambda: [])
    report = run_readiness_check()
    assert report["verdict"] == "NOT_READY"


def test_market_diversity_never_blocks_readiness(monkeypatch):
    # Even a totally INSUFFICIENT_SAMPLE market_diversity gate must not by
    # itself flip verdict away from READY if the blocking gates all pass.
    good_rows = [
        _row(ticket=str(i), date=f"2026-06-{(i % 28) + 1:02d}T10:00:00+00:00",
             market_regime="UNKNOWN")  # -> market_diversity INSUFFICIENT_SAMPLE
        for i in range(40)
    ]
    monkeypatch.setattr("tools.development_readiness_gate.load_memory_records", lambda: good_rows)
    monkeypatch.setattr(
        "tools.development_readiness_gate._check_real_backtest",
        lambda: {"status": "PASS", "message": "ok"},
    )
    report = run_readiness_check()
    assert report["gates"]["market_diversity"]["status"] == "INSUFFICIENT_SAMPLE"
    assert report["verdict"] == "READY"

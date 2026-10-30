"""اختبارات history_loader: تتحقق من قراءة بيانات حقيقية (CSV مؤقت يحاكي شكل
data/history/trades.csv و data/memory/ai_memory.csv فعليًا)، ومن أن القيم
المفقودة/غير المسجَّلة (0 أو فارغ) لا تُعامَل كقراءة حقيقية (atr=0 لا يعني
"تقلب ضعيف"، news_score=0 لا يعني "خبر متطرف")."""

from __future__ import annotations

import csv
import os

import pytest

from fer3on_masr.learning import history_loader as hl

TRADES_COLUMNS = [
    "date", "ticket", "signal", "lot", "profit", "result", "strategy",
    "session", "market_regime", "exec_grade", "rr_ratio", "quality_score", "brain_score",
]
MEMORY_COLUMNS = [
    "date", "ticket", "strategy", "signal", "result", "profit", "atr", "market_regime",
    "hour", "spread", "session", "quality_score", "confidence_score", "confidence_pct",
    "exec_grade", "rr_ratio", "choch_state", "choch_strength", "liq_map_score",
    "liq_map_dir", "mtf_strength", "mtf_structural", "news_score",
]


@pytest.fixture()
def fixture_project(tmp_path, monkeypatch):
    history_dir = tmp_path / "data" / "history"
    memory_dir = tmp_path / "data" / "memory"
    history_dir.mkdir(parents=True)
    memory_dir.mkdir(parents=True)

    trades_rows = [
        {"date": "2026-01-01", "ticket": "1", "signal": "BUY", "lot": "0.05", "profit": "10", "result": "WIN",
         "strategy": "SMC", "session": "LONDON", "market_regime": "TRENDING", "exec_grade": "A+",
         "rr_ratio": "2.0", "quality_score": "80", "brain_score": "70"},
        {"date": "2026-01-02", "ticket": "2", "signal": "SELL", "lot": "0.05", "profit": "-8", "result": "LOSS",
         "strategy": "SCALP", "session": "ASIA", "market_regime": "RANGING", "exec_grade": "B",
         "rr_ratio": "1.5", "quality_score": "40", "brain_score": "30"},
        {"date": "2026-01-03", "ticket": "3", "signal": "SELL", "lot": "0.05", "profit": "-5", "result": "LOSS",
         "strategy": "SCALP", "session": "ASIA", "market_regime": "RANGING", "exec_grade": "B",
         "rr_ratio": "1.0", "quality_score": "35", "brain_score": "28"},
        {"date": "2026-01-04", "ticket": "4", "signal": "BUY", "lot": "0.05", "profit": "0", "result": "OPEN",
         "strategy": "SWING", "session": "LONDON", "market_regime": "TRENDING", "exec_grade": "A",
         "rr_ratio": "2.0", "quality_score": "60", "brain_score": "55"},
    ]
    memory_rows = [
        {"date": "2026-01-01", "ticket": "1", "strategy": "SMC", "signal": "BUY", "result": "WIN", "profit": "10",
         "atr": "7.5", "market_regime": "TRENDING", "hour": "10", "spread": "20", "session": "LONDON",
         "quality_score": "80", "confidence_score": "80", "confidence_pct": "80", "exec_grade": "A+",
         "rr_ratio": "2.0", "choch_state": "BOS", "choch_strength": "STRONG", "liq_map_score": "20",
         "liq_map_dir": "UP", "mtf_strength": "3", "mtf_structural": "True", "news_score": "0"},
        {"date": "2026-01-02", "ticket": "2", "strategy": "SCALP", "signal": "SELL", "result": "LOSS", "profit": "-8",
         "atr": "0", "market_regime": "RANGING", "hour": "2", "spread": "15", "session": "ASIA",
         "quality_score": "40", "confidence_score": "40", "confidence_pct": "40", "exec_grade": "B",
         "rr_ratio": "1.5", "choch_state": "", "choch_strength": "", "liq_map_score": "0",
         "liq_map_dir": "", "mtf_strength": "0", "mtf_structural": "", "news_score": "0"},
        {"date": "2026-01-03", "ticket": "3", "strategy": "SCALP", "signal": "SELL", "result": "LOSS", "profit": "-5",
         "atr": "0", "market_regime": "RANGING", "hour": "3", "spread": "15", "session": "ASIA",
         "quality_score": "35", "confidence_score": "35", "confidence_pct": "35", "exec_grade": "B",
         "rr_ratio": "1.0", "choch_state": "", "choch_strength": "", "liq_map_score": "0",
         "liq_map_dir": "", "mtf_strength": "0", "mtf_structural": "", "news_score": "0"},
    ]

    trades_path = history_dir / "trades.csv"
    memory_path = memory_dir / "ai_memory.csv"
    with open(trades_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADES_COLUMNS)
        writer.writeheader()
        writer.writerows(trades_rows)
    with open(memory_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MEMORY_COLUMNS)
        writer.writeheader()
        writer.writerows(memory_rows)

    old_cwd = os.getcwd()
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    monkeypatch.chdir(old_cwd)


def test_load_closed_trades_excludes_open(fixture_project):
    closed = hl.load_closed_trades(limit=10)
    assert len(closed) == 3
    assert all(t["result"] in ("WIN", "LOSS") for t in closed)
    assert not any(t["ticket"] == "4" for t in closed)  # OPEN مستبعدة


def test_compute_history_stats_real_numbers(fixture_project):
    stats = hl.compute_history_stats(limit=10)
    assert stats["sample_size"] == 3
    assert stats["data_source"] == "real_trade_history_csv"
    assert stats["current_losing_streak"] == 2  # آخر صفقتين LOSS متتاليتان
    assert round(stats["win_rate"], 2) == round(1 / 3 * 100.0, 2)


def test_compute_history_stats_with_no_data_is_honest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stats = hl.compute_history_stats(limit=10)
    assert stats["sample_size"] == 0
    assert stats["data_source"] == "no_history_available"
    assert stats["win_rate"] is None


def test_to_evolution_record_treats_zero_atr_as_missing_not_weak(fixture_project):
    records = hl.build_diagnostic_records(limit=10)
    by_ticket = {r["ticket"]: r for r in records}
    evo_with_real_atr = hl.to_evolution_record(by_ticket["1"])
    evo_with_missing_atr = hl.to_evolution_record(by_ticket["2"])
    assert evo_with_real_atr["atr"] == 7.5
    assert evo_with_missing_atr["atr"] is None  # ليس 0.0


def test_to_evolution_record_liquidity_alignment(fixture_project):
    records = hl.build_diagnostic_records(limit=10)
    by_ticket = {r["ticket"]: r for r in records}
    evo = hl.to_evolution_record(by_ticket["1"])
    # BUY + liq_map_dir=UP -> aligned
    assert evo["liquidity_alignment"] is True


def test_build_discovery_batch_derives_features(fixture_project):
    records = hl.build_diagnostic_records(limit=10)
    batch = hl.build_discovery_batch(records)
    by_ticket = {r["trade_id"]: r for r in batch}
    assert "liquidity_sweep" in by_ticket["1"]["features"]
    assert "strong_choch" in by_ticket["1"]["features"]
    assert "mtf_aligned" in by_ticket["1"]["features"]
    assert by_ticket["1"]["success"] == 1.0
    assert by_ticket["2"]["success"] == 0.0

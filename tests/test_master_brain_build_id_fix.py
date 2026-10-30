"""
Regression test for the gap found while auditing the 2026-08-19 BRAIN-SCOPE
patch: core/build_scope.py, brain/history_learner.py, brain/trade_dna.py,
core/confidence_engine.py, core/self_optimizer.py and core/adaptive_weighting.py
were all correctly filtered by build_id -- but main.py's live decision does
not call any of those directly for its master_score. It calls
brain/master_brain.py::get_master_score() (main.py:536), which had its own
separate, unfiltered _load_history_rows() reading trades.csv /
mt5_trade_history.csv raw via csv.DictReader, and computed
dna_score = (history_score + memory_score) / 2 -- never calling the real,
already-filtered get_trade_dna_score() despite importing it. Net effect:
BRAIN-SCOPE's protection was fully built but never reached the live
decision; master_score kept blending every retired build's trades in,
identical to pre-patch behaviour.

Fix: _load_history_rows() now routes both CSV sources through
core.build_scope.filter_current_build_rows(), and dna_score now calls
brain.trade_dna.get_trade_dna_score() for real.
"""
import csv
import json

from core.settings import BUILD_ID


def _write_trades_csv(path, rows):
    fieldnames = [
        "date", "ticket", "signal", "lot", "profit", "result", "strategy",
        "session", "market_regime", "exec_grade", "rr_ratio", "quality_score",
        "brain_score", "build_id",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _trade_row(i, build_id, result, date="2026-08-20T00:00:00+00:00",
                strategy="SMC", session="LONDON", market_regime="RANGING"):
    return {
        "date": date, "ticket": f"T{i}", "signal": "BUY", "lot": 0.01,
        "profit": 10.0 if result == "WIN" else -8.0, "result": result,
        "strategy": strategy, "session": session, "market_regime": market_regime,
        "exec_grade": "A", "rr_ratio": 1.5, "quality_score": 70,
        "brain_score": 60, "build_id": build_id,
    }


def _dna_row(i, build_id, result, strategy="SMC", session="LONDON",
             market_regime="RANGING", timestamp="2026-08-20T00:00:00+00:00"):
    return {
        "timestamp": timestamp, "ticket": f"D{i}", "strategy": strategy,
        "signal": "BUY", "result": result,
        "profit": 12.0 if result == "WIN" else -9.0,
        "market_regime": market_regime, "session": session,
        "quality_score": 75, "confidence_pct": 70, "build_id": build_id,
    }


def _setup_data_dir(tmp_path):
    (tmp_path / "data" / "history").mkdir(parents=True)
    return tmp_path


def test_master_score_history_and_memory_ignore_other_build_ids(tmp_path, monkeypatch):
    monkeypatch.chdir(_setup_data_dir(tmp_path))

    # 20 retired-build SMC/RANGING/LONDON trades, mostly losing -> would
    # read as a poor win rate if blended in (this is what happened before
    # the fix: the same 141 pre-existing rows in the real repo are all
    # tagged with the OLD build_id and would previously leak straight in).
    old_rows = [_trade_row(i, "SOME_OLDER_BUILD", "LOSS" if i % 4 else "WIN")
                for i in range(20)]

    # 9 current-build SMC/RANGING/LONDON trades: 6 wins, 3 losses -> clean
    # 66.67% win rate, clears the min_trades=8 threshold on its own.
    new_rows = [_trade_row(20 + i, BUILD_ID, "WIN" if i < 6 else "LOSS")
                for i in range(9)]

    _write_trades_csv("data/history/trades.csv", old_rows + new_rows)

    import brain.master_brain as mb
    result = mb.get_master_score("SMC", "RANGING", "LONDON")

    assert result["history_score"] == 66.67, (
        f"Expected 66.67 (6/9 current-build wins only), got "
        f"{result['history_score']} -- retired-build rows leaked back in."
    )
    assert result["memory_score"] == 66.67, (
        f"Expected 66.67, got {result['memory_score']} -- retired-build "
        f"rows leaked into recent memory."
    )


def test_master_score_neutral_prior_when_only_other_build_ids_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(_setup_data_dir(tmp_path))

    # Only retired-build data on disk, none from the current build --
    # must fall back to the neutral 50.0 prior, not compute a real number
    # from stale trades.
    old_rows = [_trade_row(i, "SOME_OLDER_BUILD", "LOSS") for i in range(20)]
    _write_trades_csv("data/history/trades.csv", old_rows)

    import brain.master_brain as mb
    result = mb.get_master_score("SMC", "RANGING", "LONDON")

    assert result["history_score"] == 50.0
    assert result["memory_score"] == 50.0


def test_master_score_dna_calls_real_scorer_not_history_memory_average(tmp_path, monkeypatch):
    monkeypatch.chdir(_setup_data_dir(tmp_path))

    # history/memory data: current build, clean 100% win rate.
    new_rows = [_trade_row(i, BUILD_ID, "WIN") for i in range(9)]
    _write_trades_csv("data/history/trades.csv", new_rows)

    # DNA data: current build, deliberately different and worse (2 wins /
    # 4 losses) so it cannot coincidentally match (history+memory)/2.
    dna_rows = [_dna_row(i, BUILD_ID, "WIN" if i < 2 else "LOSS") for i in range(6)]
    with open("data/trade_dna_v2.json", "w", encoding="utf-8") as f:
        json.dump(dna_rows, f)

    import brain.master_brain as mb
    result = mb.get_master_score("SMC", "RANGING", "LONDON")

    fake_average = round((result["history_score"] + result["memory_score"]) / 2.0, 2)
    assert result["dna_score"] != fake_average, (
        "dna_score matches the old (history_score + memory_score) / 2 "
        "placeholder -- get_trade_dna_score() is not actually being called."
    )
    # history/memory are a clean 100% WIN; the DNA sample is mostly losing,
    # so a real DNA score here must land below the neutral 25.0/45.0 no-data
    # band's ceiling and well under history/memory -- confirms the DNA
    # pattern-matcher's own (worse) data is what drove the number.
    assert result["dna_score"] < 50.0, (
        f"Expected a real, DNA-driven score reflecting the mostly-losing "
        f"synthetic DNA sample, got {result['dna_score']}."
    )


def test_master_score_dna_neutral_prior_with_zero_current_build_matches(tmp_path, monkeypatch):
    monkeypatch.chdir(_setup_data_dir(tmp_path))

    # Retired-build DNA data only -- must not be used at all.
    dna_rows = [_dna_row(i, "SOME_OLDER_BUILD", "WIN") for i in range(10)]
    with open("data/trade_dna_v2.json", "w", encoding="utf-8") as f:
        json.dump(dna_rows, f)

    import brain.master_brain as mb
    result = mb.get_master_score("SMC", "RANGING", "LONDON")

    assert result["dna_score"] == 25.0, (
        f"Expected the neutral no-current-build-data prior (25.0), got "
        f"{result['dna_score']} -- retired-build DNA rows leaked in."
    )

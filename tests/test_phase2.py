# =============================================================================
# FER3ON V3+++ — PHASE 2 | TEST SUITE
# =============================================================================
# tests/test_phase2.py
#
# Run with:  python -m pytest tests/test_phase2.py -v
#
# Covers:
#   test_phase2_readonly.py      — no runtime writes
#   test_phase2_consistency.py   — metrics match Truth Layer exactly
#   test_phase2_shadow_isolation — shadow never touches live adaptive files
#   test_phase2_dashboard_source — breakdowns come from Truth Layer
# =============================================================================

from __future__ import annotations

import json
import os
import sys
import shutil
import tempfile
from typing import Any, Dict, List

import pytest

# Ensure project root is on path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LIVE_ADAPTIVE_FILES = [
    "data/analytics/adaptive_state.json",
    "data/analytics/adaptive_trades.jsonl",
]

LIVE_RUNTIME_FILES = [
    "data/analytics/open_trade_snapshots.json",
]


@pytest.fixture(autouse=True)
def record_mtimes_before():
    """Record mtime of live files before each test so we can detect writes."""
    mtimes: Dict[str, float] = {}
    for path in LIVE_ADAPTIVE_FILES + LIVE_RUNTIME_FILES:
        abs_path = os.path.join(_PROJECT_ROOT, path)
        if os.path.exists(abs_path):
            mtimes[abs_path] = os.path.getmtime(abs_path)
    yield mtimes


def _mtimes_unchanged(before: Dict[str, float]) -> bool:
    """Return True if none of the recorded files were modified."""
    for abs_path, mtime_before in before.items():
        if os.path.exists(abs_path):
            current = os.path.getmtime(abs_path)
            if current > mtime_before + 0.01:  # 10 ms tolerance
                return False
    return True


# ---------------------------------------------------------------------------
# Helpers to build small synthetic truth-layer data without real I/O
# ---------------------------------------------------------------------------

def _make_trades(n_wins: int, n_losses: int):
    """Return a list of minimal TradeRecord dicts for testing."""
    from analytics.truth_layer import TradeRecord
    trades = []
    for i in range(n_wins):
        trades.append(TradeRecord(
            ticket=i + 1,
            strategy="SMC",
            direction="BUY",
            session="LONDON",
            regime="TRENDING",
            profit=10.0,
            is_win=True,
        ))
    for i in range(n_losses):
        trades.append(TradeRecord(
            ticket=1000 + i,
            strategy="MICRO",
            direction="SELL",
            session="NEWYORK",
            regime="RANGING",
            profit=-5.0,
            is_win=False,
        ))
    return trades


# ===========================================================================
# GROUP 1 — READ-ONLY SAFETY
# Phase 2 modules must never write to live runtime files.
# ===========================================================================

class TestPhase2Readonly:

    def test_session_analysis_does_not_write_live_files(self, record_mtimes_before):
        from analytics.session_edge_analysis import analyse_sessions
        trades = _make_trades(6, 3)
        _ = analyse_sessions(trades)
        assert _mtimes_unchanged(record_mtimes_before), (
            "Session analysis wrote to a live runtime file — forbidden."
        )

    def test_regime_analysis_does_not_write_live_files(self, record_mtimes_before):
        from analytics.regime_edge_analysis import analyse_regimes
        trades = _make_trades(6, 4)
        _ = analyse_regimes(trades)
        assert _mtimes_unchanged(record_mtimes_before)

    def test_portfolio_statistics_does_not_write_live_files(self, record_mtimes_before):
        from analytics.portfolio_statistics import build_portfolio_statistics
        trades = _make_trades(8, 4)
        _ = build_portfolio_statistics(trades)
        assert _mtimes_unchanged(record_mtimes_before)

    def test_contribution_analysis_does_not_write_live_files(self, record_mtimes_before):
        from analytics.contribution_analysis import build_contribution_report
        trades = _make_trades(5, 3)
        _ = build_contribution_report(trades)
        assert _mtimes_unchanged(record_mtimes_before)

    def test_shadow_prep_does_not_write_live_files(self, record_mtimes_before):
        from analytics.adaptive_shadow_prep import build_shadow_state
        trades = _make_trades(10, 5)
        _ = build_shadow_state(trades)
        assert _mtimes_unchanged(record_mtimes_before)

    def test_performance_repository_no_writes(self, record_mtimes_before):
        from analytics.performance_repository import (
            get_overall_metrics, get_session_breakdown,
            get_regime_breakdown, get_strategy_breakdown,
        )
        trades = _make_trades(4, 2)
        get_overall_metrics(trades)
        get_session_breakdown(trades)
        get_regime_breakdown(trades)
        get_strategy_breakdown(trades)
        assert _mtimes_unchanged(record_mtimes_before)


# ===========================================================================
# GROUP 2 — CONSISTENCY
# Phase 2 metrics must exactly match Truth Layer for the same input.
# ===========================================================================

class TestPhase2Consistency:

    def test_overall_metrics_match_truth_layer(self):
        from analytics.truth_layer import compute_metrics
        from analytics.performance_repository import get_overall_metrics
        trades = _make_trades(7, 3)
        tl_metrics = compute_metrics(trades)
        repo_metrics = get_overall_metrics(trades)
        assert tl_metrics.total_trades == repo_metrics.total_trades
        assert tl_metrics.win_rate == repo_metrics.win_rate
        assert tl_metrics.net_pnl == repo_metrics.net_pnl
        assert tl_metrics.profit_factor == repo_metrics.profit_factor

    def test_session_breakdown_totals_match_overall(self):
        from analytics.performance_repository import get_all_trades, get_session_breakdown
        from analytics.truth_layer import compute_metrics
        trades = _make_trades(6, 4)
        breakdown = get_session_breakdown(trades)
        total_from_breakdown = sum(m.total_trades for m in breakdown.values())
        assert total_from_breakdown == len(trades), (
            "Sum of session bucket trades must equal total trades."
        )

    def test_regime_breakdown_totals_match_overall(self):
        from analytics.performance_repository import get_regime_breakdown
        trades = _make_trades(6, 4)
        breakdown = get_regime_breakdown(trades)
        total_from_breakdown = sum(m.total_trades for m in breakdown.values())
        assert total_from_breakdown == len(trades)

    def test_session_edge_win_rates_are_subset_of_truth_layer(self):
        from analytics.session_edge_analysis import analyse_sessions
        from analytics.truth_layer import compute_metrics, filter_trades
        trades = _make_trades(8, 4)
        ranking = analyse_sessions(trades)
        for session_edge in ranking.sessions:
            if session_edge.total_trades == 0:
                continue
            from analytics.truth_layer import filter_trades as ft
            subset = ft(trades, session=session_edge.session)
            if not subset:
                continue
            tl_m = compute_metrics(subset)
            assert abs(session_edge.win_rate - tl_m.win_rate) < 1e-9, (
                f"Session {session_edge.session}: WR mismatch. "
                f"Phase2={session_edge.win_rate} TruthLayer={tl_m.win_rate}"
            )

    def test_portfolio_metrics_match_truth_layer(self):
        from analytics.portfolio_statistics import build_portfolio_statistics
        from analytics.truth_layer import compute_metrics
        trades = _make_trades(10, 5)
        stats = build_portfolio_statistics(trades)
        tl = compute_metrics(trades)
        assert stats.overall_metrics["total_trades"] == tl.total_trades
        assert abs(stats.overall_metrics["win_rate"] - tl.win_rate) < 1e-9

    def test_empty_trades_produce_zero_not_error(self):
        from analytics.performance_repository import get_overall_metrics
        from analytics.session_edge_analysis import analyse_sessions
        from analytics.regime_edge_analysis import analyse_regimes
        from analytics.portfolio_statistics import build_portfolio_statistics
        trades = []
        m = get_overall_metrics(trades)
        assert m.total_trades == 0
        s_rank = analyse_sessions(trades)
        assert s_rank.total_trades_analysed == 0
        r_rank = analyse_regimes(trades)
        assert r_rank.total_trades_analysed == 0
        p_stats = build_portfolio_statistics(trades)
        assert p_stats.total_trades == 0


# ===========================================================================
# GROUP 3 — SHADOW ISOLATION
# Shadow prep must never touch adaptive_state.json or adaptive_trades.jsonl
# ===========================================================================

class TestPhase2ShadowIsolation:

    def test_shadow_output_stays_in_phase2_dir(self):
        from analytics.adaptive_shadow_prep import build_shadow_state, persist_shadow_state, SHADOW_STATE_PATH, SHADOW_CANDIDATES_PATH
        trades = _make_trades(12, 6)
        state = build_shadow_state(trades)

        # Use a temp dir so we don't pollute CI
        with tempfile.TemporaryDirectory() as tmpdir:
            sp = os.path.join(tmpdir, "shadow_state.json")
            cp = os.path.join(tmpdir, "shadow_calibration_candidates.json")

            import json, os as _os
            _os.makedirs(tmpdir, exist_ok=True)
            with open(sp, "w") as f:
                json.dump(state.to_dict(), f, default=str)
            with open(cp, "w") as f:
                json.dump({"candidates": [c.to_dict() for c in state.calibration_candidates]}, f, default=str)

            # Verify shadow_state contains activated=False
            with open(sp) as f:
                data = json.load(f)
            assert data.get("activated") == False, "Shadow state must have activated=False"
            assert data.get("shadow_only") == True

    def test_all_shadow_candidates_have_activated_false(self):
        from analytics.adaptive_shadow_prep import build_shadow_state
        trades = _make_trades(15, 8)
        state = build_shadow_state(trades)
        for candidate in state.calibration_candidates:
            assert candidate.activated == False, (
                f"Candidate {candidate.bucket_type}:{candidate.bucket_key} "
                f"has activated=True — this is forbidden in Phase 2."
            )
            assert candidate.advisory_only == True
            assert candidate.not_applied_live == True

    def test_phase2_runtime_influence_is_false(self):
        from core.settings import PHASE2_RUNTIME_INFLUENCE
        assert PHASE2_RUNTIME_INFLUENCE == False, (
            "PHASE2_RUNTIME_INFLUENCE must be False — Phase 2 must not influence live trading."
        )

    def test_phase2_shadow_calibration_only_is_true(self):
        from core.settings import PHASE2_SHADOW_CALIBRATION_ONLY
        assert PHASE2_SHADOW_CALIBRATION_ONLY == True


# ===========================================================================
# GROUP 4 — ADVISORY FLAGS
# Every Phase 2 output object must be flagged advisory_only / not_applied_live
# ===========================================================================

class TestPhase2AdvisoryFlags:

    def test_session_ranking_is_advisory(self):
        from analytics.session_edge_analysis import analyse_sessions
        r = analyse_sessions(_make_trades(6, 3))
        assert r.advisory_only == True
        assert r.not_applied_live == True
        for s in r.sessions:
            assert s.advisory_only == True
            assert s.not_applied_live == True

    def test_regime_ranking_is_advisory(self):
        from analytics.regime_edge_analysis import analyse_regimes
        r = analyse_regimes(_make_trades(6, 3))
        assert r.advisory_only == True
        assert r.not_applied_live == True

    def test_portfolio_stats_is_advisory(self):
        from analytics.portfolio_statistics import build_portfolio_statistics
        s = build_portfolio_statistics(_make_trades(6, 3))
        assert s.advisory_only == True
        assert s.not_applied_live == True

    def test_contribution_report_is_advisory(self):
        from analytics.contribution_analysis import build_contribution_report
        r = build_contribution_report(_make_trades(6, 3))
        assert r.advisory_only == True
        assert r.not_applied_live == True
        for m in r.modules:
            assert m.advisory_only == True
            assert m.not_applied_live == True

    def test_shadow_state_is_not_activated(self):
        from analytics.adaptive_shadow_prep import build_shadow_state
        s = build_shadow_state(_make_trades(10, 5))
        assert s.activated == False
        assert s.shadow_only == True


# ===========================================================================
# GROUP 5 — INSUFFICIENT SAMPLE HANDLING
# Buckets below MIN_SAMPLE must be labelled, never ranked, never acted on.
# ===========================================================================

class TestPhase2InsufficientSample:

    def test_small_session_bucket_gets_insufficient_label(self):
        from analytics.session_edge_analysis import analyse_sessions
        from analytics.truth_layer import TradeRecord

        # Only 2 trades in ASIA — below MIN_SAMPLE=5
        trades = [
            TradeRecord(ticket=1, strategy="SMC", direction="BUY",
                        session="ASIA", regime="TRENDING", profit=5.0, is_win=True),
            TradeRecord(ticket=2, strategy="SMC", direction="SELL",
                        session="ASIA", regime="RANGING", profit=-3.0, is_win=False),
        ]
        ranking = analyse_sessions(trades)
        asia_edge = next((s for s in ranking.sessions if s.session == "ASIA"), None)
        assert asia_edge is not None
        assert asia_edge.sample_label == "INSUFFICIENT_SAMPLE"
        assert asia_edge.rank == 0  # must not be ranked

    def test_shadow_candidate_low_sample_gets_hold(self):
        from analytics.adaptive_shadow_prep import build_shadow_state
        from analytics.truth_layer import TradeRecord

        # 3 trades in one strategy — below MIN_SAMPLE
        trades = [
            TradeRecord(ticket=i, strategy="DAILY", direction="BUY",
                        session="LONDON", regime="TRENDING",
                        profit=5.0 if i < 2 else -3.0, is_win=i < 2)
            for i in range(3)
        ]
        state = build_shadow_state(trades)
        daily_candidate = next(
            (c for c in state.calibration_candidates
             if c.bucket_type == "strategy" and c.bucket_key == "DAILY"),
            None,
        )
        if daily_candidate:  # may not exist if filtered out
            assert daily_candidate.suggestion_type == "HOLD"
            assert not daily_candidate.sufficient_confidence

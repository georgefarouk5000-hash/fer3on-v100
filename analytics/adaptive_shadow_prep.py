# =============================================================================
# FER3ON V3+++ — PHASE 2 | ADAPTIVE SHADOW PREPARATION
# =============================================================================
# Builds the shadow calibration infrastructure:
#   Memory → Analytics → Calibration Suggestions
#
# This module runs entirely in SHADOW mode.
# It NEVER activates any suggestion or modifies any live threshold.
#
# SAFETY CONTRACT:
#   ✅ Reads from Truth Layer only
#   ✅ NO writes to core/adaptive_learning.py state
#   ✅ NO writes to adaptive_state.json / adaptive_trades.jsonl
#   ✅ NO calls to tune_thresholds() or record_trade_outcome()
#   ✅ Outputs only to data/analytics/phase2/shadow/
#   ✅ All calibration candidates are flagged: activated=False
# =============================================================================

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from analytics.performance_repository import (
    get_all_trades,
    get_session_breakdown,
    get_regime_breakdown,
    get_strategy_breakdown,
    group_trades_by,
)
from analytics.truth_layer import TradeRecord, compute_metrics
from core.settings import (
    PHASE2_SHADOW_DIR,
    PHASE2_MIN_SAMPLE_PER_BUCKET,
    PHASE2_SHADOW_CALIBRATION_ONLY,
    PHASE2_RUNTIME_INFLUENCE,
    ADAPTIVE_MIN_TRADES_TO_TUNE,
)

# Enforce shadow isolation on import
assert PHASE2_SHADOW_CALIBRATION_ONLY, (
    "PHASE2_SHADOW_CALIBRATION_ONLY must be True. Shadow prep must not activate."
)
assert not PHASE2_RUNTIME_INFLUENCE, (
    "PHASE2_RUNTIME_INFLUENCE must be False. Shadow prep has no live influence."
)

# Minimum trades per bucket before we form a calibration candidate
MIN_SAMPLE = max(PHASE2_MIN_SAMPLE_PER_BUCKET, ADAPTIVE_MIN_TRADES_TO_TUNE)

SHADOW_STATE_PATH = os.path.join(PHASE2_SHADOW_DIR, "shadow_state.json")
SHADOW_CANDIDATES_PATH = os.path.join(PHASE2_SHADOW_DIR, "shadow_calibration_candidates.json")


# =============================================================================
# SHADOW METRICS PER BUCKET
# =============================================================================

@dataclass
class ShadowBucketMetrics:
    bucket_type: str        # "strategy" / "session" / "regime"
    bucket_key: str         # e.g. "SMC", "LONDON", "TRENDING"
    total_trades: int
    win_rate: float
    expectancy: float
    profit_factor: Optional[float]
    max_drawdown: float
    avg_confidence: float
    avg_quality_score: float
    sufficient_sample: bool
    sample_label: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _avg_field(trades: List[TradeRecord], attr: str) -> float:
    vals = [getattr(t, attr, 0.0) or 0.0 for t in trades]
    vals = [v for v in vals if v]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def _build_shadow_bucket(
    bucket_type: str,
    bucket_key: str,
    trades: List[TradeRecord],
) -> ShadowBucketMetrics:
    m = compute_metrics(trades)
    pf = m.profit_factor if m.profit_factor != float("inf") else None
    n = m.total_trades
    sufficient = n >= MIN_SAMPLE
    return ShadowBucketMetrics(
        bucket_type=bucket_type,
        bucket_key=bucket_key,
        total_trades=n,
        win_rate=m.win_rate,
        expectancy=m.expectancy,
        profit_factor=pf,
        max_drawdown=m.max_drawdown,
        avg_confidence=_avg_field(trades, "confidence"),
        avg_quality_score=_avg_field(trades, "quality_score"),
        sufficient_sample=sufficient,
        sample_label="OK" if sufficient else "INSUFFICIENT_SAMPLE",
    )


# =============================================================================
# CALIBRATION CANDIDATES
# =============================================================================

@dataclass
class CalibrationCandidate:
    """
    Suggested calibration for a bucket.
    activated=False always — these are suggestions for human review only.
    """
    bucket_type: str
    bucket_key: str
    current_win_rate: float
    observed_win_rate: float
    current_expectancy: float
    observed_expectancy: float
    suggestion_type: str     # "TIGHTEN" / "RELAX" / "MONITOR" / "HOLD"
    suggestion_note: str
    confidence_interval_wr: Optional[float]   # ±95% CI on win rate
    sample_size: int
    sufficient_confidence: bool
    activated: bool = False               # MUST remain False in Phase 2
    advisory_only: bool = True
    not_applied_live: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval half-width for win rate confidence."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    spread = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return round(spread, 4)


def _make_candidate(bucket: ShadowBucketMetrics, trades: List[TradeRecord]) -> CalibrationCandidate:
    wins = sum(1 for t in trades if t.profit > 0)
    ci = _wilson_ci(wins, bucket.total_trades)

    wr_observed = bucket.win_rate
    # Reference baseline: overall 50% WR (no prior — conservative)
    wr_baseline = 0.50

    if not bucket.sufficient_sample:
        suggestion = "HOLD"
        note = f"Insufficient sample ({bucket.total_trades} < {MIN_SAMPLE}). Observe more trades."
    elif wr_observed >= 0.60 and bucket.expectancy > 1.0:
        suggestion = "MONITOR"
        note = f"Strong edge detected (WR={wr_observed:.1%}, Exp={bucket.expectancy:.2f}). Monitor for stability."
    elif wr_observed <= 0.35 or bucket.expectancy < -1.0:
        suggestion = "TIGHTEN"
        note = f"Weak edge (WR={wr_observed:.1%}, Exp={bucket.expectancy:.2f}). Quality floor may need raising."
    elif wr_observed >= 0.55:
        suggestion = "RELAX"
        note = f"Good edge (WR={wr_observed:.1%}). Filters may be over-restrictive in this bucket."
    else:
        suggestion = "HOLD"
        note = f"Edge is within normal range (WR={wr_observed:.1%}). No calibration warranted."

    return CalibrationCandidate(
        bucket_type=bucket.bucket_type,
        bucket_key=bucket.bucket_key,
        current_win_rate=wr_baseline,
        observed_win_rate=wr_observed,
        current_expectancy=0.0,
        observed_expectancy=bucket.expectancy,
        suggestion_type=suggestion,
        suggestion_note=note,
        confidence_interval_wr=ci,
        sample_size=bucket.total_trades,
        sufficient_confidence=bucket.sufficient_sample and ci < 0.10,
        activated=False,
    )


# =============================================================================
# SHADOW STATE BUILD
# =============================================================================

@dataclass
class ShadowState:
    generated_at: str
    total_trades: int
    strategy_buckets: List[ShadowBucketMetrics]
    session_buckets: List[ShadowBucketMetrics]
    regime_buckets: List[ShadowBucketMetrics]
    calibration_candidates: List[CalibrationCandidate]
    shadow_only: bool = True
    activated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "total_trades": self.total_trades,
            "shadow_only": self.shadow_only,
            "activated": self.activated,
            "strategy_buckets": [b.to_dict() for b in self.strategy_buckets],
            "session_buckets": [b.to_dict() for b in self.session_buckets],
            "regime_buckets": [b.to_dict() for b in self.regime_buckets],
            "calibration_candidates": [c.to_dict() for c in self.calibration_candidates],
        }


def build_shadow_state(trades=None) -> ShadowState:
    if trades is None:
        trades = get_all_trades()

    strategy_groups = group_trades_by(trades, "strategy")
    session_groups  = group_trades_by(trades, "session")
    regime_groups   = group_trades_by(trades, "regime")

    strategy_buckets = [
        _build_shadow_bucket("strategy", k, v)
        for k, v in sorted(strategy_groups.items())
    ]
    session_buckets = [
        _build_shadow_bucket("session", k, v)
        for k, v in sorted(session_groups.items())
    ]
    regime_buckets = [
        _build_shadow_bucket("regime", k, v)
        for k, v in sorted(regime_groups.items())
    ]

    all_buckets = strategy_buckets + session_buckets + regime_buckets
    all_trade_groups = {
        **{f"strategy:{k}": v for k, v in strategy_groups.items()},
        **{f"session:{k}": v for k, v in session_groups.items()},
        **{f"regime:{k}": v for k, v in regime_groups.items()},
    }

    candidates: List[CalibrationCandidate] = []
    for bucket in all_buckets:
        key = f"{bucket.bucket_type}:{bucket.bucket_key}"
        bucket_trades = all_trade_groups.get(key, [])
        candidates.append(_make_candidate(bucket, bucket_trades))

    return ShadowState(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_trades=len(trades),
        strategy_buckets=strategy_buckets,
        session_buckets=session_buckets,
        regime_buckets=regime_buckets,
        calibration_candidates=candidates,
    )


# =============================================================================
# PERSIST — shadow dir ONLY, never touches adaptive_state.json
# =============================================================================

def persist_shadow_state(state: Optional[ShadowState] = None) -> Tuple[str, str]:
    if state is None:
        state = build_shadow_state()
    os.makedirs(PHASE2_SHADOW_DIR, exist_ok=True)

    # Full state
    with open(SHADOW_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False, default=str)

    # Calibration candidates only (for easier review)
    candidates_data = {
        "generated_at": state.generated_at,
        "total_trades": state.total_trades,
        "activated": False,
        "advisory_only": True,
        "not_applied_live": True,
        "candidates": [c.to_dict() for c in state.calibration_candidates],
    }
    with open(SHADOW_CANDIDATES_PATH, "w", encoding="utf-8") as f:
        json.dump(candidates_data, f, indent=2, ensure_ascii=False, default=str)

    return SHADOW_STATE_PATH, SHADOW_CANDIDATES_PATH


# Needed for return type annotation
from typing import Tuple


# =============================================================================
# CLI
# =============================================================================

def print_shadow_summary(state: Optional[ShadowState] = None) -> None:
    if state is None:
        state = build_shadow_state()
    print(f"\n{'='*65}")
    print(f"ADAPTIVE SHADOW STATE  [{state.generated_at[:19]}]")
    print(f"shadow_only=True  activated=False  not_applied_live=True")
    print(f"Total trades: {state.total_trades}")
    print(f"{'='*65}")
    print(f"\n  CALIBRATION CANDIDATES:")
    for c in state.calibration_candidates:
        flag = " ✓" if c.sufficient_confidence else " ?"
        print(
            f"  {c.bucket_type:<10} {c.bucket_key:<20} "
            f"WR={c.observed_win_rate:.1%}  "
            f"Exp={c.observed_expectancy:+.2f}  "
            f"→ {c.suggestion_type:<8}  {flag}  [{c.suggestion_note[:50]}]"
        )
    print()


if __name__ == "__main__":
    state = build_shadow_state()
    print_shadow_summary(state)
    sp, cp = persist_shadow_state(state)
    print(f"Shadow state saved  → {sp}")
    print(f"Candidates saved    → {cp}")

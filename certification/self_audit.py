# =============================================================================
# FAIE — Self Audit (Phase-2 spec §4 / Volume 9)
# =============================================================================
# فلسفة:
#   هذا الموديول لا يُغيّر أي قرار — هو مراجعة دورية *بأثر رجعي* على قرارات
#   FAIE المُسجَّلة فعلاً (عبر brain/faie/shadow_logging.py أو
#   testing/faie_backtest.py)، تسأل "لماذا" لا فقط "ماذا": هل القرار منحاز
#   لاتجاه واحد دون سبب حقيقي في الأدلة نفسها؟ هل سلوك أحد المحللين تغيّر
#   بشكل كبير بين فترتين؟ هل الأداء داخل العيّنة أفضل بشكل مريب من خارجها؟
#
#   قاعدة فشل صريحة (من الوثيقة): تاريخ غير كافٍ (< حد أدنى من القرارات) —
#   تقرير status=INSUFFICIENT_DATA، وليس استنتاجًا واثقًا زائفًا. هذا الموديول
#   لن "يتظاهر" بامتلاك رأي حين لا تتوفر بيانات كافية لتكوين رأي حقيقي.
# =============================================================================

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHADOW_LOG = PROJECT_ROOT / "data" / "faie" / "shadow_log.jsonl"
SELF_AUDIT_DIR = PROJECT_ROOT / "data" / "analytics"

MIN_DECISIONS_FOR_BIAS = 20
MIN_DECISIONS_FOR_DRIFT = 10  # per window
DIRECTION_SKEW_THRESHOLD = 0.70       # >=70% of decisions leaning one way
NET_SCORE_BALANCE_THRESHOLD = 0.60    # <60% same-sign net_score = "balanced"
ANALYST_DRIFT_THRESHOLD = 25.0        # net_score points (scale is -100..100)
ANALYST_PARTIAL_RATE_DRIFT_THRESHOLD = 0.30  # 30 percentage points
OVERFIT_DEGRADE_THRESHOLD = 0.20      # 20% relative degradation, higher-is-better metrics


DecisionLike = Union[Dict[str, Any], Any]


def _as_dict(decision: DecisionLike) -> Dict[str, Any]:
    """Accept either a real brain.faie.chief_decision_officer.Decision
    object (has .to_dict()) or an already-serialized dict (e.g. read back
    from shadow_log.jsonl / a backtest run) — the audit only ever needs the
    to_dict() summary shape, never the live object graph."""
    if hasattr(decision, "to_dict"):
        return decision.to_dict()
    return decision or {}


def _sign(value: float, zero_band: float = 6.0) -> str:
    # Mirrors EvidenceFusionEngine's own +/-6 neutral band (brain/faie/fusion.py)
    # so "balanced" here means the same thing fusion.py already means by it.
    if value > zero_band:
        return "POSITIVE"
    if value < -zero_band:
        return "NEGATIVE"
    return "NEAR_ZERO"


# -----------------------------------------------------------------------
# Loading accumulated decision history
# -----------------------------------------------------------------------

def load_shadow_log_decisions(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read brain/faie/shadow_logging.py's JSONL output back into a list of
    Decision.to_dict()-shaped dicts, in the order they were logged
    (chronological, since the logger only ever appends).

    Never raises: a missing file or a malformed line is skipped, not fatal
    to reading the rest of the log.
    """
    p = Path(path) if path else DEFAULT_SHADOW_LOG
    if not p.exists():
        return []
    decisions: List[Dict[str, Any]] = []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fd = row.get("faie_decision")
                if isinstance(fd, dict):
                    decisions.append(fd)
    except Exception:
        return decisions
    return decisions


def split_recent_vs_baseline(
    decisions: List[Dict[str, Any]], recent_fraction: float = 0.5
) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
    """Chronological split assuming `decisions` is already in time order
    (true for load_shadow_log_decisions' output). Returns (baseline, recent)
    — baseline = older portion, recent = newer portion."""
    n = len(decisions)
    if n == 0:
        return [], []
    split_at = max(0, n - int(round(n * recent_fraction)))
    return decisions[:split_at], decisions[split_at:]


# -----------------------------------------------------------------------
# §4a — Bias detection
# -----------------------------------------------------------------------

@dataclass
class BiasReport:
    status: str = "INSUFFICIENT_DATA"
    sample_size: int = 0
    direction_counts: Dict[str, int] = field(default_factory=dict)
    dominant_direction: str = "NONE"
    dominant_direction_share: float = 0.0
    net_score_sign_counts: Dict[str, int] = field(default_factory=dict)
    net_score_dominant_sign_share: float = 0.0
    flagged: bool = False
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "sample_size": self.sample_size,
            "direction_counts": dict(self.direction_counts),
            "dominant_direction": self.dominant_direction,
            "dominant_direction_share": round(self.dominant_direction_share, 4),
            "net_score_sign_counts": dict(self.net_score_sign_counts),
            "net_score_dominant_sign_share": round(self.net_score_dominant_sign_share, 4),
            "flagged": self.flagged,
            "note": self.note,
        }


def detect_bias(
    decisions: List[DecisionLike],
    *,
    min_sample: int = MIN_DECISIONS_FOR_BIAS,
    skew_threshold: float = DIRECTION_SKEW_THRESHOLD,
    balance_threshold: float = NET_SCORE_BALANCE_THRESHOLD,
) -> BiasReport:
    """Flag a scenario-engine bias signature: top_scenario.direction skewed
    heavily toward one side while fused_evidence.net_score's sign is roughly
    balanced across the same window. That combination — decision consistently
    favoring one direction even when the underlying evidence isn't — points
    at a bug in ScenarioEngine/ChiefDecisionOfficer, not a real market trend
    (a real trend would skew net_score's sign the same way).
    """
    dicts = [_as_dict(d) for d in decisions]
    n = len(dicts)
    if n < min_sample:
        return BiasReport(
            status="INSUFFICIENT_DATA",
            sample_size=n,
            note=f"need >= {min_sample} decisions, have {n}",
        )

    direction_counts = Counter(
        (d.get("top_scenario") or {}).get("direction", "UNKNOWN") for d in dicts
    )
    net_signs = Counter(
        _sign(float((d.get("fused_evidence") or {}).get("net_score", 0.0) or 0.0)) for d in dicts
    )

    dominant_direction, dominant_count = direction_counts.most_common(1)[0]
    direction_share = dominant_count / n

    net_dominant_sign, net_dominant_count = net_signs.most_common(1)[0]
    net_share = net_dominant_count / n

    flagged = direction_share >= skew_threshold and net_share < balance_threshold

    note = (
        f"top_scenario direction '{dominant_direction}' in {direction_share*100:.1f}% of "
        f"{n} decisions, while fused net_score sign is only {net_share*100:.1f}% "
        f"'{net_dominant_sign}' over the same window."
    )
    if flagged:
        note += " FLAGGED: decision skew not matched by evidence skew — check ScenarioEngine."

    return BiasReport(
        status="OK",
        sample_size=n,
        direction_counts=dict(direction_counts),
        dominant_direction=dominant_direction,
        dominant_direction_share=direction_share,
        net_score_sign_counts=dict(net_signs),
        net_score_dominant_sign_share=net_share,
        flagged=flagged,
        note=note,
    )


# -----------------------------------------------------------------------
# §4b — Drift detection
# -----------------------------------------------------------------------

@dataclass
class DriftReport:
    status: str = "INSUFFICIENT_DATA"
    baseline_sample_size: int = 0
    recent_sample_size: int = 0
    per_analyst_drift: List[Dict[str, Any]] = field(default_factory=list)
    flagged_analysts: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "baseline_sample_size": self.baseline_sample_size,
            "recent_sample_size": self.recent_sample_size,
            "per_analyst_drift": self.per_analyst_drift,
            "flagged_analysts": self.flagged_analysts,
            "note": self.note,
        }


def _analyst_net_scores(dicts: List[Dict[str, Any]], analyst: str) -> List[float]:
    scores = []
    for d in dicts:
        per_analyst = (d.get("fused_evidence") or {}).get("per_analyst") or {}
        if analyst in per_analyst:
            try:
                scores.append(float(per_analyst[analyst]))
            except (TypeError, ValueError):
                continue
    return scores


def _analyst_partial_rate(dicts: List[Dict[str, Any]], analyst: str) -> Optional[float]:
    if not dicts:
        return None
    partial_count = 0
    seen = 0
    for d in dicts:
        fe = d.get("fused_evidence") or {}
        per_analyst = fe.get("per_analyst") or {}
        if analyst not in per_analyst:
            continue  # analyst didn't run at all for this decision — not comparable
        seen += 1
        if analyst in (fe.get("partial_analysts") or []):
            partial_count += 1
    if seen == 0:
        return None
    return partial_count / seen


def detect_drift(
    recent_reports: List[DecisionLike],
    baseline_reports: List[DecisionLike],
    *,
    min_sample: int = MIN_DECISIONS_FOR_DRIFT,
    drift_threshold: float = ANALYST_DRIFT_THRESHOLD,
    partial_rate_drift_threshold: float = ANALYST_PARTIAL_RATE_DRIFT_THRESHOLD,
) -> DriftReport:
    """Compare per-analyst net_score behavior between an older ("baseline")
    and newer ("recent") window of decisions. Two independent signals, each
    computed only where both windows actually have data for that analyst
    (never fabricated for a missing analyst):

      1. Mean net_score shift beyond `drift_threshold` points — possible
         regime change, or the analyst's read of the market genuinely
         changed (this alone doesn't prove a bug — it's a flag to look at).
      2. A large jump in how often the analyst reports "partial" (i.e. ran
         but couldn't produce full evidence) — a classic signature of a
         broken analyst that silently defaulted to NEUTRAL instead of
         actually failing.
    """
    recent = [_as_dict(d) for d in recent_reports]
    baseline = [_as_dict(d) for d in baseline_reports]

    if len(recent) < min_sample or len(baseline) < min_sample:
        return DriftReport(
            status="INSUFFICIENT_DATA",
            baseline_sample_size=len(baseline),
            recent_sample_size=len(recent),
            note=f"need >= {min_sample} decisions in each window "
                 f"(have baseline={len(baseline)}, recent={len(recent)})",
        )

    analysts = set()
    for d in recent + baseline:
        analysts.update(((d.get("fused_evidence") or {}).get("per_analyst") or {}).keys())

    per_analyst_drift = []
    flagged_analysts = []
    for analyst in sorted(analysts):
        baseline_scores = _analyst_net_scores(baseline, analyst)
        recent_scores = _analyst_net_scores(recent, analyst)
        if not baseline_scores or not recent_scores:
            continue  # not comparable — skip, don't fabricate

        baseline_mean = sum(baseline_scores) / len(baseline_scores)
        recent_mean = sum(recent_scores) / len(recent_scores)
        delta = recent_mean - baseline_mean

        baseline_partial_rate = _analyst_partial_rate(baseline, analyst)
        recent_partial_rate = _analyst_partial_rate(recent, analyst)
        partial_rate_delta = None
        if baseline_partial_rate is not None and recent_partial_rate is not None:
            partial_rate_delta = recent_partial_rate - baseline_partial_rate

        score_flagged = abs(delta) >= drift_threshold
        partial_flagged = (
            partial_rate_delta is not None
            and partial_rate_delta >= partial_rate_drift_threshold
        )
        is_flagged = score_flagged or partial_flagged
        if is_flagged:
            flagged_analysts.append(analyst)

        per_analyst_drift.append({
            "analyst": analyst,
            "baseline_sample_size": len(baseline_scores),
            "recent_sample_size": len(recent_scores),
            "baseline_mean_net_score": round(baseline_mean, 2),
            "recent_mean_net_score": round(recent_mean, 2),
            "net_score_delta": round(delta, 2),
            "baseline_partial_rate": None if baseline_partial_rate is None else round(baseline_partial_rate, 4),
            "recent_partial_rate": None if recent_partial_rate is None else round(recent_partial_rate, 4),
            "partial_rate_delta": None if partial_rate_delta is None else round(partial_rate_delta, 4),
            "flagged": is_flagged,
        })

    status = "OK" if per_analyst_drift else "INSUFFICIENT_DATA"
    note = "" if per_analyst_drift else "no analyst had data in both windows to compare"

    return DriftReport(
        status=status,
        baseline_sample_size=len(baseline),
        recent_sample_size=len(recent),
        per_analyst_drift=per_analyst_drift,
        flagged_analysts=flagged_analysts,
        note=note,
    )


# -----------------------------------------------------------------------
# §4c — Overfitting detection
# -----------------------------------------------------------------------

@dataclass
class OverfitReport:
    status: str = "INSUFFICIENT_DATA"
    periods: List[str] = field(default_factory=list)
    metric_drifts: List[Dict[str, Any]] = field(default_factory=list)
    flagged_metrics: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "periods": list(self.periods),
            "metric_drifts": self.metric_drifts,
            "flagged_metrics": self.flagged_metrics,
            "note": self.note,
        }


def detect_overfitting(
    certification_metrics_by_period: Dict[str, Dict[str, float]],
    *,
    degrade_threshold: float = OVERFIT_DEGRADE_THRESHOLD,
) -> OverfitReport:
    """Compare numeric metrics (win_rate, profit_factor, agreement_rate,
    sharpe_ratio, ...) between two periods — first key given vs last key
    given in `certification_metrics_by_period` (e.g. {"in_sample": {...},
    "out_of_sample": {...}}, or any two chronologically-ordered periods).

    LIMITATION, stated honestly rather than silently: this treats every
    metric as "higher is better" (true for win_rate/profit_factor/
    agreement_rate/sharpe_ratio/recovery_factor). A "lower is better" metric
    like max_drawdown would be reported with an inverted sign on
    `relative_degradation` — pass it separately if that distinction matters
    for your use, rather than trusting `flagged` for it blindly.

    Needs >= 2 periods to produce anything — see
    testing.faie_backtest.run_faie_backtest for one way to generate two
    periods' worth of comparable metrics (evaluate an earlier CSV slice vs
    a later one).
    """
    periods = list(certification_metrics_by_period.keys())
    if len(periods) < 2:
        return OverfitReport(
            status="INSUFFICIENT_DATA",
            periods=periods,
            note="need >= 2 periods (e.g. 'in_sample' and 'out_of_sample') to compare",
        )

    period_a, period_b = periods[0], periods[-1]
    metrics_a = certification_metrics_by_period.get(period_a) or {}
    metrics_b = certification_metrics_by_period.get(period_b) or {}
    common_metrics = sorted(set(metrics_a.keys()) & set(metrics_b.keys()))

    drifts = []
    flagged = []
    for m in common_metrics:
        try:
            va = float(metrics_a[m])
            vb = float(metrics_b[m])
        except (TypeError, ValueError):
            continue

        relative_degradation = None
        if va != 0:
            relative_degradation = (va - vb) / abs(va)

        is_flagged = relative_degradation is not None and relative_degradation >= degrade_threshold
        if is_flagged:
            flagged.append(m)

        drifts.append({
            "metric": m,
            "period_a": period_a,
            "period_b": period_b,
            "value_a": va,
            "value_b": vb,
            "delta": round(vb - va, 4),
            "relative_degradation": None if relative_degradation is None else round(relative_degradation, 4),
            "flagged": is_flagged,
        })

    status = "OK" if drifts else "INSUFFICIENT_DATA"
    note = "" if drifts else "no overlapping numeric metrics between the two periods to compare"

    return OverfitReport(
        status=status,
        periods=periods,
        metric_drifts=drifts,
        flagged_metrics=flagged,
        note=note,
    )


# -----------------------------------------------------------------------
# Combined report + persistence
# -----------------------------------------------------------------------

def build_self_audit_report(
    *,
    decisions: Optional[List[DecisionLike]] = None,
    recent_reports: Optional[List[DecisionLike]] = None,
    baseline_reports: Optional[List[DecisionLike]] = None,
    certification_metrics_by_period: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Run all three checks and assemble one combined report dict.

    Any input left as None degrades that section to INSUFFICIENT_DATA
    rather than raising — this function is meant to be callable with
    whatever subset of history actually exists today.
    """
    bias = detect_bias(decisions or [])

    if recent_reports is None and baseline_reports is None and decisions:
        baseline_reports, recent_reports = split_recent_vs_baseline(
            [_as_dict(d) for d in decisions]
        )
    drift = detect_drift(recent_reports or [], baseline_reports or [])

    overfit = detect_overfitting(certification_metrics_by_period or {})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bias": bias.to_dict(),
        "drift": drift.to_dict(),
        "overfitting": overfit.to_dict(),
    }


def write_self_audit_report(report: Dict[str, Any], out_dir: Optional[str] = None) -> Path:
    """Persist a combined report to data/analytics/self_audit_<date>.json,
    matching certification/framework.py's STATUS_JSON convention. Never
    raises on the write side beyond what the caller can reasonably handle
    (directory creation is attempted; a genuine disk failure still
    propagates here, unlike the pure-logging helpers elsewhere in FAIE,
    since this is an explicit, on-demand report generation call, not an
    inline hook in a live decision cycle)."""
    directory = Path(out_dir) if out_dir else SELF_AUDIT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = directory / f"self_audit_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return out_path

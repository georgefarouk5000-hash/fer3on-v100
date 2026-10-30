from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from analytics.authority_impact import (
    record_risk_decision,
    load_authority_decisions,
    authority_impact_report,
)


@dataclass
class _FakeDecision:
    approved: bool = False
    final_lot_estimate: float = 0.0
    final_risk_percent: float = 0.0
    rejection_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def test_record_approved_full_risk(tmp_path):
    csv_path = str(tmp_path / "authority_impact.csv")
    decision = _FakeDecision(approved=True, final_lot_estimate=0.1, final_risk_percent=1.0)

    ok = record_risk_decision(
        strategy="SMC", direction="BUY", requested_risk_percent=1.0,
        decision=decision, csv_path=csv_path,
    )
    assert ok is True

    rows = load_authority_decisions(csv_path)
    assert len(rows) == 1
    assert rows[0]["approved"] == "True"
    assert rows[0]["risk_trimmed"] == "False"


def test_record_rejected_counts_as_prevented(tmp_path):
    csv_path = str(tmp_path / "authority_impact.csv")
    decision = _FakeDecision(approved=False, rejection_reason="PORTFOLIO_MAX_OPEN_HIT")

    record_risk_decision(
        strategy="SMC", direction="SELL", requested_risk_percent=0.5,
        decision=decision, csv_path=csv_path,
    )

    report = authority_impact_report(csv_path)
    assert report["total_candidates"] == 1
    assert report["blocked_by_authority"] == 1
    assert report["blocked_by_reason"]["PORTFOLIO_MAX_OPEN_HIT"] == 1
    assert report["total_risk_percent_prevented"] == 0.5


def test_record_trimmed_risk(tmp_path):
    csv_path = str(tmp_path / "authority_impact.csv")
    decision = _FakeDecision(approved=True, final_lot_estimate=0.05, final_risk_percent=0.3)

    record_risk_decision(
        strategy="DAILY", direction="BUY", requested_risk_percent=1.0,
        decision=decision, csv_path=csv_path,
    )

    report = authority_impact_report(csv_path)
    assert report["trimmed_by_authority"] == 1
    assert report["total_risk_percent_prevented"] == 0.7


def test_report_empty_when_no_log(tmp_path):
    csv_path = str(tmp_path / "does_not_exist.csv")
    report = authority_impact_report(csv_path)
    assert report["total_candidates"] == 0
    assert report["blocked_by_authority"] == 0

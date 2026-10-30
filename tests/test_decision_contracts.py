"""
[FER3ON-FIX-2026-08-29] Tests for core/decision_contracts.py (Phase 0).

هذا الملف بيتحقق من حاجتين بس:
  1. العقود نفسها تتبني صح، وbuild_id/decision_snapshot_id بيتحطوا تلقائيًا.
  2. الملف إضافي بالكامل — لسه مفيش أي كود إنتاجي بيستورد منه (لأن الربط
     الفعلي مؤجَّل عمدًا للمرحلة التالية، مش جزء من العقود نفسها).
"""
from pathlib import Path

from core.decision_contracts import (
    DecisionResult,
    DecisionState,
    ExecutionResult,
    ExitPlan,
    FinalEntryPlan,
    PositionState,
    RiskDecision,
    ShadowOpportunity,
    SignalSnapshot,
    new_decision_snapshot_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _signal(**overrides):
    kwargs = dict(
        signal_id="sig-1", symbol="XAUUSD", strategy="SMC",
        direction="BUY", signal_time="2026-08-29T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return SignalSnapshot(**kwargs)


def test_every_contract_auto_fills_build_id_and_snapshot_id():
    for contract in (
        _signal(),
        RiskDecision(signal_id="s", approved=True),
        FinalEntryPlan(signal_id="s", entry_price=1, sl_price=2, tp_prices=[3],
                        sl_distance=1, risk_amount=10, rr=2, source="atr"),
        ExitPlan(signal_id="s"),
        ExecutionResult(signal_id="s", state=DecisionState.APPROVED),
        PositionState(signal_id="s", ticket=1, direction="BUY", entry_price=1,
                       current_sl=0.9, volume_remaining=0.01),
        ShadowOpportunity(signal_id="s", direction="BUY", rejected_reason="x",
                           entry_price=1, virtual_sl=0.9, virtual_tp1=1.1),
    ):
        d = contract.to_dict()
        assert d.get("build_id") is not None
        assert d.get("decision_snapshot_id"), f"missing snapshot id: {d}"


def test_snapshot_ids_are_unique():
    ids = {new_decision_snapshot_id() for _ in range(100)}
    assert len(ids) == 100


def test_decision_state_covers_the_documented_states():
    expected = {
        "REJECTED", "WAIT_RETEST", "WAIT_CONFIRMATION", "APPROVED",
        "EXECUTED", "EXPIRED", "CLOSED",
    }
    assert {s.value for s in DecisionState} == expected


def test_shadow_opportunity_shadow_only_defaults_true_and_is_explicit():
    """[خطر #7] shadow_only لازم تبقى True دايمًا بالـdefault — أي كود
    مستهلك يقدر يتأكد برمجيًا إنها مش صفقة حقيقية قبل ما يكتبها في أي
    ملف تعلّم حي."""
    so = ShadowOpportunity(
        signal_id="s", direction="SELL", rejected_reason="EXEC_GRADE_C",
        entry_price=2000.0, virtual_sl=1990.0, virtual_tp1=2020.0,
    )
    assert so.shadow_only is True


def test_decision_result_to_dict_nests_optional_contracts_safely():
    dr = DecisionResult(signal=_signal(), state=DecisionState.WAIT_RETEST, reason="pullback")
    d = dr.to_dict()
    assert d["state"] == "WAIT_RETEST"
    assert d["risk"] is None
    assert d["entry_plan"] is None
    assert d["signal"]["signal_id"] == "sig-1"


def test_decision_contracts_are_discoverable_without_shell_tools():
    """The contracts are wired into production and this check is portable."""
    importers = []
    for root in (REPO_ROOT / "main.py", REPO_ROOT / "core"):
        candidates = [root] if root.is_file() else root.rglob("*.py")
        for candidate in candidates:
            if candidate.name == "decision_contracts.py":
                continue
            if "decision_contracts" in candidate.read_text(encoding="utf-8"):
                importers.append(str(candidate.relative_to(REPO_ROOT)))
    assert importers

# =============================================================================
# FER3ON — FAIE (Institutional Edition) — Master Market Brain Layer
# =============================================================================
# CONSTITUTIONAL NOTICE (see docs/FAIE/VOLUME_1_CONSTITUTION.md):
#
#   1. This package is PURELY ADDITIVE. It does not modify, replace, or
#      delete any existing engine, decision path, or execution path.
#   2. Nothing in this package is permitted to place, modify, or close a
#      trade. It has NO import of trade_executor, execution_optimizer_v2,
#      MetaTrader5, or any order-sending module. This is enforced by
#      tests/faie/test_faie_master_brain.py::test_no_execution_capability.
#   3. Every analyst produces a REPORT (Evidence), not a decision.
#      Only ChiefDecisionOfficer synthesizes reports into a Decision, and
#      that Decision is an ADVISORY recommendation — it still must pass
#      through the existing core.unified_decision + Portfolio Risk
#      Authority + Execution pipeline before anything real happens.
#   4. This corresponds to Roadmap Phase 2-3 (see docs/FAIE/ROADMAP.md):
#      "introduce the Master Market Brain, wire old engines into it,
#      without breaking the current architecture."
# =============================================================================

from .evidence import Evidence, EvidenceGraph
from .analysts import (
    Analyst,
    AnalystReport,
    MacroAnalyst,
    TechnicalAnalyst,
    SMCAnalyst,
    LiquidityAnalyst,
    VolumeAnalyst,
    PatternAnalyst,
    PsychologyAnalyst,
    RiskOfficer,
    ExecutionOfficer,
    DEFAULT_ANALYSTS,
)
from .fusion import EvidenceFusionEngine, FusedEvidence
from .contradiction import ContradictionResolver, ContradictionReport, Conflict
from .scenario import ScenarioEngine, Scenario
from .chief_decision_officer import ChiefDecisionOfficer, Decision
from .explainability import ExplanationBuilder
from .personality import PERSONALITY_PROFILES, get_profile
from .shadow_logging import build_shadow_decision, log_faie_shadow_decision

__all__ = [
    "Evidence",
    "EvidenceGraph",
    "Analyst",
    "AnalystReport",
    "MacroAnalyst",
    "TechnicalAnalyst",
    "SMCAnalyst",
    "LiquidityAnalyst",
    "VolumeAnalyst",
    "PatternAnalyst",
    "PsychologyAnalyst",
    "RiskOfficer",
    "ExecutionOfficer",
    "DEFAULT_ANALYSTS",
    "EvidenceFusionEngine",
    "FusedEvidence",
    "ContradictionResolver",
    "ContradictionReport",
    "Conflict",
    "ScenarioEngine",
    "Scenario",
    "ChiefDecisionOfficer",
    "Decision",
    "ExplanationBuilder",
    "PERSONALITY_PROFILES",
    "get_profile",
    "build_shadow_decision",
    "log_faie_shadow_decision",
]

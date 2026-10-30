"""Inventory and review gates for the project's shadow-mode systems.

The report is observational only. It never changes a live setting or trading
decision, and only counts uniquely identified records with explicit outcomes
as review samples. Counterfactual results stay separate from realized P&L.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


_TRADE_OUTCOMES = {
    "WIN",
    "LOSS",
    "BREAKEVEN",
    "TIMEOUT",
    "LOSS_INTRABAR_AMBIGUOUS",
}
_WIN_LOSS_OUTCOMES = {"WIN", "LOSS", "BREAKEVEN", "LOSS_INTRABAR_AMBIGUOUS"}
_ACTUAL_PNL_OUTCOMES = {"WIN", "LOSS", "BREAKEVEN"}
_IDENTITY_FIELDS = (
    "candidate_id",
    "decision_id",
    "signal_id",
    "ticket",
    "position_id",
    "trade_id",
)


def _system_registry() -> List[Dict[str, Any]]:
    import core.settings as settings

    phase3 = settings.PHASE3_ANALYTICS_DIR
    return [
        {
            "id": "rejected_counterfactual",
            "name": "Rejected-signal counterfactual",
            "category": "decision_evidence",
            "enabled": settings.SHADOW_COUNTERFACTUAL_ENABLED,
            "live_enabled": False,
            "path": settings.SHADOW_COUNTERFACTUAL_LOG_PATH,
            "record_type": "REJECTED_SHADOW",
            "outcome_source": "outcome",
            "sample_semantics": "counterfactual",
            "decision_candidate": True,
            "note": "نتيجة افتراضية قبل التكاليف؛ ليست ربحًا محققًا ولا تكفي وحدها لتفعيل بوابة.",
        },
        {
            "id": "virtual_shadow",
            "name": "Accepted-but-not-executed virtual trades",
            "category": "decision_evidence",
            "enabled": (
                settings.SHADOW_COUNTERFACTUAL_ENABLED
                and settings.SHADOW_ONLY_RUNTIME
            ),
            "live_enabled": False,
            "path": settings.SHADOW_COUNTERFACTUAL_LOG_PATH,
            "record_type": "VIRTUAL_SHADOW",
            "outcome_source": "outcome",
            "sample_semantics": "virtual_counterfactual",
            "decision_candidate": True,
            "note": "يفصل عن الإشارات المرفوضة؛ سجلاته لا تُعد صفقات فعلية.",
        },
        {
            "id": "entry_controller",
            "name": "Pullback entry and structural stop",
            "category": "entry_candidate",
            "enabled": settings.PHASE2_ENTRY_CONTROLLER_ENABLED,
            "live_enabled": settings.PHASE2_ENTRY_CONTROLLER_LIVE_ENABLED,
            "path": settings.PHASE2_ENTRY_CONTROLLER_LOG_PATH,
            "outcome_source": "entry_outcome",
            "comparison_outcome_source": "baseline_outcome",
            "sample_semantics": "matched_counterfactual_entry_outcome",
            "decision_candidate": True,
            "note": "نتيجة دخول افتراضي مقابل دخول السوق على الإشارة نفسها؛ لا تمثل ربحًا محققًا ولا تشمل تكاليف التنفيذ.",
        },
        {
            "id": "exit_manager",
            "name": "Alternative exit manager",
            "category": "exit_candidate",
            "enabled": settings.PHASE3_EXIT_MANAGER_ENABLED,
            "live_enabled": settings.PHASE3_EXIT_MANAGER_LIVE_ENABLED,
            "path": settings.PHASE3_EXIT_MANAGER_LOG_PATH,
            "record_type": "EXIT_SIMULATION_OUTCOME",
            "identity_field": "decision_id",
            "outcome_source": "outcome",
            "sample_semantics": "counterfactual_exit_simulation",
            "decision_candidate": True,
            "note": "إعادة تشغيل بحثية تقريبية بـATR الدخول وOHLC محافظ، دون تكاليف افتراضية؛ تُقارن بصافي الإغلاق الفعلي المكتمل التكاليف.",
        },
        {
            "id": "opportunity_allocator",
            "name": "Opportunity allocator",
            "category": "sizing_candidate",
            "enabled": settings.PHASE5_OPPORTUNITY_ALLOCATOR_ENABLED,
            "live_enabled": settings.PHASE5_OPPORTUNITY_ALLOCATOR_LIVE_ENABLED,
            "path": settings.PHASE5_ALLOCATOR_LOG_PATH,
            "outcome_source": None,
            "sample_semantics": "actual_pnl_linked_by_candidate",
            "decision_candidate": True,
            "note": "درجة التخصيص استشارية؛ نتائج P&L الفعلية تُربط بمعرّف الفرصة بعد إغلاق المركز وتُراجع خارج العينة.",
        },
        {
            "id": "final_brain",
            "name": "Phase 3 Final Brain",
            "category": "decision_candidate",
            "enabled": settings.FINAL_BRAIN_ENABLED,
            "live_enabled": settings.FINAL_BRAIN_LIVE_AUTHORITY,
            "path": os.path.join(settings.PHASE3_FINAL_BRAIN_DIR, "shadow_decisions.jsonl"),
            "outcome_source": "decision.matched_actual",
            "sample_semantics": "decision_agreement_and_linked_actual_pnl",
            "decision_candidate": True,
            "note": "اتفاق القرار ليس نتيجة تداول؛ P&L الفعلي المنسوب للفرصة يُعرض منفصلًا.",
        },
        {
            "id": "portfolio_brain",
            "name": "Portfolio Brain",
            "category": "sizing_candidate",
            "enabled": settings.PORTFOLIO_BRAIN_ENABLED,
            "live_enabled": settings.PORTFOLIO_BRAIN_LIVE_AUTHORITY,
            "path": os.path.join(settings.PHASE3_PORTFOLIO_BRAIN_DIR, "shadow_portfolio.jsonl"),
            "outcome_source": None,
            "sample_semantics": "actual_pnl_linked_by_candidate",
            "decision_candidate": True,
            "note": "تُحفظ لقطة واحدة لكل فرصة مغلقة الشمعة؛ P&L الفعلي مرتبط بها ولا يثبت وحده أثرًا سببيًا.",
        },
        {
            "id": "gold_context",
            "name": "Gold macro context",
            "category": "context_candidate",
            "enabled": settings.GOLD_CONTEXT_ENABLED,
            "live_enabled": settings.GOLD_CONTEXT_LIVE_INFLUENCE,
            "path": os.path.join(settings.PHASE3_GOLD_CONTEXT_DIR, "shadow_gold_context.jsonl"),
            "outcome_source": None,
            "sample_semantics": "actual_pnl_linked_by_candidate",
            "decision_candidate": True,
            "note": "تقييم السياق استشاري؛ يُربط بنتيجة الإغلاق الفعلية ولا تُعد نبضات التشغيل عينات مستقلة.",
        },
        {
            "id": "ml_safety",
            "name": "ML safety monitor",
            "category": "monitoring",
            "enabled": settings.ML_SAFETY_ENABLED,
            "live_enabled": settings.ML_SAFETY_LIVE_BLOCK,
            "path": os.path.join(settings.PHASE3_ML_SAFETY_DIR, "ml_safety_shadow.jsonl"),
            "outcome_source": None,
            "sample_semantics": "health_log_only",
            "decision_candidate": False,
            "note": "مراقبة صحة/انجراف النموذج؛ لا تُفعّل كقرار تداول قبل تقييمها كسياسة مستقلة.",
        },
        {
            "id": "strategy_dna",
            "name": "Strategy DNA",
            "category": "sizing_candidate",
            "enabled": settings.STRATEGY_DNA_ENABLED,
            "live_enabled": settings.STRATEGY_DNA_LIVE_INFLUENCE,
            "path": os.path.join(settings.PHASE3_STRATEGY_DNA_DIR, "strategy_dna_shadow.jsonl"),
            "outcome_source": None,
            "sample_semantics": "actual_pnl_linked_by_candidate",
            "decision_candidate": True,
            "note": "توصية DNA تُربط بنتيجة الفرصة نفسها؛ لا تُعد التوصية نتيجة تداول ويظل التحقق خارج العينة مطلوبًا.",
        },
        {
            "id": "system_health",
            "name": "System health monitor",
            "category": "monitoring",
            "enabled": settings.SYSTEM_HEALTH_ENABLED,
            "live_enabled": False,
            "path": os.path.join(settings.PHASE3_SYSTEM_HEALTH_DIR, "system_health_shadow.jsonl"),
            "outcome_source": None,
            "sample_semantics": "health_log_only",
            "decision_candidate": False,
            "note": "مراقبة تشغيلية؛ احتفظ بها فقط إذا كانت تنبيهاتها مفيدة، ولا تعاملها كاستراتيجية.",
        },
        {
            "id": "adaptive_calibration",
            "name": "Adaptive shadow calibration",
            "category": "calibration_candidate",
            "enabled": settings.ADAPTIVE_SHADOW_LOG,
            "live_enabled": not settings.ADAPTIVE_SHADOW_ONLY,
            "path": os.path.join(phase3, "adaptive_shadow", "adaptive_shadow.jsonl"),
            "outcome_source": None,
            "sample_semantics": "aggregate_actual_trade_analysis",
            "decision_candidate": False,
            "note": "تحليل مجمّع لصفقات مغلقة سابقة وليس عينة فرص مستقلة؛ يُراجع خارج العينة كتحليل مشترك.",
        },
        {
            "id": "faie",
            "name": "FAIE shadow decision",
            "category": "decision_candidate",
            "enabled": settings.FAIE_SHADOW_LOGGING_ENABLED,
            "live_enabled": False,
            "path": settings.FAIE_SHADOW_LOG_PATH,
            "outcome_source": None,
            "sample_semantics": "decision_pair_and_linked_actual_pnl",
            "decision_candidate": True,
            "note": "يسجل القرار المقابل وP&L الفعلي للفرصة منفصلين؛ التطابق وحده ليس نتيجة تداول.",
        },
        {
            "id": "shadow_context",
            "name": "Regime and performance context collector",
            "category": "analysis",
            "enabled": True,
            "live_enabled": False,
            "path": "data/analytics/shadow_context/context_observations.jsonl",
            "outcome_source": None,
            "sample_semantics": "observation_log_only",
            "decision_candidate": False,
            "note": "جامع سياق/لقطات تحليلية وليس قرار دخول أو خروج مستقلًا.",
        },
    ]


def _records(path: str) -> tuple[List[Dict[str, Any]], int, Optional[str]]:
    if not os.path.exists(path):
        return [], 0, None
    records: List[Dict[str, Any]] = []
    malformed = 0
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if isinstance(value, dict):
                    records.append(value)
                else:
                    malformed += 1
    except (OSError, UnicodeError) as exc:
        return [], malformed, f"{type(exc).__name__}: {exc}"
    return records, malformed, None


def _record_identity(
    record: Dict[str, Any],
    preferred_field: Optional[str] = None,
) -> Optional[str]:
    fields = (
        (preferred_field, *tuple(
            field for field in _IDENTITY_FIELDS if field != preferred_field
        ))
        if preferred_field
        else _IDENTITY_FIELDS
    )
    for field in fields:
        value = record.get(field)
        if value not in (None, ""):
            if field == "signal_id" and str(value).startswith("hb-"):
                continue
            return f"{field}:{value}"
    if record.get("decision_bar_time") not in (None, ""):
        from core.trade_event_ledger import create_candidate_id
        candidate_id = create_candidate_id(
            symbol=str(record.get("symbol") or ""),
            strategy=str(record.get("strategy") or ""),
            signal=str(record.get("direction") or ""),
            decision_bar_time=record.get("decision_bar_time"),
        )
        if candidate_id:
            return f"candidate_id:{candidate_id}"
    return None


def _actual_results_by_candidate(
    path: str,
) -> tuple[Dict[str, set[float]], int, int, Optional[str]]:
    records, malformed, read_error = _records(path)
    if read_error:
        return {}, 0, malformed, read_error
    decisions: Dict[str, str] = {}
    closed: Dict[str, set[float]] = {}
    incomplete = 0
    for row in records:
        event_type = row.get("event_type")
        correlation_id = str(row.get("correlation_id") or "")
        if not correlation_id:
            continue
        if event_type == "DECISION" and row.get("candidate_id"):
            decisions[correlation_id] = str(row["candidate_id"])
        elif event_type == "TRADE_CLOSED":
            if row.get("entry_cost_complete") is not True:
                incomplete += 1
                continue
            try:
                profit = float(row["total_position_net_profit"])
            except (KeyError, TypeError, ValueError):
                continue
            closed.setdefault(correlation_id, set()).add(profit)
    by_candidate: Dict[str, set[float]] = {}
    for decision_id, values in closed.items():
        candidate_id = decisions.get(decision_id)
        if candidate_id:
            by_candidate.setdefault(candidate_id, set()).update(values)
    return by_candidate, incomplete, malformed, None


def _sample_outcome(record: Dict[str, Any], outcome_source: Optional[str]) -> Optional[str]:
    if not outcome_source or outcome_source == "decision.matched_actual":
        return None
    value: Any = record
    for part in outcome_source.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    if isinstance(value, str):
        outcome = value.strip().upper()
        return outcome if outcome in _TRADE_OUTCOMES else None
    return None


def _actual_outcome(record: Dict[str, Any]) -> Optional[str]:
    for field in ("actual_outcome", "actual_result", "realized_outcome", "real_trade_result"):
        value = record.get(field)
        if isinstance(value, str) and value.strip().upper() in _ACTUAL_PNL_OUTCOMES:
            return value.strip().upper()
    profit = _actual_profit(record)
    if profit is not None:
        return "WIN" if profit > 0 else "LOSS" if profit < 0 else "BREAKEVEN"
    return None


def _actual_profit(record: Dict[str, Any]) -> Optional[float]:
    if "actual_profit" not in record and "realized_profit" not in record:
        return None
    try:
        return float(record.get("actual_profit", record.get("realized_profit")))
    except (TypeError, ValueError):
        return None


def _recommendation(
    *,
    enabled: bool,
    exists: bool,
    record_count: int,
    resolved_samples: int,
    actual_pnl_samples: int,
    initial_threshold: int,
    decision_threshold: int,
    decision_candidate: bool,
    read_error: Optional[str],
) -> str:
    if read_error:
        return "CHECK_REPORTING_ERROR"
    if not enabled:
        return "DISABLED_BY_CONFIGURATION"
    if not exists:
        return "CHECK_LOGGING_WIRING"
    if not decision_candidate:
        return "KEEP_OR_REMOVE_AS_MONITORING"
    if resolved_samples >= decision_threshold:
        if actual_pnl_samples >= decision_threshold:
            return "DECISION_REQUIRED_PROMOTE_TO_DEMO_OR_REMOVE"
        return "DECISION_REQUIRED_LINK_ACTUAL_RESULTS_OR_REMOVE"
    if resolved_samples >= initial_threshold:
        return f"FIRST_REVIEW_REQUIRED_AT_{initial_threshold}"
    if record_count >= decision_threshold and resolved_samples < initial_threshold:
        return "LINK_OUTCOMES_BEFORE_PROMOTION_REVIEW"
    if record_count == 0:
        return "NO_EVENTS_YET_CHECK_TRIGGER_OR_WIRING"
    return f"CONTINUE_SHADOW_UNTIL_{initial_threshold}_RESOLVED_SAMPLES"


def build_shadow_system_report(
    *,
    systems: Optional[Sequence[Dict[str, Any]]] = None,
    initial_threshold: Optional[int] = None,
    decision_threshold: Optional[int] = None,
    actual_events_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a consolidated inventory; never changes system activation."""
    import core.settings as settings

    initial = int(
        initial_threshold
        if initial_threshold is not None
        else settings.SHADOW_SYSTEM_REVIEW_INITIAL_SAMPLES
    )
    decision = int(
        decision_threshold
        if decision_threshold is not None
        else settings.SHADOW_SYSTEM_REVIEW_DECISION_SAMPLES
    )
    if initial < 1 or decision < initial:
        raise ValueError("Review thresholds must satisfy 1 <= initial <= decision")

    if actual_events_path is None:
        from core.trade_event_ledger import TRADE_EVENTS_FILE
        actual_events_path = TRADE_EVENTS_FILE
    actual_results, incomplete_close_events, malformed_events, events_read_error = (
        _actual_results_by_candidate(actual_events_path)
    )
    system_reports = []
    for spec in systems if systems is not None else _system_registry():
        path = str(spec["path"])
        records, malformed, read_error = _records(path)
        record_type = spec.get("record_type")
        selected = [
            row for row in records
            if record_type is None or row.get("record_type", "REJECTED_SHADOW") == record_type
        ]
        outcome_counts: Dict[str, int] = {}
        outcomes_by_id: Dict[str, set[str]] = {}
        actual_outcomes_by_id: Dict[str, set[str]] = {}
        actual_profits_by_id: Dict[str, set[float]] = {}
        comparison_outcomes_by_id: Dict[str, set[str]] = {}
        unidentified_outcomes = 0
        unstable_identity_records = 0
        decision_pairs = 0
        pending_outcome_ids: set[str] = set()
        pending_outcome_records = 0
        states: Dict[str, int] = {}
        for row in selected:
            identity = _record_identity(row, spec.get("identity_field"))
            if identity is None and str(row.get("signal_id") or "").startswith("hb-"):
                unstable_identity_records += 1
            unidentified_counted = False
            state = str(
                row.get("outcome")
                or row.get("status")
                or row.get("action")
                or row.get("record_type")
                or "UNKNOWN"
            ).upper()
            states[state] = states.get(state, 0) + 1
            pending_record = state == "PENDING"
            has_decision_pair = row.get("real_decision_summary") is not None
            if has_decision_pair:
                decision_pairs += 1
            outcome = _sample_outcome(row, spec.get("outcome_source"))
            if spec.get("outcome_source"):
                raw_outcome = row
                for part in str(spec["outcome_source"]).split("."):
                    raw_outcome = (
                        raw_outcome.get(part)
                        if isinstance(raw_outcome, dict)
                        else None
                    )
                pending_record = pending_record or (
                    str(raw_outcome or "").upper() == "PENDING"
                )
            if pending_record:
                pending_outcome_records += 1
                if identity:
                    pending_outcome_ids.add(identity)
            if outcome:
                if identity is None:
                    unidentified_outcomes += 1
                    unidentified_counted = True
                else:
                    outcomes_by_id.setdefault(identity, set()).add(outcome)
            actual_outcome = _actual_outcome(row)
            if actual_outcome:
                if identity is None:
                    if not unidentified_counted:
                        unidentified_outcomes += 1
                        unidentified_counted = True
                else:
                    actual_outcomes_by_id.setdefault(identity, set()).add(actual_outcome)
            actual_profit = _actual_profit(row)
            if actual_profit is not None:
                if identity is None:
                    if not unidentified_counted:
                        unidentified_outcomes += 1
                else:
                    actual_profits_by_id.setdefault(identity, set()).add(actual_profit)
            candidate_id = str(row.get("candidate_id") or "")
            if candidate_id:
                for linked_profit in actual_results.get(candidate_id, set()):
                    actual_profits_by_id.setdefault(
                        f"candidate_id:{candidate_id}", set()
                    ).add(linked_profit)
                    actual_outcomes_by_id.setdefault(
                        f"candidate_id:{candidate_id}", set()
                    ).add(
                        "WIN" if linked_profit > 0
                        else "LOSS" if linked_profit < 0
                        else "BREAKEVEN"
                    )
            comparison_outcome = _sample_outcome(
                row, spec.get("comparison_outcome_source")
            )
            if comparison_outcome and identity:
                comparison_outcomes_by_id.setdefault(identity, set()).add(
                    comparison_outcome
                )
            elif (
                spec.get("outcome_source") == "decision.matched_actual"
                and not has_decision_pair
            ):
                decision_data = row.get("decision")
                if isinstance(decision_data, dict) and isinstance(
                    decision_data.get("matched_actual"), bool
                ):
                    decision_pairs += 1

        outcome_counts.setdefault("PENDING", states.get("PENDING", 0))
        unique_outcomes = [
            next(iter(outcomes))
            for outcomes in outcomes_by_id.values()
            if len(outcomes) == 1
        ]
        conflicting_outcome_ids = sum(
            len(outcomes) > 1 for outcomes in outcomes_by_id.values()
        )
        resolved_samples = len(unique_outcomes)
        actual_unique_outcomes = [
            next(iter(outcomes))
            for outcomes in actual_outcomes_by_id.values()
            if len(outcomes) == 1
        ]
        actual_pnl_values = [
            next(iter(values))
            for values in actual_profits_by_id.values()
            if len(values) == 1
        ]
        actual_pnl_samples = len(actual_pnl_values)
        unique_comparisons = [
            next(iter(outcomes))
            for outcomes in comparison_outcomes_by_id.values()
            if len(outcomes) == 1
        ]
        paired_comparison_cases = sum(
            len(outcomes_by_id.get(identity, set())) == 1
            and len(comparison_outcomes_by_id.get(identity, set())) == 1
            for identity in set(outcomes_by_id) & set(comparison_outcomes_by_id)
        )
        conflicting_comparison_ids = sum(
            len(outcomes) > 1 for outcomes in comparison_outcomes_by_id.values()
        )
        conflicting_actual_ids = sum(
            len(outcomes) > 1 for outcomes in actual_outcomes_by_id.values()
        )
        conflicting_actual_pnl_ids = sum(
            len(values) > 1 for values in actual_profits_by_id.values()
        )
        for outcome in unique_outcomes:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        trade_outcomes = {
            name: count
            for name, count in outcome_counts.items()
            if name in _TRADE_OUTCOMES
        }
        decisive = sum(
            trade_outcomes.get(name, 0)
            for name in _WIN_LOSS_OUTCOMES
        )
        wins = trade_outcomes.get("WIN", 0)
        win_rate = round(wins / decisive, 4) if decisive else None
        actual_decisive = sum(
            outcome in _WIN_LOSS_OUTCOMES for outcome in actual_unique_outcomes
        )
        actual_wins = sum(outcome == "WIN" for outcome in actual_unique_outcomes)
        actual_win_rate = (
            round(actual_wins / actual_decisive, 4) if actual_decisive else None
        )
        actual_net_pnl = round(sum(actual_pnl_values), 4) if actual_pnl_values else None
        actual_gross_profit = sum(value for value in actual_pnl_values if value > 0)
        actual_gross_loss = abs(sum(value for value in actual_pnl_values if value < 0))
        actual_profit_factor = (
            round(actual_gross_profit / actual_gross_loss, 4)
            if actual_gross_loss else None
        )
        exists = os.path.exists(path)
        enabled = bool(spec.get("enabled"))
        evaluation_samples = resolved_samples
        if spec.get("outcome_source") in (None, "decision.matched_actual"):
            evaluation_samples = max(evaluation_samples, actual_pnl_samples)
        recommendation = _recommendation(
            enabled=enabled,
            exists=exists,
            record_count=len(selected),
            resolved_samples=evaluation_samples,
            actual_pnl_samples=actual_pnl_samples,
            initial_threshold=initial,
            decision_threshold=decision,
            decision_candidate=bool(spec.get("decision_candidate")),
            read_error=read_error,
        )
        system_reports.append({
            "id": str(spec["id"]),
            "name": str(spec["name"]),
            "category": str(spec["category"]),
            "enabled": enabled,
            "live_enabled": bool(spec.get("live_enabled")),
            "decision_candidate": bool(spec.get("decision_candidate")),
            "log_path": path,
            "log_exists": exists,
            "log_records": len(selected),
            "malformed_records": malformed,
            "distinct_resolved_outcome_cases": resolved_samples,
            "distinct_actual_pnl_samples": actual_pnl_samples,
            "distinct_comparison_outcome_cases": len(unique_comparisons),
            "paired_comparison_outcome_cases": paired_comparison_cases,
            "actual_net_pnl": actual_net_pnl,
            "actual_profit_factor": actual_profit_factor,
            "actual_profit_factor_unbounded": (
                bool(actual_gross_profit and not actual_gross_loss)
            ),
            "actual_expectancy": (
                round(actual_net_pnl / actual_pnl_samples, 4)
                if actual_net_pnl is not None and actual_pnl_samples else None
            ),
            "sample_semantics": str(spec.get("sample_semantics") or "unclassified"),
            "unidentified_outcome_records": unidentified_outcomes,
            "unstable_identity_records": unstable_identity_records,
            "conflicting_outcome_ids": conflicting_outcome_ids,
            "conflicting_actual_outcome_ids": conflicting_actual_ids,
            "conflicting_actual_pnl_ids": conflicting_actual_pnl_ids,
            "conflicting_comparison_ids": conflicting_comparison_ids,
            "decision_pair_records": decision_pairs,
            "outcomes": trade_outcomes,
            "states": states,
            "pending_records": states.get("PENDING", 0),
            "pending_outcome_records": pending_outcome_records,
            "distinct_pending_outcome_ids": len(pending_outcome_ids),
            "win_rate_excluding_timeouts": win_rate,
            "actual_win_rate": actual_win_rate,
            "initial_review_threshold": initial,
            "decision_threshold": decision,
            "recommendation": recommendation,
            "note": str(spec.get("note") or ""),
            "read_error": read_error,
            "actual_events_read_error": events_read_error,
            "incomplete_close_events_excluded": incomplete_close_events,
            "malformed_actual_event_records": malformed_events,
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "initial_review_after_resolved_samples": initial,
            "final_decision_after_resolved_samples": decision,
            "live_changes_automatic": False,
            "promotion_requires": [
                "attributed and resolved outcomes",
                "complete costs and execution comparison",
                "out-of-sample validation",
                "manual demo approval",
            ],
        },
        "systems": system_reports,
        "actual_trade_linkage": {
            "events_path": actual_events_path,
            "candidate_ids_with_closed_pnl": len(actual_results),
            "incomplete_close_events_excluded": incomplete_close_events,
            "malformed_records": malformed_events,
            "read_error": events_read_error,
            "linking_rule": (
                "Only final close events with entry_cost_complete=true and a matching "
                "DECISION candidate_id are counted."
            ),
        },
        "shared_consumers": [
            {
                "id": "shadow_learning_engine",
                "uses_system": "rejected_counterfactual",
                "note": "Analyzes the rejected-signal ledger; it is not a separate shadow logger or sample pool.",
            },
            {
                "id": "offline_session_and_regime_replays",
                "uses_system": "truth_layer_closed_trades",
                "note": "Session/regime replay modules consume actual closed-trade history offline; do not count them as separate live shadow systems.",
            },
            {
                "id": "adaptive_shadow_calibration",
                "uses_system": "truth_layer_closed_trades",
                "note": "Aggregate recommendations reuse closed-trade history and have no unique candidate rows; review with offline out-of-sample replay, not heartbeat thresholds.",
            },
        ],
        "summary": {
            "system_count": len(system_reports),
            "live_enabled_count": sum(row["live_enabled"] for row in system_reports),
            "decision_required_count": sum(
                row["recommendation"].startswith("DECISION_REQUIRED_")
                for row in system_reports
            ),
            "wiring_check_count": sum(
                row["recommendation"] == "CHECK_LOGGING_WIRING"
                for row in system_reports
            ),
        },
    }


def render_shadow_system_markdown(report: Dict[str, Any]) -> str:
    policy = report["policy"]
    lines = [
        "# Shadow Systems — Review and Decision Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Decision policy",
        "",
        f"- First mandatory review: **{policy['initial_review_after_resolved_samples']} uniquely identified, resolved outcome cases**.",
        f"- Final promote-to-demo-or-remove decision: **{policy['final_decision_after_resolved_samples']} resolved cases**.",
        "- Heartbeat cycles, repeated log rows, plan fills, and decision agreement do not count as outcome cases.",
        "- A shadow/counterfactual outcome is not realized P&L. Promotion review also requires 200 uniquely identified outcomes linked to actual closed-trade P&L.",
        "- This report is observational: it never changes a live flag or a trading decision.",
        "- Promotion requires attributed results, complete costs, out-of-sample validation, and explicit human approval.",
        "",
        "## System inventory",
        "",
        "| System | Mode | Log rows | Pending outcomes | Outcome cases | Paired comparisons | Actual P&L cases | Actual net P&L | Actual PF | Shadow win rate* | Actual win rate* | Recommendation |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for system in report["systems"]:
        mode = "LIVE" if system["live_enabled"] else (
            "SHADOW" if system["enabled"] else "OFF"
        )
        rate = (
            f"{system['win_rate_excluding_timeouts']:.1%}"
            if system["win_rate_excluding_timeouts"] is not None else "N/A"
        )
        actual_rate = (
            f"{system['actual_win_rate']:.1%}"
            if system["actual_win_rate"] is not None else "N/A"
        )
        actual_pnl = (
            f"{system['actual_net_pnl']:.2f}"
            if system["actual_net_pnl"] is not None else "N/A"
        )
        actual_pf = (
            f"{system['actual_profit_factor']:.2f}"
            if system["actual_profit_factor"] is not None
            else "∞" if system["actual_profit_factor_unbounded"] else "N/A"
        )
        lines.append(
            f"| {system['name']} | {mode} | {system['log_records']} | "
            f"{system['pending_outcome_records']} | "
            f"{system['distinct_resolved_outcome_cases']} | "
            f"{system['paired_comparison_outcome_cases']} | "
            f"{system['distinct_actual_pnl_samples']} | {actual_pnl} | {actual_pf} | "
            f"{rate} | {actual_rate} | "
            f"{system['recommendation']} |"
        )
    lines.extend([
        "",
        "*Win rates exclude timeouts and require explicit, uniquely identified outcomes; shadow rates are not realized returns.",
        "",
        "## Review notes",
        "",
    ])
    for system in report["systems"]:
        lines.append(
            f"- **{system['name']}** (`{system['id']}`): {system['note']} "
            f"Log: `{system['log_path'].replace(chr(92), '/')}`."
        )
        if system["read_error"]:
            lines.append(f"  - Read error: `{system['read_error']}`")
        if system["malformed_records"]:
            lines.append(
                f"  - Malformed rows excluded: {system['malformed_records']}."
            )
        if system["unidentified_outcome_records"]:
            lines.append(
                "  - Outcomes without a stable trade/decision ID excluded from sample counts: "
                f"{system['unidentified_outcome_records']}."
            )
        if system["unstable_identity_records"]:
            lines.append(
                "  - Heartbeat-ID rows excluded from candidate sample counts: "
                f"{system['unstable_identity_records']}."
            )
        if system["conflicting_outcome_ids"]:
            lines.append(
                "  - IDs with conflicting terminal outcomes excluded from sample counts: "
                f"{system['conflicting_outcome_ids']}."
            )
        if system["conflicting_comparison_ids"]:
            lines.append(
                "  - Candidate IDs with conflicting comparison outcomes excluded: "
                f"{system['conflicting_comparison_ids']}."
            )
        if system["incomplete_close_events_excluded"]:
            lines.append(
                "  - Actual close events excluded because costs were incomplete: "
                f"{system['incomplete_close_events_excluded']}."
            )
    linkage = report["actual_trade_linkage"]
    lines.extend([
        "",
        "## Actual-trade attribution",
        "",
        f"- Candidate IDs with a cost-complete final close: **{linkage['candidate_ids_with_closed_pnl']}**.",
        f"- Incomplete closes excluded: **{linkage['incomplete_close_events_excluded']}**.",
        f"- Linkage source: `{linkage['events_path']}`.",
    ])
    if linkage["read_error"]:
        lines.append(f"- Event-ledger read error: `{linkage['read_error']}`.")
    lines.extend(["", "## Shared analytics (not separate shadow systems)", ""])
    for consumer in report["shared_consumers"]:
        lines.append(
            f"- **{consumer['id']}** uses `{consumer['uses_system']}`: "
            f"{consumer['note']}"
        )
    lines.extend([
        "",
        "## Required human decision",
        "",
        "When a decision candidate reaches 100 resolved cases, review the evidence and record an interim decision. "
        "At 200 cases, choose **promote to demo** or **remove/redesign**. If the cases are only shadow estimates, "
        "link actual closed-trade P&L or remove/redesign; do not promote from estimates alone. Do not leave a system "
        "shadow-only without a dated reason and next review condition. Monitoring-only systems are not promotion candidates.",
        "",
    ])
    return "\n".join(lines)


def persist_shadow_system_report(
    *,
    json_path: Optional[str] = None,
    markdown_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Write the machine-readable and human-readable report atomically."""
    import core.settings as settings

    report = build_shadow_system_report()
    destinations = (
        (json_path or settings.SHADOW_SYSTEM_REPORT_JSON_PATH, json.dumps(
            report, ensure_ascii=False, indent=2, default=str
        )),
        (markdown_path or settings.SHADOW_SYSTEM_REPORT_MARKDOWN_PATH,
         render_shadow_system_markdown(report)),
    )
    for path, content in destinations:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary_path = f"{path}.tmp"
        with open(temporary_path, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    return report


if __name__ == "__main__":
    generated = persist_shadow_system_report()
    print(
        "Shadow system report updated | "
        f"systems={generated['summary']['system_count']} "
        f"decisions_due={generated['summary']['decision_required_count']}"
    )

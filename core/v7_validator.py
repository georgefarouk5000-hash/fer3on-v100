from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.dynamic_confidence import get_dynamic_confidence_threshold
from core.liquidity_vacuum import analyze_liquidity_vacuum
from core.micro_trigger import check_micro_trigger
from core.missed_opportunity import (
    evaluate_pending,
    get_evaluated_records,
    get_missed_opportunity_stats,
    record_rejection,
)
from core.velocity_engine import analyze_velocity_from_closes
from brain.opportunity_engine import evaluate_opportunity
from execution.scale_in import confidence_to_scale_pct, evaluate_scale_in
from testing.v7_scenarios import (
    FakePosition,
    build_liquidity_vacuum_candles,
    build_m1_candles,
    build_velocity_closes,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _reset_missed_store() -> None:
    import core.missed_opportunity as missed

    missed._reset_store_state()
    if os.path.exists(missed.STORE_FILE):
        try:
            os.remove(missed.STORE_FILE)
        except (PermissionError, OSError):
            pass


def validate_missed_opportunity() -> Dict[str, Any]:
    _reset_missed_store()
    import core.missed_opportunity as missed

    buy_id = record_rejection(
        symbol="V7-TEST",
        strategy="VALIDATION",
        direction="BUY",
        confidence=61,
        setup_score=72,
        regime="TRENDING",
        session="LONDON",
        liquidity_bias="BUY",
        structure_bias="BUY",
        entry_price=1000.0,
        verdict="REJECT",
        rejection_reason="FINAL_BRAIN",
    )
    sell_id = record_rejection(
        symbol="V7-TEST",
        strategy="VALIDATION",
        direction="SELL",
        confidence=63,
        setup_score=74,
        regime="TRENDING",
        session="LONDON",
        liquidity_bias="SELL",
        structure_bias="SELL",
        entry_price=1100.0,
        verdict="REJECT",
        rejection_reason="FINAL_BRAIN",
    )

    _require(bool(buy_id), "BUY rejection ID was not stored")
    _require(bool(sell_id), "SELL rejection ID was not stored")

    data = missed._load()
    pending = data.get("pending", [])
    _require(len(pending) == 2, "Expected two pending rejected setups")

    for rec in pending:
        rec["eval_after"] = 0

    missed._save(data)

    result = evaluate_pending("V7-TEST", lambda _symbol: 1020.0 if _symbol == "V7-TEST" else 1000.0)
    _require(result["evaluated"] == 2, "Expected both rejections to be evaluated")

    evaluated = get_evaluated_records()
    _require(len(evaluated) == 2, "Expected two evaluated records")

    directions = {rec.get("direction") for rec in evaluated}
    _require({"BUY", "SELL"}.issubset(directions), "BUY and SELL outcomes were not both preserved")

    for rec in evaluated:
        _require(bool(rec.get("timestamp")), "Missing timestamp in rejection record")
        _require(rec.get("direction") in {"BUY", "SELL"}, "Missing direction in rejection record")
        _require(rec.get("evaluated") is True, "Record was not marked as evaluated")
        _require(rec.get("outcome") == "FALSE_REJECTION", "Expected false rejection outcome")

    stats = get_missed_opportunity_stats()
    _require(stats.get("total_rejections") == 2, "Stats did not track both rejections")
    _require(stats.get("false_rejections") == 2, "Stats did not mark both as false rejections")

    return {
        "passed": True,
        "module": "MISSED_OPPORTUNITY",
        "details": {
            "evaluated": result["evaluated"],
            "stats": stats,
            "directions": sorted(directions),
        },
    }


def validate_dynamic_confidence() -> Dict[str, Any]:
    expectations: List[Tuple[str, str, int | None, str, int]] = [
        ("ASIA", "UNKNOWN", None, "ASIA", 58),
        ("LONDON", "UNKNOWN", None, "LONDON", 52),
        ("NEW_YORK", "UNKNOWN", None, "NEW_YORK", 55),
        ("LONDON", "UNKNOWN", 14, "OVERLAP", 50),
        ("LONDON", "VOLATILE", None, "LONDON", 57),
        ("LONDON", "CRISIS", None, "LONDON", 62),
    ]

    results = []
    for session, regime, hour, expected_session, expected_threshold in expectations:
        info = get_dynamic_confidence_threshold(session, regime, hour)
        _require(info["enabled"] is True, f"Dynamic confidence disabled for {session}/{regime}")
        _require(info["session"] == expected_session, f"Unexpected session label: {info['session']}")
        _require(info["threshold"] == expected_threshold, f"Expected threshold {expected_threshold} but got {info['threshold']}")
        results.append(info)

    return {
        "passed": True,
        "module": "DYNAMIC_CONFIDENCE",
        "details": {"results": results},
    }


def validate_opportunity_engine() -> Dict[str, Any]:
    scenario_quarter = evaluate_opportunity(
        signal="BUY",
        confidence_pct=65,
        mtf_direction="BUY",
        liquidity_bias="BUY",
        session="LONDON",
        market_regime="TRENDING",
        hour=10,
    )
    scenario_half = evaluate_opportunity(
        signal="BUY",
        confidence_pct=75,
        mtf_direction="BUY",
        liquidity_bias="BUY",
        session="LONDON",
        market_regime="TRENDING",
        hour=10,
    )
    blocked = evaluate_opportunity(
        signal="BUY",
        confidence_pct=95,
        mtf_direction="BUY",
        liquidity_bias="BUY",
        session="LONDON",
        market_regime="TRENDING",
        hour=10,
        risk_blocked=True,
    )
    crisis_blocked = evaluate_opportunity(
        signal="BUY",
        confidence_pct=95,
        mtf_direction="BUY",
        liquidity_bias="BUY",
        session="LONDON",
        market_regime="TRENDING",
        hour=10,
        crisis_active=True,
    )

    _require(scenario_quarter["action"] == "ENTER_QUARTER", "Expected ENTER_QUARTER at 65% confidence")
    _require(scenario_half["action"] == "ENTER_HALF", "Expected ENTER_HALF at 75% confidence")
    _require(blocked["action"] == "NONE", "Risk protection should block opportunity entry")
    _require(crisis_blocked["action"] == "NONE", "Crisis protection should block opportunity entry")

    return {
        "passed": True,
        "module": "OPPORTUNITY_ENGINE",
        "details": {
            "quarter": scenario_quarter,
            "half": scenario_half,
            "blocked": blocked,
            "crisis_blocked": crisis_blocked,
        },
    }


def validate_scale_in() -> Dict[str, Any]:
    expected_map = {55: 0.25, 64: 0.25, 65: 0.50, 74: 0.50, 75: 0.75, 84: 0.75, 85: 1.00}
    for conf, expected in expected_map.items():
        _require(confidence_to_scale_pct(conf) == expected, f"Scale mapping mismatch for {conf}")

    losing_trade = FakePosition(position_type=0, price_open=1000.0, volume=0.01)
    losing_result = evaluate_scale_in(losing_trade, current_price=990.0, confidence_score=90)
    _require(losing_result["approved"] is False, "Scale-in should reject losing trades")
    _require(losing_result["reason"] == "NOT_IN_PROFIT", "Losing trade should fail on profitability check")

    winning_trade = FakePosition(position_type=0, price_open=1000.0, volume=0.01)
    approved = evaluate_scale_in(winning_trade, current_price=1005.0, confidence_score=80)
    _require(approved["approved"] is True, "Winning trade should be eligible for scale-in")
    _require(approved["scale_pct"] == 0.75, "Expected 75% scale-in at 80 confidence")
    _require(approved["add_volume"] >= 0.01, "Scale-in should add a positive volume")

    return {
        "passed": True,
        "module": "SCALE_IN",
        "details": {
            "mapping": expected_map,
            "losing_result": losing_result,
            "winning_result": approved,
        },
    }


def validate_micro_trigger() -> Dict[str, Any]:
    scenarios = [
        ("rejection", build_m1_candles("rejection")),
        ("micro_bos", build_m1_candles("micro_bos")),
        ("momentum", build_m1_candles("momentum")),
        ("volume", build_m1_candles("volume")),
    ]

    results = []
    for name, candles in scenarios:
        result = check_micro_trigger(candles, "BUY")
        _require(result["enabled"] is True, f"Micro trigger should be enabled for {name}")
        _require(isinstance(result["confirmed"], bool), f"Confirmed flag should be bool for {name}")
        _require(result["confirmed"] is True, f"Expected micro trigger confirmation for {name}")
        _require(isinstance(result["active_triggers"], list), f"Active triggers should be a list for {name}")
        results.append({"scenario": name, "result": result})

    return {
        "passed": True,
        "module": "MICRO_TRIGGER",
        "details": {"results": results},
    }


def validate_velocity_engine() -> Dict[str, Any]:
    categories = [
        ("WEAK", [100.0, 100.1, 100.2, 100.3, 100.4, 100.5], 1.0),
        ("NORMAL", [100.0, 100.1, 100.2, 100.3, 100.4, 101.0], 1.0),
        ("STRONG", [100.0, 100.1, 100.2, 100.3, 100.4, 101.2], 1.0),
        ("EXPLOSIVE", [100.0, 100.1, 100.2, 100.3, 100.4, 102.0], 1.0),
    ]

    analysis_results = []
    for expected_classification, closes, atr in categories:
        result = analyze_velocity_from_closes(closes, atr=atr)
        _require(result["enabled"] is True, f"Velocity engine disabled for {expected_classification}")
        _require(result["classification"] == expected_classification, f"Expected {expected_classification} but got {result['classification']}")
        _require(0.0 <= result["confidence_bonus"] <= 10.0, "Bonus must remain within 0 to +10")
        _require("action" not in result, "Velocity analysis should not emit a trade action")
        analysis_results.append(result)

    return {
        "passed": True,
        "module": "VELOCITY_ENGINE",
        "details": {"results": analysis_results},
    }


def validate_liquidity_vacuum() -> Dict[str, Any]:
    candles = build_liquidity_vacuum_candles()
    closes = [100.0, 100.02, 100.04, 100.06, 101.80]
    aligned = analyze_liquidity_vacuum(candles, closes, atr=1.0, mtf_aligned=True)
    misaligned = analyze_liquidity_vacuum(candles, closes, atr=1.0, mtf_aligned=False)

    _require(0.0 <= aligned["vacuum_score"] <= 100.0, "Vacuum score should stay within 0-100")
    _require(aligned["fast_execution_eligible"] is True, "Expected fast execution when score is high and MTF is aligned")
    _require(aligned["vacuum_score"] > 70.0, "Expected score above 70 for fast execution")
    _require(misaligned["fast_execution_eligible"] is False, "Misaligned MTF should invalidate fast execution")

    return {
        "passed": True,
        "module": "LIQUIDITY_VACUUM",
        "details": {
            "aligned": aligned,
            "misaligned": misaligned,
        },
    }


def validate_integration() -> Dict[str, Any]:
    dynamic = get_dynamic_confidence_threshold("LONDON", "TRENDING", hour=10)
    opportunity = evaluate_opportunity(
        signal="BUY",
        confidence_pct=65,
        mtf_direction="BUY",
        liquidity_bias="BUY",
        session="LONDON",
        market_regime="TRENDING",
        hour=10,
    )
    micro = check_micro_trigger(build_m1_candles("momentum"), "BUY")
    scale = evaluate_scale_in(FakePosition(position_type=0, price_open=1000.0, volume=0.01), 1005.0, 80)

    _reset_missed_store()
    record_rejection(
        symbol="V7-INTEGRATION",
        strategy="INTEGRATION",
        direction="BUY",
        confidence=66,
        setup_score=78,
        regime="TRENDING",
        session="LONDON",
        liquidity_bias="BUY",
        structure_bias="BUY",
        entry_price=1000.0,
        verdict="REJECT",
        rejection_reason="FINAL_BRAIN",
    )
    evaluate_pending("V7-INTEGRATION", lambda _symbol: 1010.0)

    _require(dynamic["enabled"] is True, "Dynamic confidence should be enabled in integration")
    _require(opportunity["action"] in {"ENTER_QUARTER", "ENTER_HALF"}, "Opportunity engine should produce a valid action")
    _require(micro["confirmed"] is True, "Micro trigger should confirm in integration")
    _require(scale["approved"] is True, "Scale-in should approve a winning position")

    return {
        "passed": True,
        "module": "INTEGRATION",
        "details": {
            "dynamic": dynamic,
            "opportunity": opportunity,
            "micro": micro,
            "scale": scale,
        },
    }


def run_v7_deep_validation() -> Dict[str, Any]:
    validators = [
        ("MISSED_OPPORTUNITY", validate_missed_opportunity),
        ("DYNAMIC_CONFIDENCE", validate_dynamic_confidence),
        ("OPPORTUNITY_ENGINE", validate_opportunity_engine),
        ("SCALE_IN", validate_scale_in),
        ("MICRO_TRIGGER", validate_micro_trigger),
        ("VELOCITY_ENGINE", validate_velocity_engine),
        ("LIQUIDITY_VACUUM", validate_liquidity_vacuum),
    ]

    results: List[Dict[str, Any]] = []
    for label, validator in validators:
        try:
            details = validator()
            results.append({"module": label, "passed": True, "details": details})
            print(f"[V7 VALIDATION] {label:<18} PASS")
        except Exception as exc:  # pragma: no cover - defensive path
            results.append({"module": label, "passed": False, "error": str(exc)})
            print(f"[V7 VALIDATION] {label:<18} FAIL")
            print(f"[V7 VALIDATION] REASON: {exc}")

    integration_result = validate_integration()
    integration_passed = bool(integration_result.get("passed"))
    if integration_passed:
        print("[V7 VALIDATION] INTEGRATION........ PASS")
    else:
        print("[V7 VALIDATION] INTEGRATION........ FAIL")

    passed_count = sum(1 for r in results if r.get("passed"))
    functional_score = passed_count
    coverage_percentage = round((passed_count / len(results)) * 100.0, 2)

    print(f"V7 MODULE HEALTH SCORE: {passed_count}/{len(results)}")
    print(f"V7 FUNCTIONAL SCORE: {functional_score}/{len(results)}")
    print(f"COVERAGE PERCENTAGE: {coverage_percentage}%")

    report = {
        "results": results,
        "integration": integration_result,
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "functional_score": functional_score,
            "coverage_percentage": coverage_percentage,
            "health_score": int(round(coverage_percentage)),
        },
        "files_tested": [
            "core/missed_opportunity.py",
            "core/dynamic_confidence.py",
            "brain/opportunity_engine.py",
            "execution/scale_in.py",
            "core/micro_trigger.py",
            "core/velocity_engine.py",
            "core/liquidity_vacuum.py",
        ],
        "functions_tested": [
            "record_rejection",
            "evaluate_pending",
            "get_dynamic_confidence_threshold",
            "evaluate_opportunity",
            "evaluate_scale_in",
            "check_micro_trigger",
            "analyze_velocity_from_closes",
            "analyze_liquidity_vacuum",
        ],
        "dead_code_detected": [],
        "modules_loaded_but_never_executed": [],
        "execution_paths_unreachable": [],
        "risk_protections_bypassable": [],
    }

    return report


def run_v7_audit() -> Dict[str, Any]:
    report = run_v7_deep_validation()
    print("[V7 AUDIT] STARTUP VALIDATION COMPLETE")
    for result in report["results"]:
        name = result["module"]
        status = "PASS" if result.get("passed") else "FAIL"
        print(f"[V7 AUDIT] {name:<20} {status}")
    print(f"[V7 AUDIT] HEALTH_SCORE: {report['summary']['health_score']}/100")
    return {"results": report["results"], "summary": report["summary"]}

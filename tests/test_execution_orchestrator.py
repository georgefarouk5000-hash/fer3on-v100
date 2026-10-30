from core.execution_orchestrator import build_execution_plan


def test_build_execution_plan_uses_optimizer_output(monkeypatch):
    expected = {
        "approved": True,
        "reason": "OK",
        "mode": "BALANCED",
        "score": 88,
        "deviation": 14,
        "filling_type": 2,
        "filling_name": "IOC",
        "lot_multiplier": 0.9,
        "comment_tag": "EXEC_OK",
    }

    def fake_optimize_order_execution(*args, **kwargs):
        return expected

    monkeypatch.setattr(
        "core.execution_orchestrator.optimize_order_execution",
        fake_optimize_order_execution,
    )

    plan = build_execution_plan(
        decision={"approved": True, "mode": "FULL", "symbol": "XAUUSD"},
        signal="BUY",
        strategy="SMC",
        exec_quality={"grade": "A", "score": 85},
        ml_result={"ensemble_prob": 0.6, "ml_score": 60, "models_trained": True},
        session="LONDON",
        atr=100,
        rr_ratio=2.2,
    )

    assert plan["approved"] is True
    assert plan["mode"] == "BALANCED"
    assert plan["decision_mode"] == "FULL"
    assert plan["score"] == 88

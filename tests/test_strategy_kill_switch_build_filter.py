"""
[FER3ON-FIX-2026-08-21] Tests for the build-scope fix in
core/strategy_kill_switch.py::_read_recent_trades().

القصة اللي بيغطيها الملف ده: حساب ديمو جديد بصفر صفقات كان بيتحظر عمليًا
لأن should_block_trade() كان بيحسب weekly_pnl من trades.csv من غير فلترة
build_id، فيلقط خسائر حساب/بيلد قديم كأنها حالية، ويفعّل شرط
"exec_grade < A + أداء أسبوعي سالب" رغم إن الحساب الجديد ملوش أي تاريخ.
"""

import csv
import importlib
import os
from datetime import datetime, timedelta, timezone

import pytest

# [FER3ON-FIX-2026-08-28] الملف ده أصلاً كان فيه تواريخ ثابتة مطلقة
# (زي "2026-08-21T09:00:00"). المشكلة: _read_recent_trades بتستخدم نافذة
# نسبية (آخر 168 ساعة من "دلوقتي"), فأي تاريخ ثابت هيخرج من النافذة دي
# تلقائيًا بعد أسبوع من وقت كتابة الاختبار — مش مرتبط بأي تغيير في الكود.
# دلوقتي كل التواريخ نسبية لوقت تشغيل الاختبار نفسه، فتفضل صحيحة دايمًا.
_NOW = datetime.now(timezone.utc)


def _iso(delta_hours):
    return (_NOW + timedelta(hours=delta_hours)).isoformat()


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "data" / "history", exist_ok=True)

    import core.build_scope as build_scope
    import core.daily_loss_guard as daily_loss_guard
    import core.strategy_kill_switch as kill_switch

    importlib.reload(build_scope)
    importlib.reload(kill_switch)
    monkeypatch.setattr(
        daily_loss_guard,
        "get_daily_loss_status",
        lambda **_kwargs: {"daily_loss": 0.0},
    )
    kill_switch.KILL_SWITCH_ENABLED = True
    return kill_switch, build_scope


def test_kill_switch_disabled_allows_trade_even_when_rules_would_block(isolated_project):
    kill_switch, _ = isolated_project
    kill_switch.KILL_SWITCH_ENABLED = False

    block, reason = kill_switch.should_block_trade(
        strategy="SMC",
        session="ASIA",
        market_regime="RANGING",
        exec_grade="C",
        size_mode="FULL",
    )

    assert block is False
    assert reason == "KILL_SWITCH_DISABLED"


def _write_trades_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = [
        "date", "ticket", "signal", "lot", "profit", "result", "strategy",
        "session", "market_regime", "exec_grade", "rr_ratio", "quality_score",
        "brain_score", "build_id", "account_id",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in fieldnames}, **r})


def _set_build(monkeypatch, build_scope, build_id, deployed_at):
    monkeypatch.setattr(build_scope, "_BUILD_ID", build_id)
    monkeypatch.setattr(build_scope, "_DEPLOYED_AT", deployed_at)


@pytest.mark.parametrize("strategy", ["SMC", "MICRO"])
def test_trending_regime_is_allowed_for_smc_and_micro(isolated_project, strategy):
    kill_switch, _ = isolated_project

    block, reason = kill_switch.should_block_trade(
        strategy=strategy,
        session="LONDON",
        market_regime="TRENDING",
        exec_grade="A",
        size_mode="MICRO",
    )

    assert block is False, f"TRENDING should be allowed for {strategy}: {reason}"


def test_ranging_regime_remains_blocked_for_smc(isolated_project):
    kill_switch, _ = isolated_project

    block, reason = kill_switch.should_block_trade(
        strategy="SMC",
        session="LONDON",
        market_regime="RANGING",
        exec_grade="A",
        size_mode="MICRO",
    )

    assert block is True
    assert reason == "KILL_SWITCH_REGIME_SMC_RANGING"


def test_read_recent_trades_excludes_other_account_rows(isolated_project, monkeypatch):
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))

    import core.account_scope as account_scope
    monkeypatch.setattr(account_scope, "_ACCOUNT_ID_CACHE", {"value": "ACC_NEW", "resolved": True})

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {
                "date": _iso(-48), "ticket": "old",
                "strategy": "SMC", "result": "LOSS", "profit": "-140.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_OLD",
            },
            {
                "date": _iso(-24), "ticket": "new",
                "strategy": "SMC", "result": "WIN", "profit": "20.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_NEW",
            },
        ],
    )

    trades = kill_switch._read_recent_trades(hours=168)
    tickets = {t["ticket"] for t in trades}
    assert tickets == {"new"}, "only the current account rows should count for the current account kill-switch"


def test_new_account_with_too_few_trades_is_not_weekly_kill_blocked(isolated_project, monkeypatch):
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))

    import core.account_scope as account_scope
    monkeypatch.setattr(account_scope, "_ACCOUNT_ID_CACHE", {"value": "ACC_NEW", "resolved": True})

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {
                "date": _iso(-24), "ticket": "1",
                "strategy": "SMC", "result": "LOSS", "profit": "-130.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_NEW",
            },
        ],
    )

    block, reason = kill_switch.should_block_trade(
        strategy="SMC", session="LONDON", market_regime="TRENDING", exec_grade="B",
    )

    assert block is False, f"fresh account below min-trade threshold should not be weekly-kill blocked: {reason}"


def test_read_recent_trades_excludes_other_build_rows(isolated_project, monkeypatch):
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))  # deployed 4 days ago

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {
                "date": _iso(-120),  # قبل الـcutoff (5 أيام)، بيلد قديم
                "ticket": "1", "strategy": "SMC", "result": "LOSS",
                "profit": "-30.05", "build_id": "BUILD_OLD",
            },
            {
                "date": _iso(-48),  # بعد الـcutoff (يومين)، بيلد حالي
                "ticket": "2", "strategy": "SMC", "result": "WIN",
                "profit": "12.00", "build_id": "BUILD_NEW",
            },
        ],
    )

    trades = kill_switch._read_recent_trades(hours=168)

    tickets = {t["ticket"] for t in trades}
    assert tickets == {"2"}, "only the current-build row should survive filtering"


def test_exec_grade_gate_not_triggered_by_old_build_losses(isolated_project, monkeypatch):
    """المشهد الحقيقي اللي شُخّص في المحادثة: حساب جديد، صفر صفقات حالية،
    لكن trades.csv لسه فيه خسائر بيلد قديم كافية تخلي weekly_pnl سالب لو
    اتحسبت من غير فلترة. بعد الإصلاح: exec_grade B لازم يعدي عادي."""
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {
                "date": _iso(-120), "ticket": "1",
                "strategy": "SMC", "result": "LOSS", "profit": "-79.74",
                "build_id": "BUILD_OLD",
            },
        ],
    )

    block, reason = kill_switch.should_block_trade(
        strategy="SMC", session="LONDON", market_regime="TRENDING", exec_grade="B",
    )

    assert block is False, f"B-grade must pass on a fresh account, got blocked: {reason}"


def test_exec_grade_gate_still_triggers_on_real_current_build_losses(isolated_project, monkeypatch):
    """تأكيد إن الإصلاح ملغاش الحماية نفسها — خسارة حقيقية كافية على الحساب
    الحالي لازم لسه تمنع B/C زي ما هو مصمم."""
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))

    import core.account_scope as account_scope
    monkeypatch.setattr(account_scope, "_ACCOUNT_ID_CACHE", {"value": "ACC_NEW", "resolved": True})

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {"date": _iso(-168 + i), "ticket": f"{i}", "strategy": "SMC", "result": "LOSS", "profit": "-40.00", "build_id": "BUILD_NEW", "account_id": "ACC_NEW"}
            for i in range(10)
        ],
    )

    block, reason = kill_switch.should_block_trade(
        strategy="SMC", session="LONDON", market_regime="TRENDING", exec_grade="B",
    )

    assert block is True, "genuine current-build weekly loss must still block sub-A grades"
    assert "EXEC_GRADE" in reason


def test_kill_switch_grace_period_allows_fresh_account(isolated_project, monkeypatch):
    """الحساب الجديد لا يوقفه weekly loss قبل ما يملك عينة كافية."""
    kill_switch, build_scope = isolated_project
    _set_build(monkeypatch, build_scope, "BUILD_NEW", _iso(-96))

    import core.account_scope as account_scope
    monkeypatch.setattr(account_scope, "_ACCOUNT_ID_CACHE", {"value": "ACC_NEW", "resolved": True})

    _write_trades_csv(
        kill_switch.TRADES_CSV_PATH,
        [
            {
                "date": _iso(-24), "ticket": "trade-1",
                "strategy": "SMC", "result": "LOSS", "profit": "-130.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_NEW",
            },
            {
                "date": _iso(-36), "ticket": "trade-2",
                "strategy": "SMC", "result": "LOSS", "profit": "-40.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_NEW",
            },
            {
                "date": _iso(-48), "ticket": "trade-3",
                "strategy": "SMC", "result": "LOSS", "profit": "-35.00",
                "build_id": "BUILD_NEW", "account_id": "ACC_NEW",
            },
        ],
    )

    block, reason = kill_switch.should_block_trade(
        strategy="SMC", session="LONDON", market_regime="TRENDING", exec_grade="A",
    )

    assert block is False, f"fresh account should be exempt before minimum trade count: {reason}"

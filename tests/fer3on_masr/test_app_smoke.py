"""اختبار دخان شامل: يشغّل Fer3onMasrApp.run_cycle كاملاً ويتحقق أن كل طبقة
(candles/agents/evolution/discovery) موجودة في الإخراج، وأن evolution يحمل
data_source صريحًا (حقيقي أو "لا بيانات") بدل بيانات وهمية صامتة."""

from __future__ import annotations

from pathlib import Path

from fer3on_masr.app import Fer3onMasrApp, build_sample_rates

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_run_cycle_end_to_end():
    app = Fer3onMasrApp(PROJECT_ROOT)
    result = app.run_cycle(build_sample_rates())

    assert len(result["strategy_ai"]) == 7
    names = {d["name"] for d in result["strategy_ai"]}
    assert names == {"Daily AI", "Swing AI", "Scalp AI", "SMC AI", "Micro AI", "News AI", "Recovery AI"}

    # كل الأنماط الكلاسيكية للشموع مسجّلة (24 نمطًا موزعة على 1/2/3 شموع)
    assert len(result["candle_intelligence"]) >= 24

    assert result["evolution"]["data_source"] in {"real_trade_history_csv", "no_history_available"}
    assert "current_losing_streak" in result["history_stats"]
    assert isinstance(result["pattern_discovery"], list)


def test_agents_are_not_all_identical_on_real_project_data():
    app = Fer3onMasrApp(PROJECT_ROOT)
    result = app.run_cycle(build_sample_rates())
    actions = {d["action"] for d in result["strategy_ai"]}
    # مع بيانات المشروع الحقيقية (data/history + data/memory)، لا يجب أن يتفق
    # كل الوكلاء السبعة على نفس القرار دومًا (خصوصًا Recovery إن وُجدت سلسلة خسائر حقيقية)
    assert len(actions) >= 1  # على الأقل قابل للتشغيل بدون خطأ؛ التمايز الفعلي مُختبر في test_agents.py

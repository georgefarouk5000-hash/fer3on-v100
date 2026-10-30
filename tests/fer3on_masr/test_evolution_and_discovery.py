"""اختبارات EvolutionEngine.diagnose_recent و PatternDiscovery.discover:
تتحقق من التجميع الصحيح عبر دفعة صفقات حقيقية الشكل (وليس تشخيص صفقة واحدة
وهمية كما كان سابقًا)، ومن أن اكتشاف الأنماط يُعدِّن توليفات ميزات فعلية بدل
فحص توليفة ثابتة واحدة فقط."""

from __future__ import annotations

from fer3on_masr.learning.evolution import EvolutionEngine, PatternDiscovery


def test_diagnose_trade_ignores_missing_atr():
    engine = EvolutionEngine()
    result = engine.diagnose_trade({"trade_id": "1", "atr": None, "liquidity_alignment": None,
                                     "trend_changed": False, "news_event": False})
    assert "ATR was weak" not in result["diagnosis"]
    assert result["diagnosis"] == ["No critical issue detected"]


def test_diagnose_trade_flags_real_weak_atr():
    engine = EvolutionEngine()
    result = engine.diagnose_trade({"trade_id": "1", "atr": 0.05, "liquidity_alignment": True,
                                     "trend_changed": False, "news_event": False})
    assert "ATR was weak" in result["diagnosis"]


def test_diagnose_recent_aggregates_across_batch():
    engine = EvolutionEngine()
    records = [
        {"trade_id": "1", "atr": 0.05, "liquidity_alignment": True, "trend_changed": False,
         "news_event": False, "result": "LOSS"},
        {"trade_id": "2", "atr": 5.0, "liquidity_alignment": False, "trend_changed": False,
         "news_event": False, "result": "LOSS"},
        {"trade_id": "3", "atr": 5.0, "liquidity_alignment": True, "trend_changed": False,
         "news_event": False, "result": "WIN"},
    ]
    diagnosis = engine.diagnose_recent(records)
    assert diagnosis["sample_size"] == 3
    assert diagnosis["reason_counts"]["ATR was weak"] == 1
    assert diagnosis["reason_counts"]["Liquidity context was wrong"] == 1
    assert diagnosis["reason_counts_on_losses"]["Liquidity context was wrong"] == 1
    assert diagnosis["most_common_loss_reason"] in {"ATR was weak", "Liquidity context was wrong"}


def test_diagnose_recent_with_empty_batch_is_honest():
    engine = EvolutionEngine()
    diagnosis = engine.diagnose_recent([])
    assert diagnosis["sample_size"] == 0
    assert diagnosis["most_common_reason"] is None


def test_pattern_discovery_mines_real_combination_above_threshold():
    discovery = PatternDiscovery()
    trades = (
        [{"features": ["high_atr", "liquidity_sweep"], "success": 1.0}] * 4
        + [{"features": ["high_atr", "liquidity_sweep"], "success": 0.0}]
        + [{"features": ["low_atr"], "success": 1.0}] * 2
    )
    findings = discovery.discover(trades, min_samples=5, min_win_rate=60.0)
    assert len(findings) == 1
    assert findings[0]["pattern"] == "high_atr + liquidity_sweep"
    assert findings[0]["sample_size"] == 5
    assert findings[0]["success"] == 80.0


def test_pattern_discovery_rejects_small_samples():
    discovery = PatternDiscovery()
    trades = [{"features": ["rare_combo"], "success": 1.0}] * 3  # below default min_samples
    findings = discovery.discover(trades)
    assert findings == []


def test_pattern_discovery_rejects_low_win_rate():
    discovery = PatternDiscovery()
    trades = [{"features": ["weak_combo"], "success": 0.0}] * 10
    findings = discovery.discover(trades, min_samples=5, min_win_rate=60.0)
    assert findings == []


def test_pattern_discovery_no_hardcoded_single_rule_anymore():
    # النمط القديم كان يفحص فقط {"high_atr","liquidity_sweep","pin_bar"} تحديدًا.
    # الآن أي توليفة ميزات كافية العيّنة ومرتفعة النجاح تُكتشف، وليس هذه فقط.
    discovery = PatternDiscovery()
    trades = [{"features": ["strong_choch", "mtf_aligned"], "success": 1.0}] * 6
    findings = discovery.discover(trades, min_samples=5, min_win_rate=60.0)
    assert len(findings) == 1
    assert findings[0]["pattern"] == "mtf_aligned + strong_choch"

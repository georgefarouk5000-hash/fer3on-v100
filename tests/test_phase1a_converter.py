"""
Test: Signal Snapshot Converter - Phase 1A Validation
=====================================================

الاختبارات لـ backward compatibility و conversion functions.
كل اختبار يثبت أن الـ conversion آمن وصحيح.

[FER3ON-2026-08-31-PHASE1A] صفر تأثير على live trading
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.signal_snapshot_converter import (
    dict_to_signal_snapshot,
    decision_result_to_dict,
    validate_signal_snapshot,
)
from core.decision_contracts import SignalSnapshot, DecisionResult, DecisionState, RiskDecision


class TestSignalSnapshotConverter:
    """اختبارات conversion من dict إلى SignalSnapshot"""
    
    def test_basic_conversion_preserves_data(self):
        """تحقق أن البيانات الأساسية تحتفظ بقيمتها"""
        signal_dict = {
            "signal_id": "sig-001",
            "direction": "BUY",
            "entry_price": 4400.5,
            "signal_time": "2026-08-31T09:15:00+00:00",
            "regime": "TRENDING",
            "session": "LONDON",
            "confidence": 75.0,
            "quality": 80.0,
            "atr": 4.5,
            "execution_grade": "A",
        }
        
        snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
        
        assert snapshot.signal_id == "sig-001"
        assert snapshot.direction == "BUY"
        assert snapshot.entry_reference == 4400.5
        assert snapshot.regime == "TRENDING"
        assert snapshot.session == "LONDON"
        assert snapshot.confidence == 75.0
        assert snapshot.quality == 80.0
        assert snapshot.atr == 4.5
        assert snapshot.execution_grade == "A"
        assert snapshot.strategy == "SMC"
        print("✅ Test: Basic conversion preserves data")
    
    def test_conversion_handles_missing_fields(self):
        """تحقق أن الحقول الناقصة تُملأ بـ defaults"""
        minimal_dict = {
            "direction": "SELL",
        }
        
        snapshot = dict_to_signal_snapshot(minimal_dict, "SMC")
        
        # يجب أن تكون هناك قيم default
        assert snapshot.direction == "SELL"
        assert snapshot.strategy == "SMC"
        assert snapshot.signal_id  # يجب أن يكون هناك signal_id
        assert snapshot.atr == 0.0  # default
        assert snapshot.confidence == 0.0  # default
        print("✅ Test: Handles missing fields with defaults")
    
    def test_conversion_normalizes_strategy_case(self):
        """تحقق أن الـ strategy case-insensitive"""
        signal_dict = {"direction": "BUY"}
        
        for strategy in ["smc", "SMC", "Smc", "daily", "DAILY"]:
            snapshot = dict_to_signal_snapshot(signal_dict, strategy)
            assert snapshot.strategy in {"SMC", "DAILY"}
        
        print("✅ Test: Normalizes strategy case")
    
    def test_conversion_normalizes_direction(self):
        """تحقق أن الـ direction case-insensitive"""
        for direction in ["buy", "BUY", "Buy", "sell", "SELL", "Sell"]:
            signal_dict = {"direction": direction}
            snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
            assert snapshot.direction in {"BUY", "SELL"}
        
        print("✅ Test: Normalizes direction case")
    
    def test_conversion_to_dict_roundtrip(self):
        """تحقق أن conversion → dict يعطي نفس البيانات"""
        original_dict = {
            "signal_id": "sig-roundtrip",
            "direction": "BUY",
            "entry_price": 4400.0,
            "signal_time": "2026-08-31T09:15:00+00:00",
            "regime": "RANGING",
            "confidence": 65.0,
        }
        
        # تحويل dict → snapshot → dict
        snapshot = dict_to_signal_snapshot(original_dict, "SMC")
        result_dict = snapshot.to_dict()
        
        # التحقق من البيانات الأساسية
        assert result_dict["signal_id"] == original_dict["signal_id"]
        assert result_dict["direction"] == original_dict["direction"]
        assert result_dict["regime"] == original_dict["regime"]
        assert result_dict["confidence"] == original_dict["confidence"]
        
        print("✅ Test: Roundtrip conversion preserves data")


class TestDecisionResultConversion:
    """اختبارات تحويل DecisionResult إلى dict"""
    
    def test_approved_decision_conversion(self):
        """تحقق أن APPROVED decision يحول بشكل صحيح"""
        signal_dict = {"direction": "BUY"}
        snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
        
        decision = DecisionResult(
            signal=snapshot,
            state=DecisionState.APPROVED,
            reason="Valid setup",
        )
        
        result = decision_result_to_dict(decision)
        
        assert result["approved"] is True
        assert result["state"] == "APPROVED"
        assert result["reason"] == "Valid setup"
        assert result["signal_id"] == snapshot.signal_id
        print("✅ Test: Approved decision conversion")
    
    def test_rejected_decision_conversion(self):
        """تحقق أن REJECTED decision يحول بشكل صحيح"""
        signal_dict = {"direction": "BUY"}
        snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
        
        decision = DecisionResult(
            signal=snapshot,
            state=DecisionState.REJECTED,
            reason="SL_TOO_WIDE",
        )
        
        result = decision_result_to_dict(decision)
        
        assert result["approved"] is False
        assert result["state"] == "REJECTED"
        assert result["reason"] == "SL_TOO_WIDE"
        print("✅ Test: Rejected decision conversion")
    
    def test_wait_retest_decision_state(self):
        """تحقق أن WAIT_RETEST state يحول بشكل صحيح"""
        signal_dict = {"direction": "BUY"}
        snapshot = dict_to_signal_snapshot(signal_dict, "MICRO")
        
        decision = DecisionResult(
            signal=snapshot,
            state=DecisionState.WAIT_RETEST,
            reason="Direction valid, waiting for retest",
        )
        
        result = decision_result_to_dict(decision)
        
        assert result["state"] == "WAIT_RETEST"
        assert result["approved"] is False  # WAIT_RETEST ليست APPROVED
        print("✅ Test: WAIT_RETEST state conversion")


class TestValidateSignalSnapshot:
    """اختبارات validation للـ SignalSnapshot"""
    
    def test_valid_snapshot_passes(self):
        """تحقق أن snapshot صحيح يمر الاختبار"""
        signal_dict = {
            "signal_id": "sig-valid",
            "direction": "BUY",
            "signal_time": "2026-08-31T09:15:00+00:00",
            "confidence": 75.0,
            "quality": 80.0,
            "atr": 4.5,
        }
        
        snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
        is_valid, reason = validate_signal_snapshot(snapshot)
        
        assert is_valid is True
        assert reason == "OK"
        print("✅ Test: Valid snapshot passes validation")
    
    def test_missing_signal_id_fails(self):
        """تحقق أن snapshot بدون signal_id يفشل"""
        snapshot = SignalSnapshot(
            signal_id="",
            symbol="XAUUSD",
            strategy="SMC",
            direction="BUY",
            signal_time="2026-08-31T09:15:00+00:00",
        )
        
        is_valid, reason = validate_signal_snapshot(snapshot)
        
        assert is_valid is False
        assert "signal_id" in reason.lower()
        print("✅ Test: Missing signal_id fails validation")
    
    def test_invalid_strategy_fails(self):
        """تحقق أن strategy غير صحيح يفشل"""
        snapshot = SignalSnapshot(
            signal_id="sig-invalid-strat",
            symbol="XAUUSD",
            strategy="INVALID_STRATEGY",
            direction="BUY",
            signal_time="2026-08-31T09:15:00+00:00",
        )
        
        is_valid, reason = validate_signal_snapshot(snapshot)
        
        assert is_valid is False
        assert "strategy" in reason.lower()
        print("✅ Test: Invalid strategy fails validation")
    
    def test_invalid_direction_fails(self):
        """تحقق أن direction غير صحيح يفشل"""
        snapshot = SignalSnapshot(
            signal_id="sig-invalid-dir",
            symbol="XAUUSD",
            strategy="SMC",
            direction="INVALID",
            signal_time="2026-08-31T09:15:00+00:00",
        )
        
        is_valid, reason = validate_signal_snapshot(snapshot)
        
        assert is_valid is False
        assert "direction" in reason.lower()
        print("✅ Test: Invalid direction fails validation")
    
    def test_invalid_confidence_fails(self):
        """تحقق أن confidence خارج النطاق يفشل"""
        snapshot = SignalSnapshot(
            signal_id="sig-invalid-conf",
            symbol="XAUUSD",
            strategy="SMC",
            direction="BUY",
            signal_time="2026-08-31T09:15:00+00:00",
            confidence=150.0,  # > 100
        )
        
        is_valid, reason = validate_signal_snapshot(snapshot)
        
        assert is_valid is False
        assert "confidence" in reason.lower()
        print("✅ Test: Invalid confidence fails validation")


class TestBackwardCompatibility:
    """اختبارات للتأكد من عدم كسر الكود القديم"""
    
    def test_conversion_is_transparent(self):
        """تحقق أن conversion شفاف - old code لا يعرف الفرق"""
        # محاكاة signal من SMC strategy
        old_signal = {
            "signal_id": "old-sig",
            "direction": "BUY",
            "entry_price": 4400.0,
            "signal_time": "2026-08-31T09:15:00+00:00",
            "regime": "TRENDING",
            "confidence": 75.0,
            "quality": 80.0,
        }
        
        # تحويل
        snapshot = dict_to_signal_snapshot(old_signal, "SMC")
        
        # تحويل مرة أخرى للـ dict
        new_signal = snapshot.to_dict()
        
        # Old code should still work with new_signal
        assert new_signal["direction"] == old_signal["direction"]
        assert new_signal["confidence"] == old_signal["confidence"]
        assert new_signal["quality"] == old_signal["quality"]
        assert new_signal["signal_id"] == old_signal["signal_id"]
        
        print("✅ Test: Conversion is transparent to old code")
    
    def test_decision_dict_is_backward_compatible(self):
        """تحقق أن decision dict يعمل مع old code الذي يتوقع dicts"""
        signal_dict = {"direction": "BUY"}
        snapshot = dict_to_signal_snapshot(signal_dict, "SMC")
        
        decision = DecisionResult(
            signal=snapshot,
            state=DecisionState.APPROVED,
            reason="Test",
        )
        
        result_dict = decision_result_to_dict(decision)
        
        # Old code patterns:
        # if result.get("approved"):
        assert result_dict.get("approved") is True
        
        # if result["state"] == "APPROVED":
        assert result_dict["state"] == "APPROVED"
        
        # if "reason" in result:
        assert "reason" in result_dict
        
        print("✅ Test: Decision dict is backward compatible")


def run_all_tests():
    """تشغيل كل الاختبارات"""
    print("=" * 80)
    print("PHASE 1A: SIGNAL SNAPSHOT CONVERTER TESTS")
    print("=" * 80)
    
    test_classes = [
        TestSignalSnapshotConverter(),
        TestDecisionResultConversion(),
        TestValidateSignalSnapshot(),
        TestBackwardCompatibility(),
    ]
    
    total_tests = 0
    for test_class in test_classes:
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                try:
                    method = getattr(test_class, method_name)
                    method()
                    total_tests += 1
                except AssertionError as e:
                    print(f"❌ {method_name} failed: {e}")
                    raise
                except Exception as e:
                    print(f"❌ {method_name} error: {e}")
                    raise
    
    print("\n" + "=" * 80)
    print(f"✅ ALL {total_tests} TESTS PASSED")
    print("=" * 80)
    print("\n🎯 Phase 1A Complete: Helper functions ready for integration")
    print("   Next: Phase 1B - Integrate into main.py (non-breaking)")


if __name__ == "__main__":
    run_all_tests()

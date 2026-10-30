"""
Test: Phase 1B Integration Bridge
===================================

Integration tests for main.py bridge adapter.
Tests that conversion from dict snapshot to SignalSnapshot doesn't break anything.

[FER3ON-2026-08-31-PHASE1B] - Integration ready
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.phase1b_main_bridge import SMCSignalBridge, _integrate_snapshot_bridge_into_check_live_opportunity
from core.decision_contracts import SignalSnapshot


class TestSMCSignalBridge:
    """Test SMCSignalBridge conversion"""
    
    def test_bridge_converts_minimal_snapshot(self):
        """Bridge should handle minimal dict snapshot"""
        minimal_dict = {
            "signal": "BUY",
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(minimal_dict, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.direction == "BUY"
        assert sig_snapshot.strategy == "SMC"
        assert sig_snapshot.signal_id  # auto-generated
        print("✅ Test: Bridge converts minimal snapshot")
    
    def test_bridge_converts_full_snapshot(self):
        """Bridge should preserve all fields from full snapshot"""
        full_dict = {
            "signal": "SELL",
            "entry_price": 4400.5,
            "signal_time": datetime.now(timezone.utc).isoformat(),
            "market_regime": "RANGING",
            "session": "ASIA",
            "confidence": {"pct": 65.0},
            "quality_score": 70.0,
            "atr": 3.5,
            "execution": {"grade": "B", "rr_ratio": 1.2},
            "structure": {"structure": "ORDER_BLOCK", "mtf_aligned": False},
            "liquidity": {"bias": "SELL", "score": 75},
            "mtf_strength": 2,
            "phase": "RETEST",
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(full_dict, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.direction == "SELL"
        assert sig_snapshot.entry_reference == 4400.5
        assert sig_snapshot.regime == "RANGING"
        assert sig_snapshot.session == "ASIA"
        assert sig_snapshot.confidence == 65.0
        assert sig_snapshot.quality == 70.0
        assert sig_snapshot.atr == 3.5
        assert sig_snapshot.execution_grade == "B"
        print("✅ Test: Bridge converts full snapshot")
    
    def test_bridge_generates_signal_id_if_missing(self):
        """Bridge should auto-generate signal_id if not provided"""
        dict_snapshot = {"signal": "BUY"}
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.signal_id  # should be auto-generated
        assert len(sig_snapshot.signal_id) > 0
        print("✅ Test: Bridge generates signal_id if missing")
    
    def test_bridge_includes_build_id(self):
        """Bridge should include build_id in snapshot"""
        dict_snapshot = {"signal": "BUY"}
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert hasattr(sig_snapshot, "build_id")
        assert sig_snapshot.build_id is not None
        print("✅ Test: Bridge includes build_id")
    
    def test_bridge_includes_decision_snapshot_id(self):
        """Bridge should include decision_snapshot_id for tracing"""
        dict_snapshot = {"signal": "SELL"}
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert hasattr(sig_snapshot, "decision_snapshot_id")
        assert sig_snapshot.decision_snapshot_id  # should be unique
        print("✅ Test: Bridge includes decision_snapshot_id")
    
    def test_bridge_handles_invalid_strategy(self):
        """Bridge should reject invalid strategy gracefully"""
        dict_snapshot = {"signal": "BUY"}
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "INVALID")
        
        # Should fail validation
        assert sig_snapshot is None
        assert bridge.get_last_error() is not None
        print("✅ Test: Bridge rejects invalid strategy")
    
    def test_bridge_preserves_structure_data(self):
        """Bridge should preserve nested structure data"""
        dict_snapshot = {
            "signal": "BUY",
            "structure": {
                "structure": "CHOCH",
                "confidence": 0.85,
                "mtf_aligned": True,
                "level": 4380.5,
            }
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.structure["structure"] == "CHOCH"
        assert sig_snapshot.structure["confidence"] == 0.85
        assert sig_snapshot.structure["mtf_aligned"] is True
        print("✅ Test: Bridge preserves structure data")
    
    def test_bridge_preserves_liquidity_data(self):
        """Bridge should preserve liquidity data"""
        dict_snapshot = {
            "signal": "SELL",
            "liquidity": {
                "bias": "SELL",
                "score": 85,
                "sweep": True,
                "pools": [4390.0, 4385.0],
            }
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "DAILY")
        
        assert sig_snapshot is not None
        assert sig_snapshot.liquidity["bias"] == "SELL"
        assert sig_snapshot.liquidity["score"] == 85
        assert sig_snapshot.liquidity["sweep"] is True
        print("✅ Test: Bridge preserves liquidity data")


class TestBackwardCompatibility:
    """Test that old dict-based code still works"""
    
    def test_original_dict_unchanged_after_bridge(self):
        """Original dict should be unchanged after bridge conversion"""
        original_dict = {
            "ready": True,
            "signal": "BUY",
            "entry_price": 4400.0,
            "market_regime": "TRENDING",
            "session": "LONDON",
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(original_dict, "SMC")
        
        # Original dict should still have all original keys
        assert original_dict["ready"] is True
        assert original_dict["signal"] == "BUY"
        assert original_dict["entry_price"] == 4400.0
        
        # Snapshot is separate object
        assert sig_snapshot is not None
        assert sig_snapshot is not original_dict
        print("✅ Test: Original dict unchanged after bridge")
    
    def test_dual_return_integration_helper(self):
        """Integration helper should return both dict and snapshot"""
        dict_snapshot = {
            "signal": "SELL",
            "entry_price": 4395.0,
            "market_regime": "RANGING",
        }
        
        returned_dict, returned_snapshot = _integrate_snapshot_bridge_into_check_live_opportunity(
            dict_snapshot, "SMC"
        )
        
        # Dict is unchanged
        assert returned_dict is dict_snapshot
        assert returned_dict["signal"] == "SELL"
        
        # Snapshot is new
        assert returned_snapshot is not None
        assert returned_snapshot.direction == "SELL"
        print("✅ Test: Dual return integration helper works")


class TestActiveStrategySupport:
    """Test bridge supports the remaining entry strategies."""
    
    def test_bridge_supports_all_strategies(self):
        """Bridge should work for SMC and DAILY."""
        dict_snapshot = {"signal": "BUY"}
        bridge = SMCSignalBridge()
        
        for strategy in ["SMC", "DAILY"]:
            sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, strategy)
            assert sig_snapshot is not None
            assert sig_snapshot.strategy == strategy.upper()
        
        print("✅ Test: Bridge supports active strategies")
    
    def test_bridge_normalizes_strategy_case(self):
        """Bridge should handle strategy case-insensitive"""
        dict_snapshot = {"signal": "BUY"}
        bridge = SMCSignalBridge()
        
        for strategy_input in ["smc", "SMC", "Smc", "daily", "DAILY"]:
            sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, strategy_input)
            assert sig_snapshot is not None
            assert sig_snapshot.strategy in {"SMC", "DAILY"}
        
        print("✅ Test: Bridge normalizes strategy case")


class TestErrorHandling:
    """Test error handling in bridge"""
    
    def test_bridge_handles_missing_signal_field(self):
        """Bridge should handle missing 'signal' field gracefully"""
        dict_snapshot = {}  # No 'signal' field
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
        
        # Should fail because direction is required
        assert sig_snapshot is None
        assert bridge.get_last_error() is not None
        print("✅ Test: Bridge handles missing signal field")
    
    def test_bridge_stores_last_error(self):
        """Bridge should store last error for debugging"""
        dict_snapshot = {}
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "INVALID")
        
        assert sig_snapshot is None
        error = bridge.get_last_error()
        assert error is not None
        assert isinstance(error, str)
        assert len(error) > 0
        print("✅ Test: Bridge stores last error")


def run_all_tests():
    """Run all Phase 1B integration tests"""
    print("=" * 80)
    print("PHASE 1B: MAIN.PY INTEGRATION BRIDGE TESTS")
    print("=" * 80)
    
    test_classes = [
        TestSMCSignalBridge(),
        TestBackwardCompatibility(),
        TestActiveStrategySupport(),
        TestErrorHandling(),
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
    print(f"✅ ALL {total_tests} INTEGRATION TESTS PASSED")
    print("=" * 80)
    print("\n🎯 Phase 1B Complete: Bridge ready for main.py integration")
    print("   Next: Import and test in main.py (non-breaking)")


if __name__ == "__main__":
    run_all_tests()

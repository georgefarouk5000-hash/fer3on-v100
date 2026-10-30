"""
Test: Phase 1C - Main.py Bridge Integration
=============================================

Integration tests to verify the bridge works correctly in main.py context.
Tests that the converter handles real snapshot data from trading loop.

[FER3ON-2026-08-31-PHASE1C] - Integration in progress
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.phase1b_main_bridge import SMCSignalBridge
from core.decision_contracts import SignalSnapshot


class TestPhase1CMainIntegration:
    """Test bridge integration in main.py context"""
    
    def test_bridge_converts_real_smc_snapshot(self):
        """Bridge should convert realistic SMC snapshot from main.py"""
        
        # Simulate snapshot returned by _build_live_snapshot() in main.py
        realistic_snapshot = {
            "ready": True,
            "tick": None,
            "rates": [],
            "atr": 4.2,
            "market_regime": "TRENDING",
            "session": "LONDON",
            "phase": "SETUP",
            "signal": "BUY",
            "structure": {
                "structure": "CHOCH",
                "confidence": 0.85,
                "bias": "BUY",
                "mtf_aligned": True,
            },
            "structure_analysis": {
                "structure_strength": 75.0,
                "choch_strength": "STRONG",
                "level": 4400.0,
            },
            "liquidity": {
                "bias": "BUY",
                "score": 80,
                "sweep": True,
                "pools": [4395.0, 4390.0],
                "equal_highs": [4405.0],
                "equal_lows": [],
            },
            "mtf_strength": 3,
            "candle": {"confirmed": True, "score": 85.0, "weight": 2},
            "smc_confirmed": True,
            "entry_grade": "A",
            "smc_details": {"grade_score": 85.0},
            "confidence": {"pct": 78.0},
            "quality_gate": {"mode": "APPROVED"},
            "quality_score": 82.0,
            "brain": {"master_score": 75.0, "memory_score": 70.0},
            "execution": {
                "grade": "A",
                "spread_pts": 0.5,
                "rr_ratio": 1.5,
                "score": 80.0,
            },
            "ml": {"ml_score": 72.0, "rl_action": "TRADE"},
            "feature_record": {},
            "decision_context": {},
            "news_state": {"is_news": False, "impact": "LOW"},
            "position_limits": {"allowed": True},
            "loss_limits": {"daily_used": 20.0, "weekly_used": 50.0},
            "balance": 1050.0,
            "entry_price": 4400.0,
            "sl_dist": 4.0,
            "tp_dist": 6.0,
            "entry_readiness": {"ready": True},
            "structural_targets": [4410.0, 4415.0],
            "swing_structure_report": "STRONG CHOCH",
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(realistic_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.direction == "BUY"
        assert sig_snapshot.strategy == "SMC"
        assert sig_snapshot.confidence == 78.0
        assert sig_snapshot.quality == 82.0
        assert sig_snapshot.regime == "TRENDING"
        assert sig_snapshot.session == "LONDON"
        assert sig_snapshot.execution_grade == "A"
        assert sig_snapshot.atr == 4.2
        print("✅ Test: Bridge converts realistic SMC snapshot")
    
    def test_original_snapshot_unchanged(self):
        """Original dict snapshot should remain unchanged after bridge"""
        
        original_snapshot = {
            "ready": True,
            "signal": "SELL",
            "entry_price": 4390.0,
            "market_regime": "RANGING",
            "session": "ASIA",
            "confidence": {"pct": 60.0},
            "quality_score": 65.0,
            "execution": {"grade": "B"},
        }
        
        # Keep a reference to verify immutability
        original_dict_values = dict(original_snapshot)
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(original_snapshot, "SMC")
        
        # Verify original is unchanged
        assert original_snapshot == original_dict_values
        assert original_snapshot["ready"] is True
        assert original_snapshot["signal"] == "SELL"
        
        # Verify snapshot is separate
        assert sig_snapshot is not original_snapshot
        assert sig_snapshot.direction == "SELL"
        print("✅ Test: Original snapshot unchanged after bridge")
    
    def test_bridge_gracefully_handles_incomplete_snapshot(self):
        """Bridge should work even with incomplete snapshot data"""
        
        minimal_snapshot = {
            "ready": True,
            "signal": "BUY",
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(minimal_snapshot, "SMC")
        
        assert sig_snapshot is not None
        assert sig_snapshot.direction == "BUY"
        assert sig_snapshot.strategy == "SMC"
        # Missing fields should have defaults
        assert sig_snapshot.confidence >= 0
        assert sig_snapshot.quality >= 0
        print("✅ Test: Bridge handles incomplete snapshot gracefully")
    
    def test_bridge_multiple_snapshots_sequential(self):
        """Bridge should handle multiple snapshots in sequence (main loop simulation)"""
        
        snapshots = [
            {"signal": "BUY", "market_regime": "TRENDING", "confidence": {"pct": 70}},
            {"signal": "SELL", "market_regime": "RANGING", "confidence": {"pct": 60}},
            {"signal": "BUY", "market_regime": "TRENDING", "confidence": {"pct": 75}},
        ]
        
        bridge = SMCSignalBridge()
        converted_snapshots = []
        
        for snap in snapshots:
            sig_snapshot = bridge.from_dict_snapshot(snap, "SMC")
            assert sig_snapshot is not None
            converted_snapshots.append(sig_snapshot)
        
        assert len(converted_snapshots) == 3
        assert converted_snapshots[0].direction == "BUY"
        assert converted_snapshots[1].direction == "SELL"
        assert converted_snapshots[2].direction == "BUY"
        print("✅ Test: Bridge handles multiple sequential snapshots")
    
    def test_bridge_preserves_context_data(self):
        """Bridge should preserve all context needed for decision authority"""
        
        snapshot_with_context = {
            "ready": True,
            "signal": "BUY",
            "entry_price": 4400.0,
            "market_regime": "TRENDING",
            "session": "LONDON",
            "confidence": {"pct": 75.0},
            "quality_score": 80.0,
            "execution": {"grade": "A", "rr_ratio": 1.5},
            "structure": {
                "structure": "CHOCH",
                "mtf_aligned": True,
            },
            "liquidity": {
                "bias": "BUY",
                "score": 85,
            },
            "mtf_strength": 3,
            "smc_confirmed": True,
            "decision_context": {
                "strategy": "SMC",
                "signal": "BUY",
                "confidence_pct": 75.0,
            },
        }
        
        bridge = SMCSignalBridge()
        sig_snapshot = bridge.from_dict_snapshot(snapshot_with_context, "SMC")
        
        assert sig_snapshot is not None
        # Verify all decision-relevant fields are preserved
        assert sig_snapshot.direction == "BUY"
        assert sig_snapshot.entry_reference == 4400.0
        assert sig_snapshot.regime == "TRENDING"
        assert sig_snapshot.session == "LONDON"
        assert sig_snapshot.confidence == 75.0
        assert sig_snapshot.quality == 80.0
        assert sig_snapshot.execution_grade == "A"
        assert sig_snapshot.structure["structure"] == "CHOCH"
        assert sig_snapshot.liquidity["bias"] == "BUY"
        print("✅ Test: Bridge preserves all context data")


class TestPhase1CBackwardCompatibility:
    """Test that main.py old code path still works"""
    
    def test_snapshot_dict_usable_after_bridge(self):
        """Original dict snapshot should still be usable by old code"""
        
        dict_snapshot = {
            "ready": True,
            "signal": "BUY",
            "entry_price": 4400.0,
            "market_regime": "TRENDING",
            "session": "LONDON",
            "confidence": {"pct": 75.0},
            "quality_score": 80.0,
            "decision_context": {"strategy": "SMC"},
            "execution": {"grade": "A"},
        }
        
        bridge = SMCSignalBridge()
        
        # Simulate old code that doesn't know about the bridge
        if dict_snapshot.get("ready"):
            # Old code should still be able to access all fields
            assert dict_snapshot["signal"] == "BUY"
            assert dict_snapshot["market_regime"] == "TRENDING"
            assert dict_snapshot["confidence"]["pct"] == 75.0
            
            # Now bridge the conversion
            sig_snapshot = bridge.from_dict_snapshot(dict_snapshot, "SMC")
            
            # But old code should still work unchanged
            assert dict_snapshot["signal"] == "BUY"
            assert dict_snapshot["ready"] is True
        
        print("✅ Test: Old dict-based code still works after bridge")


class TestPhase1CMainLoopBehavior:
    """Test bridge behavior in main loop context"""
    
    def test_bridge_does_not_modify_decision_flow(self):
        """Bridge should not affect decision flow in main loop"""
        
        snapshot = {
            "ready": True,
            "signal": "BUY",
            "decision_context": {"strategy": "SMC", "confidence_pct": 75},
        }
        
        # Main loop: check if ready
        if snapshot.get("ready"):
            # Main loop: get decision_context
            decision_context = snapshot.get("decision_context")
            
            # Main loop: also bridge convert (new)
            bridge = SMCSignalBridge()
            sig_snapshot = bridge.from_dict_snapshot(snapshot, "SMC")
            
            # Both should be valid
            assert decision_context is not None
            assert sig_snapshot is not None
            
            # Main loop would still use decision_context
            assert decision_context["strategy"] == "SMC"
            assert decision_context["confidence_pct"] == 75
        
        print("✅ Test: Bridge does not modify decision flow")


def run_all_phase1c_tests():
    """Run all Phase 1C integration tests"""
    print("=" * 80)
    print("PHASE 1C: MAIN.PY BRIDGE INTEGRATION TESTS")
    print("=" * 80)
    
    test_classes = [
        TestPhase1CMainIntegration(),
        TestPhase1CBackwardCompatibility(),
        TestPhase1CMainLoopBehavior(),
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
    print(f"✅ ALL {total_tests} PHASE 1C INTEGRATION TESTS PASSED")
    print("=" * 80)
    print("\n🎯 Phase 1C Complete: Bridge integrated into main.py")
    print("   Ready for 50-trade live test")


if __name__ == "__main__":
    run_all_phase1c_tests()

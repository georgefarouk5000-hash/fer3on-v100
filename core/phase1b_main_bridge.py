"""
Phase 1B: Main.py Integration Adapter
======================================

Role: Bridge between old dict-based signals and new SignalSnapshot contracts.
This is the FIRST file to touch live code paths, but in a non-breaking way.

[FER3ON-2026-08-31-PHASE1B]
- Integration starts here
- main.py snapshot → SignalSnapshot conversion
- Zero behavior change (backward compatible)
- Safe rollback possible at any step
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from typing import Any, Dict, Optional
from core.signal_snapshot_converter import (
    dict_to_signal_snapshot,
    validate_signal_snapshot,
)
from core.decision_contracts import SignalSnapshot


class UnifiedStrategyBridge:
    """
    Converts strategy dictionaries to SignalSnapshot contracts.
    
    Usage in main.py (Phase 1E):
    ┌──────────────────────────────────────────────────────────┐
    │ bridge = UnifiedStrategyBridge()                        │
    │                                                          │
    │ # For SMC:                                               │
    │ smc_snapshot = bridge.from_dict_snapshot(               │
    │     dict_snapshot=smc_dict, strategy='SMC')            │
    │                                                          │
    └──────────────────────────────────────────────────────────┘
    """
    
    def __init__(self):
        self.last_snapshot = None
        self.last_error = None
    
    def from_dict_snapshot(
        self,
        dict_snapshot: Dict[str, Any],
        strategy: str = "SMC",
    ) -> Optional[SignalSnapshot]:
        """
        Convert a strategy snapshot dictionary to SignalSnapshot.
        
        Args:
            dict_snapshot: Full dict from the strategy's signal evaluation.
            strategy: Strategy name.
        
        Returns:
            SignalSnapshot or None if conversion failed
        """
        
        try:
            # Extract signal direction from various possible locations
            direction = None
            if 'signal' in dict_snapshot:
                direction = dict_snapshot.get('signal')
            elif 'direction' in dict_snapshot:
                direction = dict_snapshot.get('direction')
            elif 'mode' in dict_snapshot:
                direction = dict_snapshot.get('mode')
            
            if not direction:
                self.last_error = "No direction/signal found in snapshot"
                return None
            
            # Extract essential fields with fallbacks for each strategy
            signal_dict = {
                "signal_id": dict_snapshot.get("signal_id"),
                "direction": direction,
                "entry_price": dict_snapshot.get("entry_price") or dict_snapshot.get("current_price", 0),
                "signal_time": dict_snapshot.get("signal_time") or dict_snapshot.get("timestamp"),
                "regime": dict_snapshot.get("market_regime", "") or dict_snapshot.get("regime", ""),
                "session": dict_snapshot.get("session", ""),
                "confidence": dict_snapshot.get("confidence", {}).get("pct") or dict_snapshot.get("confidence_pct", 0),
                "quality": dict_snapshot.get("quality_score", 0) or dict_snapshot.get("score", 0),
                "atr": dict_snapshot.get("atr", 0),
                "execution_grade": dict_snapshot.get("execution", {}).get("grade") or dict_snapshot.get("grade", ""),
                "structure": dict_snapshot.get("structure", {}),
                "liquidity": dict_snapshot.get("liquidity", {}),
                "raw_signal_reason": dict_snapshot.get("phase", "") or dict_snapshot.get("reason", ""),
                "mtf_alignment": dict_snapshot.get("mtf_strength", 0),
            }
            
            # Convert to SignalSnapshot
            snapshot = dict_to_signal_snapshot(signal_dict, strategy)
            
            # Validate
            is_valid, reason = validate_signal_snapshot(snapshot)
            if not is_valid:
                self.last_error = reason
                return None
            
            # Store for debugging
            self.last_snapshot = snapshot
            return snapshot
            
        except Exception as e:
            self.last_error = str(e)
            return None
    
    def get_last_error(self) -> Optional[str]:
        """Get last conversion error"""
        return self.last_error


# Backward compatibility: SMCSignalBridge is now just an alias
SMCSignalBridge = UnifiedStrategyBridge


def _integrate_snapshot_bridge_into_check_live_opportunity(
    original_snapshot: Dict[str, Any],
    strategy: str = "SMC",
) -> tuple[Dict[str, Any], Optional[SignalSnapshot]]:
    """
    Helper function for Phase 1B integration.
    
    Returns BOTH the original dict (for backward compat) AND the new SignalSnapshot.
    This allows gradual migration without breaking existing code.
    
    Example usage (future):
    ┌────────────────────────────────────────────────────────┐
    │ dict_snapshot = check_live_opportunity(...)           │
    │ dict_snap, sig_snapshot = _integrate_snapshot_...(...) │
    │                                                        │
    │ # Old code still works:                               │
    │ if dict_snap.get('ready'):                            │
    │     execute_trade(dict_snap)  # Still works!          │
    │                                                        │
    │ # New code uses SignalSnapshot:                       │
    │ if sig_snapshot:                                      │
    │     decision = authority.decide(sig_snapshot)        │
    └────────────────────────────────────────────────────────┘
    """
    
    bridge = SMCSignalBridge()
    sig_snapshot = bridge.from_dict_snapshot(original_snapshot, strategy)
    
    # Original dict is unchanged
    return original_snapshot, sig_snapshot


if __name__ == "__main__":
    # Example: test the bridge with mock data
    print("=" * 80)
    print("PHASE 1B: Main.py Integration Bridge Test")
    print("=" * 80)
    
    from datetime import datetime, timezone
    
    # Mock a snapshot from check_live_opportunity()
    mock_snapshot = {
        "ready": True,
        "signal": "BUY",
        "entry_price": 4400.0,
        "signal_time": datetime.now(timezone.utc).isoformat(),
        "market_regime": "TRENDING",
        "session": "LONDON",
        "confidence": {"pct": 75.0},
        "quality_score": 80.0,
        "atr": 4.5,
        "execution": {"grade": "A", "rr_ratio": 1.5},
        "structure": {"structure": "CHOCH", "mtf_aligned": True},
        "liquidity": {"bias": "BUY", "score": 80},
        "mtf_strength": 3,
        "phase": "SETUP",
    }
    
    bridge = SMCSignalBridge()
    sig_snapshot = bridge.from_dict_snapshot(mock_snapshot, "SMC")
    
    if sig_snapshot:
        print("✅ Bridge conversion successful!")
        print(f"   Signal ID: {sig_snapshot.signal_id}")
        print(f"   Strategy: {sig_snapshot.strategy}")
        print(f"   Direction: {sig_snapshot.direction}")
        print(f"   Confidence: {sig_snapshot.confidence}%")
        print(f"   Quality: {sig_snapshot.quality}%")
        print(f"   Build ID: {sig_snapshot.build_id}")
        print(f"   Decision Snapshot ID: {sig_snapshot.decision_snapshot_id}")
    else:
        print(f"❌ Bridge conversion failed: {bridge.get_last_error()}")
    
    print("\n" + "=" * 80)
    print("✅ Phase 1B Bridge ready for integration into main.py")
    print("=" * 80)

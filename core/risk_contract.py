"""
FER3ON Risk Contract — Single Source of Truth for All Risk Limits
[FER3ON-2026-08-31]

This module unifies all risk-related settings and validations.
Every runtime risk decision reads from this contract, never from defaults.

The contract is the bridge between:
  - core/settings.py (live values)
  - core/risk_policy.py (documented policy)
  - core/risk_manager.py (enforcement)
  - core/strategy_kill_switch.py (safety guards)
  - core/trade_executor.py (execution limits)
"""

from __future__ import annotations

from typing import Any, Dict


class RiskContract:
    """Canonical risk limits contract - read directly from settings."""
    
    def __init__(self):
        """Load all risk limits from core.settings on instantiation."""
        self._load_from_settings()
    
    def _load_from_settings(self):
        """Import and cache all values from core.settings (single read)."""
        from core import settings as _s
        
        # =========== Account & Position Sizing ===========
        self.base_account_balance = _s.BASE_ACCOUNT_BALANCE
        self.min_lot = _s.MIN_LOT
        self.max_lot = _s.MAX_LOT
        self.max_open_trades = _s.MAX_OPEN_TRADES
        self.max_open_per_strategy = _s.MAX_OPEN_PER_STRATEGY
        
        # =========== Risk Per Trade ===========
        self.risk_per_trade_pct = _s.RISK_PER_TRADE_PERCENT
        self.min_effective_risk_pct = _s.MIN_EFFECTIVE_RISK_PERCENT
        self.max_risk_per_day_pct = _s.MAX_RISK_PER_DAY_PERCENT
        self.max_daily_loss_usd = _s.MAX_DAILY_LOSS_USD
        
        # =========== Stop Loss Limits (Critical) ===========
        self.max_sl_distance_dollars = _s.MAX_SL_DISTANCE_DOLLARS
        self.min_sl_distance_points = _s.MIN_SL_DISTANCE
        self.min_lot_risk_multiple_cap = _s.MIN_LOT_RISK_MULTIPLE_CAP
        
        # =========== Kill-Switch Limits ===========
        # Daily loss limits (per strategy)
        self.daily_loss_limits = {
            "SMC": _s.KILL_SWITCH_DAILY_LOSS_LIMITS.get("SMC", 50.0),
            "DAILY": _s.KILL_SWITCH_DAILY_LOSS_LIMITS.get("DAILY", 80.0),
        }
        
        # Weekly loss limits (per strategy)
        self.weekly_loss_limits = {
            "SMC": _s.KILL_SWITCH_WEEKLY_LOSS_LIMITS.get("SMC", 120.0),
            "DAILY": _s.KILL_SWITCH_WEEKLY_LOSS_LIMITS.get("DAILY", 200.0),
        }
        
        # =========== Session/Regime Blocks ===========
        self.session_block_enabled = _s.KILL_SWITCH_SESSION_BLOCK_ENABLED
        self.blocked_sessions = _s.KILL_SWITCH_BLOCKED_SESSIONS
        self.blocked_regimes = _s.KILL_SWITCH_BLOCKED_REGIMES
        
        # =========== Execution Grade Requirements ===========
        self.strict_exec_grade_strategies = _s.KILL_SWITCH_STRICT_EXEC_GRADE_STRATEGIES
        self.allowed_exec_grades = _s.KILL_SWITCH_ALLOWED_EXEC_GRADES
        
        # =========== Grace Period ===========
        self.grace_enabled = _s.KILL_SWITCH_GRACE_ENABLED
        self.min_trades_for_daily_block = _s.KILL_SWITCH_MIN_TRADES_FOR_DAILY_BLOCK
        self.min_trades_for_weekly_block = _s.KILL_SWITCH_MIN_TRADES_FOR_WEEKLY_BLOCK
        
        # =========== Quality Gates ===========
        self.quality_score_trust_enabled = _s.QUALITY_SCORE_TRUST_ENABLED
        self.london_volatile_block_enabled = _s.LONDON_VOLATILE_BLOCK_ENABLED
        self.london_volatile_start = _s.LONDON_VOLATILE_START
        self.london_volatile_end = _s.LONDON_VOLATILE_END
        
        # =========== Broker/Order Configuration ===========
        self.broker_stop_level_fallback = _s.BROKER_STOP_LEVEL_FALLBACK
        self.order_retry_on_stops_rejection = _s.ORDER_RETRY_ON_STOPS_REJECTION_ENABLED
        self.order_retry_max_attempts = _s.ORDER_RETRY_MAX_ATTEMPTS
        self.order_retry_step_pct = _s.ORDER_RETRY_STEP_PCT
        self.order_retry_max_widen_factor = _s.ORDER_RETRY_MAX_WIDEN_FACTOR
    
    def validate(self) -> tuple[bool, str]:
        """Validate contract integrity (all values in valid range)."""
        checks = [
            (self.min_lot > 0, "min_lot must be > 0"),
            (self.max_lot > self.min_lot, "max_lot must be > min_lot"),
            (self.max_sl_distance_dollars > 0, "max_sl_distance_dollars must be > 0"),
            (self.risk_per_trade_pct > 0, "risk_per_trade_pct must be > 0"),
            (self.max_risk_per_day_pct > 0, "max_risk_per_day_pct must be > 0"),
            (self.max_daily_loss_usd > 0, "max_daily_loss_usd must be > 0"),
            (self.max_open_trades > 0, "max_open_trades must be > 0"),
            (len(self.daily_loss_limits) == 2, "daily_loss_limits must cover active strategies"),
            (len(self.weekly_loss_limits) == 2, "weekly_loss_limits must cover active strategies"),
            (len(self.allowed_exec_grades) > 0, "allowed_exec_grades must not be empty"),
        ]
        
        for condition, message in checks:
            if not condition:
                return False, message
        
        return True, "Contract valid"
    
    def get_daily_loss_limit(self, strategy: str) -> float:
        """Return daily loss limit for strategy, with fallback."""
        return self.daily_loss_limits.get(strategy.upper(), 50.0)
    
    def get_weekly_loss_limit(self, strategy: str) -> float:
        """Return weekly loss limit for strategy, with fallback."""
        return self.weekly_loss_limits.get(strategy.upper(), 120.0)
    
    def is_exec_grade_allowed(self, grade: str, strategy: str) -> bool:
        """Return True if exec_grade is allowed for strategy."""
        if strategy.upper() not in self.strict_exec_grade_strategies:
            # Strategy is not strict — all grades allowed
            return True
        # Strategy is strict — only allowed grades pass
        return grade.upper() in self.allowed_exec_grades
    
    def is_session_blocked(self, session: str, strategy: str) -> bool:
        """Return True if session is blocked for strategy."""
        if not self.session_block_enabled:
            return False
        blocked = self.blocked_sessions.get(strategy.upper(), set())
        return session.upper() in blocked
    
    def is_regime_blocked(self, regime: str, strategy: str) -> bool:
        """Return True if market regime is blocked for strategy."""
        blocked = self.blocked_regimes.get(strategy.upper(), set())
        return regime.upper() in blocked
    
    def to_dict(self) -> Dict[str, Any]:
        """Export contract as dict (for logging/audit)."""
        return {
            "base_account_balance": self.base_account_balance,
            "min_lot": self.min_lot,
            "max_lot": self.max_lot,
            "max_open_trades": self.max_open_trades,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_sl_distance_dollars": self.max_sl_distance_dollars,
            "daily_loss_limits": self.daily_loss_limits,
            "weekly_loss_limits": self.weekly_loss_limits,
            "session_block_enabled": self.session_block_enabled,
            "grace_enabled": self.grace_enabled,
        }


# Singleton instance (cached on first import)
_INSTANCE: RiskContract | None = None


def get_risk_contract() -> RiskContract:
    """Get (or create) the global RiskContract instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = RiskContract()
        is_valid, msg = _INSTANCE.validate()
        if not is_valid:
            raise RuntimeError(f"RiskContract validation failed: {msg}")
    return _INSTANCE


def reload_risk_contract() -> RiskContract:
    """Force reload of RiskContract (useful for tests/config changes)."""
    global _INSTANCE
    _INSTANCE = RiskContract()
    is_valid, msg = _INSTANCE.validate()
    if not is_valid:
        raise RuntimeError(f"RiskContract validation failed: {msg}")
    return _INSTANCE

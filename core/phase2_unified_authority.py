# =============================================================================
# FER3ON PHASE 2 — UNIFIED AUTHORITY FOR ACTIVE STRATEGIES
# =============================================================================
# Purpose: Single decision authority for SMC and DAILY
# Integration: Extends fer3on_decision_authority.py with strategy-aware context building
# Prerequisites: Phase 1E SignalSnapshot bridge (UnifiedStrategyBridge)
# =============================================================================

from typing import Any, Dict, Optional
from datetime import datetime, timezone

from core.unified_bridge import (
    build_decision_context as _build_decision_context,
    decide_and_log,
)
from core.fer3on_decision_authority import (
    decide_trade,
    decision_to_runtime_format,
    format_authority_log,
)
from core.unified_decision import DecisionResult


class UnifiedStrategyAuthority:
    """
    Single authority for deciding trade approval across active strategies.
    
    Handles:
    - Strategy-aware decision context building
    - Unified decide_trade calls for SMC and DAILY
    - Backward compatibility with existing SMC decision path
    - Comprehensive logging and traceability
    
    Usage:
        authority = UnifiedStrategyAuthority()
        
        # For SMC
        result = authority.decide_for_strategy('SMC', smc_snapshot_dict)
        
        # For DAILY
        result = authority.decide_for_strategy('DAILY', daily_result_dict)
    """

    def __init__(self):
        """Initialize authority with error tracking."""
        self.last_error = None
        self.last_strategy = None
        self.decision_count = 0

    def _normalize_context_data(
        self, snapshot: Dict[str, Any], strategy: str
    ) -> Dict[str, Any]:
        """
        Extract and normalize decision context fields from strategy snapshot.
        
        Handles field name variations across strategies:
        - direction/signal/mode → signal
        - confidence.pct / confidence_pct → confidence_pct
        - market_regime / regime → market_regime
        - quality_score / score → quality_score
        - execution.grade / grade → execution_grade
        
        Args:
            snapshot: Strategy result dict (from run_smc_cycle, run_scalp_cycle, etc.)
            strategy: Active strategy name (SMC or DAILY)
        
        Returns:
            Normalized dict with all required fields for DecisionContext
        """
        strat_upper = str(strategy or '').upper()

        # Extract signal direction (handles all naming conventions)
        signal = (
            snapshot.get('signal')
            or snapshot.get('direction')
            or snapshot.get('mode')
            or 'NONE'
        )

        # CRITICAL FIX #3: Null validation - safely extract confidence
        confidence_data = snapshot.get('confidence')
        if isinstance(confidence_data, dict):
            confidence_pct = float(confidence_data.get('pct', 0) or 0)
        else:
            confidence_pct = float(snapshot.get('confidence_pct', 0) or 0)
        confidence_pct = max(0.0, min(100.0, confidence_pct))  # Clamp to valid range

        # Extract quality score (handles naming variations)
        quality_score = float(
            snapshot.get('quality_score')
            or snapshot.get('quality', {}).get('score', 0)
            or snapshot.get('quality', 0)
            or 0
        )

        # Extract execution grade (handles nested vs flat)
        execution_grade = (
            snapshot.get('execution_grade')
            or snapshot.get('execution', {}).get('grade', 'UNKNOWN')
            or snapshot.get('grade', 'UNKNOWN')
            or 'UNKNOWN'
        )

        # Extract market regime (handles naming variations)
        market_regime = (
            snapshot.get('market_regime')
            or snapshot.get('regime', 'RANGING')
            or 'RANGING'
        )

        # Extract brain/DNA scores
        brain_data = snapshot.get('brain', {})
        brain_score = float(
            brain_data.get('master_score', 50) if isinstance(brain_data, dict) else 50
        )
        memory_score = float(
            brain_data.get('memory_score', 50) if isinstance(brain_data, dict) else 50
        )
        dna_score = float(
            brain_data.get('dna_score', 50) if isinstance(brain_data, dict) else 50
        )

        # Extract execution data
        execution_data = snapshot.get('execution', {})
        execution_score = float(
            execution_data.get('score', 0) if isinstance(execution_data, dict) else 0
        )
        spread_ratio = float(
            execution_data.get('spread_pct', 0)
            if isinstance(execution_data, dict)
            else 0
        )
        rr_ratio = float(
            execution_data.get('rr_ratio', 0)
            if isinstance(execution_data, dict)
            else 0
        )

        # Extract structure and liquidity
        structure_data = snapshot.get('structure_analysis', {})
        structure_quality = float(
            structure_data.get('structure_strength', 50)
            if isinstance(structure_data, dict)
            else 50
        )

        liquidity_data = snapshot.get('liquidity', {})
        liquidity_alignment = (
            float(liquidity_data.get('score', 50) / 15.0 * 100.0)
            if isinstance(liquidity_data, dict)
            else 50.0
        )

        # Extract ML data
        ml_data = snapshot.get('ml_result', {})
        ml_score = float(
            ml_data.get('ml_score', 50) if isinstance(ml_data, dict) else 50
        )
        ml_rl_action = (
            ml_data.get('rl_action', 'PASS') if isinstance(ml_data, dict) else 'PASS'
        )

        # Extract confirmation states
        candle_data = snapshot.get('candle', {})
        candle_trigger_confirmed = bool(
            candle_data.get('confirmed') if isinstance(candle_data, dict) else False
        )
        candle_weight = int(
            candle_data.get('weight', 0) if isinstance(candle_data, dict) else 0
        )
        candle_bonus = float(
            candle_data.get('candle_bonus', 0) if isinstance(candle_data, dict) else 0
        )
        candle_penalty = float(
            candle_data.get('candle_penalty', 0) if isinstance(candle_data, dict) else 0
        )

        # Extract bias and MTF
        daily_bias = snapshot.get('daily_bias', 'NONE')
        mtf_strength = int(snapshot.get('mtf_strength', 0) or 0)
        smc_strength = float(snapshot.get('smc_strength', 0) or 0)
        smc_confirmed = snapshot.get('smc_entry_confirmed', False)

        # Extract session and regime data
        session_name = snapshot.get('session', 'UNKNOWN')
        session_score = float(snapshot.get('session_score', 50) or 50)
        sweep_prob = float(snapshot.get('sweep_probability', 0) or 0)

        # Extract ATR and risk data
        atr = float(snapshot.get('atr', 1.0) or 1.0)
        atr_sufficient = atr >= 1.0

        return {
            'strategy': strat_upper,
            'signal': signal,
            'quality_score': quality_score,
            'confidence_pct': confidence_pct,
            'brain_score': brain_score,
            'execution_score': execution_score,
            'execution_grade': execution_grade,
            'structure_quality': structure_quality,
            'daily_bias': daily_bias,
            'mtf_strength': mtf_strength,
            'smc_strength': smc_strength,
            'smc_entry_confirmed': smc_confirmed,
            'candle_trigger_confirmed': candle_trigger_confirmed,
            'candle_weight': candle_weight,
            'candle_bonus': candle_bonus,
            'candle_penalty': candle_penalty,
            'liquidity_alignment': liquidity_alignment,
            'sweep_probability': sweep_prob,
            'session': session_name,
            'market_regime': market_regime,
            'session_score': session_score,
            'memory_score': memory_score,
            'dna_score': dna_score,
            'spread_ratio': spread_ratio,
            'atr_sufficient': atr_sufficient,
            'rr_ratio': rr_ratio,
            'ml_score': ml_score,
            'ml_rl_action': ml_rl_action,
        }

    def decide_for_strategy(
        self,
        strategy: str,
        snapshot: Dict[str, Any],
        risk_limits_hit: bool = False,
        cooldown_active: bool = False,
        daily_loss_capped: bool = False,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
    ) -> Optional[DecisionResult]:
        """
        Make a unified decision for a specific strategy.
        
        Args:
            strategy: Active strategy name (SMC or DAILY)
            snapshot: Strategy result dict
            risk_limits_hit: Whether risk limits are exceeded
            cooldown_active: Whether strategy cooldown is active
            daily_loss_capped: Whether daily loss cap is hit
            hour: UTC hour (defaults to now)
            minute: UTC minute (defaults to now)
        
        Returns:
            DecisionResult with decision, score, risk_multiplier, etc.
            Returns None on error (non-fatal, original dict snapshot still valid)
        """
        try:
            if str(strategy or '').upper() not in {'SMC', 'DAILY'}:
                raise ValueError(f'Unsupported strategy: {strategy}')
            self.last_strategy = strategy
            self.last_error = None

            # Normalize context data from snapshot
            context_data = self._normalize_context_data(snapshot, strategy)

            # Build decision context using unified bridge
            ctx = _build_decision_context(
                strategy=context_data['strategy'],
                signal=context_data['signal'],
                symbol='XAUUSD',
                quality_score=context_data['quality_score'],
                confidence_pct=context_data['confidence_pct'],
                brain_score=context_data['brain_score'],
                execution_score=context_data['execution_score'],
                execution_grade=context_data['execution_grade'],
                structure_quality=context_data['structure_quality'],
                daily_bias=context_data['daily_bias'],
                mtf_strength=context_data['mtf_strength'],
                smc_strength=context_data['smc_strength'],
                smc_entry_confirmed=context_data['smc_entry_confirmed'],
                candle_trigger_confirmed=context_data[
                    'candle_trigger_confirmed'
                ],
                candle_weight=context_data['candle_weight'],
                candle_bonus=context_data['candle_bonus'],
                candle_penalty=context_data['candle_penalty'],
                liquidity_alignment=context_data['liquidity_alignment'],
                sweep_probability=context_data['sweep_probability'],
                session=context_data['session'],
                market_regime=context_data['market_regime'],
                session_score=context_data['session_score'],
                risk_limits_hit=risk_limits_hit,
                cooldown_active=cooldown_active,
                daily_loss_capped=daily_loss_capped,
                spread_ratio=context_data['spread_ratio'],
                atr_sufficient=context_data['atr_sufficient'],
                rr_ratio=context_data['rr_ratio'],
                ml_score=context_data['ml_score'],
                ml_rl_action=context_data['ml_rl_action'],
                memory_score=context_data['memory_score'],
                dna_score=context_data['dna_score'],
                hour=hour,
                minute=minute,
            )

            # Make decision using unified authority
            result = decide_trade(ctx)

            # Track decision
            self.decision_count += 1

            return result

        except Exception as e:
            self.last_error = f'{strategy}: {str(e)}'
            # Fail-closed: any exception in the unified authority must reject the
            # trade instead of silently allowing it through.
            print(f'⚠️ [PHASE2] Authority error for {strategy}: {self.last_error}')
            return DecisionResult(
                decision='HARD_BLOCK',
                composite_score=0.0,
                risk_multiplier=0.0,
                size_mode='NONE',
                reasons=['HARD_BLOCK:FAIL_CLOSED_AUTHORITY_EXCEPTION'],
                penalties={'authority_exception': 100.0},
                bonuses={},
                hard_block_reason='FAIL_CLOSED_AUTHORITY_EXCEPTION',
                debug={'strategy': strategy, 'error': str(e)},
            )

    def get_last_error(self) -> Optional[str]:
        """Get the last error message, if any."""
        return self.last_error

    def get_decision_count(self) -> int:
        """Get total decisions made by this authority."""
        return self.decision_count

    def reset_stats(self):
        """Reset decision counter and error tracking."""
        self.decision_count = 0
        self.last_error = None
        self.last_strategy = None


# Module-level singleton instance
_unified_authority = None


def get_unified_authority() -> UnifiedStrategyAuthority:
    """Get or create the module-level authority instance (singleton pattern)."""
    global _unified_authority
    if _unified_authority is None:
        _unified_authority = UnifiedStrategyAuthority()
    return _unified_authority


# =============================================================================
# Convenience Functions (for direct import use)
# =============================================================================


def _run_unified_decision(
    strategy: str,
    snapshot: Dict[str, Any],
    *,
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Optional[DecisionResult]:
    """Canonical helper: all strategy calls route through the single authority."""
    strat = str(strategy or '').upper()
    if not strat:
        return None
    return get_unified_authority().decide_for_strategy(
        strat,
        snapshot,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        daily_loss_capped=daily_loss_capped,
        hour=hour,
        minute=minute,
    )


def decide_smc(
    snapshot: Dict[str, Any],
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Optional[DecisionResult]:
    """Backward-compatible alias for the unified SMC decision path."""
    return _run_unified_decision(
        'SMC',
        snapshot,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        daily_loss_capped=daily_loss_capped,
        hour=hour,
        minute=minute,
    )


def decide_daily(
    snapshot: Dict[str, Any],
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Optional[DecisionResult]:
    """Backward-compatible alias for the unified DAILY decision path."""
    return _run_unified_decision(
        'DAILY',
        snapshot,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        daily_loss_capped=daily_loss_capped,
        hour=hour,
        minute=minute,
    )


def decide_unified(
    strategy: str,
    snapshot: Dict[str, Any],
    *,
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Optional[DecisionResult]:
    """Canonical single-interface entry point for the whole unified decision system."""
    return _run_unified_decision(
        strategy,
        snapshot,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        daily_loss_capped=daily_loss_capped,
        hour=hour,
        minute=minute,
    )


def apply_unified_strategy_decision(
    strategy: str,
    snapshot: Dict[str, Any],
    *,
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Optional[DecisionResult]:
    """Alias kept for compatibility; canonical entry point is decide_unified()."""
    return decide_unified(
        strategy,
        snapshot,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        daily_loss_capped=daily_loss_capped,
        hour=hour,
        minute=minute,
    )


def apply_unified_strategy_decisions(
    snapshots: Dict[str, Dict[str, Any]],
    *,
    risk_limits_hit: bool = False,
    cooldown_active: bool = False,
    daily_loss_capped: bool = False,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Dict[str, Optional[DecisionResult]]:
    """Run a single unified decision flow for multiple strategy snapshots."""
    return {
        strategy: decide_unified(
            strategy,
            snapshot,
            risk_limits_hit=risk_limits_hit,
            cooldown_active=cooldown_active,
            daily_loss_capped=daily_loss_capped,
            hour=hour,
            minute=minute,
        )
        for strategy, snapshot in (snapshots or {}).items()
    }

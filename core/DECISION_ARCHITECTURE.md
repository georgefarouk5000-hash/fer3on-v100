# FER3ON Decision Architecture [FER3ON-2026-08-31]

## Single Responsibility Principle: Three Layers

This document defines the clear separation between decision layers in FER3ON.

---

## Layer 1: SIGNAL AUTHORITY (core/fer3on_decision_authority.py)

**Purpose**: Determine if a signal is technically valid and worth trading.

**Input**:
- DecisionContext (market analysis, regime, session, structure, etc.)

**Output**:
- DecisionResult with decision: APPROVE / WAIT / REJECT

**Scope**:
- ✅ Market regime alignment
- ✅ Session quality
- ✅ Technical structure
- ✅ Confidence threshold
- ✅ Expected edge

**NOT Scope**:
- ❌ Daily loss caps
- ❌ Strategy-specific blocks
- ❌ Account protection
- ❌ Execution feasibility

**Key File**: `core/unified_decision.py::unified_decide()`

---

## Layer 2: SAFETY GUARD (core/strategy_kill_switch.py)

**Purpose**: Prevent execution when account protection rules are triggered.

**Input**:
- strategy, session, market_regime, exec_grade
- Live trade history (from trades.csv)

**Output**:
- (block: bool, reason: str)

**Scope**:
- ✅ Daily loss limits (per strategy)
- ✅ Weekly loss limits (per strategy)
- ✅ Session blocks (ASIA, NEWYORK disabled)
- ✅ Regime blocks (RANGING, TRENDING)
- ✅ Execution grade requirements (A/A+/ELITE only)
- ✅ Grace period for new accounts

**NOT Scope**:
- ❌ Technical signal evaluation
- ❌ Market structure analysis
- ❌ Confidence thresholds

**Config**: All values in `core/settings.py` (KILL_SWITCH_*)

**Key File**: `core/strategy_kill_switch.py::should_block_trade()`

---

## Layer 3: EXECUTION GUARD (core/trade_executor.py)

**Purpose**: Verify that requested order respects broker/account limits.

**Input**:
- order dict (symbol, volume, price, sl, tp, etc.)
- Account state

**Output**:
- MT5 execution result

**Scope**:
- ✅ Broker minimum stop distance validation
- ✅ MAX_SL_DISTANCE_DOLLARS enforcement
- ✅ Retry logic for stop-rejection
- ✅ Order building and sending

**NOT Scope**:
- ❌ Trading decision validation
- ❌ Risk policy enforcement (delegated to Layer 2)
- ❌ Market analysis

**Config**: MAX_SL_DISTANCE_DOLLARS, ORDER_RETRY_* in `core/settings.py`

**Key File**: `core/trade_executor.py::execute_trade()`

---

## Decision Flow

```
main.py: has a signal candidate
     ↓
core/fer3on_decision_authority.py::decide_trade()  [LAYER 1: Authority]
    • Evaluates DecisionContext
    • Returns: APPROVE / WAIT / REJECT
    • If REJECT → stop here, no order sent
     ↓
core/trade_executor.py::execute_trade()  [LAYER 2: Safety Guard]
    • Calls should_block_trade()
    • If blocked → stop here, no order sent
    • If allowed → proceed to Layer 3
     ↓
core/trade_executor.py: build & send order  [LAYER 3: Execution]
    • Enforce MAX_SL_DISTANCE_DOLLARS
    • Build MT5 order
    • Send to broker
```

---

## Configuration Sources (Single Source of Truth)

| Setting | File | Layer |
|---------|------|-------|
| MAX_SL_DISTANCE_DOLLARS | core/settings.py | Execution |
| KILL_SWITCH_DAILY_LOSS_LIMITS | core/settings.py | Safety |
| KILL_SWITCH_WEEKLY_LOSS_LIMITS | core/settings.py | Safety |
| KILL_SWITCH_BLOCKED_REGIMES | core/settings.py | Safety |
| KILL_SWITCH_BLOCKED_SESSIONS | core/settings.py | Safety |
| KILL_SWITCH_ALLOWED_EXEC_GRADES | core/settings.py | Safety |
| KILL_SWITCH_GRACE_ENABLED | core/settings.py | Safety |
| QUALITY_SCORE_TRUST_ENABLED | core/settings.py | Authority |
| LONDON_VOLATILE_BLOCK_ENABLED | core/settings.py | Authority (runtime gate) |

All values read directly from core/settings.py (never from hardcoded defaults).

---

## Shadow Logging (FAIE)

**Important**: FAIE shadow logging runs in LAYER 1 only:
- Receives DecisionContext
- Produces advisory Decision (never executed)
- Writes to data/faie/shadow_log.jsonl
- Never influences execution layers

FAIE advisory decisions are ONLY for post-trade analysis, never live control.

---

## Fail-Closed Guarantee

If ANY exception occurs in Layer 2 (Safety Guard):
- Trade is REJECTED
- No order is sent
- Log includes `KILL_SWITCH_CHECK_FAILED`

Exception in Layer 2 = automatic block (fail-closed behavior).

---

## Summary

| Layer | Purpose | Block Reason | Source |
|-------|---------|-----|--------|
| 1 | Signal validity | HARD_BLOCK / PASS_MICRO | Market analysis |
| 2 | Account safety | KILL_SWITCH_* | Live history |
| 3 | Execution safety | BROKER_* / MAX_SL_* | Broker response |

Each layer is independent. Failure in Layer 2 does not require knowledge of Layer 1.

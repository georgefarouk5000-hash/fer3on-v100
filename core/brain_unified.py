import json
import time

from core.conflict_resolution import resolve_conflicting_signals


# =========================================
# GLOBAL AI STATE
# =========================================

LAST_LOSS_TIME = 0
CONSECUTIVE_LOSSES = 0
AI_COOLDOWN_ACTIVE = False


# =========================================
# HELPERS
# =========================================

def _grade_to_score(grade):
    return {
        "ELITE": 100,
        "A+": 92,
        "A": 84,
        "B+": 76,
        "B": 68,
        "C": 58,
        "REJECT": 20,
        "NONE": 50,
    }.get(str(grade or "NONE").upper(), 50)


def _normalize_strategy(strategy):
    return str(strategy or "SMC").upper()


# =========================================
# CONTROLLED AGGRESSION ENGINE
# =========================================

def compute_controlled_aggression(
    final_score,
    session_intelligence=50,
    volatility_state="NORMAL",
    recovery_mode=False,
):
    aggression = 1.0

    if final_score >= 90:
        aggression += 0.25
    elif final_score >= 80:
        aggression += 0.15
    elif final_score < 65:
        aggression -= 0.20

    if session_intelligence >= 75:
        aggression += 0.10

    if volatility_state == "EXPLOSIVE":
        aggression -= 0.15

    if recovery_mode:
        aggression -= 0.25

    aggression = max(0.45, min(1.50, aggression))
    return round(aggression, 2)


# =========================================
# SMART COOLDOWN ENGINE
# =========================================

def should_activate_cooldown():
    global LAST_LOSS_TIME
    global CONSECUTIVE_LOSSES
    global AI_COOLDOWN_ACTIVE

    if CONSECUTIVE_LOSSES >= 2:
        elapsed = time.time() - LAST_LOSS_TIME

        # 15 minute cooldown
        if elapsed < 900:
            AI_COOLDOWN_ACTIVE = True
            remaining = int((900 - elapsed) / 60)

            print(
                f"🧊 AI COOLDOWN ACTIVE"
                f" | losses={CONSECUTIVE_LOSSES}"
                f" | remaining={remaining}m"
            )

            return True

    AI_COOLDOWN_ACTIVE = False
    return False


# =========================================
# STRATEGY CONFIG
# =========================================

def get_strategy_mode_config(strategy="SMC", recovery=False):
    normalized = _normalize_strategy(strategy)

    if recovery or normalized == "RECOVERY":
        return {
            "threshold": 64,
            "penalty_multiplier": 1.2,
            "aggressiveness": "high",
            "execution_mode": "RECOVERY",
        }

    return {
        "threshold": 72 if normalized == "DAILY" else 66,
        "penalty_multiplier": 3.0 if normalized == "DAILY" else 1.5,
        "aggressiveness": "conservative" if normalized == "DAILY" else "balanced",
        "execution_mode": normalized if normalized in {"SMC", "DAILY"} else "SMC",
    }


# =========================================
# MASTER BREAKDOWN
# =========================================

def build_master_breakdown(brain_scores):
    parts = {
        "dna": round(float(brain_scores.get("dna_score", 0) or 0), 2),
        "knowledge": round(float(brain_scores.get("knowledge_score", 0) or 0), 2),
        "history": round(float(brain_scores.get("history_score", 0) or 0), 2),
        "news": round(float(brain_scores.get("news_score", 0) or 0), 2),
    }

    total = round(float(brain_scores.get("master_score", 0) or 0), 2)

    return {
        "master_score": total,
        "components": parts,
        "weights": {
            "dna": 0.35,
            "knowledge": 0.15,
            "history": 0.30,
            "news": 0.20,
        },
    }


# =========================================
# FINAL AI BRAIN
# =========================================

def compute_final_brain_score(
    master_score,
    confidence_pct,
    quality_score,
    exec_grade,
    ml_score=50,
    candle_weight=0,
    conflict_report=None,
    quality_gate_mode="STRICT_PASS",
    v7_bonus=0.0,
    reject_floor=54,
    wait_floor=54,
    reduced_floor=66,
    full_floor=80,
    conflict_penalty_reduction=0.0,
    strategy="SMC",
    ai_override=False,
    session_intelligence=50,
    volatility_state="NORMAL",
    recovery_mode=False,
):
    strategy_key = _normalize_strategy(strategy)
    strategy_mode = get_strategy_mode_config(strategy_key)

    # =====================================
    # AI COOLDOWN
    # =====================================

    if should_activate_cooldown():
        return {
            "final_score": 0,
            "verdict": "COOLDOWN",
            "strategy": strategy_key,
            "mode": strategy_mode.get("execution_mode", "SMC"),
            "cooldown_active": True,
        }

    # =====================================
    # CORE COMPONENTS
    # =====================================

    strategic_prior = round(float(master_score or 0), 2)

    setup_confidence = round(float(confidence_pct or 0), 2)

    executable_quality = round(
        (_grade_to_score(exec_grade) * 0.58) +
        (float(quality_score or 0) * 0.42),
        2,
    )

    learning_modifier = round(float(ml_score or 50), 2)

    candle_intelligence = round(
        min(max(float(candle_weight or 0), 0), 4) / 4 * 100,
        2,
    )

    ml_weight = {
        "DAILY": 0.15,
        "SMC": 0.25,
        "RECOVERY": 0.30,
    }.get(strategy_key, 0.10)

    base_score = round(
        strategic_prior * 0.28 +
        setup_confidence * 0.28 +
        executable_quality * 0.24 +
        learning_modifier * ml_weight +
        candle_intelligence * 0.10,
        2,
    )

    # =====================================
    # CONFLICT PENALTY
    # =====================================

    conflict_penalty = 0.0

    if isinstance(conflict_report, dict):

        aligned = int(conflict_report.get("aligned_count", 0) or 0)
        opposed = int(conflict_report.get("opposed_count", 0) or 0)

        if opposed > aligned:
            conflict_penalty = min(
                (opposed - aligned) *
                float(strategy_mode.get("penalty_multiplier", 4.0)),
                12.0,
            )

        elif aligned >= opposed + 2:
            conflict_penalty = -2.0

    penalty_reduction = float(conflict_penalty_reduction or 0)

    if penalty_reduction > 0 and conflict_penalty > 0:
        conflict_penalty = max(
            0.0,
            conflict_penalty - penalty_reduction,
        )

    # =====================================
    # AI ARBITRATION
    # =====================================

    arbitration = resolve_conflicting_signals(
        ai_score=max(0.0, min(1.0, setup_confidence / 100.0)),
        structure_score=max(0.0, min(1.0, strategic_prior / 100.0)),
        execution_score=max(0.0, min(1.0, executable_quality / 100.0)),
        risk_score=max(0.0, min(1.0, 1.0 - (float(quality_score or 0) / 100.0))),
    )

    arbitration_adjustment = 0.0

    if arbitration["decision"] == "reject":
        arbitration_adjustment = -8.0

    elif arbitration["decision"] == "hold":
        arbitration_adjustment = -2.0

    # =====================================
    # FINAL SCORE
    # =====================================

    final_score = round(
        max(
            0.0,
            min(
                100.0,
                base_score
                - conflict_penalty
                + float(v7_bonus or 0)
                + arbitration_adjustment
            ),
        ),
        2,
    )

    # =====================================
    # CONTROLLED AGGRESSION
    # =====================================

    aggression_multiplier = compute_controlled_aggression(
        final_score=final_score,
        session_intelligence=session_intelligence,
        volatility_state=volatility_state,
        recovery_mode=recovery_mode,
    )

    # =====================================
    # AI OVERRIDE
    # =====================================

    ai_override_applied = bool(
        ai_override
        and float(ml_score or 0) >= 90
        and float(confidence_pct or 0) >= 85
        and int(candle_weight or 0) >= 2
    )

    if ai_override_applied:
        final_score = round(min(100.0, final_score + 10.0), 2)

    # =====================================
    # VERDICT
    # =====================================

    if final_score >= float(full_floor):
        verdict = "EXECUTE_FULL"

    elif final_score >= float(reduced_floor):
        verdict = "EXECUTE_REDUCED"

    elif final_score >= float(wait_floor):
        verdict = "WAIT"

    else:
        verdict = "REJECT"

    # =====================================
    # FINAL OUTPUT
    # =====================================

    print(
        f"🧠 FINAL_BRAIN"
        f" | score={final_score}"
        f" | aggression={aggression_multiplier}"
        f" | verdict={verdict}"
        f" | strategy={strategy_key}"
    )

    return {
        "strategic_prior": strategic_prior,
        "setup_confidence": setup_confidence,
        "execution_quality": executable_quality,
        "learning_modifier": learning_modifier,
        "candle_intelligence": candle_intelligence,
        "conflict_penalty": round(conflict_penalty, 2),
        "final_score": final_score,
        "verdict": verdict,
        "strategy": strategy_key,
        "mode": strategy_mode.get("execution_mode", "SMC"),
        "aggression_multiplier": aggression_multiplier,
        "cooldown_active": False,
        "ai_override_applied": ai_override_applied,
    }


# =========================================
# REPORT STRING
# =========================================

def stringify_report(data):
    try:
        return json.dumps(data, ensure_ascii=False)

    except Exception:
        return str(data)
    
    # =========================================
# CONFLICT REPORT
# =========================================

def build_conflict_report(
    signal,
    daily_bias,
    mtf_direction,
    liquidity_bias,
    structure_bias,
    choch_data=None,
    liq_map=None
):

    bullish = []
    bearish = []

    def add(bucket, text):
        if text and text not in bucket:
            bucket.append(text)

    if signal == "BUY":
        add(bullish, f"Primary signal={signal}")

    elif signal == "SELL":
        add(bearish, f"Primary signal={signal}")

    if daily_bias == "BUY":
        add(bullish, "Daily bias bullish")

    elif daily_bias == "SELL":
        add(bearish, "Daily bias bearish")

    if mtf_direction == "BUY":
        add(bullish, "MTF structure bullish")

    elif mtf_direction == "SELL":
        add(bearish, "MTF structure bearish")

    if liquidity_bias == "BUY":
        add(bullish, "Liquidity bias bullish")

    elif liquidity_bias == "SELL":
        add(bearish, "Liquidity bias bearish")

    if structure_bias == "BUY":
        add(bullish, "Internal structure bullish")

    elif structure_bias == "SELL":
        add(bearish, "Internal structure bearish")

    if isinstance(choch_data, dict):

        choch = str(
            choch_data.get("choch_h4", "NONE")
        )

        if "BULL" in choch:
            add(bullish, f"CHOCH={choch}")

        elif "BEAR" in choch:
            add(bearish, f"CHOCH={choch}")

    if isinstance(liq_map, dict):

        liq_dir = str(
            liq_map.get("direction", "NEUTRAL")
        )

        if liq_dir in ("BUY", "UP"):
            add(bullish, "Liquidity map target above")

        elif liq_dir in ("SELL", "DOWN"):
            add(bearish, "Liquidity map target below")

    if len(bullish) > len(bearish):
        net = "BULLISH"

    elif len(bearish) > len(bullish):
        net = "BEARISH"

    else:
        net = "MIXED"

    aligned = len(bullish) if signal == "BUY" else len(bearish)
    opposed = len(bearish) if signal == "BUY" else len(bullish)

    return {
        "bullish_reasons": bullish,
        "bearish_reasons": bearish,
        "net_bias": net,
        "aligned_count": aligned,
        "opposed_count": opposed,
        "conflict_delta": aligned - opposed,
    }
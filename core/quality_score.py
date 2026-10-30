# =========================================
# FER3ON V5.6 — TRADE QUALITY SCORE
# Adaptive gate بدل الرفض المتشدد
# =========================================

from core.settings import (
    MIN_QUALITY_SCORE,
    QUALITY_SOFT_FLOOR,
    QUALITY_CONFIDENCE_BYPASS,
    QUALITY_SESSION_FLOORS,
    QUALITY_ADAPTIVE_MIN_FLOOR,
    QUALITY_FLOOR_SMC_ADJ,
    QUALITY_FLOOR_CANDLE_ADJ,
    QUALITY_FLOOR_SWEEP_ADJ,
    QUALITY_FLOOR_MISSED_ADJ,
    QUALITY_RISK_TABLE,
    MAX_RISK_TOTAL,
    TESTING_MODE,
    TESTING_MODE_QUALITY_THRESHOLDS,
    TESTING_MODE_RISK_MULTIPLIERS,
    NEWYORK_MIN_QUALITY_ENABLED,
    NEWYORK_MIN_QUALITY,
    QUALITY_SCORE_TRUST_ENABLED,
)


def _normalize_quality_session(session):
    text = str(session or "UNKNOWN").strip().upper().replace(" ", "_")
    aliases = {"NEWYORK": "NEW_YORK", "NEW_YORK": "NEW_YORK", "NY": "NEW_YORK"}
    return aliases.get(text, text)


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _strategy_soft_floor(strategy):
    return QUALITY_SOFT_FLOOR


def _session_floor(session, strategy):
    session_key = _normalize_quality_session(session)
    strategy_floor = _strategy_soft_floor(strategy)
    default_floor = int(QUALITY_SESSION_FLOORS.get(session_key, strategy_floor))
    # =========================================================================
    # FER3ON FINAL — NEWYORK QUALITY FLOOR (ported from V3.7, threshold from
    # V9FINAL1: 75 instead of V3.7's 80 which the build spec judged too
    # strict, and instead of no floor at all which V9fixed used). Instead of
    # the normal session logic (NEW_YORK lowers the floor by -2 below),
    # NEWYORK raises the minimum sharply — see build spec Merge item #3 /
    # FER3ON_FINAL_CHANGELOG.md [QUALITY-1]. This is an explicit override
    # that replaces the normal default_floor entirely for this session only.
    # =========================================================================
    if session_key == "NEW_YORK" and NEWYORK_MIN_QUALITY_ENABLED:
        return max(int(NEWYORK_MIN_QUALITY), default_floor)
    if session_key == "ASIA":
        return max(strategy_floor - 4, default_floor)
    if session_key == "LONDON":
        return max(strategy_floor - 1, default_floor)
    if session_key == "NEW_YORK":
        return max(strategy_floor - 2, default_floor)
    return max(strategy_floor, default_floor)


def calculate_quality_score(
    daily_bias,
    signal,
    mtf_strength,
    smc_strength,
    session_score,
    market_regime,
    candle_weight,
    strategy,
    execution_feasibility=1.0,
    liquidity_alignment=1.0,
):
    """
    يحسب جودة الصفقة (0-100) من 6 عوامل:
      Daily Bias     (0-20)
      MTF Consensus  (0-20)
      SMC Strength   (0-20) — SMC only
      Session        (0-10)
      Market Regime  (0-10)
      Candle Trigger (0-20)
    """
    score = 0
    max_possible = 0

    # 1) DAILY BIAS
    max_possible += 20
    if daily_bias == signal:
        score += 20
    elif daily_bias == "NONE":
        score += 10

    # 2) MTF CONSENSUS
    max_possible += 20
    mtf_pts = {3: 20, 2: 13, 1: 6, 0: 0}
    score += mtf_pts.get(mtf_strength, 0)

    # 3) SMC STRENGTH
    if str(strategy or "").upper() == "SMC":
        max_possible += 20
        smc_pts = min(int(smc_strength / 9 * 20), 20)
        score += smc_pts

    # 4) SESSION
    max_possible += 10
    session_pts = min(int(session_score / 100 * 10), 10)
    score += session_pts

    # 5) MARKET REGIME
    max_possible += 10
    regime_map = {
        "TRENDING": 10,
        "RANGING": 7,
        "VOLATILE": 4,
        "CRISIS": 0,
        "UNKNOWN": 4,
    }
    score += regime_map.get(market_regime, 5)

    # 6) CANDLE TRIGGER
    max_possible += 20
    candle_pts = {4: 20, 3: 18, 2: 13, 1: 7, 0: 0}
    score += candle_pts.get(candle_weight, 0)

    # 7) EXECUTION FEASIBILITY (new)
    max_possible += 10
    execution_pts = min(int(float(execution_feasibility or 0) * 10), 10)
    score += execution_pts

    # 8) LIQUIDITY ALIGNMENT (new)
    max_possible += 10
    liquidity_pts = min(int(float(liquidity_alignment or 0) * 10), 10)
    score += liquidity_pts

    if max_possible == 0:
        return 0

    return round(score / max_possible * 100)


def evaluate_quality_gate(
    quality_score,
    confidence_pct=0,
    strategy="UNKNOWN",
    optimizer_weights=None,
    dynamic_confidence_threshold=None,
    session="UNKNOWN",
    smc_entry_confirmed=False,
    candle_trigger_confirmed=False,
    sweep_probability=None,
    missed_opportunity_score=None,
    ml_score=None,
):
    """
    Adaptive quality gate with session-specific floors and reduced execution path.
    """
    # =========================================================================
    # FER3ON-FIX-2026-08-19 [QUALITY-INVERSION-1]: data from 120 real trades
    # proved the score is INVERTED (losers avg 55.5 > winners avg 35.6).
    # While QUALITY_SCORE_TRUST_ENABLED is False the gate passes everything
    # through and entry authority belongs to strategy_kill_switch +
    # expected_edge_gate. Recalibrate on >=50 post-FIX trades, verify positive
    # score/profit correlation, THEN re-enable via QUALITY_SCORE_TRUST=True.
    # =========================================================================
    if not QUALITY_SCORE_TRUST_ENABLED:
        return {
            "approved": True,
            "mode": "QUALITY_TRUST_DISABLED",
            "threshold": 0,
            "risk_multiplier": 1.00,
            "reason": (
                "QUALITY_SCORE_INVERTED_UNCALIBRATED: score bypassed per "
                "[QUALITY-INVERSION-1]; kill-switch + EV gate hold authority"
            ),
        }
    optimizer_weights = optimizer_weights or {}
    strict_threshold = int(optimizer_weights.get(f"{strategy}_threshold", MIN_QUALITY_SCORE))
    bypass_conf = int(
        dynamic_confidence_threshold
        if dynamic_confidence_threshold is not None
        else optimizer_weights.get("quality_confidence_bypass", QUALITY_CONFIDENCE_BYPASS)
    )

    if TESTING_MODE:
        thresholds = TESTING_MODE_QUALITY_THRESHOLDS
        full_threshold = int(thresholds.get("FULL", 65))
        reduced_threshold = int(thresholds.get("REDUCED", 55))
        micro_threshold = int(thresholds.get("MICRO", 45))

        if quality_score >= full_threshold and int(confidence_pct or 0) >= 50:
            return {
                "approved": True,
                "mode": "STRICT_PASS",
                "threshold": full_threshold,
                "risk_multiplier": 1.00,
                "reason": f"TESTING_FULL:{quality_score}>={full_threshold}",
            }

        context_boost = int(bool(smc_entry_confirmed)) + int(bool(candle_trigger_confirmed))
        if (
            quality_score >= micro_threshold
            and int(confidence_pct or 0) >= 50
            and (context_boost > 0 or _to_float(sweep_probability) > 80 or _to_float(missed_opportunity_score) > 60)
        ):
            return {
                "approved": True,
                "mode": "STRICT_PASS",
                "threshold": micro_threshold,
                "risk_multiplier": 1.00,
                "reason": f"QUALITY_FLOOR_ADJUSTMENT context_boost={context_boost}",
            }

        if quality_score >= reduced_threshold and int(confidence_pct or 0) >= 50:
            return {
                "approved": True,
                "mode": "EXECUTE_REDUCED",
                "threshold": reduced_threshold,
                "risk_multiplier": TESTING_MODE_RISK_MULTIPLIERS.get("REDUCED", 0.75),
                "reason": f"TESTING_REDUCED:{quality_score}>={reduced_threshold}",
            }

        min_confidence = 50
        if quality_score >= micro_threshold and int(confidence_pct or 0) >= min_confidence:
            return {
                "approved": True,
                "mode": "EXECUTE_MICRO",
                "threshold": micro_threshold,
                "risk_multiplier": TESTING_MODE_RISK_MULTIPLIERS.get("MICRO", 0.50),
                "reason": f"TESTING_MICRO:{quality_score}>={micro_threshold}",
            }

        return {
            "approved": False,
            "mode": "REJECT",
            "threshold": micro_threshold,
            "risk_multiplier": 0.0,
            "reason": f"TESTING_BLOCK:{quality_score}<{micro_threshold}",
        }

    session_key = _normalize_quality_session(session)
    strategy_floor = _strategy_soft_floor(strategy)
    base_floor = int(
        optimizer_weights.get(
            f"quality_floor_{session_key.lower()}",
            _session_floor(session, strategy),
        )
    )
    session_adj = base_floor - strategy_floor
    smc_adj = QUALITY_FLOOR_SMC_ADJ if bool(smc_entry_confirmed) else 0
    candle_adj = QUALITY_FLOOR_CANDLE_ADJ if bool(candle_trigger_confirmed) else 0
    sweep_adj = QUALITY_FLOOR_SWEEP_ADJ if _to_float(sweep_probability) > 80 else 0
    missed_adj = QUALITY_FLOOR_MISSED_ADJ if _to_float(missed_opportunity_score) > 60 else 0
    final_floor = max(
        QUALITY_ADAPTIVE_MIN_FLOOR,
        base_floor + smc_adj + candle_adj + sweep_adj + missed_adj,
    )

    floor_log = (
        f"QUALITY_FLOOR_ADJUSTMENT BaseFloor={base_floor} "
        f"SessionAdj={session_adj:+d} SMCAdj={smc_adj:+d} "
        f"CandleAdj={candle_adj:+d} SweepAdj={sweep_adj:+d} "
        f"MissedOppAdj={missed_adj:+d} FinalFloor={final_floor}"
    )

    ai_confident = int(ml_score or 0) >= 90 and int(confidence_pct or 0) >= 85
    reduced_bypass = ai_confident and int(quality_score or 0) >= max(QUALITY_ADAPTIVE_MIN_FLOOR - 12, 30)

    # =========================================================================
    # FER3ON FINAL — NEWYORK QUALITY FLOOR: also applied to strict_threshold.
    # Without this, the STRICT_PASS path below used strict_threshold built
    # from MIN_QUALITY_SCORE alone (session-unaware), so a NEWYORK trade could
    # pass here at a lower quality than NEWYORK_MIN_QUALITY before the
    # session-aware final_floor is ever checked. Ported from V3.7 — see
    # build spec Merge item #3 / FER3ON_FINAL_CHANGELOG.md [QUALITY-1].
    # =========================================================================
    is_newyork = NEWYORK_MIN_QUALITY_ENABLED and _normalize_quality_session(session) == "NEW_YORK"
    if is_newyork:
        strict_threshold = max(strict_threshold, int(NEWYORK_MIN_QUALITY))

    if quality_score >= strict_threshold and int(confidence_pct or 0) >= 55:
        return {
            "approved": True,
            "mode": "STRICT_PASS",
            "threshold": strict_threshold,
            "risk_multiplier": 1.00,
            "reason": f"{floor_log} | QUALITY_OK:{quality_score}>={strict_threshold}",
        }

    reduced_threshold = max(final_floor, strict_threshold + 1)
    # FER3ON FINAL: this SMC fast-pass bypasses the floor logic entirely
    # at a flat quality>=45 — excluded during NEWYORK so no path can dodge
    # NEWYORK_MIN_QUALITY (see [QUALITY-1]).
    if (
        not is_newyork
        and quality_score >= max(45.0, final_floor - 2.0)
        and int(confidence_pct or 0) >= 45
        and str(strategy or "UNKNOWN").upper() == "SMC"
    ):
        return {
            "approved": True,
            "mode": "STRICT_PASS",
            "threshold": 45,
            "risk_multiplier": 0.75,
            "reason": f"{floor_log} | QUALITY_FLOOR_ADJUSTMENT context_boost=2",
        }
    # =========================================================================
    # FER3ON FINAL — NEWYORK QUALITY FLOOR applied to the weak-bypass path.
    # Ported from V3.7: the general `quality_score >= QUALITY_ADAPTIVE_MIN_FLOOR`
    # bypass (a flat ~42 regardless of session) used to override final_floor
    # completely. Now blocked for NEWYORK specifically when quality is below
    # final_floor — ai_confident (reduced_bypass) stays allowed even in
    # NEWYORK since it already requires ml_score>=90 and confidence>=85,
    # which counts as "exceptionally clear" on its own. See [QUALITY-1].
    # =========================================================================
    weak_bypass_blocked_in_newyork = (
        is_newyork and int(quality_score or 0) < final_floor
    )
    weak_bypass_ok = (
        quality_score >= QUALITY_ADAPTIVE_MIN_FLOOR
        and int(confidence_pct or 0) >= 45
        and not weak_bypass_blocked_in_newyork
    )
    if reduced_bypass or weak_bypass_ok:
        return {
            "approved": True,
            "mode": "EXECUTE_REDUCED",
            "threshold": reduced_threshold,
            "risk_multiplier": TESTING_MODE_RISK_MULTIPLIERS.get("REDUCED", 0.75),
            "reason": f"{floor_log} | QUALITY_REDUCED:{quality_score} < {strict_threshold} | AI_BYPASS={ai_confident}",
        }

    if quality_score >= final_floor:
        return {
            "approved": True,
            "mode": "ADAPTIVE_PASS",
            "threshold": final_floor,
            "risk_multiplier": TESTING_MODE_RISK_MULTIPLIERS.get("REDUCED", 0.75),
            "reason": f"{floor_log} | QUALITY_ADAPTIVE:{quality_score}>={final_floor}",
        }

    # =========================================================================
    # FER3ON FINAL — NEWYORK QUALITY FLOOR applied to the last-resort fallback.
    # This is the final line of defense before REJECT — it used to be a flat
    # 43 regardless of session, letting a NEWYORK trade at quality 58 through
    # as EXECUTE_MICRO despite final_floor=75 computed above. Ported from
    # V3.7 — see [QUALITY-1]. Other sessions (final_floor typically <=43)
    # keep their exact prior behaviour.
    # =========================================================================
    hard_floor = max(43, final_floor) if is_newyork else 43
    if int(quality_score or 0) >= hard_floor and int(confidence_pct or 0) >= 40:
        return {
            "approved": True,
            "mode": "EXECUTE_MICRO",
            "threshold": hard_floor,
            "risk_multiplier": TESTING_MODE_RISK_MULTIPLIERS.get("MICRO", 0.50),
            "reason": f"{floor_log} | QUALITY_MICRO_FALLBACK:{quality_score}>={hard_floor}",
        }

    return {
        "approved": False,
        "mode": "REJECT",
        "threshold": final_floor,
        "risk_multiplier": 0.0,
        "reason": f"{floor_log} | QUALITY_REJECT:{quality_score} < HardFloor={hard_floor}",
    }


def get_quality_risk(quality_score):
    for threshold, risk in QUALITY_RISK_TABLE:
        if quality_score >= threshold:
            return min(risk, MAX_RISK_TOTAL)
    return min(QUALITY_RISK_TABLE[-1][1], MAX_RISK_TOTAL)


def quality_label(score):
    if score >= 90:
        return "EXCELLENT ✨"
    if score >= 80:
        return "GOOD 👍"
    if score >= 70:
        return "ACCEPTABLE ✅"
    if score >= 60:
        return "BORDERLINE+ ✅"
    if score >= QUALITY_SOFT_FLOOR:
        return "ADAPTIVE ⚠️"
    return "REJECTED ❌"

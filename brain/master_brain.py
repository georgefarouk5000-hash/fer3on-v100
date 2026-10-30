# =========================================
# FER3ON V7.0 — MASTER BRAIN V4 (ADAPTIVE)
# - hard floor 25 → 20
# - low_score floor 42 → 35 + MICRO fallback بدل block
# - تكامل مع unified_decision (يصبح ranking only لا veto)
# =========================================
MASTER_HARD_FLOOR = 20
MASTER_LOW_SCORE_FLOOR = 35
MASTER_MICRO_BAND_TOP = 44   # 35–44 → MICRO suggestion

import csv
from pathlib import Path

from brain.trade_dna import get_trade_dna_score
from brain.knowledge_base import get_knowledge_score, get_psychology_notes
from brain.news_memory import get_news_score
from core.build_scope import filter_current_build_rows
from core.outcome_learning import get_replay_memory, get_probability_distribution

# [FER3ON-FIX-2026-08-20 BRAIN-SCOPE-CONNECT]
# get_trade_dna_display, find_similar_trades and get_history_score were
# imported here but never called anywhere in this file (verified: zero
# call sites below besides the import line itself) — dead imports left
# over from before this module had its own separate, unfiltered
# _calculate_historical_wr()/_calculate_recent_memory() implementation.
# get_trade_dna_score is now genuinely used below; find_similar_trades is
# reached transitively through it (brain/trade_dna.py calls it
# internally). get_trade_dna_display and get_history_score are still
# unused here on purpose — see the comment on _load_history_rows() below
# for why history_score/memory_score were fixed by filtering their
# existing data source rather than switching to
# history_learner.get_history_score()/analyze_history(), which measures a
# different thing (global BUY vs SELL win rate, no strategy/regime/session
# breakdown) and has no `signal` argument available in this function's
# signature.


# =========================================
# REGIME ↔ STRATEGY MATRIX
# =========================================

REGIME_STRATEGY_FIT = {
    "DAILY": {
        "TRENDING": 1.18,
        "RANGING": 0.62,
        "VOLATILE": 0.58,
        "CRISIS": 0.30,
    },
    "SMC": {
        "TRENDING": 1.02,
        "RANGING": 1.18,
        "VOLATILE": 0.96,
        "CRISIS": 0.60,
    },
}

ENTRY_GRADE_SCORE = {
    "A+": 96,
    "A": 88,
    "B+": 79,
    "B": 70,
    "C": 57,
    "NONE": 40,
}

SOFT_PENALTIES = {
    "DAILY_BIAS_CONFLICT": -6,
    "OFF_SESSION": -4,
    "WEAK_SMC": -7,
    "VOLATILE_LIGHT": -6,
}

MAX_SOFT_PENALTY = 15

STRATEGY_SCORE_WEIGHTS = {
    "SMC": {
        "master": 0.22,
        "session": 0.10,
        "dna": 0.08,
        "regime": 0.10,
        "signal": 0.12,
        "alignment": 0.10,
        "entry": 0.28,
    },
    "DAILY": {
        "master": 0.34,
        "session": 0.14,
        "dna": 0.12,
        "regime": 0.18,
        "signal": 0.08,
        "alignment": 0.14,
        "entry": 0.00,
    },
}


# =========================================
# HELPERS
# =========================================


def _safe_grade(grade):
    return str(grade or "NONE").upper()



def _calc_alignment_score(signal, daily_bias, liquidity_bias, structure_bias):
    score = 50

    if daily_bias == signal:
        score += 16
    elif daily_bias not in ("NONE", "NEUTRAL", None) and daily_bias != signal:
        score -= 12

    if liquidity_bias == signal:
        score += 18
    elif liquidity_bias not in ("NONE", "NEUTRAL", None) and liquidity_bias != signal:
        score -= 14

    if structure_bias == signal:
        score += 16
    elif structure_bias not in ("NONE", "NEUTRAL", None) and structure_bias != signal:
        score -= 12

    return max(0, min(100, round(score, 2)))



def _calc_signal_quality(strategy, smc_strength, entry_grade):
    grade = _safe_grade(entry_grade)
    base = 55

    if strategy == "SMC":
        base = 35 + min(max(float(smc_strength or 0), 0), 9) * 6.5
        base = (base * 0.42) + (ENTRY_GRADE_SCORE.get(grade, 40) * 0.58)
    elif strategy == "DAILY":
        base = 62

    return max(0, min(100, round(base, 2)))



def _calc_entry_score(strategy, entry_grade):
    if strategy != "SMC":
        return 50
    return ENTRY_GRADE_SCORE.get(_safe_grade(entry_grade), 40)



def _apply_penalties(strategy, market_regime, session_score, smc_strength, daily_bias, signal):
    penalties = []
    penalty_total = 0

    if strategy == "SMC" and daily_bias not in ("NONE", None) and signal != daily_bias:
        penalties.append("DAILY_BIAS_CONFLICT")
        penalty_total += abs(SOFT_PENALTIES["DAILY_BIAS_CONFLICT"])

    if session_score < 30:
        penalties.append("OFF_SESSION")
        penalty_total += abs(SOFT_PENALTIES["OFF_SESSION"])

    if strategy == "SMC" and float(smc_strength or 0) < 2:
        penalties.append("WEAK_SMC")
        penalty_total += abs(SOFT_PENALTIES["WEAK_SMC"])

    if market_regime == "VOLATILE":
        penalties.append("VOLATILE_LIGHT")
        penalty_total += abs(SOFT_PENALTIES["VOLATILE_LIGHT"])

    return penalties, min(MAX_SOFT_PENALTY, penalty_total)


# =========================================
# GET MASTER SCORE
# =========================================

HISTORY_TRADES_CSV = Path('data/history/trades.csv')
HISTORY_MT5_CSV = Path('data/history/mt5_trade_history.csv')


def _load_history_rows():
    # [FER3ON-FIX-2026-08-20 BRAIN-SCOPE-CONNECT]
    # This was the actual disconnect the 2026-08-19 BRAIN-SCOPE patch left
    # open: main.py's live decision calls get_master_score() (main.py:536),
    # not core/brain_unified.py (which only test/smoke scripts import) —
    # and get_master_score() fed history_score + memory_score (60% of its
    # weights) from this loader with zero build_id/date filtering, reading
    # trades.csv/mt5_trade_history.csv raw via csv.DictReader. That meant
    # core/build_scope.py's protection never actually reached the live
    # master_score despite shipping the same day.
    #
    # Route both sources through the same central filter the rest of
    # BRAIN-SCOPE already uses (history_learner.py, trade_dna.py,
    # self_optimizer.py, adaptive_weighting.py, confidence_engine.py) —
    # each with the date_field matching its own schema, since these two
    # CSVs are not the same shape: trades.csv has a `date` column
    # (trade_logger.py), mt5_trade_history.csv has open_time/close_time
    # instead (mt5_history_sync.py), no `date` field at all. In current
    # data every row in both files already carries an explicit build_id
    # (old value 'FER3ON-FINAL-build1'), so the date fallback isn't
    # exercised today — but it's wired correctly for any future row that
    # ever lands here without one. No data is deleted; excluded rows stay
    # on disk as archive, same as every other BRAIN-SCOPE filter.
    rows = []
    for path, date_field in (
        (HISTORY_TRADES_CSV, 'date'),
        (HISTORY_MT5_CSV, 'close_time'),
    ):
        if not path.exists():
            continue
        try:
            with path.open('r', encoding='utf-8', newline='') as fh:
                raw_rows = list(csv.DictReader(fh))
            rows.extend(filter_current_build_rows(raw_rows, date_field=date_field))
        except Exception:
            continue
    return rows


def _calculate_historical_wr(strategy, market_regime, session, min_trades=8):
    try:
        strategy = str(strategy or 'SMC').upper()
        market_regime = str(market_regime or 'RANGING').upper()
        session = str(session or 'LONDON').upper()
        matches = []
        for row in _load_history_rows():
            if (
                str(row.get('strategy', '')).upper() == strategy
                and str(row.get('regime', row.get('market_regime', ''))).upper() == market_regime
                and str(row.get('session', '')).upper() == session
            ):
                matches.append(row)
        if len(matches) < min_trades:
            return 50.0
        wins = sum(
            1
            for row in matches
            if str(row.get('result', '')).upper() == 'WIN'
            or float(row.get('profit', 0) or 0) > 0
        )
        return round(wins / len(matches) * 100.0, 2)
    except Exception:
        return 50.0


def _calculate_recent_memory(strategy, window=20):
    try:
        strategy = str(strategy or 'SMC').upper()
        strat_rows = [
            row
            for row in _load_history_rows()
            if str(row.get('strategy', '')).upper() == strategy
        ]
        strat_rows = strat_rows[-window:]
        if len(strat_rows) < 5:
            return 50.0
        wins = sum(
            1
            for row in strat_rows
            if str(row.get('result', '')).upper() == 'WIN'
            or float(row.get('profit', 0) or 0) > 0
        )
        return round(wins / len(strat_rows) * 100.0, 2)
    except Exception:
        return 50.0


def get_master_score(strategy='SMC', market_regime='RANGING', session='LONDON'):
    # history_score / memory_score: same local calculations as before,
    # now reading build-filtered rows via the updated _load_history_rows().
    history_score = _calculate_historical_wr(strategy, market_regime, session)
    memory_score = _calculate_recent_memory(strategy)
    # [FER3ON-FIX-2026-08-20 BRAIN-SCOPE-CONNECT] dna_score used to be a
    # fake stand-in, (history_score + memory_score) / 2 — it never called
    # the real DNA similarity scorer despite importing it (0 call sites).
    # It now calls the actual build-filtered, pattern-matched score from
    # brain/trade_dna.py (identical strategy/market_regime/session
    # signature), which carries its own conservative neutral-prior
    # gradient: 25.0 flat with zero current-build matches, 25->45 for a
    # 1-4 trade sample, a real weighted score once >=5 similar trades
    # exist.
    dna_score = get_trade_dna_score(strategy, market_regime, session)
    knowledge_score = get_knowledge_score(market_regime, session)
    news_score = get_news_score()
    # ملاحظات سيكولوجية إرشادية فقط — لا تُدمج في master_score العددي
    # عمدًا (خلط "جودة الإشارة" بـ"حالة نفسية متوقعة" في رقم واحد قد
    # يُفهم خطأً كثقة إحصائية إضافية بالصفقة).
    psychology_notes = get_psychology_notes(market_regime, session)

    master_score = round(
        history_score * 0.35
        + memory_score * 0.25
        + dna_score * 0.20
        + knowledge_score * 0.10
        + news_score * 0.10,
        2,
    )

    print(
        f'🧠 MASTER LIVE | Hist:{history_score}'
        f' | Memory:{memory_score}'
        f' | DNA:{dna_score}'
        f' | Know:{knowledge_score}'
        f' | News:{news_score}'
        f' | MASTER:{master_score}'
    )

    return {
        'master_score': master_score,
        'history_score': round(history_score, 2),
        'memory_score': round(memory_score, 2),
        'dna_score': round(dna_score, 2),
        'knowledge_score': round(knowledge_score, 2),
        'news_score': round(news_score, 2),
        'psychology_notes': psychology_notes,
        # [BRAIN-SCOPE-CONNECT] was 'live_csv' (unfiltered) — now build-scoped.
        'source': 'live_csv_build_filtered',
        'breakdown': {
            'history': round(history_score, 2),
            'memory': round(memory_score, 2),
            'dna': round(dna_score, 2),
            'knowledge': round(knowledge_score, 2),
            'news': round(news_score, 2),
            'weights': {
                'history': 0.35,
                'memory': 0.25,
                'dna': 0.20,
                'knowledge': 0.10,
                'news': 0.10,
            },
        },
    }

# =========================================
# MASTER BRAIN DECIDE V3
# =========================================


def master_brain_decide(
    available_signals,
    smc_strength,
    market_regime,
    session,
    daily_bias,
    master_score,
    dna_score,
    session_score,
    crisis_mult,
    entry_grade="NONE",
    liquidity_bias="NEUTRAL",
    structure_bias="NEUTRAL",
):
    """
    V5.7:
      - SMC grade تم تحويلها إلى score band حقيقي
      - الخصومات القصوى لا تتجاوز 15 نقطة
      - SMC uses the Entry Grade score directly
      - إعادة وزن القرار لتقليل ظلم SMC عند وجود B+ أو أعلى
    """

    if market_regime == "CRISIS":
        return _block("CRISIS_REGIME")

    if crisis_mult == 0:
        return _block("CRISIS_FREEZE")

    if master_score < MASTER_HARD_FLOOR:
        return _block("LOW_MASTER_SCORE")

    ranked = []

    for strategy, signal in available_signals.items():
        if strategy not in STRATEGY_SCORE_WEIGHTS:
            continue
        if signal == "NONE":
            continue

        regime_fit = REGIME_STRATEGY_FIT.get(strategy, {}).get(market_regime, 0.8)
        if regime_fit == 0:
            continue

        weights = STRATEGY_SCORE_WEIGHTS.get(strategy, STRATEGY_SCORE_WEIGHTS["DAILY"])
        regime_score = max(0, min(100, round(regime_fit * 100, 2)))
        signal_quality = _calc_signal_quality(strategy, smc_strength, entry_grade)
        alignment_score = _calc_alignment_score(signal, daily_bias, liquidity_bias, structure_bias)
        entry_score = _calc_entry_score(strategy, entry_grade)
        replay = get_replay_memory(
            strategy=strategy,
            signal=signal,
            session=session,
            market_regime=market_regime,
            quality_score=signal_quality,
            exec_grade=entry_grade if strategy == "SMC" else "B",
        )
        probabilities = get_probability_distribution(
            signal=signal,
            replay_stats=replay,
            base_confidence=(signal_quality + alignment_score + entry_score) / 3,
        )
        directional_prob = probabilities.get(signal, 50.0)

        base_score = (
            master_score * weights["master"] +
            session_score * weights["session"] +
            dna_score * weights["dna"] +
            regime_score * weights["regime"] +
            signal_quality * weights["signal"] +
            alignment_score * weights["alignment"] +
            entry_score * weights["entry"]
        )

        penalties_applied, penalty_total = _apply_penalties(
            strategy=strategy,
            market_regime=market_regime,
            session_score=session_score,
            smc_strength=smc_strength,
            daily_bias=daily_bias,
            signal=signal,
        )

        smc_override_bonus = 0
        replay_bonus = 0
        grade = _safe_grade(entry_grade)
        if strategy == "SMC" and grade in ("A+", "A", "B+"):
            if liquidity_bias == signal:
                smc_override_bonus += 4
            if structure_bias == signal:
                smc_override_bonus += 3
            if daily_bias not in ("NONE", None) and daily_bias != signal:
                smc_override_bonus += 2
            smc_override_bonus = min(smc_override_bonus, 7)

        if replay.get("count", 0) >= 5:
            if directional_prob >= 68:
                replay_bonus += min((directional_prob - 60) / 4.0, 6)
            elif directional_prob <= 45:
                replay_bonus -= min((50 - directional_prob) / 3.0, 6)

        total_score = round(max(0, min(100, base_score - penalty_total + smc_override_bonus + replay_bonus)), 2)

        if penalties_applied:
            print(
                f"⚠️  {strategy}: Soft Penalties Applied: {penalties_applied}"
                f" | PenaltyCap:{penalty_total}"
                f" | Score after:{total_score}"
            )

        print(
            f"🧠 BRAIN FACTORS {strategy} {signal}"
            f" | Base:{round(base_score, 2)}"
            f" | Entry:{entry_score}"
            f" | Align:{alignment_score}"
            f" | SignalQ:{signal_quality}"
            f" | Regime:{regime_score}"
            f" | Bonus:{smc_override_bonus:+d}"
            f" | Replay:{replay_bonus:+.1f}"
            f" | Prob:{directional_prob:.1f}%"
            f" | Final:{total_score}"
        )

        ranked.append({
            "strategy": strategy,
            "signal": signal,
            "score": total_score,
            "regime_fit": regime_fit,
            "penalties": penalties_applied,
            "penalty_total": penalty_total,
            "entry_grade": grade,
            "entry_score": entry_score,
            "alignment_score": alignment_score,
            "signal_quality": signal_quality,
            "smc_override_bonus": smc_override_bonus,
            "replay_bonus": round(replay_bonus, 2),
            "replay_memory": replay,
            "probabilities": probabilities,
            "directional_prob": round(directional_prob, 1),
        })

    if not ranked:
        return _block("NO_VALID_SIGNALS")

    ranked.sort(
        key=lambda x: (
            x["score"],
            x["entry_score"] if x["strategy"] == "SMC" else 0,
            x["alignment_score"],
        ),
        reverse=True,
    )
    best = ranked[0]

    # V7 ADAPTIVE: بدل ما نعمل block على 42, نخفض الـ floor إلى 35
    # وكل ما تحت 44 يدخل بـ MICRO path (يقرره unified_decision لاحقاً)
    if best["score"] < MASTER_LOW_SCORE_FLOOR:
        return _block(f"LOW_SCORE_{best['score']}")

    suggest_size = "FULL"
    if best["score"] < MASTER_MICRO_BAND_TOP:
        suggest_size = "MICRO"
        risk_mult = 0.30
    elif best["score"] < 58:
        suggest_size = "REDUCED"
        risk_mult = 0.55
    elif best["score"] < 74:
        risk_mult = 0.85
    elif best["score"] < 86:
        risk_mult = 1.00
    else:
        risk_mult = 1.15

    print(
        f"🧠 FER3ON AI V2 BRAIN: {best['strategy']}"
        f" {best['signal']}"
        f" | Score:{best['score']}"
        f" | EntryGrade:{best['entry_grade']}"
        f" | EntryScore:{best['entry_score']}"
        f" | Align:{best['alignment_score']}"
        f" | Prob:{best.get('directional_prob', 50)}%"
        f" | RiskMult:{risk_mult}"
    )

    return {
        "execute": True,
        "strategy": best["strategy"],
        "signal": best["signal"],
        "score": best["score"],
        "risk_mult": risk_mult,
        "suggest_size": suggest_size,    # V7: FULL / REDUCED / MICRO suggestion
        "entry_grade": best["entry_grade"],
        "reason": "OK",
        "penalties": best["penalties"],
        "directional_prob": best.get("directional_prob", 50),
        "alignment_score": best.get("alignment_score", 50),
        "signal_quality": best.get("signal_quality", 50),
    }


# =========================================
# HELPER
# =========================================


def _block(reason):
    print(f"🧠 BRAIN BLOCKED: {reason}")
    return {
        "execute": False,
        "strategy": None,
        "signal": None,
        "score": 0,
        "risk_mult": 0,
        "entry_grade": "NONE",
        "reason": reason,
        "penalties": [],
    }

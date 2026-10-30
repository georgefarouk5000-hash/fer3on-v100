# =============================================================================
# FER3ON — PHASE 3 | GOLD_CONTEXT_LAYER (Shadow Mode)
# =============================================================================
# الدور: طبقة السياق الماكرو لـ XAUUSD.
# الوضع الحالي: SHADOW ONLY — modifier فقط، لا يحجب وحده أبداً.
#
# العوامل المُقيَّمة:
#   - DXY Trend (اتجاه الدولار)
#   - Real Yields (العوائد الحقيقية)
#   - CPI Pressure (ضغط التضخم)
#   - NFP Momentum (زخم سوق العمل)
#   - FOMC Stance (موقف الفيدرالي)
#   - Geopolitical Risk (المخاطر الجيوسياسية)
#   - Rate Differential (فروق أسعار الفائدة)
#
# المخرج: Gold_Context_Score (0-100) — عامل ترجيح خفيف في FINAL_BRAIN
# القيد الصارم: لا يُستخدم كشرط دخول أساسي وحده
#
# ما لا يفعله:
#   - لا يفتح صفقة وحده
#   - لا يُغيّر direction logic
#   - لا يعمل كـ hard blocker
# =============================================================================

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.settings import (
    GOLD_CONTEXT_ENABLED,
    GOLD_CONTEXT_FACTOR_WEIGHTS,
    GOLD_CONTEXT_HARD_BLOCK_ALLOWED,
    GOLD_CONTEXT_LIVE_INFLUENCE,
    GOLD_CONTEXT_MAX_NEGATIVE_INFLUENCE,
    GOLD_CONTEXT_MAX_POSITIVE_INFLUENCE,
    GOLD_CONTEXT_SHADOW_LOG,
    PHASE3_GOLD_CONTEXT_DIR,
    PHASE3_GOLD_MACRO_FACTORS_PATH,
)

_SHADOW_LOG_FILE = os.path.join(PHASE3_GOLD_CONTEXT_DIR, "shadow_gold_context.jsonl")
_STATE_FILE = os.path.join(PHASE3_GOLD_CONTEXT_DIR, "gold_context_state.json")

assert not GOLD_CONTEXT_HARD_BLOCK_ALLOWED, (
    "GOLD_CONTEXT: Hard blocking is disabled by design. "
    "Gold context is a modifier only, never a standalone blocker."
)
assert not GOLD_CONTEXT_LIVE_INFLUENCE, (
    "GOLD_CONTEXT: Live influence is disabled in Phase 3. "
    "Enable only after shadow validation."
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GoldMacroFactors:
    """
    العوامل الماكرو لـ XAUUSD.
    اتفاقية الإشارة الموحّدة:
      قيمة موجبة (+) = إيجابي للذهب (bullish gold)
      قيمة سلبية (-) = سلبي للذهب (bearish gold)
      0 = محايد / غير متاح

    أمثلة:
      dxy_trend = -60  → دولار قوي = سلبي للذهب
      dxy_trend = +60  → دولار ضعيف = إيجابي للذهب
      real_yields = -50 → عوائد مرتفعة = سلبي للذهب
      real_yields = +50 → عوائد منخفضة = إيجابي للذهب
      cpi_pressure = +70 → تضخم مرتفع = إيجابي للذهب
      geopolitical = +80 → توترات = إيجابي للذهب كملاذ آمن
      fomc_stance = -60 → hawkish = سلبي للذهب
      fomc_stance = +60 → dovish = إيجابي للذهب
    """
    dxy_trend: float = 0.0
    real_yields: float = 0.0
    cpi_pressure: float = 0.0
    nfp_momentum: float = 0.0
    fomc_stance: float = 0.0
    geopolitical: float = 0.0
    rate_differential: float = 0.0
    data_freshness_hours: float = 24.0
    source: str = "manual"


@dataclass
class GoldContextOutput:
    """مخرج طبقة السياق."""
    gold_context_score: float = 50.0    # 0-100، 50 = محايد
    context_influence: float = 0.0     # التأثير الفعلي على الدرجة (محدود بـ settings)
    signal_alignment: str = "NEUTRAL"  # BULLISH_ALIGNED / BEARISH_ALIGNED / NEUTRAL
    factor_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    mode: str = "SHADOW"
    timestamp: float = field(default_factory=time.time)


def load_gold_macro_factors(
    path: str = PHASE3_GOLD_MACRO_FACTORS_PATH,
    *,
    now: Optional[datetime] = None,
) -> Tuple[Optional[GoldMacroFactors], str]:
    """Load validated, timestamped macro inputs; never manufacture neutral data."""
    try:
        with open(path, "r", encoding="utf-8") as source_file:
            data = json.load(source_file)
    except FileNotFoundError:
        return None, "macro feed file not found"
    except (OSError, json.JSONDecodeError) as error:
        return None, f"macro feed could not be read: {error}"

    if not isinstance(data, dict):
        return None, "macro feed must be a JSON object"

    sampled_at = data.get("sampled_at")
    provider = data.get("source")
    factor_values = data.get("factors")
    if not isinstance(sampled_at, str) or not isinstance(provider, str) or not provider.strip():
        return None, "macro feed requires sampled_at and a non-empty source"
    if not isinstance(factor_values, dict):
        return None, "macro feed requires a factors object"

    try:
        sampled_time = datetime.fromisoformat(sampled_at.replace("Z", "+00:00"))
        if sampled_time.tzinfo is None:
            return None, "macro feed sampled_at must include a timezone"
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            return None, "current time must include a timezone"
        age_hours = (current_time - sampled_time).total_seconds() / 3600
    except (TypeError, ValueError) as error:
        return None, f"macro feed sampled_at is invalid: {error}"

    if age_hours < -5 / 60:
        return None, "macro feed timestamp is in the future"
    if age_hours > 72:
        return None, f"macro feed is stale ({age_hours:.1f} hours old)"

    factor_names = (
        "dxy_trend",
        "real_yields",
        "cpi_pressure",
        "nfp_momentum",
        "fomc_stance",
        "geopolitical",
        "rate_differential",
    )
    validated: Dict[str, float] = {}
    for name in factor_names:
        value = factor_values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"macro factor {name} must be numeric"
        if not math.isfinite(value) or not -100 <= value <= 100:
            return None, f"macro factor {name} must be finite and between -100 and 100"
        validated[name] = float(value)

    return GoldMacroFactors(
        **validated,
        data_freshness_hours=max(0.0, age_hours),
        source=provider.strip(),
    ), "available"


# =============================================================================
# CORE LOGIC
# =============================================================================

def _ensure_dirs() -> None:
    os.makedirs(PHASE3_GOLD_CONTEXT_DIR, exist_ok=True)


def _compute_weighted_context(factors: GoldMacroFactors) -> Tuple[float, Dict[str, float]]:
    """
    يحسب الدرجة المركّبة المرجّحة للسياق الماكرو.
    يعيد (raw_score في نطاق -100 إلى +100، تفاصيل العوامل).
    """
    factor_values = {
        "dxy_trend":        factors.dxy_trend,
        "real_yields":      factors.real_yields,
        "cpi_pressure":     factors.cpi_pressure,
        "nfp_momentum":     factors.nfp_momentum,
        "fomc_stance":      factors.fomc_stance,
        "geopolitical":     factors.geopolitical,
        "rate_differential": factors.rate_differential,
    }

    weighted_sum = 0.0
    factor_scores = {}
    total_weight = 0.0

    for factor_name, weight in GOLD_CONTEXT_FACTOR_WEIGHTS.items():
        value = factor_values.get(factor_name, 0.0)
        # قيّد كل عامل في [-100, +100]
        clamped = max(-100.0, min(100.0, value))
        contribution = clamped * weight
        weighted_sum += contribution
        factor_scores[factor_name] = round(contribution, 3)
        total_weight += weight

    # تطبيع إذا كان مجموع الأوزان لا يساوي 1
    if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
        weighted_sum /= total_weight

    return weighted_sum, factor_scores


def _apply_freshness_decay(raw_score: float, freshness_hours: float) -> float:
    """
    تخفيف تأثير البيانات القديمة تدريجياً.
    بيانات > 48 ساعة → تأثير النصف.
    بيانات > 72 ساعة → لا تأثير (محايد).
    """
    if freshness_hours <= 24:
        return raw_score
    elif freshness_hours <= 48:
        decay = 1.0 - ((freshness_hours - 24) / 24) * 0.5
        return raw_score * decay
    elif freshness_hours <= 72:
        decay = 0.5 - ((freshness_hours - 48) / 24) * 0.5
        return raw_score * max(0.0, decay)
    else:
        return 0.0  # بيانات قديمة جداً → محايد


def _determine_signal_alignment(context_influence: float, signal: str) -> str:
    """هل السياق الماكرو متوافق مع إشارة التداول؟"""
    is_bullish_context = context_influence > 2.0
    is_bearish_context = context_influence < -2.0

    if signal in ("BUY", "LONG"):
        if is_bullish_context:
            return "BULLISH_ALIGNED"
        elif is_bearish_context:
            return "BEARISH_CONFLICT"
        else:
            return "NEUTRAL"
    elif signal in ("SELL", "SHORT"):
        if is_bearish_context:
            return "BEARISH_ALIGNED"
        elif is_bullish_context:
            return "BULLISH_CONFLICT"
        else:
            return "NEUTRAL"
    return "NEUTRAL"


# =============================================================================
# PUBLIC API
# =============================================================================

def evaluate_gold_context(
    factors: Optional[GoldMacroFactors] = None,
    signal: str = "UNKNOWN",
    candidate_id: Optional[str] = None,
) -> GoldContextOutput:
    """
    تقييم السياق الماكرو لـ XAUUSD في وضع Shadow.
    يُعيد gold_context_score لاستخدامه في FINAL_BRAIN كعامل ترجيح خفيف.

    لا يُفعَّل live حتى اكتمال شروط التفعيل.
    """
    if not GOLD_CONTEXT_ENABLED:
        return GoldContextOutput(
            gold_context_score=50.0,
            mode="DISABLED",
        )

    if factors is None:
        return GoldContextOutput(
            gold_context_score=50.0,
            warnings=["Macro data unavailable; no observed macro score was calculated"],
            mode="SHADOW_DATA_UNAVAILABLE",
        )

    raw_score, factor_scores = _compute_weighted_context(factors)
    decayed_score = _apply_freshness_decay(raw_score, factors.data_freshness_hours)

    # تطبيق حدود التأثير من settings
    context_influence = max(
        GOLD_CONTEXT_MAX_NEGATIVE_INFLUENCE,
        min(GOLD_CONTEXT_MAX_POSITIVE_INFLUENCE, decayed_score),
    )

    # تحويل من [-MAX, +MAX] إلى [0, 100]، 50 = محايد
    influence_range = abs(GOLD_CONTEXT_MAX_POSITIVE_INFLUENCE) + abs(GOLD_CONTEXT_MAX_NEGATIVE_INFLUENCE)
    normalized = 50.0 + (context_influence / (influence_range / 2)) * 50.0
    gold_context_score = round(min(100.0, max(0.0, normalized)), 2)

    signal_alignment = _determine_signal_alignment(context_influence, signal)

    warnings = []
    if factors.data_freshness_hours > 48:
        warnings.append(f"Macro data is stale ({factors.data_freshness_hours:.0f}h old)")
    if signal_alignment in ("BEARISH_CONFLICT", "BULLISH_CONFLICT"):
        warnings.append(f"Signal-context conflict: {signal_alignment}")
    if abs(context_influence) > 6.0:
        warnings.append(f"Strong macro context: {context_influence:+.2f}")

    output = GoldContextOutput(
        gold_context_score=gold_context_score,
        context_influence=round(context_influence, 4),
        signal_alignment=signal_alignment,
        factor_scores=factor_scores,
        warnings=warnings,
        mode="SHADOW",
    )

    if GOLD_CONTEXT_SHADOW_LOG:
        _ensure_dirs()
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate_id,
            "factors": asdict(factors),
            "output": asdict(output),
            "signal": signal,
        }
        try:
            from core.trade_event_ledger import append_candidate_record
            append_candidate_record(_SHADOW_LOG_FILE, record)
        except Exception as e:
            print(f"[GOLD_CONTEXT] Log error: {e}")

    if warnings:
        for w in warnings:
            print(f"[GOLD_CONTEXT SHADOW] ⚠ {w}")

    print(
        f"[GOLD_CONTEXT SHADOW] Score={gold_context_score:.1f} | "
        f"Influence={context_influence:+.2f} | Alignment={signal_alignment}"
    )

    return output


def build_neutral_factors() -> GoldMacroFactors:
    """Construct neutral factors only when a caller explicitly requests them."""
    return GoldMacroFactors()


def get_gold_context_status() -> Dict[str, Any]:
    """تقرير حالة GOLD_CONTEXT_LAYER."""
    return {
        "component": "GOLD_CONTEXT_LAYER",
        "mode": "SHADOW",
        "enabled": GOLD_CONTEXT_ENABLED,
        "live_influence": GOLD_CONTEXT_LIVE_INFLUENCE,
        "hard_block_allowed": GOLD_CONTEXT_HARD_BLOCK_ALLOWED,
        "max_positive_influence": GOLD_CONTEXT_MAX_POSITIVE_INFLUENCE,
        "max_negative_influence": GOLD_CONTEXT_MAX_NEGATIVE_INFLUENCE,
        "factor_weights": GOLD_CONTEXT_FACTOR_WEIGHTS,
        "macro_feed_path": PHASE3_GOLD_MACRO_FACTORS_PATH,
        "note": "Modifier only — never standalone entry condition or hard blocker",
    }

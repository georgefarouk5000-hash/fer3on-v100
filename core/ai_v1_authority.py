# =============================================================================
# FER3ON AI V1 — DECISION AUTHORITY MODULE
# =============================================================================
# الفلسفة (مأخوذة حرفياً من Master Context):
#   - لا حذف للأركان: كل محرك V6/V7 يبقى موجوداً كـ Evidence Producer
#   - سلطة قرار واحدة: المحرك الموحد هو الحَكَم النهائي الوحيد
#   - 4 قرارات فقط: HARD_BLOCK / PASS_FULL / PASS_REDUCED / PASS_MICRO
#   - WAIT نادرٌ جداً (market_closed / micro_timing_window فقط)
#   - الرفض الكامل نادر: Crisis حقيقية، Hard caps، Market unsafe، No signal
#   - الباقي يتحوّل إلى penalty على composite score
#
# هذا الموديول يربط:
#   1) EvidenceCollector  — يجمع نتائج جميع المحركات بدون اعتراضها
#   2) LegacyTranslator   — يحوّل قرارات legacy (Final Brain reject, ML reject…)
#                            إلى penalties بدل continues
#   3) UnifiedAuthority   — يمرر السياق إلى واجهة القرار الموحدة ويرجع النتيجة
# =============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List

from core.unified_decision import DecisionResult
from core.fer3on_decision_authority import decide_trade
from core.unified_bridge import build_decision_context, decide_and_log
from core.settings import (
    AI_V1_RISK_MULT_FULL,
    AI_V1_RISK_MULT_PREMIUM,
    AI_V1_RISK_MULT_REDUCED,
    AI_V1_RISK_MULT_MICRO,
    AI_V1_RISK_MULT_CRISIS_MICRO,
    AI_V1_LOG_DECISIONS,
    AI_V1_LOG_EVIDENCE,
    AI_V1_SHOW_BRAND_BANNER,
    BOT_NAME,
    BOT_VERSION,
    BOT_TAGLINE,
    MAX_RISK_TOTAL,
)


# =============================================================================
# EVIDENCE COLLECTOR
# =============================================================================
# المحركات القديمة كانت ترفع "continue" عند الفشل.
# هنا نحوّل تلك الإشارات إلى penalties رقمية على composite score.

# جدول الترجمة: legacy_reason → penalty_value
#   - penalty سالب يخفض composite (يحوّل FULL→REDUCED→MICRO)
#   - "catastrophic" يعني hard block فعلي (لا penalty)
LEGACY_REJECTION_PENALTIES: Dict[str, float] = {
    # ===== Quality Gate =====
    "QUALITY_TOO_LOW":          -12,   # كان يرفض كاملاً → الآن يخفض إلى MICRO
    "QUALITY_BELOW_FLOOR":      -8,
    "QUALITY_RISK_MAP_FAIL":    -10,

    # ===== ML (modifier فقط في AI V1) =====
    "ML_REJECTED":              -10,
    "ML_RL_SKIP":               -6,
    "ML_LOW_PROBABILITY":       -8,

    # ===== Final Brain (لم يعد veto) =====
    "FINAL_BRAIN_REJECT":       -12,   # كان يقتل الصفقة → الآن penalty
    "FINAL_BRAIN_WAIT":         -8,    # كان يجمّد → الآن mild penalty
    "FINAL_BRAIN_LOW_SCORE":    -6,

    # ===== Execution Optimizer (asesor فقط) =====
    "OPTIMIZER_PRESSURE":       -6,
    "OPTIMIZER_BLOCKED":        -8,

    # ===== Filter Relaxation suggestion =====
    "FILTER_SUGGESTION":        -4,

    # ===== Recovery / Survival hints =====
    "SURVIVAL_HOLD":            -10,
    "MICRO_PROBE_HOLD":         -6,

    # ===== V7 timing =====
    "V7_MICRO_TIMING_WAIT":     -3,   # هذا قد يصبح WAIT حقيقي لو micro window قصير
}


# Catastrophic reasons → hard block فقط (لا penalty)
# لا تُمَس: حماية رأس المال + سلامة السوق + سلامة الحساب
CATASTROPHIC_REASONS = frozenset({
    "EMERGENCY_STOP",
    "DAILY_LOSS_CAPPED",
    "MARKET_UNSAFE",
    "NEWS_PAUSE",
    "CRISIS_FREEZE",
    "RISK_LIMITS_HIT",
    "COOLDOWN_ACTIVE",
    "DYNAMIC_RISK_HARD_BLOCK",
    "AI_OVERRIDE_OPPOSITE",        # AI يطلب اتجاه عكسي = منطق سلامة
    "ACCOUNT_PROTECTION",
    "NO_SIGNAL",
    "SPREAD_CATASTROPHIC",
    "ATR_INSUFFICIENT",
    "BROKER_UNAVAILABLE",
    "STRATEGY_HARD_GATE",
})


@dataclass
class AIV1Evidence:
    """مجمع شامل لكل ما تنتجه المحركات في دورة واحدة."""
    legacy_penalties: Dict[str, float] = field(default_factory=dict)
    catastrophic_flag: Optional[str]   = None
    extra_bonuses: Dict[str, float]    = field(default_factory=dict)
    notes: List[str]                   = field(default_factory=list)

    def add_legacy_rejection(self, reason: str, custom_penalty: Optional[float] = None) -> None:
        """يستدعى عند الفشل بأي محرك legacy.
        - لو السبب catastrophic → يرفع علم block.
        - غير ذلك → يضيف penalty على composite.
        """
        reason = (reason or "UNKNOWN").upper().strip()
        if reason in CATASTROPHIC_REASONS:
            self.catastrophic_flag = reason
            self.notes.append(f"CATASTROPHIC:{reason}")
            return
        penalty = custom_penalty if custom_penalty is not None else LEGACY_REJECTION_PENALTIES.get(reason, -5)
        # تجميع نفس السبب لو تكرر
        self.legacy_penalties[reason] = self.legacy_penalties.get(reason, 0) + penalty
        self.notes.append(f"PENALTY:{reason}={penalty}")

    def add_bonus(self, key: str, value: float) -> None:
        self.extra_bonuses[key] = self.extra_bonuses.get(key, 0) + value

    def is_catastrophic(self) -> bool:
        return self.catastrophic_flag is not None


# =============================================================================
# UNIFIED AUTHORITY — السلطة النهائية الوحيدة
# =============================================================================

def ai_v1_decide(
    *,
    evidence: AIV1Evidence,
    strategy: str,
    signal: str,
    quality_score: float,
    confidence_pct: float,
    brain_score: float,
    execution_score: float,
    execution_grade: str = "UNKNOWN",
    structure_quality: float = 50.0,
    daily_bias: str,
    mtf_strength: int,
    smc_strength: float,
    smc_entry_confirmed: bool,
    candle_trigger_confirmed: bool,
    candle_weight: int,
    liquidity_alignment: float,
    liquidity_bias: str,
    structure_bias: str,
    sweep_probability: float,
    session: str,
    market_regime: str,
    session_score: float,
    crisis_active: bool,
    news_pause: bool,
    risk_limits_hit: bool,
    cooldown_active: bool,
    market_unsafe: bool,
    daily_loss_capped: bool,
    emergency_stop: bool,
    spread_ratio: float,
    atr_sufficient: bool,
    rr_ratio: float,
    ml_score: float,
    ml_rl_action: str,
    memory_score: float,
    dna_score: float,
    symbol: str = "XAUUSD",
) -> DecisionResult:
    """نقطة الدخول الوحيدة لاتخاذ القرار في FER3ON AI V1.

    تجمع كل evidence من المحركات (legacy + new) ثم تمرر السياق مرة واحدة
    إلى واجهة السلطة الموحدة لإخراج verdict نهائي من 4 احتمالات فقط.
    """

    # 1) لو evidence فيه catastrophic flag → block مباشر بدون composite حساب
    if evidence.is_catastrophic():
        result = DecisionResult()
        result.decision = "HARD_BLOCK"
        result.size_mode = "NONE"
        result.risk_multiplier = 0.0
        result.hard_block_reason = evidence.catastrophic_flag
        result.reasons.append(f"AI_V1_CATASTROPHIC:{evidence.catastrophic_flag}")
        if AI_V1_LOG_DECISIONS:
            print(f"🚫 AI V1 CATASTROPHIC BLOCK: {evidence.catastrophic_flag}")
        return result

    # 2) بناء DecisionContext قياسي + legacy penalties كـ input (immutable output)
    net_legacy = sum(evidence.legacy_penalties.values()) + sum(evidence.extra_bonuses.values())

    ctx = build_decision_context(
        strategy=strategy,
        signal=signal,
        symbol=symbol,
        quality_score=quality_score,
        confidence_pct=confidence_pct,
        brain_score=brain_score,
        execution_score=execution_score,
        execution_grade=execution_grade,
        structure_quality=structure_quality,
        daily_bias=daily_bias,
        mtf_strength=mtf_strength,
        smc_strength=smc_strength,
        smc_entry_confirmed=smc_entry_confirmed,
        candle_trigger_confirmed=candle_trigger_confirmed,
        candle_weight=candle_weight,
        liquidity_alignment=liquidity_alignment,
        liquidity_bias=liquidity_bias,
        structure_bias=structure_bias,
        sweep_probability=sweep_probability,
        session=session,
        market_regime=market_regime,
        session_score=session_score,
        crisis_active=crisis_active,
        news_pause=news_pause,
        risk_limits_hit=risk_limits_hit,
        cooldown_active=cooldown_active,
        market_unsafe=market_unsafe,
        daily_loss_capped=daily_loss_capped,
        emergency_stop=emergency_stop,
        spread_ratio=spread_ratio,
        atr_sufficient=atr_sufficient,
        rr_ratio=rr_ratio,
        ml_score=ml_score,
        ml_rl_action=ml_rl_action,
        memory_score=memory_score,
        dna_score=dna_score,
    )
    ctx.legacy_score_adjustment = net_legacy

    # Route every authority facade through the same canonical decision entrypoint.
    result = decide_trade(ctx)

    if net_legacy != 0 and result.decision != "HARD_BLOCK":
        result.debug["legacy_penalties"] = dict(evidence.legacy_penalties)
        result.debug["legacy_bonuses"] = dict(evidence.extra_bonuses)
        result.debug["legacy_net"] = net_legacy

    # 4) Telemetry
    if AI_V1_LOG_DECISIONS:
        print(format_ai_v1_log(result, evidence))

    return result


def format_ai_v1_log(result: DecisionResult, evidence: AIV1Evidence) -> str:
    """تنسيق log موحّد بهوية AI V1."""
    icons = {
        "HARD_BLOCK":   "🚫",
        "PASS_FULL":    "🟢",
        "PASS_REDUCED": "🟡",
        "PASS_MICRO":   "🔵",
    }
    icon = icons.get(result.decision, "⚪")
    base = (
        f"{icon} [AI V1] {result.decision} "
        f"| Composite:{result.composite_score:.1f} "
        f"| Risk×{result.risk_multiplier:.2f} "
        f"| Mode:{result.size_mode}"
    )
    if result.hard_block_reason:
        return f"{base} | BLOCK={result.hard_block_reason}"

    parts = []
    if AI_V1_LOG_EVIDENCE:
        if result.bonuses:
            parts.append("+:" + ",".join(f"{k}{v:+.0f}" for k, v in result.bonuses.items()))
        if result.penalties:
            parts.append("-:" + ",".join(f"{k}{v:+.0f}" for k, v in result.penalties.items()))
        if evidence.legacy_penalties:
            parts.append("LEG:" + ",".join(f"{k}{v:+.0f}" for k, v in evidence.legacy_penalties.items()))
    if parts:
        return f"{base} | " + " | ".join(parts)
    return base


# =============================================================================
# RISK SHAPING HELPER
# =============================================================================

def apply_ai_v1_risk(base_risk: float, result: DecisionResult,
                     crisis_active: bool = False,
                     strategy: str = "") -> float:
    """يطبق multiplier النهائي ضمن hard caps."""
    if result.decision == "HARD_BLOCK":
        return 0.0

    mult = float(result.risk_multiplier or 0.0)
    if mult <= 0:
        # safety fallback by mode
        mode = result.size_mode or "NONE"
        if mode == "FULL":
            mult = AI_V1_RISK_MULT_FULL
        elif mode == "REDUCED":
            mult = AI_V1_RISK_MULT_REDUCED
        elif mode == "MICRO":
            mult = AI_V1_RISK_MULT_CRISIS_MICRO if (crisis_active and strategy in ("DAILY", "SMC")) \
                   else AI_V1_RISK_MULT_MICRO
        else:
            return 0.0

    risk = base_risk * mult
    return min(risk, MAX_RISK_TOTAL)


# =============================================================================
# BRAND BANNER
# =============================================================================

def print_brand_banner() -> None:
    if not AI_V1_SHOW_BRAND_BANNER:
        return
    print("=" * 72)
    print(f"  🏛️  {BOT_NAME}  —  v{BOT_VERSION}")
    print(f"  {BOT_TAGLINE}")
    print("=" * 72)
    print("  Doctrine: No deletion · Single authority · Layered execution")
    print("  Verdicts: HARD_BLOCK · PASS_FULL · PASS_REDUCED · PASS_MICRO")
    print("=" * 72)

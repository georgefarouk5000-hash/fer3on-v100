# =============================================================================
# FAIE — Volume 3: Chief Market Brain -> Analysts
# =============================================================================
# Each Analyst below is an ADAPTER, not a re-implementation. It reads fields
# that the existing pipeline already computes on core.unified_decision's
# DecisionContext (the project's own canonical "unified" input struct — see
# core/unified_decision.py) and turns them into standardized Evidence.
#
# No analyst executes anything. No analyst calls another analyst. Each one
# only ever returns an AnalystReport (a list of Evidence + a headline bias).
#
# Where the current codebase does not yet expose a real signal (e.g. genuine
# tick/volume data), the analyst is explicitly marked PARTIAL in its notes
# instead of fabricating a plausible-looking but fake number. This is a
# deliberate Volume 9 (Self-Audit) requirement: an honest gap beats a
# confident guess.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.unified_decision import DecisionContext
from .evidence import Evidence, BULLISH, BEARISH, NEUTRAL


def _direction_from_signal(signal: Optional[str]) -> str:
    s = (signal or "NONE").upper()
    if s == "BUY":
        return BULLISH
    if s == "SELL":
        return BEARISH
    return NEUTRAL


def _opposite(direction: str) -> str:
    return {BULLISH: BEARISH, BEARISH: BULLISH, NEUTRAL: NEUTRAL}[direction]


@dataclass
class AnalystReport:
    analyst: str
    evidence: List[Evidence] = field(default_factory=list)
    bias: str = NEUTRAL
    notes: str = ""
    partial: bool = False  # True if this analyst is running on incomplete data

    def to_dict(self) -> Dict:
        return {
            "analyst": self.analyst,
            "bias": self.bias,
            "notes": self.notes,
            "partial": self.partial,
            "evidence": [e.to_dict() for e in self.evidence],
        }


def _report_from_evidence(name: str, evidence: List[Evidence], notes: str = "", partial: bool = False) -> AnalystReport:
    if not evidence:
        return AnalystReport(analyst=name, evidence=[], bias=NEUTRAL, notes=notes or "no evidence produced", partial=partial)
    net = sum(e.weighted_score for e in evidence) / len(evidence)
    if net > 8:
        bias = BULLISH
    elif net < -8:
        bias = BEARISH
    else:
        bias = NEUTRAL
    return AnalystReport(analyst=name, evidence=evidence, bias=bias, notes=notes, partial=partial)


class Analyst:
    name = "BaseAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:  # pragma: no cover - interface
        raise NotImplementedError


# -----------------------------------------------------------------------
# Macro Analyst — regime / crisis / news state
# -----------------------------------------------------------------------
class MacroAnalyst(Analyst):
    name = "MacroAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        regime = str(ctx.market_regime or "UNKNOWN").upper()
        regime_conf = {"TRENDING": 70, "RANGING": 55, "VOLATILE": 40, "CRISIS": 30}.get(regime, 40)
        ev.append(Evidence(
            self.name, f"Market regime is {regime}", NEUTRAL,
            strength=50, confidence=regime_conf, timeframe="MACRO",
            tags=["regime", regime.lower()], source="core.unified_decision.DecisionContext.market_regime",
        ))
        if ctx.crisis_active:
            ev.append(Evidence(
                self.name, "Crisis regime flag active — elevated tail risk", BEARISH,
                strength=85, confidence=75, timeframe="MACRO",
                tags=["crisis"], source="DecisionContext.crisis_active",
            ))
        if ctx.news_pause:
            ev.append(Evidence(
                self.name, "News blackout window active", NEUTRAL,
                strength=60, confidence=90, timeframe="MACRO",
                tags=["news", "pause"], source="DecisionContext.news_pause",
            ))
        return _report_from_evidence(self.name, ev)


# -----------------------------------------------------------------------
# Technical Analyst — trend strength / structure / MTF alignment
# -----------------------------------------------------------------------
class TechnicalAnalyst(Analyst):
    name = "TechnicalAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        sig_dir = _direction_from_signal(ctx.signal)
        trend_strength = float(ctx.trend_strength or 0.0)
        if trend_strength:
            ev.append(Evidence(
                self.name, f"Trend strength reads {trend_strength:.1f}", sig_dir,
                strength=min(100.0, abs(trend_strength)), confidence=60, timeframe="PRIMARY",
                tags=["trend"], source="DecisionContext.trend_strength",
            ))
        if ctx.market_structure and ctx.market_structure != "UNKNOWN":
            struct_dir = BULLISH if "BULL" in ctx.market_structure.upper() else (
                BEARISH if "BEAR" in ctx.market_structure.upper() else NEUTRAL)
            ev.append(Evidence(
                self.name, f"Market structure: {ctx.market_structure}", struct_dir,
                strength=65, confidence=55, timeframe="PRIMARY",
                tags=["structure"], source="DecisionContext.market_structure",
            ))
        mode = str(ctx.mtf_alignment_mode or "NEUTRAL").upper()
        if mode == "ALIGNED":
            ev.append(Evidence(
                self.name, "Multi-timeframe trend is ALIGNED with signal", sig_dir,
                strength=60, confidence=65, timeframe="MTF",
                tags=["mtf", "aligned"], source="DecisionContext.mtf_alignment_mode",
            ))
        elif mode == "CONFLICT":
            ev.append(Evidence(
                self.name, "Multi-timeframe trend CONFLICTS with signal", _opposite(sig_dir),
                strength=55, confidence=65, timeframe="MTF",
                tags=["mtf", "conflict"], source="DecisionContext.mtf_alignment_mode",
            ))
        return _report_from_evidence(self.name, ev)


# -----------------------------------------------------------------------
# SMC Analyst — Smart Money Concepts strength / entry confirmation
# -----------------------------------------------------------------------
class SMCAnalyst(Analyst):
    name = "SMCAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        sig_dir = _direction_from_signal(ctx.signal)
        smc_strength = float(ctx.smc_strength or 0.0)
        if smc_strength:
            ev.append(Evidence(
                self.name, f"SMC composite strength {smc_strength:.1f}", sig_dir,
                strength=min(100.0, smc_strength * 10), confidence=60, timeframe="PRIMARY",
                tags=["smc"], source="DecisionContext.smc_strength",
            ))
        if ctx.smc_entry_confirmed:
            ev.append(Evidence(
                self.name, "SMC entry pattern confirmed", sig_dir,
                strength=70, confidence=70, timeframe="PRIMARY",
                tags=["smc", "entry_confirmed"], source="DecisionContext.smc_entry_confirmed",
            ))
        if ctx.sweep_probability:
            ev.append(Evidence(
                self.name, f"Liquidity sweep probability {ctx.sweep_probability:.1f}%", sig_dir,
                strength=float(ctx.sweep_probability), confidence=55, timeframe="PRIMARY",
                tags=["smc", "sweep"], source="DecisionContext.sweep_probability",
            ))
        return _report_from_evidence(self.name, ev)


# -----------------------------------------------------------------------
# Liquidity Analyst
# -----------------------------------------------------------------------
class LiquidityAnalyst(Analyst):
    name = "LiquidityAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        sig_dir = _direction_from_signal(ctx.signal)
        liq = float(ctx.liquidity_strength or 50.0)
        # liquidity_strength is scored 0-100 around a 50 neutral midpoint
        deviation = liq - 50.0
        if abs(deviation) > 3:
            direction = sig_dir if deviation > 0 else _opposite(sig_dir)
            ev.append(Evidence(
                self.name, f"Liquidity strength {liq:.1f} (deviation {deviation:+.1f} from neutral)", direction,
                strength=min(100.0, abs(deviation) * 2), confidence=50, timeframe="PRIMARY",
                tags=["liquidity"], source="DecisionContext.liquidity_strength",
            ))
        liq_align = float(ctx.liquidity_alignment or 50.0)
        if liq_align > 55:
            ev.append(Evidence(
                self.name, f"Liquidity alignment favors signal ({liq_align:.1f})", sig_dir,
                strength=min(100.0, liq_align), confidence=55, timeframe="PRIMARY",
                tags=["liquidity", "alignment"], source="DecisionContext.liquidity_alignment",
            ))
        return _report_from_evidence(self.name, ev)


# -----------------------------------------------------------------------
# Volume Analyst — PARTIAL: no real volume/tick feed is wired into
# DecisionContext yet. Documented honestly rather than faked.
# -----------------------------------------------------------------------
class VolumeAnalyst(Analyst):
    name = "VolumeAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        return AnalystReport(
            analyst=self.name,
            evidence=[],
            bias=NEUTRAL,
            notes=(
                "PARTIAL: no real volume/tick-flow field is currently exposed on "
                "DecisionContext. This analyst intentionally abstains (NEUTRAL, no "
                "evidence) instead of fabricating a volume read. See "
                "docs/FAIE/GAP_ANALYSIS.md — Volume Engine."
            ),
            partial=True,
        )


# -----------------------------------------------------------------------
# Pattern Analyst — candle trigger / confirmation
# -----------------------------------------------------------------------
class PatternAnalyst(Analyst):
    name = "PatternAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        sig_dir = _direction_from_signal(ctx.signal)
        if ctx.candle_trigger_confirmed:
            ev.append(Evidence(
                self.name, "Candle confirmation trigger fired", sig_dir,
                strength=60, confidence=60, timeframe="PRIMARY",
                tags=["candle", "confirmed"], source="DecisionContext.candle_trigger_confirmed",
            ))
        bonus = float(ctx.candle_bonus or 0.0)
        penalty = float(ctx.candle_penalty or 0.0)
        if bonus:
            ev.append(Evidence(
                self.name, f"Candle pattern bonus {bonus:+.1f}", sig_dir,
                strength=min(100.0, abs(bonus) * 10), confidence=45, timeframe="PRIMARY",
                tags=["candle", "bonus"], source="DecisionContext.candle_bonus",
            ))
        if penalty:
            ev.append(Evidence(
                self.name, f"Candle pattern penalty {penalty:+.1f}", _opposite(sig_dir),
                strength=min(100.0, abs(penalty) * 10), confidence=45, timeframe="PRIMARY",
                tags=["candle", "penalty"], source="DecisionContext.candle_penalty",
            ))
        return _report_from_evidence(self.name, ev)


# -----------------------------------------------------------------------
# Psychology Analyst — wraps brain.knowledge_base psychology notes
# -----------------------------------------------------------------------
class PsychologyAnalyst(Analyst):
    name = "PsychologyAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        notes_text = ""
        try:
            from brain.knowledge_base import get_psychology_notes
            notes_text = get_psychology_notes(ctx.market_regime, ctx.session) or ""
        except Exception as exc:  # pragma: no cover - defensive, knowledge base is optional
            return AnalystReport(
                analyst=self.name, evidence=[], bias=NEUTRAL,
                notes=f"PARTIAL: brain.knowledge_base.get_psychology_notes unavailable ({exc})",
                partial=True,
            )
        if notes_text:
            ev.append(Evidence(
                self.name, notes_text[:180], NEUTRAL,
                strength=30, confidence=40, timeframe="CONTEXT",
                tags=["psychology"], source="brain.knowledge_base.get_psychology_notes",
            ))
        return _report_from_evidence(self.name, ev, notes="informational only — psychology notes never set direction")


# -----------------------------------------------------------------------
# Risk Officer — READ-ONLY. Reports risk state, never sizes or blocks.
# -----------------------------------------------------------------------
class RiskOfficer(Analyst):
    name = "RiskOfficer"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        flags = {
            "emergency_stop": ctx.emergency_stop,
            "daily_loss_capped": ctx.daily_loss_capped,
            "market_unsafe": ctx.market_unsafe,
            "risk_limits_hit": ctx.risk_limits_hit,
            "cooldown_active": ctx.cooldown_active,
        }
        active_flags = [k for k, v in flags.items() if v]
        if active_flags:
            ev.append(Evidence(
                self.name, f"Active risk constitution flags: {', '.join(active_flags)}", NEUTRAL,
                strength=95, confidence=95, timeframe="RISK",
                tags=["risk", "hard_gate"] + active_flags, source="DecisionContext risk flags",
            ))
        portfolio_note = ""
        try:
            from core.portfolio_risk_authority import get_portfolio_state
            state = get_portfolio_state()
            open_trades = getattr(state, "open_trades", None)
            open_count = len(open_trades) if isinstance(open_trades, list) else "n/a"
            portfolio_note = (
                f"open_trades={open_count}, daily_pnl={getattr(state, 'daily_pnl', 'n/a')}, "
                f"emergency_stop={getattr(state, 'emergency_stop', 'n/a')}"
            )
            # §3.4 Portfolio Intelligence — informational-only correlated
            # exposure note, appended (not replacing) the existing
            # read-only portfolio snapshot above. Still does not gate or
            # resize anything; core.portfolio_risk_authority's existing
            # diversification-vs-conflict rule is unchanged.
            if isinstance(open_trades, list):
                from analytics.portfolio_intelligence import assess_correlated_exposure
                correlated = assess_correlated_exposure(open_trades)
                portfolio_note += f" | correlated_exposure: {correlated.note}"
        except Exception as exc:  # pragma: no cover - defensive
            portfolio_note = f"portfolio snapshot unavailable ({exc})"
        notes = (
            "RiskOfficer is READ-ONLY: it reports the existing Portfolio Risk "
            f"Authority state, it does not gate or size trades itself. {portfolio_note}"
        )
        return _report_from_evidence(self.name, ev, notes=notes)


# -----------------------------------------------------------------------
# Execution Officer — spread / ATR / risk-reward readiness signals
# -----------------------------------------------------------------------
class ExecutionOfficer(Analyst):
    name = "ExecutionOfficer"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        ev: List[Evidence] = []
        if ctx.spread_ratio and ctx.spread_ratio > 0.30:
            ev.append(Evidence(
                self.name, f"Spread ratio elevated ({ctx.spread_ratio:.2f})", NEUTRAL,
                strength=min(100.0, ctx.spread_ratio * 150), confidence=70, timeframe="EXECUTION",
                tags=["execution", "spread"], source="DecisionContext.spread_ratio",
            ))
        if not ctx.atr_sufficient:
            ev.append(Evidence(
                self.name, "ATR insufficient for reliable execution", NEUTRAL,
                strength=90, confidence=80, timeframe="EXECUTION",
                tags=["execution", "atr"], source="DecisionContext.atr_sufficient",
            ))
        if ctx.rr_ratio and ctx.rr_ratio > 0:
            sig_dir = _direction_from_signal(ctx.signal)
            quality = "favorable" if ctx.rr_ratio >= 1.5 else "marginal"
            ev.append(Evidence(
                self.name, f"Risk/reward ratio {ctx.rr_ratio:.2f} ({quality})",
                sig_dir if ctx.rr_ratio >= 1.5 else NEUTRAL,
                strength=min(100.0, ctx.rr_ratio * 30), confidence=50, timeframe="EXECUTION",
                tags=["execution", "rr"], source="DecisionContext.rr_ratio",
            ))
        return _report_from_evidence(self.name, ev, notes="execution readiness only — does not place orders")


# -----------------------------------------------------------------------
# Session Analyst — §3.2 Institutional Session Engine (upgrade)
# -----------------------------------------------------------------------
# core.session_intelligence already models liquidity-window behavior in
# fine detail (LONDON_OPEN / LONDON_SWEEP / LONDON_EXPANSION / NY_OPEN /
# OVERLAP / NY_EXPANSION / ASIA / OFF_HOURS, each with its own aggression/
# risk/confidence modifiers) — this analyst is a thin adapter over that
# existing engine, not a re-implementation, same as every other analyst in
# this file. It reports NEUTRAL-direction evidence on purpose: liquidity
# window *strength* describes how much institutional activity/spread risk
# to expect in this window, not a bullish/bearish lean (same established
# pattern as MacroAnalyst's regime read and RiskOfficer's portfolio note —
# see brain/faie/fusion.py's per-analyst net_score: NEUTRAL evidence always
# nets to 0, which is correct here, not a bug).
_COARSE_SESSION_TO_PHASE = {
    "ASIA": "ASIA",
    "LONDON": "LONDON_EXPANSION",
    "NEW_YORK": "NY_EXPANSION",
    "NEWYORK": "NY_EXPANSION",
    "OVERLAP": "OVERLAP",
    "OFF_HOURS": "OFF_HOURS",
}


class SessionAnalyst(Analyst):
    name = "SessionAnalyst"

    def analyze(self, ctx: DecisionContext) -> AnalystReport:
        try:
            from core.session_intelligence import detect_session_phase, get_phase_modifiers
        except Exception as exc:  # pragma: no cover - defensive
            return AnalystReport(
                analyst=self.name, evidence=[], bias=NEUTRAL,
                notes=f"PARTIAL: core.session_intelligence unavailable ({exc})",
                partial=True,
            )

        hour = getattr(ctx, "hour", None)
        if hour is not None:
            # A real clock time is available on this context (the live
            # decision loop always sets one — see core.unified_bridge
            # .build_decision_context) — use the real sub-window read.
            phase = detect_session_phase(int(hour), int(getattr(ctx, "minute", 0) or 0))
            read_confidence = 65.0
            source = "core.session_intelligence.detect_session_phase(ctx.hour, ctx.minute)"
        else:
            # No real clock time on this context — e.g. a historical row
            # replayed through testing/faie_backtest.py, which has no
            # persisted hour for a past trade. Falling back to "now" would
            # fabricate a session-phase read for a moment that isn't
            # actually now, so instead this degrades honestly to a coarser
            # read derived only from the already-known `ctx.session` label,
            # at visibly lower confidence.
            coarse = str(ctx.session or "UNKNOWN").upper()
            phase = _COARSE_SESSION_TO_PHASE.get(coarse, "OFF_HOURS")
            read_confidence = 30.0
            source = "ctx.session (coarse fallback — no ctx.hour on this context)"

        mods = get_phase_modifiers(phase)
        aggression = float(mods.get("aggression", 1.0))
        confidence_mod = float(mods.get("confidence", 0.0))
        # 0-100 score, 50 = neutral window. aggression is centered on 1.0 in
        # PHASE_MODIFIERS (e.g. ASIA=0.88, LONDON_SWEEP~1.2+), so this
        # amplifies deviation from that center; confidence_mod (already a
        # small +/- points adjustment in PHASE_MODIFIERS) nudges it further.
        strength_score = max(0.0, min(100.0,
            50.0 + (aggression - 1.0) * 150.0 + confidence_mod * 2.0
        ))

        ev = [Evidence(
            self.name,
            f"{phase} liquidity window strength {strength_score:.1f}/100 "
            f"(aggression={aggression:.2f})",
            NEUTRAL,
            strength=strength_score, confidence=read_confidence, timeframe="SESSION",
            tags=["session", "liquidity_window", phase.lower()], source=source,
        )]

        notes = f"phase={phase}, liquidity_window_strength={strength_score:.1f}/100"
        if strength_score < 40.0:
            notes += " — WEAK window: spread/slippage risk typically elevated here"
        if hour is None:
            notes += " (degraded coarse read — no ctx.hour available)"

        return _report_from_evidence(self.name, ev, notes=notes)


DEFAULT_ANALYSTS: List[Analyst] = [
    MacroAnalyst(),
    TechnicalAnalyst(),
    SMCAnalyst(),
    LiquidityAnalyst(),
    VolumeAnalyst(),
    PatternAnalyst(),
    PsychologyAnalyst(),
    RiskOfficer(),
    ExecutionOfficer(),
    SessionAnalyst(),
]

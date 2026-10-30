# =============================================================================
# FER3ON — Portfolio Intelligence (Phase-2 spec §3.4, new addition)
# =============================================================================
# فلسفة:
#   core/portfolio_risk_authority.py يعالج بالفعل، وبشكل صحيح موثَّق، عدة
#   صفقات مفتوحة بنفس الاتجاه (مثلاً 3 صفقات BUY XAUUSD من استراتيجيات
#   مختلفة) كتنويع (diversification) لا تعارض (conflict) على مستوى سلطة
#   القرار. هذا الموديول لا يغيّر تلك القاعدة إطلاقًا — هو طبقة "رؤية"
#   إضافية فوقها فقط: يجعل حجم التعرض الاتجاهي المتراكم مرئيًا لمن يراجع
#   القرار (إنسان أو RiskOfficer/FAIE عبر حقل notes)، دون أن يحظر أو يُغيّر
#   حجم أي صفقة بنفسه.
#
#   READ-ONLY: يقرأ فقط PortfolioState.open_trades الموجود بالفعل (نفس
#   الاستدعاء الذي يستخدمه RiskOfficer FAIE أصلاً) — لا حالة جديدة، لا
#   كتابة، لا استدعاء لأي مسار تنفيذ.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PortfolioRiskNote:
    same_direction_count: int = 0
    same_direction_symbols: List[str] = field(default_factory=list)
    net_directional_exposure: float = 0.0  # sum of risk_percent, signed by direction
    dominant_direction: str = "NONE"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "same_direction_count": self.same_direction_count,
            "same_direction_symbols": list(self.same_direction_symbols),
            "net_directional_exposure": round(self.net_directional_exposure, 4),
            "dominant_direction": self.dominant_direction,
            "note": self.note,
        }


def _trade_symbol(trade: Dict[str, Any]) -> str:
    # record_trade_open() (core/portfolio_risk_authority.py) does not
    # currently store `symbol` as a top-level key — this module is
    # deliberately read-only and does not add one there. Instead it looks
    # for a symbol wherever a caller may already have put it (top-level key
    # first, then the free-form `meta` dict), and falls back to UNKNOWN
    # rather than guessing a single-symbol account.
    sym = trade.get("symbol")
    if sym:
        return str(sym).upper()
    meta = trade.get("meta") or {}
    sym = meta.get("symbol") if isinstance(meta, dict) else None
    return str(sym).upper() if sym else "UNKNOWN"


def assess_correlated_exposure(open_trades: List[Dict[str, Any]]) -> PortfolioRiskNote:
    """Read-only visibility note over currently open trades.

    Does NOT block, resize, or reorder anything — see module docstring.
    Empty input returns an explicit "no correlated exposure" note rather
    than an error, per spec failure handling.
    """
    if not open_trades:
        return PortfolioRiskNote(note="no correlated exposure — no open trades")

    buy_trades = [t for t in open_trades if str(t.get("direction", "")).upper() == "BUY"]
    sell_trades = [t for t in open_trades if str(t.get("direction", "")).upper() == "SELL"]

    def _risk_sum(trades: List[Dict[str, Any]]) -> float:
        total = 0.0
        for t in trades:
            try:
                total += float(t.get("risk_percent", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    buy_risk = _risk_sum(buy_trades)
    sell_risk = _risk_sum(sell_trades)
    net_exposure = buy_risk - sell_risk

    if len(buy_trades) >= len(sell_trades) and buy_trades:
        dominant_trades = buy_trades
        dominant_direction = "BUY"
    elif sell_trades:
        dominant_trades = sell_trades
        dominant_direction = "SELL"
    else:
        dominant_trades = []
        dominant_direction = "NONE"

    same_direction_count = len(dominant_trades)
    same_direction_symbols = sorted({_trade_symbol(t) for t in dominant_trades})

    if same_direction_count <= 1:
        note = "no correlated exposure — at most one position per direction"
    else:
        note = (
            f"{same_direction_count} open {dominant_direction} positions across "
            f"{len(same_direction_symbols)} symbol(s) "
            f"({', '.join(same_direction_symbols)}) — informational only, "
            "core.portfolio_risk_authority already treats this as diversification, "
            "not conflict, at the decision-authority level"
        )

    return PortfolioRiskNote(
        same_direction_count=same_direction_count,
        same_direction_symbols=same_direction_symbols,
        net_directional_exposure=net_exposure,
        dominant_direction=dominant_direction,
        note=note,
    )

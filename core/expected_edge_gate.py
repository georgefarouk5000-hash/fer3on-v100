"""
[FER3ON-FIX-2026-08-19] Expected Edge Gate
==========================================
البوابة الأخيرة قبل فتح الصفقة: هل الصفقة تملك ميزة رياضية موجبة؟

  Expected Value = (WR * avg_win) - ((1 - WR) * avg_loss)

نستخدم win_rate التاريخي الحقيقي (من data/history/trades.csv) لكل استراتيجية
مع R:R الحالي المقترح للصفقة. لو EV سالب → نرفض.

الفلسفة:
  - لا يمكن ربح استراتيجية بدون edge رياضي موجب على المدى الطويل.
  - نطبق ذلك لكل صفقة قبل التنفيذ.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Tuple

TRADES_CSV_PATH = "data/history/trades.csv"

# Conservative win-rate priors for the active strategies. Recalibrate from
# current-build trade data after at least MIN_SAMPLE_TRADES trades are available.
DEFAULT_WR = {
    "SMC": 0.40,
    "DAILY": 0.45,
}

# [EDGE-CALIB-1] حد أدنى للعينة: أقل من كده نرجع للـ prior المتحفظ
MIN_SAMPLE_TRADES = 50

# [EDGE-CALIB-1] نحسب WR من صفقات البيلد الحالي فقط (صفقات النسخ الفاشلة
# القديمة لا تُعتمد). لو BUILD_ID غير متاح نستخدم كل الصفقات مع شرط العينة.
try:
    from core.settings import BUILD_ID as _CURRENT_BUILD_ID
except Exception:
    _CURRENT_BUILD_ID = None

# الحد الأدنى للـ Expected Value (كنسبة من SL) — 0 = التعادل، 0.05 = ميزة 5%
MIN_EV_RATIO = 0.05


def _load_win_rates() -> Dict[str, float]:
    """يحسب win_rate الحقيقي من آخر 100 صفقة مغلقة لكل استراتيجية"""
    path = Path(TRADES_CSV_PATH)
    if not path.exists():
        return DEFAULT_WR.copy()

    per_strat: Dict[str, list] = {}
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for row in csv.DictReader(f):
                strat = str(row.get("strategy", "")).upper()
                if strat not in DEFAULT_WR:
                    continue
                result = str(row.get("result", "")).upper()
                if result not in {"WIN", "LOSS"}:
                    continue
                # [EDGE-CALIB-1] صفقات البيلد الحالي فقط — صفقات النسخة
                # الفاشلة القديمة (build_id مختلف) لا تدخل في حساب WR
                if _CURRENT_BUILD_ID:
                    row_build = str(row.get("build_id", "") or "")
                    if row_build != str(_CURRENT_BUILD_ID):
                        continue
                per_strat.setdefault(strat, []).append(result)
    except OSError:
        return DEFAULT_WR.copy()

    wrs = DEFAULT_WR.copy()
    for strat, results in per_strat.items():
        recent = results[-100:]
        # [EDGE-CALIB-1] عينة أقل من MIN_SAMPLE_TRADES → prior متحفظ
        if len(recent) < MIN_SAMPLE_TRADES:
            continue
        wins = sum(1 for r in recent if r == "WIN")
        wrs[strat] = wins / len(recent)
    return wrs


def compute_expected_value(
    *, strategy: str, risk_reward: float, sl_distance: float
) -> Tuple[float, float]:
    """
    Returns (ev_dollars_per_unit_lot_at_1$_per_point, ev_ratio_to_sl).
    ev_ratio_to_sl >= MIN_EV_RATIO means the trade has positive edge.
    """
    strat = str(strategy or "").upper()
    wrs = _load_win_rates()
    wr = wrs.get(strat, 0.5)

    # افترض 1$/نقطة كوحدة مرجعية
    avg_win = sl_distance * risk_reward
    avg_loss = sl_distance
    ev = (wr * avg_win) - ((1.0 - wr) * avg_loss)
    ev_ratio = ev / sl_distance if sl_distance > 0 else 0.0
    return round(ev, 4), round(ev_ratio, 4)


def should_reject_by_edge(
    *, strategy: str, risk_reward: float, sl_distance: float
) -> Tuple[bool, str, float]:
    """
    Returns (reject, reason, ev_ratio).
    reject=True means the trade has no positive mathematical edge.
    """
    ev, ev_ratio = compute_expected_value(
        strategy=strategy, risk_reward=risk_reward, sl_distance=sl_distance
    )
    if ev_ratio < MIN_EV_RATIO:
        return True, (
            f"EDGE_GATE_NEGATIVE_EV | strategy={strategy} | wr={_load_win_rates().get(strategy.upper(), 0.5):.2f}"
            f" | rr={risk_reward:.2f} | ev_ratio={ev_ratio:.3f} | min={MIN_EV_RATIO}"
        ), ev_ratio
    return False, "EDGE_OK", ev_ratio


if __name__ == "__main__":
    # اختبار سريع على السيناريوهات المتوقعة
    for strat in ("SMC", "DAILY"):
        for rr in (0.7, 1.0, 1.5, 2.0, 2.5, 3.0):
            ev, ratio = compute_expected_value(strategy=strat, risk_reward=rr, sl_distance=100.0)
            reject, reason, _ = should_reject_by_edge(
                strategy=strat, risk_reward=rr, sl_distance=100.0
            )
            marker = "REJECT" if reject else "  OK  "
            print(f"  [{marker}] {strat:6s} RR={rr}  EV={ev:+7.2f}  ratio={ratio:+.3f}")

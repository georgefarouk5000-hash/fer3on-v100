# =============================================================================
# FER3ON V3.6 — MULTI-TP LADDER EXECUTION LAYER
# =============================================================================
# الفلسفة:
#   نظام TP متدرج (TP1/TP2/TP3) بنسب مختلفة حسب طبيعة كل استراتيجية —
#   SMC وDAILY تستفيدان من تدرج كامل (وقت كافٍ لتطور الحركة).
#
#   عند تعارض MTF (CONFLICT من core/trend_confluence.py) — يتجاوز الجدول
#   المعتاد ويستخدم هدفًا واحدًا سريعًا وحذِرًا (خروج كامل مبكر) بدل التدرج،
#   حماية لرأس المال في حال كان التعارض بداية انعكاس حقيقي.
#
#   هذا الموديول حسابي بحت (يُرجع dict) — لا يستدعي mt5.order_send مباشرة،
#   بنفس نمط execution/scale_in.py. التنفيذ الفعلي يتم في trade_executor.py.
# =============================================================================

from __future__ import annotations

import math
from typing import Any, Dict, List

from core.settings import (
    MULTI_TP_ENABLED,
    MULTI_TP_PROFILE,
    MULTI_TP_CONFLICT_MODE,
    MULTI_TP_STRATEGY_ENABLED,
)


# =============================================================================
# IN-MEMORY TP LADDER REGISTRY
# =============================================================================
# main.py يعمل كحلقة واحدة مستمرة (while True) طوال عمر العملية — تمامًا كما
# تُستخدم متغيرات module-level أخرى في core/trade_executor.py (_live_trade_count)
# و core/trailing_stop.py. هذا قاموس بسيط بمفتاح ticket يُسجَّل عند فتح الصفقة
# ويُستهلك من حلقة مراقبة الصفقات المفتوحة لمعرفة أي TP لم يُحقَّق بعد.
# لا حاجة لتخزين دائم (CSV/DB) لأن إعادة تشغيل العملية تُعيد بناء الصفقات
# المفتوحة فعليًا من MT5 مباشرة عبر mt5.positions_get().
# =============================================================================

_TP_LADDER_REGISTRY: Dict[int, Dict[str, Any]] = {}


def register_tp_ladder(ticket: int, ladder_result: Dict[str, Any]) -> None:
    """يُسجَّل عند نجاح فتح الصفقة في core/trade_executor.py."""
    try:
        _TP_LADDER_REGISTRY[int(ticket)] = {
            **ladder_result,
            "closed_labels": [],
        }
    except Exception:
        pass


def get_registered_ladder(ticket: int) -> Dict[str, Any] | None:
    return _TP_LADDER_REGISTRY.get(int(ticket))


def mark_target_closed(ticket: int, label: str) -> None:
    entry = _TP_LADDER_REGISTRY.get(int(ticket))
    if entry is not None and label not in entry.get("closed_labels", []):
        entry.setdefault("closed_labels", []).append(label)


def forget_ticket(ticket: int) -> None:
    """يُستدعى عند إغلاق الصفقة بالكامل (TP3 أو SL) لتنظيف الذاكرة."""
    _TP_LADDER_REGISTRY.pop(int(ticket), None)


def get_tp_ladder(strategy: str, mtf_mode: str = "ALIGNED") -> Dict[str, Any]:
    """
    يُرجع جدول أهداف TP لاستراتيجية معيّنة، واعيًا بحالة محاذاة الفريمات.

    Parameters
    ----------
    strategy : "SMC" | "DAILY"
    mtf_mode : "ALIGNED" | "NEUTRAL" | "CONFLICT" (من core/trend_confluence.py)

    Returns
    -------
    dict:
        enabled       : bool
        mode          : "LADDER" | "SINGLE_FAST_EXIT" | "SINGLE"
        targets       : List[{"label": "TP1", "pct": float, "rr": float}]
        reason        : str
    """
    strat = str(strategy or "").upper()

    if not MULTI_TP_ENABLED:
        return {
            "enabled": False, "mode": "DISABLED", "targets": [],
            "reason": "MULTI_TP_DISABLED",
        }

    # CONFLICT mode يتجاوز كل الجداول — خروج سريع وحذِر واحد، لكل الاستراتيجيات
    if str(mtf_mode or "").upper() == "CONFLICT":
        conflict_cfg = MULTI_TP_CONFLICT_MODE
        return {
            "enabled": True,
            "mode": "SINGLE_FAST_EXIT",
            "targets": [
                {"label": "TP1", "pct": float(conflict_cfg["tp1_pct"]), "rr": float(conflict_cfg["tp1_rr"])},
            ],
            "reason": "MTF_CONFLICT_FAST_EXIT",
        }

    profile = MULTI_TP_PROFILE.get(strat)
    if not profile:
        return {
            "enabled": False, "mode": "NO_PROFILE", "targets": [],
            "reason": f"NO_MULTI_TP_PROFILE_FOR_{strat}",
        }

    if not MULTI_TP_STRATEGY_ENABLED.get(strat, True):
        return {
            "enabled": False,
            "mode": "DISABLED",
            "targets": [],
            "reason": f"{strat}_MULTI_TP_DISABLED",
        }

    targets: List[Dict[str, Any]] = []
    if profile.get("tp1_pct", 0) > 0:
        targets.append({"label": "TP1", "pct": float(profile["tp1_pct"]), "rr": float(profile["tp1_rr"])})
    if profile.get("tp2_pct", 0) > 0:
        targets.append({"label": "TP2", "pct": float(profile["tp2_pct"]), "rr": float(profile["tp2_rr"])})
    if profile.get("tp3_pct", 0) > 0:
        targets.append({"label": "TP3", "pct": float(profile["tp3_pct"]), "rr": float(profile["tp3_rr"])})

    mode = "SINGLE" if len(targets) <= 1 else "LADDER"

    return {
        "enabled": True,
        "mode": mode,
        "targets": targets,
        "reason": f"{strat}_{mode}",
    }


def compute_tp_prices(
    entry_price: float,
    sl_distance: float,
    direction: str,
    strategy: str,
    mtf_mode: str = "ALIGNED",
    point: float = 0.01,
    max_tp_distance: float | None = None,
) -> Dict[str, Any]:
    """
    يحوّل جدول الأهداف (نسب RR) إلى أسعار فعلية + أحجام إغلاق نسبية،
    جاهزة لتُستهلك من trade_executor.py عند فتح الصفقة وجدولة partial closes.

    Parameters
    ----------
    entry_price : سعر الدخول
    sl_distance : مسافة الـ SL بالنقاط (points، لا بالسعر الخام)
    max_tp_distance : final broker TP in raw price units, when available;
        the last remaining ladder fraction is merged into that boundary.
    direction   : "BUY" | "SELL"
    """
    try:
        entry_price = float(entry_price)
        sl_distance = float(sl_distance)
        point = float(point)
    except (TypeError, ValueError):
        return {
            "enabled": False,
            "levels": [],
            "mode": "INVALID",
            "reason": "INVALID_INPUT",
        }
    if (
        not math.isfinite(entry_price)
        or not math.isfinite(sl_distance)
        or not math.isfinite(point)
        or sl_distance <= 0
        or entry_price <= 0
        or point <= 0
    ):
        return {
            "enabled": False,
            "levels": [],
            "mode": "INVALID",
            "reason": "INVALID_INPUT",
        }

    final_distance = 0.0
    if max_tp_distance is not None:
        try:
            final_distance = float(max_tp_distance)
        except (TypeError, ValueError):
            final_distance = 0.0
        if not math.isfinite(final_distance) or final_distance <= 0:
            return {
                "enabled": False,
                "levels": [],
                "mode": "INVALID",
                "reason": "INVALID_FINAL_TP_DISTANCE",
            }

    ladder = get_tp_ladder(strategy, mtf_mode=mtf_mode)
    if not ladder["enabled"]:
        return {"enabled": False, "levels": [], "mode": ladder.get("mode", "NONE"),
                "reason": ladder.get("reason", "INVALID_INPUT")}

    direction = str(direction or "").upper()
    if direction not in {"BUY", "SELL"}:
        return {
            "enabled": False,
            "levels": [],
            "mode": "INVALID",
            "reason": "INVALID_DIRECTION",
        }
    levels = []
    targets = list(ladder["targets"])

    if final_distance > 0:
        bounded_targets = []
        for index, target in enumerate(targets):
            configured_distance = sl_distance * float(target["rr"])
            if configured_distance < final_distance - max(point, 1e-8):
                bounded_targets.append(target)
                continue
            remaining_pct = sum(float(item["pct"]) for item in targets[index:])
            if remaining_pct > 0:
                bounded_targets.append({
                    "label": "TP_FINAL",
                    "pct": remaining_pct,
                    "rr": final_distance / sl_distance,
                })
            break
        targets = bounded_targets

    for t in targets:
        tp_distance_price = sl_distance * float(t["rr"])
        if direction == "BUY":
            tp_price = round(entry_price + tp_distance_price, 5)
        elif direction == "SELL":
            tp_price = round(entry_price - tp_distance_price, 5)
        else:
            continue

        levels.append({
            "label": t["label"],
            "price": tp_price,
            "close_pct": t["pct"],
            "rr": t["rr"],
        })

    return {
        "enabled": True,
        "mode": ladder["mode"],
        "levels": levels,
        "reason": ladder["reason"],
    }


def next_pending_target(levels: List[Dict[str, Any]], already_closed_labels: List[str]) -> Dict[str, Any] | None:
    """
    يُرجع أقرب هدف لم يُحقَّق بعد (يُستخدم من المُراقب الدوري للصفقات المفتوحة
    لمعرفة أي TP يجب التحقق منه تاليًا).
    """
    closed = set(already_closed_labels or [])
    for level in levels:
        if level["label"] not in closed:
            return level
    return None


def target_hit(position_type: str, current_price: float, target_price: float) -> bool:
    """True لو السعر الحالي حقق هدف TP المحدد."""
    pt = str(position_type or "").upper()
    if pt in ("BUY", "0"):
        return current_price >= target_price
    if pt in ("SELL", "1"):
        return current_price <= target_price
    return False

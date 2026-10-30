from __future__ import annotations

import statistics
from typing import Any

from core.ai_memory import load_memory_records
from core.data_integrity import HISTORY_FILE, read_csv_records

# =============================================================================
# REAL HISTORY / MEMORY LOADER — replaces the hardcoded example records that
# used to live inside fer3on_masr/app.py.
# =============================================================================
# EvolutionEngine.diagnose_trade() و PatternDiscovery.discover() كانا يُغذَّيان
# من قاموس/قائمة ثابتة مكتوبة يدويًا داخل app.py (بيانات تجريبية وهمية لا
# علاقة لها بأي صفقة حقيقية). هذا الملف يستبدل ذلك بقراءة فعلية من نفس ملفات
# السجل التي يكتبها البوت أثناء التشغيل:
#   - data/history/trades.csv   (عبر core.data_integrity.HISTORY_FILE)
#   - data/memory/ai_memory.csv (عبر core.ai_memory.load_memory_records)
#
# لا تكرار لمنطق قراءة CSV: تُستخدم نفس دوال core.data_integrity /
# core.ai_memory المستخدمة فعليًا في بقية المشروع (المتوافق مع فلسفة الدمج
# الموصوفة في README_MASR.md)، بدل كتابة parser جديد مستقل.
#
# قيد صريح: إن لم توجد بيانات حقيقية بعد (تثبيت جديد، لا صفقات مسجّلة)، تُرجع
# كل الدوال هنا قوائم/قواميس فارغة موسومة بوضوح (data_source) بدل اختلاق
# بيانات صناعية — نفس مبدأ الشفافية المطبَّق في BACKTEST_VALIDITY_NOTICE.md.

CLOSED_RESULTS = {"WIN", "LOSS"}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_closed_trades(limit: int = 200) -> list[dict[str, Any]]:
    """صفقات مغلقة حقيقية (WIN/LOSS) من data/history/trades.csv — نفس الملف
    الذي يكتبه البوت فعليًا (core.data_integrity.HISTORY_FILE)، وليس بيانات
    تجريبية. يُرجع قائمة فارغة بصمت إن لم يوجد الملف بعد (تثبيت جديد)."""
    rows = read_csv_records(HISTORY_FILE)
    closed = [r for r in rows if str(r.get("result", "")).upper() in CLOSED_RESULTS]
    return closed[-limit:] if limit else closed


def load_memory_snapshot(limit: int = 400) -> list[dict[str, Any]]:
    """سجلات ai_memory.csv الحقيقية (نفس مصدر بيانات core/session_intelligence.py)
    — تحمل حقولًا أغنى (ATR، CHoCH، خريطة السيولة، بنية MTF) تُستخدم لاشتقاق
    ميزات Pattern Discovery و Evolution Engine."""
    rows = load_memory_records()
    closed = [r for r in rows if str(r.get("result", "")).upper() in CLOSED_RESULTS]
    return closed[-limit:] if limit else closed


def _join_by_ticket(trades: list[dict[str, Any]], memory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    memory_by_ticket = {str(m.get("ticket")): m for m in memory if m.get("ticket")}
    enrich_fields = (
        "atr", "choch_state", "choch_strength", "liq_map_score", "liq_map_dir",
        "mtf_strength", "mtf_structural", "news_score", "confidence_score",
    )
    joined = []
    for trade in trades:
        ticket = str(trade.get("ticket", ""))
        merged = dict(trade)
        mem_row = memory_by_ticket.get(ticket)
        if mem_row:
            for key in enrich_fields:
                if mem_row.get(key) not in (None, ""):
                    merged[key] = mem_row[key]
        joined.append(merged)
    return joined


def build_diagnostic_records(limit: int = 200) -> list[dict[str, Any]]:
    """يبني سجلات مُثراة (trades.csv + ai_memory.csv) جاهزة للتغذية المباشرة
    لـ EvolutionEngine و PatternDiscovery — بيانات حقيقية مسجّلة فعليًا من
    تشغيل البوت (ديمو أو حي)، وليست بيانات ثابتة داخل app.py."""
    trades = load_closed_trades(limit)
    if not trades:
        return []
    memory = load_memory_snapshot(limit * 3)
    return _join_by_ticket(trades, memory)


def to_evolution_record(row: dict[str, Any]) -> dict[str, Any]:
    """يحوّل صفًا حقيقيًا واحدًا إلى الشكل الذي يتوقعه
    EvolutionEngine.diagnose_trade().

    ملاحظة بيانات صريحة (اكتُشفت بفحص البيانات الحقيقية فعليًا، وليست
    افتراضًا نظريًا): عمود news_score في data/memory/ai_memory.csv غير مُفعَّل
    عمليًا في أكثر من 99% من الصفوف الحالية (قيمته 0 تقريبًا دومًا)، وعمود atr
    صفر أو فارغ في نحو نصف الصفوف. صفر هنا يعني على الأرجح "لم يُسجَّل بعد"
    وليس "قراءة فعلية بصفر تقلّب/صفر انحراف إخباري" (ATR صفري فعليًا لأصل مثل
    XAUUSD غير واقعي). لذا نُميّز صراحة بين "لا توجد بيانات" (None) و"بيانات
    فعلية متاحة" بدل معاملة الصفر كقيمة حقيقية — وإلا فإن كل صفقة تقريبًا
    كانت ستُشخَّص خطأً بأن الـATR كان ضعيفًا وأن هناك تأثيرًا إخباريًا، لمجرد
    غياب التسجيل، وليس كدليل فعلي."""
    signal = str(row.get("signal", "")).upper()
    liq_dir = str(row.get("liq_map_dir", "")).upper()
    liquidity_alignment: bool | None = None
    if liq_dir in {"UP", "DOWN"}:
        liquidity_alignment = (signal == "BUY" and liq_dir == "UP") or (signal == "SELL" and liq_dir == "DOWN")

    mtf_raw = str(row.get("mtf_structural", "")).strip().lower()
    trend_changed = mtf_raw in {"false", "0"}

    atr_raw = safe_float(row.get("atr"), 0.0)
    atr = atr_raw if atr_raw > 0 else None

    news_score_raw = safe_float(row.get("news_score"), 0.0)
    news_event = news_score_raw > 0 and abs(news_score_raw - 50.0) >= 15.0

    return {
        "trade_id": row.get("ticket", "unknown"),
        "atr": atr,
        "liquidity_alignment": liquidity_alignment,
        "trend_changed": trend_changed,
        "news_event": news_event,
        "result": str(row.get("result", "")).upper(),
    }


def to_discovery_record(row: dict[str, Any], atr_median: float) -> dict[str, Any]:
    """يشتق ميزات (features) وصفية من صف صفقة حقيقي واحد لتغذية
    PatternDiscovery.discover(). الميزات مبنية على أعمدة موجودة فعليًا في
    السجل الحقيقي (trades.csv/ai_memory.csv) — وليست أسماء افتراضية ثابتة."""
    features: list[str] = []

    atr = safe_float(row.get("atr"), 0.0)
    if atr_median > 0 and atr >= atr_median:
        features.append("high_atr")

    liq_score = safe_float(row.get("liq_map_score"), 0.0)
    if liq_score >= 15.0:
        features.append("liquidity_sweep")

    if str(row.get("choch_strength", "")).upper() == "STRONG":
        features.append("strong_choch")

    if str(row.get("mtf_structural", "")).strip().lower() == "true":
        features.append("mtf_aligned")

    if str(row.get("exec_grade", "")).upper() in {"A+", "A"}:
        features.append("high_exec_grade")

    success = 1.0 if str(row.get("result", "")).upper() == "WIN" else 0.0
    return {"features": features, "success": success, "trade_id": row.get("ticket")}


def build_discovery_batch(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    atrs = [safe_float(r.get("atr")) for r in records if safe_float(r.get("atr")) > 0]
    atr_median = statistics.median(atrs) if atrs else 0.0
    return [to_discovery_record(r, atr_median) for r in records]


def compute_history_stats(limit: int = 100) -> dict[str, Any]:
    """إحصاءات وصفية بسيطة من سجل صفقات حقيقي (ليس باك-تيست، ليس تحققًا
    إحصائيًا صارمًا) — تُستخدم من Recovery AI لتفادي مضاعفة الحجم بعد
    سلسلة خسائر (anti-martingale)."""
    trades = load_closed_trades(limit)
    if not trades:
        return {
            "sample_size": 0,
            "win_rate": None,
            "current_losing_streak": 0,
            "avg_rr": None,
            "data_source": "no_history_available",
        }

    wins = sum(1 for t in trades if str(t.get("result", "")).upper() == "WIN")
    win_rate = round(wins / len(trades) * 100.0, 2)

    streak = 0
    for t in reversed(trades):
        if str(t.get("result", "")).upper() == "LOSS":
            streak += 1
        else:
            break

    rr_values = [safe_float(t.get("rr_ratio")) for t in trades if safe_float(t.get("rr_ratio")) > 0]
    avg_rr = round(sum(rr_values) / len(rr_values), 3) if rr_values else None

    return {
        "sample_size": len(trades),
        "win_rate": win_rate,
        "current_losing_streak": streak,
        "avg_rr": avg_rr,
        "data_source": "real_trade_history_csv",
    }

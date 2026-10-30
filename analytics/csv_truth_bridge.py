# =============================================================================
# FER3ON — CSV → TRUTH LAYER SYNC BRIDGE
# =============================================================================
# الإصلاح #1 (حرج): Quant Engine كان يقرأ من truth_layer/trade_history.json
# الذي يحتوي 3 صفقات تجريبية فقط، بينما الصفقات الحقيقية المُغلقة تُكتب
# في data/history/trades.csv عبر core/trade_logger.py.
#
# هذا الجسر يمزج المصدرين:
#   1. يقرأ trades.csv ← صفقات مُغلقة (result != OPEN) فقط
#   2. يحوّلها إلى TradeRecord ويُضيفها إلى truth_layer إن لم تكن موجودة
#      (تتحقق بـ ticket لمنع التكرار)
#   3. يُستدعى من analytics/truth_layer.load_all_trades() شفافيًا بدون
#      تغيير أي كود آخر في المشروع
#
# DESIGN DECISION: عدم تعديل truth_layer.load_all_trades() نفسها مباشرة
# لتجنب تعقيد جوهرها — بدلًا من ذلك يوفر هذا الملف:
#   - sync_csv_to_truth_layer()  ← يُشغَّل عند الإقلاع (main.py / startup)
#   - load_all_trades_merged()   ← بديل مدمج يُستخدم من quant_engine.py
#     بدون أي تغيير في truth_layer.py نفسها
# =============================================================================

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from typing import List, Set

from analytics.truth_layer import TradeRecord, append_trade, load_all_trades
from core.data_integrity import HISTORY_FILE


# =============================================================================
# FIELD MAPPING — trades.csv → TradeRecord
# =============================================================================

def _session_from_hour(hour: int) -> str:
    if 0 <= hour < 8:
        return "ASIA"
    if 8 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 18:
        return "NEWYORK"
    return "OFF_HOURS"


def _csv_row_to_trade_record(row: dict) -> TradeRecord:
    """
    يحوّل صف trades.csv إلى TradeRecord.
    الحقول المتاحة في CSV:
      date, ticket, signal, lot, profit, result,
      strategy, session, market_regime, exec_grade,
      rr_ratio, quality_score, brain_score
    """
    try:
        profit = float(row.get("profit") or 0)
    except (ValueError, TypeError):
        profit = 0.0

    try:
        lot = float(row.get("lot") or 0)
    except (ValueError, TypeError):
        lot = 0.0

    try:
        rr = float(row.get("rr_ratio") or 0)
    except (ValueError, TypeError):
        rr = 0.0

    try:
        quality = float(row.get("quality_score") or 0)
    except (ValueError, TypeError):
        quality = 0.0

    date_str = str(row.get("date") or "")
    session = str(row.get("session") or "UNKNOWN").upper()
    if not session or session in ("UNKNOWN", ""):
        try:
            dt = datetime.fromisoformat(date_str)
            session = _session_from_hour(dt.hour)
        except Exception:
            session = "UNKNOWN"

    result_str = str(row.get("result") or "").upper()
    is_win = result_str == "WIN"
    raw_conditions = row.get("entry_conditions")
    if isinstance(raw_conditions, list):
        entry_conditions = [str(value) for value in raw_conditions]
    else:
        try:
            parsed_conditions = json.loads(str(raw_conditions or "[]"))
            entry_conditions = (
                [str(value) for value in parsed_conditions]
                if isinstance(parsed_conditions, list) else []
            )
        except (TypeError, ValueError):
            entry_conditions = []

    try:
        ticket = int(float(str(row.get("ticket") or 0)))
    except (ValueError, TypeError):
        ticket = 0

    return TradeRecord(
        ticket=ticket,
        strategy=str(row.get("strategy") or "UNKNOWN").upper(),
        direction=str(row.get("signal") or "UNKNOWN").upper(),
        session=session,
        regime=str(row.get("market_regime") or "UNKNOWN").upper(),
        open_time=date_str,
        close_time=date_str,
        lot=lot,
        profit=profit,
        rr_achieved=rr,
        quality_score=quality,
        entry_reason=str(row.get("entry_reason") or ""),
        entry_conditions=entry_conditions,
        is_win=is_win,
        build_id=str(row.get("build_id") or ""),
        extra={
            "source": "csv_truth_bridge",
            "exec_grade": str(row.get("exec_grade") or ""),
            "brain_score": str(row.get("brain_score") or ""),
            "entry_cost_complete": (
                str(row.get("entry_cost_complete") or "").strip().lower() == "true"
                if str(row.get("entry_cost_complete") or "").strip().lower()
                in {"true", "false"}
                else None
            ),
        },
    )


# =============================================================================
# SYNC: CSV → TRUTH LAYER (يُشغَّل مرة عند الإقلاع)
# =============================================================================

def sync_csv_to_truth_layer() -> dict:
    """
    يقرأ data/history/trades.csv ويُضيف الصفقات المُغلقة غير الموجودة
    في truth_layer/trade_history.json.

    يعتمد على ticket كمفتاح مقارنة (لا يُكرَّر).
    يتجاهل صفوف OPEN تمامًا (profit=0, result=OPEN).

    Returns dict: {"synced": int, "skipped_open": int, "already_exists": int}
    """
    if not os.path.exists(HISTORY_FILE):
        print("ℹ️ CSV_BRIDGE: trades.csv غير موجود — لا شيء للمزامنة")
        return {"synced": 0, "skipped_open": 0, "already_exists": 0}

    # جمع التذاكر الموجودة حاليًا في truth_layer لمنع التكرار
    existing_tickets: Set[int] = {
        t.ticket for t in load_all_trades()
    }

    synced = 0
    skipped_open = 0
    already_exists = 0

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                result = str(row.get("result") or "").upper()

                # تجاهل الصفقات المفتوحة
                if result == "OPEN" or result == "":
                    skipped_open += 1
                    continue

                try:
                    ticket = int(float(str(row.get("ticket") or 0)))
                except (ValueError, TypeError):
                    continue

                if ticket == 0:
                    continue

                if ticket in existing_tickets:
                    already_exists += 1
                    continue

                record = _csv_row_to_trade_record(row)
                try:
                    append_trade(record)
                    existing_tickets.add(ticket)
                    synced += 1
                except Exception as e:
                    print(f"⚠️ CSV_BRIDGE: فشل في إضافة ticket={ticket}: {e}")

    except Exception as e:
        print(f"❌ CSV_BRIDGE: خطأ في قراءة trades.csv: {e}")
        return {"synced": 0, "skipped_open": skipped_open, "already_exists": already_exists}

    print(
        f"✅ CSV_BRIDGE: مزامنة مكتملة | "
        f"synced={synced} | skipped_open={skipped_open} | already_exists={already_exists}"
    )
    return {"synced": synced, "skipped_open": skipped_open, "already_exists": already_exists}


# =============================================================================
# MERGED LOAD — يجمع truth_layer + CSV بدون تكرار (للاستخدام من quant_engine)
# =============================================================================

def load_all_trades_merged() -> List[TradeRecord]:
    """
    مثل load_all_trades() لكن يضمن شمول جميع الصفقات المُغلقة من trades.csv
    حتى لو لم تُشغَّل sync_csv_to_truth_layer() بعد.

    يُستخدم داخليًا فقط — quant_engine يستهلك load_all_trades() العادية
    بعد تشغيل sync عند الإقلاع. هذا الدالة احتياطية إضافية.
    """
    truth_records = load_all_trades()
    existing_tickets: Set[int] = {t.ticket for t in truth_records}
    extra_records: List[TradeRecord] = []

    if not os.path.exists(HISTORY_FILE):
        return truth_records

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                result = str(row.get("result") or "").upper()
                if result == "OPEN" or result == "":
                    continue
                try:
                    ticket = int(float(str(row.get("ticket") or 0)))
                except (ValueError, TypeError):
                    continue
                if ticket == 0 or ticket in existing_tickets:
                    continue
                record = _csv_row_to_trade_record(row)
                extra_records.append(record)
                existing_tickets.add(ticket)
    except Exception as e:
        print(f"⚠️ CSV_BRIDGE load_merged: {e}")

    return truth_records + extra_records

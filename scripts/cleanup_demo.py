#!/usr/bin/env python3
# =============================================================================
# FER3ON — تنظيف الصفقات العالقة قبل الديمو
# =============================================================================
# الإصلاح #2: 379 صفقة OPEN عالقة في data/history/trades.csv من جلسات
# الاختبار القديمة. هذا السكريبت:
#
#   1. يحفظ نسخة احتياطية: data/history/trades_backup_<timestamp>.csv
#   2. يُنشئ trades.csv جديد يحتوي الصفقات المُغلقة فقط (WIN/LOSS/SYNC)
#      — أو فارغًا تمامًا لو أردت بداية نظيفة 100%
#   3. يحفظ نسخة احتياطية من truth_layer أيضًا ويعيد بناءه من الصفقات
#      المُغلقة المتبقية
#
# الاستخدام:
#   python scripts/cleanup_demo.py             ← يحتفظ بالمُغلقات، يزيل OPEN
#   python scripts/cleanup_demo.py --full      ← يبدأ من صفر كامل (ملفات فارغة)
#
# الأمان: لا شيء يُحذف، فقط نسخ احتياطية ثم كتابة جديدة.
# =============================================================================

import argparse
import csv
import os
import shutil
from datetime import datetime, timezone


HISTORY_FILE = "data/history/trades.csv"
TRUTH_LAYER_FILE = "data/truth_layer/trade_history.json"
BACKUP_DIR = "data/history"

HISTORY_COLUMNS = [
    "date", "ticket", "signal", "lot", "profit", "result",
    "strategy", "session", "market_regime", "exec_grade",
    "rr_ratio", "quality_score", "brain_score",
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_file(path: str) -> str:
    """ينشئ نسخة احتياطية ويعيد مسارها."""
    if not os.path.exists(path):
        return ""
    ts = _timestamp()
    base = os.path.basename(path).replace(".", f"_backup_{ts}.")
    backup_path = os.path.join(BACKUP_DIR, base)
    shutil.copy2(path, backup_path)
    print(f"  💾 نسخة احتياطية: {backup_path}")
    return backup_path


def read_all_rows(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path: str, columns: list, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def rebuild_truth_layer_from_csv(closed_rows: list) -> None:
    """يُعيد بناء truth_layer/trade_history.json من الصفقات المُغلقة فقط."""
    import json
    os.makedirs(os.path.dirname(TRUTH_LAYER_FILE), exist_ok=True)

    lines = []
    for row in closed_rows:
        result = str(row.get("result") or "").upper()
        if result == "OPEN":
            continue
        try:
            ticket = int(float(str(row.get("ticket") or 0)))
        except Exception:
            continue
        try:
            profit = float(row.get("profit") or 0)
        except Exception:
            profit = 0.0
        is_win = result == "WIN"
        record = {
            "ticket": ticket,
            "strategy": str(row.get("strategy") or "UNKNOWN").upper(),
            "direction": str(row.get("signal") or "UNKNOWN").upper(),
            "session": str(row.get("session") or "UNKNOWN").upper(),
            "regime": str(row.get("market_regime") or "UNKNOWN").upper(),
            "regime_strength": 0.0,
            "open_time": str(row.get("date") or ""),
            "close_time": str(row.get("date") or ""),
            "entry_price": 0.0,
            "exit_price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "lot": float(row.get("lot") or 0),
            "rr_achieved": float(row.get("rr_ratio") or 0),
            "profit": profit,
            "risk_percent": 0.0,
            "confidence": 0.0,
            "quality_score": float(row.get("quality_score") or 0),
            "ml_boost": 0.0,
            "composite_score": 0.0,
            "duration_sec": 0.0,
            "exit_reason": str(row.get("exec_grade") or ""),
            "is_win": is_win,
            "extra": {"source": "csv_cleanup_rebuild"},
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    with open(TRUTH_LAYER_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

    print(f"  ✅ truth_layer أُعيد بناؤه بـ {len(lines)} صفقة مُغلقة")


def main():
    parser = argparse.ArgumentParser(
        description="تنظيف صفقات OPEN العالقة في trades.csv قبل الديمو"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="بداية نظيفة كاملة: احذف كل الصفقات وابدأ من صفر",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  FER3ON — تنظيف قبل الديمو")
    print("=" * 60)

    # --- قراءة الوضع الحالي ---
    all_rows = read_all_rows(HISTORY_FILE)
    total = len(all_rows)
    open_rows = [r for r in all_rows if str(r.get("result") or "").upper() == "OPEN"]
    closed_rows = [r for r in all_rows if str(r.get("result") or "").upper() != "OPEN"]

    print(f"\n📊 الوضع الحالي في trades.csv:")
    print(f"   إجمالي الصفوف  : {total}")
    print(f"   صفقات OPEN     : {len(open_rows)}  ← ستُحذف")
    print(f"   صفقات مُغلقة   : {len(closed_rows)}  ← ستُحفظ")

    if total == 0:
        print("\nℹ️ trades.csv فارغ أصلًا — لا شيء للتنظيف")
        return

    # --- نسخ احتياطية ---
    print(f"\n💾 حفظ النسخ الاحتياطية...")
    backup_file(HISTORY_FILE)
    backup_file(TRUTH_LAYER_FILE)

    # --- الكتابة الجديدة ---
    if args.full:
        print(f"\n🧹 وضع --full: بداية نظيفة كاملة (ملفات فارغة)")
        write_rows(HISTORY_FILE, HISTORY_COLUMNS, [])
        # إعادة بناء truth_layer فارغًا
        os.makedirs(os.path.dirname(TRUTH_LAYER_FILE), exist_ok=True)
        open(TRUTH_LAYER_FILE, "w").close()
        print("  ✅ trades.csv: فارغ")
        print("  ✅ trade_history.json: فارغ")
    else:
        print(f"\n🧹 إزالة {len(open_rows)} صفقة OPEN + الاحتفاظ بـ {len(closed_rows)} مُغلقة...")
        write_rows(HISTORY_FILE, HISTORY_COLUMNS, closed_rows)
        print(f"  ✅ trades.csv: {len(closed_rows)} صفقة مُغلقة محفوظة")

        # إعادة بناء truth_layer من الصفقات المُغلقة
        rebuild_truth_layer_from_csv(closed_rows)

    print(f"\n{'=' * 60}")
    print(f"  ✅ التنظيف مكتمل — النظام جاهز للديمو")
    print(f"  📂 النسخ الاحتياطية في: {BACKUP_DIR}/")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()

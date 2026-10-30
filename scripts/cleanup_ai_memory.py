#!/usr/bin/env python3
# =============================================================================
# FER3ON — تنظيف ai_memory.csv من بيانات ما قبل إصلاح enrichment
# =============================================================================
# نفس فلسفة scripts/cleanup_demo.py (نسخة احتياطية أولًا، ثم كتابة جديدة —
# لا شيء يُحذف بلا نسخة احتياطية) لكن لملف data/memory/ai_memory.csv، الذي
# له نمط تلوّث مختلف قليلًا عن trades.csv بسبب باگ enrichment القديم:
#
#   - صفوف OPEN عالقة للأبد (result=OPEN، لم تُغلَق أبدًا بسبب باگ
#     الـ ticket mismatch القديم في mt5_history_sync.py — تم إصلاحه، لكن
#     الصفوف القديمة العالقة ما زالت هنا).
#   - صفوف SYNC يتيمة (exec_grade=SYNC، بدون أي enrichment حقيقي — كانت
#     تُكتب دائمًا كصف جديد منفصل بدل الدمج مع صف OPEN الأصلي، فارغة تمامًا
#     من choch/liquidity/mtf/atr الحقيقية).
#   - صفوف مُغلقة حقيقية (WIN/LOSS بـ exec_grade حقيقي) — قد تكون قيّمة،
#     أو قد تكون -مثل trades.csv عند هذا المستخدم- من نسخة بوت قديمة تمامًا
#     لا علاقة لها بهذا الإصدار.
#
# الاستخدام:
#   python scripts/cleanup_ai_memory.py          ← يحتفظ بالصفوف المُغلقة
#                                                    الحقيقية (exec_grade
#                                                    != SYNC)، يزيل
#                                                    OPEN العالقة وSYNC
#                                                    اليتيمة فقط
#   python scripts/cleanup_ai_memory.py --full   ← بداية نظيفة كاملة
#                                                    (ملف فارغ بالكامل)
#
# الأمان: لا شيء يُحذف بلا نسخة احتياطية أولًا في data/memory/.
# =============================================================================

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_integrity import AI_MEMORY_COLUMNS, AI_MEMORY_FILE  # noqa: E402

BACKUP_DIR = "data/memory"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_file(path: str) -> str:
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


def main():
    parser = argparse.ArgumentParser(
        description="تنظيف صفوف OPEN العالقة و SYNC اليتيمة في ai_memory.csv"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="بداية نظيفة كاملة: احذف كل الصفوف وابدأ من صفر",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  FER3ON — تنظيف ai_memory.csv")
    print("=" * 60)

    all_rows = read_all_rows(AI_MEMORY_FILE)
    total = len(all_rows)
    open_rows = [r for r in all_rows if str(r.get("result") or "").upper() == "OPEN"]
    sync_orphan_rows = [
        r for r in all_rows
        if str(r.get("result") or "").upper() != "OPEN"
        and str(r.get("exec_grade") or "").upper() == "SYNC"
    ]
    real_closed_rows = [
        r for r in all_rows
        if str(r.get("result") or "").upper() != "OPEN"
        and str(r.get("exec_grade") or "").upper() != "SYNC"
    ]

    print("\n📊 الوضع الحالي في ai_memory.csv:")
    print(f"   إجمالي الصفوف         : {total}")
    print(f"   صفقات OPEN عالقة      : {len(open_rows)}  ← ستُحذف")
    print(f"   صفوف SYNC يتيمة       : {len(sync_orphan_rows)}  ← ستُحذف (بلا enrichment حقيقي)")
    print(f"   صفقات مُغلقة حقيقية   : {len(real_closed_rows)}  ← ستُحفظ (إلا مع --full)")

    if total == 0:
        print("\nℹ️ ai_memory.csv فارغ أصلًا — لا شيء للتنظيف")
        return

    print("\n💾 حفظ نسخة احتياطية...")
    backup_file(AI_MEMORY_FILE)

    if args.full:
        print("\n🧹 وضع --full: بداية نظيفة كاملة (ملف فارغ)")
        write_rows(AI_MEMORY_FILE, AI_MEMORY_COLUMNS, [])
        print("  ✅ ai_memory.csv: فارغ")
    else:
        print(
            f"\n🧹 إزالة {len(open_rows)} صفقة OPEN عالقة + "
            f"{len(sync_orphan_rows)} صف SYNC يتيم، "
            f"الاحتفاظ بـ {len(real_closed_rows)} صفقة مُغلقة حقيقية..."
        )
        write_rows(AI_MEMORY_FILE, AI_MEMORY_COLUMNS, real_closed_rows)
        print(f"  ✅ ai_memory.csv: {len(real_closed_rows)} صفقة مُغلقة محفوظة")

    print(f"\n{'=' * 60}")
    print("  ✅ التنظيف مكتمل")
    print(f"  📂 النسخة الاحتياطية في: {BACKUP_DIR}/")
    print("  ℹ️ نصيحة: شغّل 'python -m fer3on readiness' الآن لرؤية الأثر")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()

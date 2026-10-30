"""
[FER3ON-FIX-2026-08-19 BRAIN-SCOPE] Dedupe adaptive_trades.jsonl
================================================================
data/analytics/adaptive_trades.jsonl فيه تكرار حرفي (1007 سطر منهم 958 فريد
فقط — على الأغلب sync اتنفذ أكتر من مرة). التكرار ده يضخّم وزن الصفقات
المكررة في أي تحليل بيقرا الملف.

الأداة دي تشيل الأسطر المكررة حرفيًا مع الحفاظ على ترتيب أول ظهور.
Idempotent — إعادة التشغيل لا تغيّر شيئًا. بدون --apply = dry run.

Usage:
    python3 tools/dedupe_adaptive_trades.py [--apply]
"""
from __future__ import annotations

import argparse
import os
import shutil

JSONL_PATH = "data/analytics/adaptive_trades.jsonl"


def dedupe(apply: bool) -> None:
    if not os.path.exists(JSONL_PATH):
        print(f"[skip] {JSONL_PATH} not found")
        return

    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    seen = set()
    kept = []
    dupes = 0
    for line in lines:
        key = line.strip()
        if not key:
            continue
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        kept.append(line if line.endswith("\n") else line + "\n")

    print(f"{JSONL_PATH}: {len(lines)} lines -> {len(kept)} unique kept, {dupes} exact duplicates removed")

    if not apply or dupes == 0:
        if not apply and dupes:
            print("  (dry run — pass --apply to write)")
        return

    shutil.copy2(JSONL_PATH, JSONL_PATH + ".bak")
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        f.writelines(kept)
    print(f"  -> backup of original saved to {JSONL_PATH}.bak")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    dedupe(args.apply)


if __name__ == "__main__":
    main()

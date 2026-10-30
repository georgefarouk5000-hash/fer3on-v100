#!/usr/bin/env python3
# =========================================
# MIGRATE LEGACY KNOWLEDGE TXT -> STRUCTURED JSON
# يحوّل قواعد data/knowledge/*.txt (نص حر) إلى
# data/knowledge/structured/rules.json (بنية صريحة قابلة للتحقق)
#
# لماذا؟
# التصميم القديم كان يعتمد على "احتواء نص" (substring match) بلا أي
# فهم لما إذا كانت الكلمة تعني شرط تشغيل حقيقي أو مجرد ذكر عرضي،
# وكل قاعدة مطابقة تضيف +5 نقاط بشكل تراكمي بلا سقف تناقصي، لذلك
# أي عدد معقول من القواعد (10-15) يشبع الدرجة عند 100 تلقائيًا.
#
# هذا السكربت يحافظ على كل قاعدة موجودة (لا حذف بيانات) لكنه يعيد
# تمثيلها كشروط صريحة (conditions) + نوع (regime_session / correlation)
# + وزن ابتدائي (confidence) قابل لاحقًا للمعايرة عبر نتائج باك-تيست
# حقيقية (انظر core/backtest_validity.py).
# =========================================

import json
import os
import re

LEGACY_FOLDER = "data/knowledge"
OUTPUT_PATH = "data/knowledge/structured/rules.json"

CATEGORY_BY_FILE = {
    "smc_rules.txt": "smc",
    "price_action_rules.txt": "price_action",
    "risk_management_rules.txt": "risk_management",
    "gold_rules.txt": "gold_xauusd",
}

# شروط تُعتبر "نظام سوق" (regime) أو "جلسة تداول" (session)
# تُستخدم لتصنيف نوع القاعدة تلقائيًا
REGIME_TOKENS = {"TRENDING", "RANGING", "VOLATILE"}
SESSION_TOKENS = {"LONDON", "NEWYORK", "ASIA", "LONDON + NEWYORK OVERLAP", "OVERLAP"}


def _split_rule_line(line):
    line = line.strip()
    if not line or "=" not in line:
        return None
    left, advice = line.split("=", 1)
    conditions = [c.strip().upper() for c in left.split("+") if c.strip()]
    advice = advice.strip()
    return conditions, advice


def _classify(conditions):
    has_regime = any(c in REGIME_TOKENS for c in conditions)
    has_session = any(
        c in SESSION_TOKENS or "OVERLAP" in c or c in ("LONDON", "NEWYORK", "ASIA")
        for c in conditions
    )
    if has_regime and has_session:
        return "regime_session", 0.14
    if has_regime or has_session:
        return "partial_context", 0.06
    return "correlation", 0.08


def migrate():
    rules = []
    rule_id = 0

    for file_name, category in CATEGORY_BY_FILE.items():
        file_path = os.path.join(LEGACY_FOLDER, file_name)
        if not os.path.exists(file_path):
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

        for raw in raw_lines:
            parsed = _split_rule_line(raw)
            if not parsed:
                continue
            conditions, advice = parsed
            rule_type, default_weight = _classify(conditions)

            rule_id += 1
            rules.append({
                "id": f"legacy_{rule_id:03d}",
                "category": category,
                "type": rule_type,
                "conditions": conditions,
                "advice": advice,
                "weight": default_weight,
                # يُملأ لاحقًا من نتائج باك-تيست حقيقية إن وُجدت
                # (None = لم تتم معايرته على بيانات تاريخية فعلية بعد)
                "validated_win_rate": None,
                "source": "legacy_txt_migration",
            })

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

    print(f"✅ تم ترحيل {len(rules)} قاعدة إلى {OUTPUT_PATH}")
    return rules


if __name__ == "__main__":
    migrate()

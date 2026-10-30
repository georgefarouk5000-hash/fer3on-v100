"""
=========================================
KNOWLEDGE BASE — SCORING ENGINE (v2)
=========================================

هذا الملف هو إعادة تصميم لآلية get_knowledge_score القديمة.

ما الذي تغيّر ولماذا (توثيق صريح للقيود المتبقية):

1) القواعد الآن مُهيكلة (JSON) بدل نص حر (.txt) يُفحص عبر
   substring match. كل قاعدة لها: conditions صريحة (regime/session)،
   نوع (regime_session / partial_context / correlation)، ووزن.
   => هذا يمنع تطابقات عرضية (مثل كلمة "TREND" داخل كلمة أخرى)
   ويجعل كل قاعدة تُفعَّل فقط عندما تتطابق شروطها فعليًا مع
   السياق الحالي (market_regime, session) وليس بمجرد ظهور الكلمة
   في أي مكان بالسطر.

2) الدرجة لم تعد مجموعًا خطيًا (+5 لكل تطابق) بلا سقف تناقصي.
   الصيغة الجديدة تدمج الأدلة بطريقة "احتمالية تناقصية"
   (soft-OR / diminishing returns): كل قاعدة إضافية تقارب الدرجة
   أكثر من 100 لكنها لا تصل إليها بسهولة، والقواعد ذات التطابق
   الكامل (نظام سوق + جلسة معًا) تُرجَّح أعلى من التطابق الجزئي.
   هذا يحل تحديدًا مشكلة "التشبع عند 100 بمجرد إضافة قواعد كافية".

3) هذا **ليس** فهمًا سياقيًا حقيقيًا (لا NLP ولا نموذج لغوي يفهم
   المعنى) — يبقى مطابقة شروط منظّمة (structured condition matching)
   وليس فهمًا دلاليًا. الفرق عن النسخة القديمة هو أن المطابقة الآن
   على حقول صريحة بدل نص حر، وأن التجميع تناقصي بدل تراكمي، لا أكثر.
   إن أردت فهمًا سياقيًا حقيقيًا لاحقًا فهذا يتطلب طبقة تعلّم آلي
   منفصلة (انظر ml/) تُدرَّب على بيانات تاريخية فعلية، وليس تحسين
   هذه الدالة نفسها.

4) وزن كل قاعدة (weight) قابل للمعايرة لاحقًا عبر
   validated_win_rate بمجرد توفر نتائج باك-تيست على بيانات
   تاريخية حقيقية (انظر core/backtest_validity.py وتحذيره،
   لأن الوضع الحالي للباك-تيست في المشروع يعتمد على بيانات
   اصطناعية عشوائية بلا تأكيد جدوى فعلي — نقطة الضعف #2).
"""

import json
import os

STRUCTURED_RULES_PATH = "data/knowledge/structured/rules.json"
PSYCHOLOGY_RULES_PATH = "data/knowledge/structured/psychology_rules.json"

# نُبقي على المسار القديم لأغراض التوافق الخلفي فقط (لا يُستخدم
# داخليًا بعد الآن في get_knowledge_score، لكن load_knowledge()
# ما زالت متاحة إن اعتمد عليها كود خارجي).
LEGACY_KNOWLEDGE_FOLDER = "data/knowledge"


# =========================================
# LEGACY LOADER (BACKWARD COMPAT — UNCHANGED BEHAVIOUR)
# =========================================

def load_knowledge():
    knowledge = []

    if not os.path.exists(LEGACY_KNOWLEDGE_FOLDER):
        os.makedirs(LEGACY_KNOWLEDGE_FOLDER, exist_ok=True)
        return knowledge

    for file_name in os.listdir(LEGACY_KNOWLEDGE_FOLDER):
        if not file_name.endswith(".txt"):
            continue

        file_path = os.path.join(LEGACY_KNOWLEDGE_FOLDER, file_name)

        with open(file_path, "r", encoding="utf-8") as file:
            for line in file.readlines():
                line = line.strip()
                if line:
                    knowledge.append(line)

    return knowledge


# =========================================
# STRUCTURED RULE LOADING
# =========================================

def _load_json_rules(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def load_structured_rules():
    """يحمّل قواعد السوق المهيكلة (SMC / price action / risk / gold)."""
    return _load_json_rules(STRUCTURED_RULES_PATH)


def load_psychology_rules():
    """يحمّل قواعد السيكولوجيا المرتبطة بـ market_regime/session."""
    return _load_json_rules(PSYCHOLOGY_RULES_PATH)


# =========================================
# MATCHING
# =========================================

def _rule_matches(conditions, regime, session):
    """
    يُرجع نوع التطابق: 'joint' (نظام السوق + الجلسة معًا)،
    'partial' (أحدهما فقط)، أو None (لا تطابق).
    مطابقة صريحة على القيمة الكاملة للشرط، وليست substring،
    لتفادي تطابقات عرضية.
    """
    conds = set(conditions)
    has_regime = regime in conds
    has_session = session in conds or any(
        session in c or "OVERLAP" in c for c in conds
    )

    if has_regime and has_session:
        return "joint"
    if has_regime or has_session:
        return "partial"
    return None


def _effective_weight(rule):
    """
    الوزن الأساسي + تعديل اختياري إذا توفر تحقق فعلي (validated_win_rate)
    من باك-تيست على بيانات تاريخية حقيقية. بدون تحقق فعلي، يبقى
    الوزن الافتراضي الثابت كما هو (لا نتظاهر بثقة غير موجودة).
    """
    base_weight = float(rule.get("weight", 0.08))
    validated_wr = rule.get("validated_win_rate")

    if validated_wr is None:
        return base_weight

    # إن وُجد تحقق فعلي: كلما ابتعد معدل الربح الموثّق عن 50%
    # (عشوائي) زاد وزن القاعدة، وكلما اقترب منه قلّ وزنها تلقائيًا
    # (قاعدة أثبتت أنها لا تضيف قيمة حقيقية تُهمَّش وحدها دون حذف).
    edge = abs(float(validated_wr) - 50.0) / 50.0  # 0..1
    return max(0.02, min(0.25, base_weight * (0.5 + edge)))


def get_knowledge_score(market_regime, session, return_breakdown=False):
    """
    يُرجع درجة معرفة (0-100) بدل جمع خطي بسيط:
    - تجميع تناقصي (diminishing returns) بدل جمع تراكمي غير محدود
      => يمنع التشبع السريع عند 100 لمجرد وجود عدد كافٍ من القواعد.
    - تطابق كامل (regime + session) يُرجَّح أعلى من تطابق جزئي.
    - القواعد المُتحقَّق منها فعليًا (validated_win_rate) تؤثر أكثر
      من القواعد الافتراضية غير المُختبرة على بيانات حقيقية.
    """
    regime = str(market_regime or "").upper().strip()
    sess = str(session or "").upper().strip()

    rules = load_structured_rules()

    joint_rules = []
    partial_rules = []

    for rule in rules:
        match = _rule_matches(rule.get("conditions", []), regime, sess)
        if match == "joint":
            joint_rules.append(rule)
        elif match == "partial":
            partial_rules.append(rule)

    # دمج تناقصي: كل قاعدة تُقلّص "عدم اليقين المتبقي" بدل أن تُضاف له
    remaining_uncertainty = 1.0
    for rule in joint_rules:
        remaining_uncertainty *= (1.0 - _effective_weight(rule))
    for rule in partial_rules:
        # التطابق الجزئي يُعطى نصف تأثير التطابق الكامل تقريبًا
        remaining_uncertainty *= (1.0 - _effective_weight(rule) * 0.4)

    evidence_strength = 1.0 - remaining_uncertainty  # في [0, ~1)
    score = 50.0 + 50.0 * evidence_strength
    score = max(0.0, min(100.0, round(score, 2)))

    if not return_breakdown:
        return score

    return {
        "score": score,
        "joint_matches": len(joint_rules),
        "partial_matches": len(partial_rules),
        "matched_rule_ids": [r.get("id") for r in joint_rules + partial_rules],
        "note": (
            "مطابقة شروط مهيكلة + تجميع تناقصي — ليست فهمًا سياقيًا حقيقيًا. "
            "راجع docstring الملف لتفاصيل القيود."
        ),
    }


# =========================================
# PSYCHOLOGY NOTES (WEAKNESS #3)
# =========================================

def get_psychology_notes(market_regime, session):
    """
    يُرجع تحذيرات/ملاحظات سيكولوجية مرتبطة بـ market_regime/session
    الحالي (نص إرشادي، وليس رقمًا يُدمج في درجة القرار العددية —
    لتفادي خلط "جودة إشارة السوق" بـ"حالة نفسية متوقعة للمتداول"
    داخل رقم واحد قد يُفسَّر خطأً كثقة إحصائية بالصفقة).

    كل عنصر يعود يحتوي: condition الذي فعّله + نص التحذير + الفئة.
    """
    regime = str(market_regime or "").upper().strip()
    sess = str(session or "").upper().strip()

    rules = load_psychology_rules()
    matched = []

    for rule in rules:
        match = _rule_matches(rule.get("conditions", []), regime, sess)
        if match:
            matched.append({
                "id": rule.get("id"),
                "match_type": match,
                "warning": rule.get("advice"),
                "category": rule.get("category", "psychology"),
            })

    return matched

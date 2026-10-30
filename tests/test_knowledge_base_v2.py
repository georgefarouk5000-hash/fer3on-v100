import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.knowledge_base import get_knowledge_score, get_psychology_notes, load_structured_rules


def test_structured_rules_loaded():
    rules = load_structured_rules()
    assert len(rules) > 0, "يجب أن تُحمَّل القواعد المهيكلة من الترحيل"


def test_score_no_longer_saturates_at_100():
    # حتى مع تطابقات متعددة (joint + partial) يجب ألا تصل الدرجة لـ100 بسهولة
    score = get_knowledge_score("TRENDING", "LONDON")
    assert 50 <= score < 100, f"الدرجة {score} يجب ألا تُشبع عند 100"


def test_unmatched_context_stays_near_baseline():
    score = get_knowledge_score("NONEXISTENT_REGIME", "NONEXISTENT_SESSION")
    assert 48 <= score <= 60, f"سياق غير مطابق يجب أن يبقى قرب الحياد (50), got {score}"


def test_joint_match_scores_higher_than_partial_only():
    joint_score = get_knowledge_score("TRENDING", "LONDON")  # يوجد تطابق كامل موثق
    partial_only_score = get_knowledge_score("TRENDING", "NONEXISTENT_SESSION")
    assert joint_score > partial_only_score


def test_psychology_notes_return_for_known_combo():
    notes = get_psychology_notes("VOLATILE", "NEWYORK")
    assert len(notes) > 0
    assert all("warning" in n and "id" in n for n in notes)


def test_psychology_notes_not_a_numeric_score():
    notes = get_psychology_notes("RANGING", "ASIA")
    assert isinstance(notes, list)
    for n in notes:
        assert isinstance(n["warning"], str)


if __name__ == "__main__":
    test_structured_rules_loaded()
    test_score_no_longer_saturates_at_100()
    test_unmatched_context_stays_near_baseline()
    test_joint_match_scores_higher_than_partial_only()
    test_psychology_notes_return_for_known_combo()
    test_psychology_notes_not_a_numeric_score()
    print("✅ كل اختبارات knowledge_base v2 نجحت")

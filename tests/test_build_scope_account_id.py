"""
[FER3ON-FIX-2026-08-28] Tests for the account_id filtering layer added to
core/build_scope.py::is_current_build_row().

القصة: تبديل حساب MT5 من غير تغيير البيلد كان بيسيب صفوف الحساب القديم
تعدي فلترة build_id (لأن build_id بتاعهم بيطابق البيلد الحالي بالظبط —
هم اتسجلوا بنفس الكود، بس على حساب تاني). الفحص الجديد طبقة مستقلة فوق
فحص build_id الموجود، بنفس فلسفة backward-compat: صف من غير account_id
خالص (بيانات قديمة قبل الإضافة) لا يُستبعد.
"""
import importlib

import pytest


@pytest.fixture
def bs(monkeypatch):
    import core.build_scope as build_scope
    importlib.reload(build_scope)
    monkeypatch.setattr(build_scope, "_BUILD_ID", "BUILD_X")
    monkeypatch.setattr(build_scope, "_DEPLOYED_AT", "2026-08-01T00:00:00+00:00")
    return build_scope


def test_same_build_same_account_passes(bs, monkeypatch):
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "111")
    row = {"build_id": "BUILD_X", "account_id": "111", "date": "2026-08-25T00:00:00+00:00"}
    assert bs.is_current_build_row(row) is True


def test_same_build_different_account_is_excluded(bs, monkeypatch):
    """السيناريو الحقيقي: build_id بيطابق (نفس الكود)، لكن account_id
    مختلف (حساب MT5 اتغيّر). لازم يُستبعد رغم إن build_id سليم."""
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "222")
    row = {"build_id": "BUILD_X", "account_id": "111", "date": "2026-08-25T00:00:00+00:00"}
    assert bs.is_current_build_row(row) is False


def test_row_without_account_id_is_not_excluded_backward_compat(bs, monkeypatch):
    """بيانات قديمة اتسجلت قبل إضافة account_id — مفيش الحقل خالص. لازم
    الفحص يتراجع (زي فحص build_id بالظبط) مش يستبعد كل شيء بالخطأ."""
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "222")
    row = {"build_id": "BUILD_X", "date": "2026-08-25T00:00:00+00:00"}
    assert bs.is_current_build_row(row) is True


def test_different_build_is_still_excluded_regardless_of_account(bs, monkeypatch):
    """فحص الـbuild الأصلي لازم يفضل شغال زي ما هو — الإضافة الجديدة طبقة
    فوقه مش بديلة عنه."""
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "111")
    row = {"build_id": "OLD_BUILD", "account_id": "111", "date": "2026-08-25T00:00:00+00:00"}
    assert bs.is_current_build_row(row) is False


def test_current_account_unknown_excludes_tagged_rows_failsafe(bs, monkeypatch):
    """لو معرفناش الحساب الحالي (MT5 مش متصل مثلًا) بس الصف *فيه*
    account_id صريح، الأفضل نستبعد (fail-safe) بدل ما نفترض تطابق مجهول."""
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "")
    row = {"build_id": "BUILD_X", "account_id": "111", "date": "2026-08-25T00:00:00+00:00"}
    assert bs.is_current_build_row(row) is False


def test_filter_current_build_rows_applies_both_layers(bs, monkeypatch):
    monkeypatch.setattr(bs, "_get_current_account_id", lambda: "111")
    rows = [
        {"build_id": "BUILD_X", "account_id": "111", "date": "2026-08-25T00:00:00+00:00", "id": "keep"},
        {"build_id": "BUILD_X", "account_id": "999", "date": "2026-08-25T00:00:00+00:00", "id": "wrong_account"},
        {"build_id": "OLD", "account_id": "111", "date": "2026-08-25T00:00:00+00:00", "id": "wrong_build"},
    ]
    kept = bs.filter_current_build_rows(rows)
    assert [r["id"] for r in kept] == ["keep"]

# =============================================================================
# FER3ON-FIX-2026-08-21 — ACCOUNT SCOPE GUARD
# =============================================================================
"""
المشكلة اللي الملف ده بيحلها:

  core/build_scope.py بيحل مشكلة "بيانات من نسخة كود قديمة" عن طريق الفلترة
  وقت القراءة — من غير ما يحتاج يمسح حاجة، لأن السجلات (trades.csv,
  ai_memory.csv, trade_dna_v2.json) عبارة عن صفوف قابلة للفلترة بالـ build_id
  أو بالتاريخ.

  لكن فيه ملفات تانية مش "سجل صفوف" — هي عدّاد حالة واحد بيتغيّر حي وقت كل
  صفقة تتقفل (consecutive_losses في loss_pause_guard.json، total_trades/
  wins/losses في adaptive_state.json). الفلترة مش حل هنا؛ رقم واحد إما يمثّل
  الواقع الحالي أو لأ. الحل الوحيد الصحيح هو reset فعلي — لكن بس لما "الحساب"
  (مصدر الفلوس الحقيقي) يتغيّر فعلاً، مش كل مرة يتغيّر فيها الكود أو الـbuild.

  ده تحديدًا الفرق بين:
    - "نسخة كود جديدة على نفس الحساب"  -> build_scope.py (فلترة، بدون مسح)
    - "حساب MT5 جديد بالكامل"          -> account_scope.py (reset فعلي، هنا)

آلية العمل:
  1. عند كل startup، بنقرأ رقم حساب MT5 الحالي (mt5.account_info().login).
  2. بنقارنه بآخر رقم حساب مسجّل في data/analytics/account_fingerprint.json.
  3. لو الرقمين متطابقين -> مفيش أي فعل، الملفات تفضل زي ما هي.
  4. لو مختلفين (أو أول مرة) -> بنعمل أرشفة (نسخة محفوظة بتاريخ) ثم reset
     لـ loss_pause_guard.json وadaptive_state.json، وبنسجّل الرقم الجديد.
  5. لو الملفات already في حالتها الافتراضية (زي لو حد عمل reset يدوي قبل
     كده) -> بنسجّل الرقم من غير أرشفة زيادة عن الحاجة، عشان منكررش شغل.
  6. لو مفيش وصول لمعلومات الحساب أصلاً (MT5 مش متاح، أو stub بيئة اختبار)
     -> منعملش حاجة خالص. عدم اليقين مش سبب كافي لمسح حالة حقيقية.

مهم: الملف ده ميلمسش trades.csv / ai_memory.csv / mt5_trade_history.csv /
trade_dna_v2.json / kill_switch_state.json. الثلاثة الأول سجلات بيتفلتروا
بالـbuild_id وقت القراءة (build_scope.py) — مسحهم هيفقّد القدرة تتأكد إن أي
إصلاح شغال. والأخير (kill_switch_state.json) snapshot مُشتق بيتولّد من جديد
من _read_recent_trades() في كل مرة — إصلاحه الحقيقي هو فلترة تلك الدالة
نفسها بالـbuild_id (شوف core/strategy_kill_switch.py)، مش تصفير الملف.

التكامل:
  main.py بينادي ensure_account_scope() مرة واحدة بعد connect_mt5() وقبل
  sync_mt5_history()، في startup فقط — مش جوه اللوب.

  يشتغل برضو كـ CLI مستقل:
    python3 -m core.account_scope --status
    python3 -m core.account_scope --force
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.mt5_compat import MT5_AVAILABLE, mt5

FINGERPRINT_PATH = os.path.join("data", "analytics", "account_fingerprint.json")
ARCHIVE_DIR = os.path.join("data", "analytics", "account_archive")

LOSS_PAUSE_STATE_PATH = os.path.join("data", "memory", "loss_pause_guard.json")
ADAPTIVE_STATE_PATH = os.path.join("data", "analytics", "adaptive_state.json")

# نفس الشكل الافتراضي بالحرف زي core/loss_pause_guard.py::force_reset()،
# مكرر هنا فقط كـ fallback لو الاستيراد فشل — المصدر الحقيقي هو الاستيراد.
_LOSS_PAUSE_DEFAULT: Dict[str, Any] = {
    "consecutive_losses": 0,
    "last_loss_timestamp": 0.0,
    "last_loss_ticket": None,
    "pause_active": False,
    "pause_start_timestamp": 0.0,
    "last_signal_signature": "",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_current_account_login() -> Optional[int]:
    """
    رقم حساب MT5 الحالي، أو None لو مش متاح (MT5 غير متصل، أو stub بيئة
    اختبار مالوش .login أصلاً). محدّش يفترض إن None يعني "حساب جديد" —
    الاستدعاء الرئيسي بيتعامل مع None كـ "معرفش، متعملش حاجة".
    """
    if not MT5_AVAILABLE:
        return None
    try:
        account = mt5.account_info()
    except Exception:
        return None
    if account is None:
        return None
    login = getattr(account, "login", None)
    if login is None:
        return None
    try:
        return int(login)
    except (TypeError, ValueError):
        return None


_ACCOUNT_ID_CACHE: Dict[str, Any] = {"value": None, "resolved": False}


def get_cached_account_id() -> str:
    """
    [FER3ON-FIX-2026-08-28] نسخة مُخزَّنة (cached) من get_current_account_login()
    كـstring جاهز للكتابة المباشرة في صف CSV/JSON — الفرق عن النداء المباشر:

      - بتتصل بـMT5 مرة واحدة بس لكل عملية تشغيل، مش مرة لكل صف بيتكتب
        (log_trade/save_trade_memory/record_trade_dna بتتنادى مرات كتير).
      - بترجع "" (مش None) لو مش متاح، عشان تتكتب في CSV من غير مشاكل type.

    الكاش بيتصفّر تلقائيًا لو الحساب اتغيّر خلال نفس العملية (نادر جدًا في
    الواقع، لكن أرخص من مخاطرة قيمة قديمة) عن طريق ensure_account_scope()
    اللي بتنادي refresh_account_id_cache() عند أي reset حقيقي.
    """
    if not _ACCOUNT_ID_CACHE["resolved"]:
        login = get_current_account_login()
        _ACCOUNT_ID_CACHE["value"] = str(login) if login is not None else ""
        _ACCOUNT_ID_CACHE["resolved"] = True
    return _ACCOUNT_ID_CACHE["value"]


def refresh_account_id_cache() -> str:
    """يجبر إعادة قراءة رقم الحساب من MT5 بدل الاعتماد على الكاش."""
    _ACCOUNT_ID_CACHE["resolved"] = False
    return get_cached_account_id()


def _load_fingerprint() -> Optional[Dict[str, Any]]:
    try:
        with open(FINGERPRINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_fingerprint(login: int, *, previous_login: Optional[int] = None) -> None:
    os.makedirs(os.path.dirname(FINGERPRINT_PATH), exist_ok=True)
    payload = {
        "account_login": login,
        "previous_login": previous_login,
        "first_seen_at": _now_iso(),
        "last_checked_at": _now_iso(),
    }
    existing = _load_fingerprint()
    if existing and existing.get("account_login") == login:
        payload["first_seen_at"] = existing.get("first_seen_at", payload["first_seen_at"])
    tmp = FINGERPRINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FINGERPRINT_PATH)


def _touch_last_checked() -> None:
    fp = _load_fingerprint()
    if not fp:
        return
    fp["last_checked_at"] = _now_iso()
    tmp = FINGERPRINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fp, f, indent=2, ensure_ascii=False)
    os.replace(tmp, FINGERPRINT_PATH)


def _loss_pause_is_clean() -> bool:
    try:
        with open(LOSS_PAUSE_STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True  # مفيش ملف = مفيش حاجة تتصفّر
    return (
        int(d.get("consecutive_losses", 0) or 0) == 0
        and not bool(d.get("pause_active", False))
    )


def _adaptive_state_is_clean() -> bool:
    try:
        with open(ADAPTIVE_STATE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return True
    return int(d.get("total_trades", 0) or 0) == 0


def _archive(path: str, archive_subdir: str) -> Optional[str]:
    """ينسخ الملف (لو موجود) لمجلد أرشيف بدل ما يمسحه، ويرجّع مساره."""
    if not os.path.exists(path):
        return None
    os.makedirs(archive_subdir, exist_ok=True)
    dest = os.path.join(archive_subdir, os.path.basename(path))
    shutil.copy2(path, dest)
    return dest


def _reset_loss_pause_guard() -> Dict[str, Any]:
    try:
        from core.loss_pause_guard import force_reset  # مصدر الحقيقة الفعلي

        return force_reset()
    except Exception:
        # fallback فقط لو الاستيراد فشل لأي سبب — نفس الشكل بالحرف.
        os.makedirs(os.path.dirname(LOSS_PAUSE_STATE_PATH), exist_ok=True)
        with open(LOSS_PAUSE_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(_LOSS_PAUSE_DEFAULT, f, indent=2)
        return dict(_LOSS_PAUSE_DEFAULT)


def _reset_adaptive_state() -> None:
    # adaptive_learning.load_state() بيرجع DEFAULT_STATE تلقائيًا لو الملف
    # مش موجود — فمسح الملف هو الـreset الصحيح والمتوافق مع مصدر الحقيقة.
    if os.path.exists(ADAPTIVE_STATE_PATH):
        os.remove(ADAPTIVE_STATE_PATH)


def ensure_account_scope(force: bool = False) -> Dict[str, Any]:
    """
    نقطة الدخول الرئيسية. تُستدعى مرة واحدة عند startup بعد connect_mt5().

    Returns:
        dict فيه: action ('skipped_no_account' | 'no_change' | 'reset' |
        'recorded_only'), account_login, reason.
    """
    login = get_current_account_login()
    _ACCOUNT_ID_CACHE["value"] = str(login) if login is not None else ""
    _ACCOUNT_ID_CACHE["resolved"] = True

    if login is None and not force:
        return {
            "action": "skipped_no_account",
            "account_login": None,
            "reason": "MT5 account info unavailable — no destructive action taken.",
        }

    fingerprint = _load_fingerprint()
    previous_login = fingerprint.get("account_login") if fingerprint else None
    account_changed = (fingerprint is None) or (previous_login != login)

    if not account_changed and not force:
        _touch_last_checked()
        return {
            "action": "no_change",
            "account_login": login,
            "reason": f"Account {login} matches last known fingerprint; nothing to reset.",
        }

    already_clean = _loss_pause_is_clean() and _adaptive_state_is_clean()

    if already_clean and not force:
        _save_fingerprint(login if login is not None else -1, previous_login=previous_login)
        print(
            f"✅ ACCOUNT_SCOPE | account={login} | state already clean — "
            f"fingerprint recorded, no archive needed."
        )
        return {
            "action": "recorded_only",
            "account_login": login,
            "reason": "State files already at default values; recorded fingerprint only.",
        }

    stamp = _safe_stamp()
    archive_subdir = os.path.join(
        ARCHIVE_DIR, f"{previous_login if previous_login is not None else 'unknown'}_{stamp}"
    )
    archived = []
    for path in (LOSS_PAUSE_STATE_PATH, ADAPTIVE_STATE_PATH):
        dest = _archive(path, archive_subdir)
        if dest:
            archived.append(dest)

    _reset_loss_pause_guard()
    _reset_adaptive_state()
    _save_fingerprint(login if login is not None else -1, previous_login=previous_login)

    print(
        f"🔄 ACCOUNT_SCOPE_RESET | previous_account={previous_login} -> "
        f"new_account={login} | archived {len(archived)} file(s) to {archive_subdir} | "
        f"loss_pause_guard.json + adaptive_state.json reset to defaults."
    )
    return {
        "action": "reset",
        "account_login": login,
        "previous_login": previous_login,
        "archived_to": archive_subdir if archived else None,
        "reason": "New/changed MT5 account detected — stateful counters reset.",
    }


def force_reset_account_scope() -> Dict[str, Any]:
    """Reset صريح بغض النظر عن تطابق الحساب — للاستخدام اليدوي فقط."""
    return ensure_account_scope(force=True)


def get_status() -> Dict[str, Any]:
    login = get_current_account_login()
    fingerprint = _load_fingerprint()
    return {
        "current_account_login": login,
        "fingerprint": fingerprint,
        "loss_pause_clean": _loss_pause_is_clean(),
        "adaptive_state_clean": _adaptive_state_is_clean(),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FER3ON account-scope guard")
    parser.add_argument("--status", action="store_true", help="اعرض الحالة الحالية بدون تعديل")
    parser.add_argument("--force", action="store_true", help="نفّذ reset فوري بغض النظر عن الحساب")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(get_status(), indent=2, ensure_ascii=False, default=str))
    elif args.force:
        result = force_reset_account_scope()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        result = ensure_account_scope()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

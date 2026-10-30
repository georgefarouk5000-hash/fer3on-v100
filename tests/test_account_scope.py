"""
[FER3ON-FIX-2026-08-21] Tests for core/account_scope.py.

يغطي:
  - مفيش معلومات حساب (MT5 غير متاح) -> skip آمن، مفيش تعديل.
  - أول تشغيل وحالة "متسخة" (فيها صفقات حقيقية) -> أرشفة + reset.
  - أول تشغيل وحالة "نظيفة أصلاً" (زي بعد reset يدوي) -> تسجيل fingerprint
    بس، من غير أرشفة زيادة عن الحاجة.
  - نفس الحساب مرتين -> no-op في المرة التانية، حتى لو الملفات "اتسخت"
    بعد كده (لأن ده مش المفروض يحصل غير عبر صفقات حقيقية جديدة).
  - تغيير الحساب -> reset فعلي حتى لو المحتوى الحالي "حقيقي".
  - force=True -> reset دايمًا بغض النظر عن التطابق.

كل اختبار بيشتغل جوه tmp_path معزولة تمامًا (chdir)، ملوش أي علاقة
بالبيانات الحقيقية في data/.
"""

import importlib
import json
import os

import pytest


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """يبني هيكل data/ فاضي جوه tmp_path ويرجع موديول account_scope مستورد
    من جديد فوقه، عشان أي path نسبي جوه الموديول يشاور على tmp_path."""
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "data" / "memory", exist_ok=True)
    os.makedirs(tmp_path / "data" / "analytics", exist_ok=True)

    import core.account_scope as account_scope

    importlib.reload(account_scope)
    return account_scope


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class _FakeAccount:
    def __init__(self, login):
        self.login = login
        self.trade_mode = 0
        self.balance = 1000.0


class _FakeMT5:
    def __init__(self, login):
        self._login = login

    def account_info(self):
        if self._login is None:
            return None
        return _FakeAccount(self._login)


def _set_account(monkeypatch, module, login, available=True):
    monkeypatch.setattr(module, "MT5_AVAILABLE", available)
    monkeypatch.setattr(module, "mt5", _FakeMT5(login))


def test_no_account_info_skips_safely(isolated_project, monkeypatch):
    mod = isolated_project
    _write_json(
        mod.LOSS_PAUSE_STATE_PATH,
        {"consecutive_losses": 2, "pause_active": True, "last_loss_ticket": 999},
    )
    _set_account(monkeypatch, mod, login=None, available=False)

    result = mod.ensure_account_scope()

    assert result["action"] == "skipped_no_account"
    with open(mod.LOSS_PAUSE_STATE_PATH) as f:
        d = json.load(f)
    assert d["consecutive_losses"] == 2, "must not touch state when account is unknown"


def test_first_run_dirty_state_is_archived_and_reset(isolated_project, monkeypatch):
    mod = isolated_project
    _write_json(
        mod.LOSS_PAUSE_STATE_PATH,
        {
            "consecutive_losses": 2,
            "pause_active": True,
            "last_loss_ticket": 10091834050,
            "last_loss_timestamp": 123.0,
            "pause_start_timestamp": 123.0,
            "last_signal_signature": "NONE|BOS_UP|SELL",
        },
    )
    _write_json(mod.ADAPTIVE_STATE_PATH, {"total_trades": 1731, "wins": 900, "losses": 831})
    _set_account(monkeypatch, mod, login=555)

    result = mod.ensure_account_scope()

    assert result["action"] == "reset"
    assert result["archived_to"] is not None
    assert os.path.isdir(result["archived_to"]), "must preserve old state, not delete it silently"

    with open(mod.LOSS_PAUSE_STATE_PATH) as f:
        loss_pause = json.load(f)
    assert loss_pause["consecutive_losses"] == 0
    assert loss_pause["pause_active"] is False

    assert not os.path.exists(mod.ADAPTIVE_STATE_PATH), (
        "adaptive_learning.load_state() already returns DEFAULT_STATE when the "
        "file is missing, so removing it is the correct reset"
    )

    fp = mod._load_fingerprint()
    assert fp["account_login"] == 555


def test_first_run_already_clean_records_without_archiving(isolated_project, monkeypatch):
    mod = isolated_project
    _write_json(
        mod.LOSS_PAUSE_STATE_PATH,
        {
            "consecutive_losses": 0,
            "pause_active": False,
            "last_loss_ticket": None,
            "last_loss_timestamp": 0.0,
            "pause_start_timestamp": 0.0,
            "last_signal_signature": "",
        },
    )
    _set_account(monkeypatch, mod, login=777)

    result = mod.ensure_account_scope()

    assert result["action"] == "recorded_only"
    assert not os.path.isdir(mod.ARCHIVE_DIR), "nothing dirty -> nothing to archive"
    assert mod._load_fingerprint()["account_login"] == 777


def test_same_account_second_call_is_noop(isolated_project, monkeypatch):
    mod = isolated_project
    _set_account(monkeypatch, mod, login=111)
    first = mod.ensure_account_scope()
    assert first["action"] in ("reset", "recorded_only")

    # حاجة حقيقية حصلت على نفس الحساب — المفروض ما تتصفرش تاني
    _write_json(mod.LOSS_PAUSE_STATE_PATH, {"consecutive_losses": 1, "pause_active": False})

    second = mod.ensure_account_scope()

    assert second["action"] == "no_change"
    with open(mod.LOSS_PAUSE_STATE_PATH) as f:
        d = json.load(f)
    assert d["consecutive_losses"] == 1, "must not silently wipe real same-account progress"


def test_account_change_resets_even_real_looking_data(isolated_project, monkeypatch):
    mod = isolated_project
    _set_account(monkeypatch, mod, login=111)
    mod.ensure_account_scope()
    _write_json(
        mod.LOSS_PAUSE_STATE_PATH,
        {"consecutive_losses": 3, "pause_active": True, "last_loss_ticket": 42},
    )

    _set_account(monkeypatch, mod, login=222)
    result = mod.ensure_account_scope()

    assert result["action"] == "reset"
    assert result["previous_login"] == 111
    with open(mod.LOSS_PAUSE_STATE_PATH) as f:
        d = json.load(f)
    assert d["consecutive_losses"] == 0


def test_force_resets_even_when_account_matches(isolated_project, monkeypatch):
    mod = isolated_project
    _set_account(monkeypatch, mod, login=111)
    mod.ensure_account_scope()
    _write_json(mod.LOSS_PAUSE_STATE_PATH, {"consecutive_losses": 5, "pause_active": True})

    result = mod.force_reset_account_scope()

    assert result["action"] == "reset"
    with open(mod.LOSS_PAUSE_STATE_PATH) as f:
        d = json.load(f)
    assert d["consecutive_losses"] == 0

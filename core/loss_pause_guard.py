# =============================================================================
# FER3ON-AI-V3-SLTP-FIXED — LOSS PAUSE GUARD
# بعد N صفقات خاسرة متتالية — انتظر حتى يظهر CHoCH أو BOS جديد
# =============================================================================
"""
الفلسفة:
  - بعد 3 (LOSS_PAUSE_TRIGGER) صفقات خاسرة متتالية، نوقف التداول مؤقتاً.
  - لتجاوز الإيقاف، يجب أن يظهر:
      * CHoCH_BULLISH / CHoCH_BEARISH  (تغيّر الاتجاه)
      * BOS_UP / BOS_DOWN             (كسر هيكلي جديد)
  - بمجرد ظهور أي من هذه الإشارات، العدّاد ينصفر ويُسمح بالتداول.
  - يعمل فقط في regimes: RANGING و VOLATILE (في CRISIS بالفعل hard_stop).

التكامل:
  - يُستدعى من main.py قبل تنفيذ أي صفقة.
  - يستخدم get_market_structure() و detect_choch/detect_real_bos().
"""

from __future__ import annotations

import json
import os
import time
import threading
from typing import Optional


try:
    from core.settings import (
        LOSS_PAUSE_ENABLED,
        LOSS_PAUSE_TRIGGER,
        LOSS_PAUSE_REQUIRE_FRESH,
        LOSS_PAUSE_REQUIRE_REGIME,
        LOSS_PAUSE_COOLDOWN_SEC,
    )
except Exception:  # fallback when import fails
    LOSS_PAUSE_ENABLED = True
    LOSS_PAUSE_TRIGGER = 3
    LOSS_PAUSE_REQUIRE_FRESH = True
    LOSS_PAUSE_REQUIRE_REGIME = ('RANGING', 'VOLATILE')
    LOSS_PAUSE_COOLDOWN_SEC = 0


# مسار التخزين الدائم لحالة الـ guard
_STATE_PATH = os.path.join('data', 'memory', 'loss_pause_guard.json')

# HIGH FIX #8: Thread-safe pause guard — prevent race when SMC & runners
# both check evaluate_loss_pause() and decide to activate pause simultaneously
_pause_guard_lock = threading.RLock()


def _ensure_state_dir() -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    except Exception:
        pass


def _load_state() -> dict:
    _ensure_state_dir()
    if not os.path.exists(_STATE_PATH):
        return {
            'consecutive_losses': 0,
            'last_loss_timestamp': 0.0,
            'last_loss_ticket': None,
            'pause_active': False,
            'pause_start_timestamp': 0.0,
            'last_signal_signature': '',
            'pause_signal_baseline_captured': False,
        }
    try:
        with open(_STATE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('state not dict')
        # make sure keys exist
        return {
            'consecutive_losses': int(data.get('consecutive_losses', 0) or 0),
            'last_loss_timestamp': float(data.get('last_loss_timestamp', 0.0) or 0.0),
            'last_loss_ticket': data.get('last_loss_ticket'),
            'pause_active': bool(data.get('pause_active', False)),
            'pause_start_timestamp': float(data.get('pause_start_timestamp', 0.0) or 0.0),
            'last_signal_signature': str(data.get('last_signal_signature', '') or ''),
            'pause_signal_baseline_captured': bool(
                data.get('pause_signal_baseline_captured', False)
            ),
        }
    except Exception:
        return {
            'consecutive_losses': 0,
            'last_loss_timestamp': 0.0,
            'last_loss_ticket': None,
            'pause_active': False,
            'pause_start_timestamp': 0.0,
            'last_signal_signature': '',
            'pause_signal_baseline_captured': False,
        }


def _save_state(state: dict) -> None:
    _ensure_state_dir()
    try:
        with open(_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        print(f'⚠️ LOSS_PAUSE_GUARD: failed to persist state: {exc}')


def _fetch_choch_bos(snapshot_or_symbol) -> dict:
    """
    استخراج حالة CHoCH/BOS من snapshot الممرّر أو fetch جديد.

    Returns:
      {
        'choch': 'BULLISH' | 'BEARISH' | 'NONE',
        'bos':   'UP' | 'DOWN' | 'NONE',
        'signature': str — hash مركّب للإشارة الحالية،
        'found': bool — هل signature تغير عن المخزّن؟
      }
    """
    try:
        # Case 1: snapshot dict already containing structure info
        if isinstance(snapshot_or_symbol, dict):
            structure = snapshot_or_symbol.get('structure') or {}
            structure_analysis = snapshot_or_symbol.get('structure_analysis') or {}
            choch = (
                structure_analysis.get('choch')
                or structure.get('choch_h1')
                or structure.get('choch_h4')
                or snapshot_or_symbol.get('choch_state')
                or 'NONE'
            )
            bos = (
                structure_analysis.get('bos')
                or structure.get('bos_h1')
                or structure.get('bos_h4')
                or snapshot_or_symbol.get('bos_state')
                or 'NONE'
            )
            bias = structure.get('bias') or snapshot_or_symbol.get('signal') or 'NEUTRAL'
            signal = snapshot_or_symbol.get('signal') or bias
            signature = f'{choch}|{bos}|{bias}'
            return {
                'choch': str(choch).upper(),
                'bos': str(bos).upper(),
                'bias': str(bias).upper(),
                'signal': str(signal).upper(),
                'signature': signature,
                'found': True,
            }

        # Case 2: symbol string → fetch from market_structure & choch_engine
        from core.choch_engine import detect_choch, detect_real_bos
        from core.market_structure import get_market_structure
        from core.mt5_compat import mt5

        structure = get_market_structure(snapshot_or_symbol)
        rates = mt5.copy_rates_from_pos(snapshot_or_symbol, mt5.TIMEFRAME_M15, 0, 60)
        rates = rates if rates is not None and len(rates) > 20 else None

        choch = 'NONE'
        bos = 'NONE'
        if rates is not None:
            try:
                ch_type, _, _ = detect_choch(rates)
                if ch_type:
                    choch = ch_type  # CHOCH_BULLISH | CHOCH_BEARISH | NONE
            except Exception:
                pass
            try:
                b_type, _, _ = detect_real_bos(rates)
                if b_type:
                    bos = b_type  # BOS_UP | BOS_DOWN | NONE
            except Exception:
                pass

        bias = structure.get('bias') if isinstance(structure, dict) else 'NEUTRAL'
        signature = f'{choch}|{bos}|{bias}'
        return {
            'choch': str(choch).upper(),
            'bos': str(bos).upper(),
            'bias': str(bias).upper() if bias else 'NEUTRAL',
            'signal': 'NONE',
            'signature': signature,
            'found': True,
        }
    except Exception as exc:
        print(f'⚠️ LOSS_PAUSE_GUARD: fetch_choch_bos failed: {exc}')
        return {
            'choch': 'NONE',
            'bos': 'NONE',
            'bias': 'NEUTRAL',
            'signal': 'NONE',
            'signature': '',
            'found': False,
        }


def register_trade_result(trade_result: str, ticket: Optional[int] = None,
                           profit: float = 0.0) -> dict:
    """
    تحديث العدّاد بعد إغلاق صفقة.

    Args:
      trade_result: 'WIN' | 'LOSS' | 'OPEN' | 'BREAKEVEN' | غير ذلك
      ticket: رقم التذكرة (للتسجيل فقط)
      profit: ربح الصفقة (سالب = خسارة)

    Returns:
      dict الحالة الجديدة.
    """
    state = _load_state()

    if trade_result == 'LOSS' or (profit is not None and float(profit) < 0):
        state['consecutive_losses'] = int(state.get('consecutive_losses', 0)) + 1
        state['last_loss_timestamp'] = float(time.time())
        state['last_loss_ticket'] = int(ticket) if ticket else None
        print(
            f'🛡 LOSS_PAUSE_GUARD | consequential LOSS #{state["consecutive_losses"]} '
            f'(ticket={ticket}, profit={profit})'
        )
        # هل يجب تشغيل الإيقاف؟
        if LOSS_PAUSE_ENABLED and state['consecutive_losses'] >= LOSS_PAUSE_TRIGGER:
            if not state.get('pause_active'):
                state['pause_active'] = True
                state['pause_start_timestamp'] = float(time.time())
                state['last_signal_signature'] = ''
                state['pause_signal_baseline_captured'] = False
                print(
                    f'🛑 LOSS_PAUSE_GUARD ACTIVATED | {state["consecutive_losses"]} consecutive losses.\n'
                    f'    ⏸ Will resume ONLY after a fresh CHoCH or BOS appears.\n'
                    f'    Configured regimes: {LOSS_PAUSE_REQUIRE_REGIME}'
                )
    elif trade_result == 'WIN' or (profit is not None and float(profit) > 0):
        # فوز → تصفير العدّاد وإلغاء الإيقاف فوراً
        if state['consecutive_losses'] > 0 or state.get('pause_active'):
            print(
                f'✅ LOSS_PAUSE_GUARD | WIN resets streak '
                f'(was {state["consecutive_losses"]} losses, pause={state.get("pause_active")})'
            )
        state['consecutive_losses'] = 0
        state['pause_active'] = False
        state['pause_start_timestamp'] = 0.0
        state['last_signal_signature'] = ''
        state['pause_signal_baseline_captured'] = False
    # BREAKEVEN و OPEN لا تغيّر العدّاد

    _save_state(state)
    return state


# =========================================================================
# الفحص الرئيسي — يُستدعى قبل كل صفقة
# =========================================================================


def evaluate_loss_pause(snapshot_or_symbol, market_regime: Optional[str] = None) -> dict:
    """
    فحص ما إذا كان التداول مسموحاً الآن.

    HIGH FIX #8: Protected by _pause_guard_lock to prevent race conditions
    when concurrent evaluations activate/update pause state.

    Returns:
      {
        'trading_allowed': bool,
        'reason': str,
        'state': dict,
        'fresh_signal_detected': bool,
        'consecutive_losses': int,
        'regime_active_for_pause': bool,
      }
    """
    with _pause_guard_lock:  # HIGH FIX #8: Lock entire evaluation
        return _evaluate_loss_pause_impl(snapshot_or_symbol, market_regime)


def _evaluate_loss_pause_impl(snapshot_or_symbol, market_regime: Optional[str] = None) -> dict:
    """Implementation of loss pause evaluation. MUST be called under _pause_guard_lock."""
    if not LOSS_PAUSE_ENABLED:
        return {
            'trading_allowed': True,
            'reason': 'LOSS_PAUSE_DISABLED',
            'state': _load_state(),
            'fresh_signal_detected': False,
            'consecutive_losses': 0,
            'regime_active_for_pause': False,
        }

    state = _load_state()
    consecutive = int(state.get('consecutive_losses', 0) or 0)
    pause_active = bool(state.get('pause_active', False))

    # (1) هل regime الحالي ضمن القائمة المسموحة لتشغيل الإيقاف؟
    regime_norm = str(market_regime or '').upper() if market_regime else ''
    regime_active_for_pause = regime_norm in {str(r).upper() for r in LOSS_PAUSE_REQUIRE_REGIME}
    # (2) إذا العداد لم يصل للـ trigger → التداول مسموح
    if consecutive < LOSS_PAUSE_TRIGGER and not pause_active:
        return {
            'trading_allowed': True,
            'reason': 'BELOW_THRESHOLD',
            'state': state,
            'fresh_signal_detected': False,
            'consecutive_losses': consecutive,
            'regime_active_for_pause': regime_active_for_pause,
        }

    # (3) وصلنا أو تجاوزنا trigger → فعّل الإيقاف إذا لم يكن مفعّلاً
    if not pause_active:
        state['pause_active'] = True
        state['pause_start_timestamp'] = float(time.time())
        state['last_signal_signature'] = ''
        state['pause_signal_baseline_captured'] = False
        _save_state(state)
        pause_active = True
        print(
            f'🛑 LOSS_PAUSE_GUARD ACTIVATED | {consecutive} consecutive losses ≥ '
            f'{LOSS_PAUSE_TRIGGER}. Awaiting fresh CHoCH/BOS.'
        )

    # (4) الإيقاف مفعّل → فحص إشارة جديدة
    market_info = _fetch_choch_bos(snapshot_or_symbol)
    current_signature = str(market_info.get('signature', ''))
    last_signature = str(state.get('last_signal_signature', ''))
    cooldown_left = max(
        0,
        int(
            LOSS_PAUSE_COOLDOWN_SEC
            - (time.time() - float(state.get('pause_start_timestamp', 0) or 0))
        ),
    ) if LOSS_PAUSE_COOLDOWN_SEC > 0 else 0

    fresh_signal_detected = False
    has_bullish = 'BULLISH' in market_info.get('choch', '') or 'UP' in market_info.get('bos', '')
    has_bearish = 'BEARISH' in market_info.get('choch', '') or 'DOWN' in market_info.get('bos', '')

    if LOSS_PAUSE_REQUIRE_FRESH:
        if not state.get('pause_signal_baseline_captured', False):
            state['last_signal_signature'] = current_signature
            state['pause_signal_baseline_captured'] = True
            last_signature = current_signature
            _save_state(state)
        if (
            cooldown_left == 0
            and current_signature
            and current_signature != last_signature
            and (has_bullish or has_bearish)
        ):
            fresh_signal_detected = True
    else:
        # فقط وجود أي CHoCH/BOS كافٍ
        fresh_signal_detected = has_bullish or has_bearish

    if fresh_signal_detected and cooldown_left == 0:
        # إشارة جديدة ظهرت → نسمح بالتداول ونصفر الحالة
        print(
            f'✅ LOSS_PAUSE_GUARD LIFTED | fresh signal detected: '
            f'choch={market_info.get("choch")} bos={market_info.get("bos")} '
            f'bias={market_info.get("bias")} (was {consecutive}L)'
        )
        state['consecutive_losses'] = 0
        state['pause_active'] = False
        state['pause_start_timestamp'] = 0.0
        state['last_signal_signature'] = current_signature
        state['pause_signal_baseline_captured'] = False
        _save_state(state)
        return {
            'trading_allowed': True,
            'reason': 'FRESH_CHOCH_OR_BOS',
            'state': state,
            'fresh_signal_detected': True,
            'consecutive_losses': 0,
            'regime_active_for_pause': regime_active_for_pause,
        }

    # (5) لا إشارة جديدة حتى الآن → الإيقاف مستمر
    reason = (
        f'AWAITING_FRESH_CHOCH_OR_BOS | '
        f'consecutive_losses={consecutive} choch={market_info.get("choch")} '
        f'bos={market_info.get("bos")} cooldown_left={cooldown_left}s'
    )
    print(f'⏸ LOSS_PAUSE_GUARD BLOCKED | {reason}')
    return {
        'trading_allowed': False,
        'reason': reason,
        'state': state,
        'fresh_signal_detected': False,
        'consecutive_losses': consecutive,
        'regime_active_for_pause': regime_active_for_pause,
        'market_info': market_info,
    }


def force_reset() -> dict:
    """
    مسح حالة الإيقاف يدوياً (للأدوات والاختبار).
    """
    state = {
        'consecutive_losses': 0,
        'last_loss_timestamp': 0.0,
        'last_loss_ticket': None,
        'pause_active': False,
        'pause_start_timestamp': 0.0,
        'last_signal_signature': '',
        'pause_signal_baseline_captured': False,
    }
    _save_state(state)
    print('🧹 LOSS_PAUSE_GUARD | manual reset done.')
    return state


def get_status() -> dict:
    """قراءة الحالة الحالية بدون تعديل."""
    state = _load_state()
    return {
        'enabled': bool(LOSS_PAUSE_ENABLED),
        'trigger': int(LOSS_PAUSE_TRIGGER),
        'consecutive_losses': int(state.get('consecutive_losses', 0) or 0),
        'pause_active': bool(state.get('pause_active', False)),
        'last_loss_timestamp': float(state.get('last_loss_timestamp', 0.0) or 0.0),
        'last_signal_signature': state.get('last_signal_signature', ''),
        'regimes': list(LOSS_PAUSE_REQUIRE_REGIME),
    }

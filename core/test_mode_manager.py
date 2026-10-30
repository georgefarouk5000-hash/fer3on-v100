from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.settings import TESTING_MODE, TESTING_MODE_LOT_CAPS, MAX_DAILY_TRADES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = PROJECT_ROOT / 'data' / 'analytics' / 'test_mode_state.json'

# =============================================================================
# FIXED: 80 صفقة يومياً بدل 8 - مُفتّح بالكامل للتداول الكثيف
# =============================================================================

MAX_MICRO = 60
MAX_REDUCED = 30
MAX_FULL = 20
MAX_TOTAL = MAX_DAILY_TRADES  # 80

# Lot caps من settings
MICRO_LOT_CAP = TESTING_MODE_LOT_CAPS.get('MICRO', 0.05)
REDUCED_LOT_CAP = TESTING_MODE_LOT_CAPS.get('REDUCED', 0.10)
FULL_LOT_CAP = TESTING_MODE_LOT_CAPS.get('FULL', 0.20)

NORMAL_LOT = MICRO_LOT_CAP


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _default_state() -> Dict[str, Any]:
    return {
        'date': _utc_day(),
        'used_micro': 0,
        'used_reduced': 0,
        'used_full': 0,
        'used_total': 0,
        'remaining_micro': MAX_MICRO,
        'remaining_reduced': MAX_REDUCED,
        'remaining_full': MAX_FULL,
        'remaining_total': MAX_TOTAL,
        'daily_max_trades': MAX_TOTAL,
        'micro_lot_cap': MICRO_LOT_CAP,
        'reduced_lot_cap': REDUCED_LOT_CAP,
        'full_lot_cap': FULL_LOT_CAP,
        'testing_mode': bool(TESTING_MODE),
    }


def _sync_totals(state: Dict[str, Any]) -> Dict[str, Any]:
    state['used_micro'] = int(state.get('used_micro', 0) or 0)
    state['used_reduced'] = int(state.get('used_reduced', 0) or 0)
    state['used_full'] = int(state.get('used_full', 0) or 0)
    state['used_total'] = int(state.get('used_total', 0) or 0)
    state['remaining_micro'] = max(0, MAX_MICRO - state['used_micro'])
    state['remaining_reduced'] = max(0, MAX_REDUCED - state['used_reduced'])
    state['remaining_full'] = max(0, MAX_FULL - state['used_full'])
    state['remaining_total'] = max(0, MAX_TOTAL - state['used_total'])
    state['daily_max_trades'] = MAX_TOTAL
    state['micro_lot_cap'] = MICRO_LOT_CAP
    state['reduced_lot_cap'] = REDUCED_LOT_CAP
    state['full_lot_cap'] = FULL_LOT_CAP
    state['testing_mode'] = bool(TESTING_MODE)
    return state


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return _default_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        if str(data.get('date', '')) != _utc_day():
            return _default_state()
        return _sync_totals(data)
    except Exception:
        return _default_state()


def save_state(state: Dict[str, Any]) -> Dict[str, Any]:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    synced = _sync_totals(dict(state))
    STATE_FILE.write_text(json.dumps(synced, ensure_ascii=False, indent=2), encoding='utf-8')
    return synced


def get_quota_state() -> Dict[str, Any]:
    return save_state(load_state())


def planned_lot_for_mode(size_mode: str | None = None) -> float:
    mode = str(size_mode or 'NORMAL').upper()
    if mode == 'MICRO':
        return MICRO_LOT_CAP
    elif mode == 'REDUCED':
        return REDUCED_LOT_CAP
    elif mode == 'FULL':
        return FULL_LOT_CAP
    return NORMAL_LOT


def classify_bucket(*, lot: float | None = None, size_mode: str | None = None) -> str:
    mode = str(size_mode or '').upper()
    if mode == 'MICRO':
        return 'micro'
    if mode == 'REDUCED':
        return 'reduced'
    if mode == 'FULL':
        return 'full'
    if lot is not None and float(lot or 0) <= 0.015:
        return 'micro'
    return 'reduced'


def can_allocate(*, lot: float | None = None, size_mode: str | None = None) -> Dict[str, Any]:
    state = get_quota_state()
    if not TESTING_MODE:
        return {
            'allowed': True,
            'reason': 'TEST_MODE_DISABLED',
            'bucket': classify_bucket(lot=lot, size_mode=size_mode),
            'planned_lot': float(lot or planned_lot_for_mode(size_mode)),
            'state': state,
        }

    bucket = classify_bucket(lot=lot, size_mode=size_mode)

    if state['used_total'] >= MAX_TOTAL:
        return {
            'allowed': False,
            'reason': 'TEST_MODE_DAILY_LIMIT_REACHED',
            'bucket': bucket,
            'planned_lot': planned_lot_for_mode(size_mode),
            'state': state,
        }

    if bucket == 'micro' and state['used_micro'] >= MAX_MICRO:
        return {
            'allowed': False,
            'reason': 'TEST_MODE_MICRO_LIMIT_REACHED',
            'bucket': bucket,
            'planned_lot': MICRO_LOT_CAP,
            'state': state,
        }

    if bucket == 'reduced' and state['used_reduced'] >= MAX_REDUCED:
        return {
            'allowed': False,
            'reason': 'TEST_MODE_REDUCED_LIMIT_REACHED',
            'bucket': bucket,
            'planned_lot': REDUCED_LOT_CAP,
            'state': state,
        }

    if bucket == 'full' and state['used_full'] >= MAX_FULL:
        return {
            'allowed': False,
            'reason': 'TEST_MODE_FULL_LIMIT_REACHED',
            'bucket': bucket,
            'planned_lot': FULL_LOT_CAP,
            'state': state,
        }

    return {
        'allowed': True,
        'reason': 'TEST_MODE_QUOTA_OK',
        'bucket': bucket,
        'planned_lot': planned_lot_for_mode(size_mode),
        'state': state,
    }


def register_trade(*, lot: float | None = None, size_mode: str | None = None) -> Dict[str, Any]:
    quota = can_allocate(lot=lot, size_mode=size_mode)
    if not quota['allowed']:
        return quota
    state = dict(quota['state'])
    bucket = quota['bucket']
    state['used_total'] = int(state.get('used_total', 0)) + 1
    if bucket == 'micro':
        state['used_micro'] = int(state.get('used_micro', 0)) + 1
    elif bucket == 'reduced':
        state['used_reduced'] = int(state.get('used_reduced', 0)) + 1
    else:
        state['used_full'] = int(state.get('used_full', 0)) + 1
    return {
        'allowed': True,
        'reason': 'TEST_MODE_REGISTERED',
        'bucket': bucket,
        'planned_lot': quota['planned_lot'],
        'state': save_state(state),
    }
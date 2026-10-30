from __future__ import annotations

from typing import Dict, Optional

from core.settings import (
    DAILY_MAGIC,
    SMC_MAGIC,
    RECOVERY_MAGIC,
    SURVIVAL_MAGIC,
)


STRATEGY_TO_MAGIC = {
    "DAILY": int(DAILY_MAGIC),
    "SMC": int(SMC_MAGIC),
    # AUDIT FIX: registered so magic_from_strategy()/resolve_trade_identity()
    # resolve these correctly if any of the orphaned RECOVERY/SURVIVAL
    # modules is ever wired into a live entry path -- see core/settings.py's
    # MAGIC NUMBERS section for the full rationale.
    "RECOVERY": int(RECOVERY_MAGIC),
    "SURVIVAL": int(SURVIVAL_MAGIC),
}

LEGACY_MAGIC_TO_STRATEGY = {
    1001: "SCALP",
    3001: "SWING",
    5001: "MICRO",
    100000: "SMC",  # legacy sample/runtime magic detected in current codebase
}

MAGIC_TO_STRATEGY = {v: k for k, v in STRATEGY_TO_MAGIC.items()}
MAGIC_TO_STRATEGY.update(LEGACY_MAGIC_TO_STRATEGY)


def normalize_strategy(strategy: Optional[str]) -> str:
    return str(strategy or "UNKNOWN").strip().upper()


def strategy_from_magic(magic: Optional[int], default: str = "UNKNOWN") -> str:
    try:
        key = int(magic)
    except Exception:
        return normalize_strategy(default)
    return MAGIC_TO_STRATEGY.get(key, normalize_strategy(default))


def magic_from_strategy(strategy: Optional[str], fallback: Optional[int] = None) -> int:
    normalized = normalize_strategy(strategy)
    if normalized in STRATEGY_TO_MAGIC:
        return STRATEGY_TO_MAGIC[normalized]
    try:
        return int(fallback) if fallback is not None else 0
    except Exception:
        return 0


def resolve_trade_identity(strategy: Optional[str] = None, magic: Optional[int] = None) -> Dict[str, object]:
    normalized_strategy = normalize_strategy(strategy)
    try:
        raw_magic = int(magic) if magic is not None else 0
    except Exception:
        raw_magic = 0

    inferred_strategy = strategy_from_magic(raw_magic, default=normalized_strategy)
    canonical_strategy = inferred_strategy if inferred_strategy != "UNKNOWN" else normalized_strategy
    canonical_magic = magic_from_strategy(canonical_strategy, fallback=raw_magic)

    return {
        "strategy": canonical_strategy,
        "magic": canonical_magic,
        "raw_magic": raw_magic,
        "magic_mismatch": bool(raw_magic and canonical_magic and raw_magic != canonical_magic),
        "legacy_magic": raw_magic in LEGACY_MAGIC_TO_STRATEGY,
    }

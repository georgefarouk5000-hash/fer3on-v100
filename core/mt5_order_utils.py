# =========================================
# FER3ON V3 — MT5 ORDER UTILITIES
# Comment sanitization + Filling-Fallback (P2-B)
# Source: V2.2 INVALID + V2.2 OPERATIONAL (merged)
# =========================================

from core.mt5_compat import mt5


MT5_COMMENT_MAX_LEN = 30
DEFAULT_COMMENT = "FER3ON"


# =========================================
# FILLING FALLBACK  (من V2.2 INVALID — P2-B)
# =========================================


def get_default_market_filling() -> int:
    """Use a safe default request filling mode instead of raw symbol_info.filling_mode."""
    return int(getattr(mt5, "ORDER_FILLING_IOC", 1))


def get_filling_fallback_sequence(current=None):
    """Return unique filling modes to try in broker-safe order."""
    candidates = [
        current,
        getattr(mt5, "ORDER_FILLING_IOC", None),
        getattr(mt5, "ORDER_FILLING_FOK", None),
        getattr(mt5, "ORDER_FILLING_RETURN", None),
    ]
    ordered = []
    for value in candidates:
        if value is None:
            continue
        try:
            value = int(value)
        except Exception:
            continue
        if value not in ordered:
            ordered.append(value)
    return ordered or [1]


# =========================================
# COMMENT SANITIZATION (من OPERATIONAL — لم يتغير)
# =========================================


def sanitize_mt5_comment(comment: str) -> str:
    """
    MT5 brokers usually limit comment length.
    Keep only safe ASCII characters and max 30 chars.
    """
    if comment is None:
        return DEFAULT_COMMENT

    comment = str(comment)

    allowed = []
    for c in comment:
        if c.isalnum() or c in "_-":
            allowed.append(c)

    comment = "".join(allowed)

    if len(comment) > MT5_COMMENT_MAX_LEN:
        comment = comment[:MT5_COMMENT_MAX_LEN]

    return comment or DEFAULT_COMMENT


def build_compact_order_comment(strategy, exec_grade="B"):
    """
    Compact MT5 comment for active strategies, such as F6_SMC_A.
    """
    strat = str(strategy or "UNK").upper()[:6]
    grade = str(exec_grade or "B").upper()
    grade = grade.replace("ELITE", "E").replace("+", "P")[:2]
    return sanitize_mt5_comment(f"F6_{strat}_{grade}")


def prepare_order_comment(request):
    """Sanitize comment on an MT5 request dict in-place; return request."""
    raw = request.get("comment", DEFAULT_COMMENT)
    request["comment"] = sanitize_mt5_comment(raw)
    if len(request["comment"]) > MT5_COMMENT_MAX_LEN:
        request["comment"] = request["comment"][:MT5_COMMENT_MAX_LEN]
    return request

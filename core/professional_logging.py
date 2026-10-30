import builtins
from datetime import datetime, timezone

_LOG_MODE = "PRODUCTION"
_ORIGINAL_PRINT = builtins.print
_FILTER_INSTALLED = False

_ALLOWED_KEYWORDS = {
    "SYSTEM HEALTH", "SESSION", "REGIME", "ACTIVE STRATEGIES", "POSITIONS",
    "CURRENT RISK", "CURRENT PNL", "CRITICAL EVENTS", "ERRORS", "STATUS",
    "ENTRY", "EXIT", "ERROR", "REGIME CHANGE", "RISK EVENT", "ML FAILURE",
    "WATCHDOG EVENT", "FER3ON", "STARTUP", "SYSTEM_READY", "SYSTEM_BLOCKED",
    "READY", "BLOCKED", "TRADE EXECUTED", "EXECUTION FAILED", "ORDER REQUEST"
}
_SUPPRESSED_HINTS = {"ATR", "RSI", "EMA", "FEATURE", "DUPLICATE", "CONFIRMATION", "INDICATOR", "VECTOR"}


def configure_logging(mode="PRODUCTION"):
    global _LOG_MODE
    _LOG_MODE = (mode or "PRODUCTION").upper()
    return _LOG_MODE


def _should_emit_message(message: str, level: str = "INFO") -> bool:
    if _LOG_MODE == "DEBUG":
        return True
    level = (level or "INFO").upper()
    if level in {"ERROR", "CRITICAL", "WARNING"}:
        return True
    message_upper = str(message or "").upper()
    if any(keyword in message_upper for keyword in _ALLOWED_KEYWORDS):
        return True
    if any(hint in message_upper for hint in _SUPPRESSED_HINTS):
        return False
    return False


def install_print_filter(force=False):
    global _FILTER_INSTALLED
    if _FILTER_INSTALLED and not force:
        return False

    def filtered_print(*args, **kwargs):
        if _LOG_MODE == "DEBUG":
            return _ORIGINAL_PRINT(*args, **kwargs)
        message = " ".join(str(a) for a in args)
        if _should_emit_message(message):
            return _ORIGINAL_PRINT(*args, **kwargs)
        return None

    builtins.print = filtered_print
    _FILTER_INSTALLED = True
    return True


def log_system_event(message, level="INFO"):
    level = (level or "INFO").upper()
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{timestamp}][{level}] {message}"
    if _should_emit_message(line, level=level):
        _ORIGINAL_PRINT(line)


def format_status_line(label, value):
    return f"{label}: {value}"

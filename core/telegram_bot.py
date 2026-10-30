import os
import time
import requests

try:
    from dotenv import load_dotenv
except ImportError:  # dependency is optional at runtime if env vars are already set
    def load_dotenv(*args, **kwargs):
        return False

# =========================================
# LOAD ENV
# =========================================

load_dotenv("config.env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("TELEGRAM_TOKEN", "")).strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
BASE_URL = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""
_HEALTH_CACHE_SECONDS = 300
_health_cache = None
_health_checked_at = 0.0


def _telegram_ready():
    return bool(TOKEN and CHAT_ID and BASE_URL)


def check_telegram_health():
    """Return a cached Telegram API health result; probe at most every five minutes."""
    global _health_cache, _health_checked_at
    now = time.monotonic()
    if _health_cache is not None and now - _health_checked_at < _HEALTH_CACHE_SECONDS:
        return dict(_health_cache)

    if not TOKEN or not BASE_URL:
        result = {
            "available": False,
            "latency_ms": None,
            "status": "NOT_CONFIGURED",
        }
    else:
        started = time.monotonic()
        try:
            response = requests.get(f"{BASE_URL}/getMe", timeout=3)
            response.raise_for_status()
            payload = response.json()
            bot_info = payload.get("result") if isinstance(payload, dict) else None
            available = (
                isinstance(payload, dict)
                and payload.get("ok") is True
                and isinstance(bot_info, dict)
                and bot_info.get("is_bot") is True
            )
            result = {
                "available": available,
                "latency_ms": (time.monotonic() - started) * 1000,
                "status": "HEALTHY" if available else "INVALID_RESPONSE",
            }
        except (requests.RequestException, ValueError):
            result = {
                "available": False,
                "latency_ms": (time.monotonic() - started) * 1000,
                "status": "REQUEST_FAILED",
            }

    _health_cache = result
    _health_checked_at = time.monotonic()
    return dict(result)


# =========================================
# SEND MESSAGE
# =========================================

def send_telegram_message(message):
    if not _telegram_ready():
        print("ℹ️ Telegram skipped: credentials not configured")
        return False

    try:
        url = f"{BASE_URL}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": str(message)}
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as error:
        print(f"❌ Telegram Error: {error}")
        return False


# =========================================
# GET LAST COMMAND
# =========================================

def get_last_command(last_update_id):
    if not _telegram_ready():
        return None, last_update_id

    try:
        params = {"timeout": 5}
        if last_update_id is not None:
            params["offset"] = last_update_id

        response = requests.get(
            f"{BASE_URL}/getUpdates",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or not data.get("ok"):
            return None, last_update_id

        results = data.get("result", [])
        if not results:
            return None, last_update_id

        last = results[-1]
        update_id = last.get("update_id", last_update_id)
        message = last.get("message", {})
        text = message.get("text")
        return text, update_id + 1

    except Exception as error:
        print(f"❌ Telegram Polling Error: {error}")
        return None, last_update_id


# V5.1 Command handlers (تُستدعى من main.py)
# /choch   → get_full_structure_analysis
# /liqmap  → build_liquidity_map
# /weights → get_adaptive_weights
# /adapt   → run_adaptive_weighting(force=True)

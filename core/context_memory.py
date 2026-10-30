# =========================================
# FER3ON V4.5 — CONTEXT MEMORY
# يحفظ أداء كل سياق ويعطي نقاط تعديل
# Context = Session + Signal + Regime + ATR_Bucket
# =========================================

import json
import os

from core.settings import (
    MEMORY_DIR,
    CONTEXT_MIN_TRADES,
    CONTEXT_GOOD_WR,
    CONTEXT_OK_WR,
    CONTEXT_BAD_WR,
    CONTEXT_POOR_WR
)


class ContextMemory:

    def __init__(self):
        self._path = os.path.join(
            MEMORY_DIR, "context_memory.json"
        )
        self._data = {}
        self._load()

    # =========================================
    # KEY BUILDER
    # =========================================

    def _key(self, session, signal, regime, atr, strategy="UNKNOWN"):
        bucket = (
            "low"  if atr < 5  else
            "high" if atr > 12 else
            "mid"
        )
        return f"{str(strategy or 'UNKNOWN').upper()}|{session}|{signal}|{regime}|{bucket}"

    # =========================================
    # GET SCORE ADJUSTMENT (-10 → +10)
    # =========================================

    def get_score(self, session, signal, regime, atr, strategy="UNKNOWN"):
        """
        يعيد تعديل النقاط بناءً على الأداء التاريخي.
        القيمة: -10 إلى +10 (تُضاف لـ quality_score)
        """
        key   = self._key(session, signal, regime, atr, strategy)
        entry = self._data.get(key)

        if not entry:
            return 0

        total = entry.get("wins", 0) + entry.get("losses", 0)

        if total < CONTEXT_MIN_TRADES:
            return 0   # بيانات غير كافية

        winrate = entry["wins"] / total

        if winrate >= CONTEXT_GOOD_WR:    # 0.75+
            adj = +10
        elif winrate >= CONTEXT_OK_WR:    # 0.60+
            adj = +5
        elif winrate <= CONTEXT_POOR_WR:  # 0.30-
            adj = -10
        elif winrate <= CONTEXT_BAD_WR:   # 0.40-
            adj = -5
        else:
            adj = 0

        print(
            f"🧠 CONTEXT MEMORY"
            f" | Key:{key}"
            f" | {entry['wins']}W/{total}T"
            f" | WR:{round(winrate*100,1)}%"
            f" | Adj:{adj:+d}"
        )

        return adj

    # =========================================
    # UPDATE AFTER TRADE CLOSE
    # =========================================

    def update(self, session, signal, regime, atr, result, strategy="UNKNOWN"):
        """
        يُستدعى عند إغلاق صفقة لتحديث السياق.
        result: "WIN" | "LOSS"
        """
        key = self._key(session, signal, regime, atr, strategy)

        if key not in self._data:
            self._data[key] = {"wins": 0, "losses": 0}

        if result == "WIN":
            self._data[key]["wins"]   += 1
        else:
            self._data[key]["losses"] += 1

        self._save()

    # =========================================
    # PERSISTENCE
    # =========================================

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, "r") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self):
        try:
            os.makedirs(MEMORY_DIR, exist_ok=True)
            with open(self._path, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Context Memory save error: {e}")

    # =========================================
    # SUMMARY
    # =========================================

    def summary(self):
        if not self._data:
            return "🧠 Context Memory: empty"

        lines = ["🧠 CONTEXT MEMORY SUMMARY:"]
        for key, val in sorted(self._data.items()):
            total = val["wins"] + val["losses"]
            if total < CONTEXT_MIN_TRADES:
                continue
            wr = round(val["wins"] / total * 100, 1)
            lines.append(
                f"  {key:35s}"
                f" {val['wins']}W/{total}T"
                f" WR:{wr}%"
            )

        return "\n".join(lines) if len(lines) > 1 \
            else "🧠 Context Memory: insufficient data"


# Singleton
context_memory = ContextMemory()

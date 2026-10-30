# =========================================
# FER3ON V7 — RECOVERY ENGINE
# Controlled Aggression + Cooldown Logic
# =========================================

import time
from collections import deque


class RecoveryEngine:

    def __init__(self):

        self.loss_streak = 0
        self.win_streak = 0

        self.cooldown_until = 0

        self.last_results = deque(maxlen=20)

        self.false_signal_count = 0
        self.total_trades = 0

    # =====================================
    # REGISTER TRADE RESULT
    # =====================================

    def register_trade_result(
        self,
        result,
        profit=0,
        signal_quality=0,
    ):

        result = str(result).upper()

        self.total_trades += 1
        self.last_results.append(result)

        if result == "WIN":

            self.win_streak += 1
            self.loss_streak = 0

        else:

            self.loss_streak += 1
            self.win_streak = 0

            if signal_quality >= 70 and profit < 0:
                self.false_signal_count += 1

        # ================================
        # SMART COOLDOWN
        # ================================

        if self.loss_streak >= 2:

            cooldown_minutes = min(
                60,
                5 * self.loss_streak
            )

            self.cooldown_until = (
                time.time() + cooldown_minutes * 60
            )

            print(
                f"[RECOVERY+] COOLDOWN ACTIVE "
                f"| losses={self.loss_streak} "
                f"| wait={cooldown_minutes}m"
            )

    # =====================================
    # CAN TRADE ?
    # =====================================

    def can_trade(self):

        now = time.time()

        if now < self.cooldown_until:

            remaining = int(
                (self.cooldown_until - now) / 60
            )

            return {
                "allowed": False,
                "reason": f"COOLDOWN_{remaining}M",
                "remaining_minutes": remaining
            }

        return {
            "allowed": True,
            "reason": "OK",
            "remaining_minutes": 0
        }

    # =====================================
    # RECOVERY MODE
    # =====================================

    def get_recovery_state(self):

        if self.loss_streak >= 4:

            return {
                "mode": "DEFENSIVE",
                "risk_multiplier": 0.40,
                "confidence_boost": -8,
                "lot_multiplier": 0.50,
                "aggression": "LOW"
            }

        if self.loss_streak >= 2:

            return {
                "mode": "RECOVERY",
                "risk_multiplier": 0.65,
                "confidence_boost": -4,
                "lot_multiplier": 0.75,
                "aggression": "CONTROLLED"
            }

        if self.win_streak >= 4:

            return {
                "mode": "SMART_AGGRESSION",
                "risk_multiplier": 1.15,
                "confidence_boost": 3,
                "lot_multiplier": 1.10,
                "aggression": "HIGH"
            }

        return {
            "mode": "NORMAL",
            "risk_multiplier": 1.0,
            "confidence_boost": 0,
            "lot_multiplier": 1.0,
            "aggression": "NORMAL"
        }

    # =====================================
    # FALSE SIGNAL RATE
    # =====================================

    def get_false_signal_rate(self):

        if self.total_trades <= 0:
            return 0.0

        rate = (
            self.false_signal_count /
            self.total_trades
        ) * 100

        return round(rate, 2)

    # =====================================
    # DASHBOARD
    # =====================================

    def get_dashboard(self):

        state = self.get_recovery_state()
        cooldown = self.can_trade()

        return {

            "mode": state["mode"],

            "loss_streak": self.loss_streak,

            "win_streak": self.win_streak,

            "risk_multiplier": state["risk_multiplier"],

            "lot_multiplier": state["lot_multiplier"],

            "confidence_boost": state["confidence_boost"],

            "false_signal_rate": self.get_false_signal_rate(),

            "cooldown_active": not cooldown["allowed"],

            "cooldown_remaining":
                cooldown["remaining_minutes"],

            "aggression":
                state["aggression"]
        }


# =========================================
# GLOBAL INSTANCE
# =========================================

recovery_engine = RecoveryEngine()
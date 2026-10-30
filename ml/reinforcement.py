# =========================================
# FER3ON V5.7 — REINFORCEMENT LEARNING
# Q-Learning + policy confidence + warmup honesty
# =========================================

import os
import json
import random as _random
from datetime import datetime, timezone

Q_TABLE_FILE = "data/models/q_table.json"
ALPHA = 0.10
GAMMA = 0.95
EPSILON_START = 0.30
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.995
WARMUP_MIN_UPDATES = 40
TRUSTED_STATE_VISITS = 5

ACTIONS = ["ENTER_FULL", "ENTER_HALF", "ENTER_QUARTER", "SKIP"]
ACTION_IDX = {a: i for i, a in enumerate(ACTIONS)}
IDX_ACTION = {i: a for i, a in enumerate(ACTIONS)}
ACTION_PRIORITY = ["ENTER_FULL", "ENTER_HALF", "ENTER_QUARTER", "SKIP"]

LOT_MULT = {
    "ENTER_FULL": 1.00,
    "ENTER_HALF": 0.50,
    "ENTER_QUARTER": 0.25,
    "SKIP": 0.00,
}


def encode_state(
    market_regime,
    session,
    quality_band,
    mtf_strength,
    choch_active,
    liq_score_band,
    spread_band=None,
    atr_band=None,
    volatility_band=None,
    sweep_detected=False,
    volume_spike=False,
    micro_breakout=False,
    drawdown_state="NORMAL",
    session_killzone=None,
    execution_latency="NORMAL",
    news_impact="NONE",
):
    regime = {"TRENDING": "TR", "RANGING": "RN", "VOLATILE": "VL", "CRISIS": "CR"}.get(market_regime, "UK")
    sess = {"LONDON": "LN", "NEWYORK": "NY", "ASIA": "AS", "OVERLAP": "OV", "OFF_HOURS": "OF"}.get(session, "UK")
    q_band = "HI" if quality_band >= 85 else ("MD" if quality_band >= 70 else "LO")
    mtf = str(min(int(mtf_strength), 4))
    choch = "Y" if choch_active else "N"
    liq = "HI" if liq_score_band >= 15 else ("MD" if liq_score_band >= 8 else "LO")

    spread = {"TIGHT": "TI", "NORMAL": "NO", "WIDE": "WI", "EXTREME": "EX"}.get(spread_band, "NO")
    atr = {"LOW": "LO", "NORMAL": "NO", "HIGH": "HI", "EXTREME": "EX"}.get(atr_band, "NO")
    vol = {"LOW": "LO", "NORMAL": "NO", "HIGH": "HI", "EXTREME": "EX"}.get(volatility_band, "NO")
    sweep = "Y" if sweep_detected else "N"
    volume = "Y" if volume_spike else "N"
    breakout = "Y" if micro_breakout else "N"
    drawdown = {"LOW": "LO", "NORMAL": "NO", "HIGH": "HI", "CRITICAL": "CR"}.get(drawdown_state, "NO")
    killzone = {"LONDON": "LN", "NEW_YORK": "NY", "ASIA": "AS"}.get(session_killzone, "NO")
    latency = {"LOW": "LO", "NORMAL": "NO", "HIGH": "HI"}.get(execution_latency, "NO")
    news = {"LOW": "LO", "NORMAL": "NO", "HIGH": "HI", "CRITICAL": "CR"}.get(news_impact, "NO")

    return f"{regime}_{sess}_{q_band}_{mtf}_{choch}_{liq}_{spread}_{atr}_{vol}_{sweep}_{volume}_{breakout}_{drawdown}_{killzone}_{latency}_{news}"


class QTable:
    def __init__(self):
        self.table = {}
        self.epsilon = EPSILON_START
        self.total_updates = 0
        self.state_visits = {}
        self.action_counts = {a: 0 for a in ACTIONS}
        self._load()

    def _load(self):
        if not os.path.exists(Q_TABLE_FILE):
            return
        try:
            with open(Q_TABLE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.table = data.get("table", {})
            self.epsilon = float(data.get("epsilon", EPSILON_START) or EPSILON_START)
            self.total_updates = int(data.get("total_updates", 0) or 0)
            self.state_visits = data.get("state_visits", {}) or {}
            loaded_counts = data.get("action_counts", {}) or {}
            self.action_counts = {a: int(loaded_counts.get(a, 0) or 0) for a in ACTIONS}
            print(
                f"✅ Q-Table loaded"
                f" | States:{len(self.table)}"
                f" | Updates:{self.total_updates}"
                f" | ε={self.epsilon:.3f}"
            )
        except Exception as e:
            print(f"⚠️  Q-Table load error: {e}")

    def _save(self):
        os.makedirs("data/models", exist_ok=True)
        try:
            with open(Q_TABLE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "table": self.table,
                        "epsilon": self.epsilon,
                        "total_updates": self.total_updates,
                        "state_visits": self.state_visits,
                        "action_counts": self.action_counts,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        except Exception as e:
            print(f"⚠️  Q-Table save error: {e}")

    def _get_q(self, state):
        if state not in self.table:
            self.table[state] = [0.0] * len(ACTIONS)
        return self.table[state]

    def _preferential_argmax(self, q_values):
        best_q = max(q_values)
        best_actions = [IDX_ACTION[i] for i, v in enumerate(q_values) if v == best_q]
        for action_name in ACTION_PRIORITY:
            if action_name in best_actions:
                return ACTION_IDX[action_name]
        return q_values.index(best_q)

    def _compute_confidence(self, q_values, visits):
        ordered = sorted(q_values, reverse=True)
        top = ordered[0] if ordered else 0.0
        second = ordered[1] if len(ordered) > 1 else 0.0
        spread = (max(q_values) - min(q_values)) if q_values else 0.0
        separation = top - second
        confidence = (visits * 7.0) + (separation * 28.0) + (spread * 10.0)
        return round(max(0.0, min(100.0, confidence)), 1)

    def choose_action(self, state):
        q_values = self._get_q(state)
        visits = int(self.state_visits.get(state, 0) or 0) + 1
        self.state_visits[state] = visits

        all_zero = all(abs(v) < 1e-9 for v in q_values)
        policy_mode = "POLICY"
        exploring = False
        confidence = self._compute_confidence(q_values, visits)

        if self.total_updates < WARMUP_MIN_UPDATES and all_zero:
            action_idx = ACTION_IDX["ENTER_HALF"] if confidence > 75 else ACTION_IDX["ENTER_QUARTER"]
            policy_mode = "WARMUP"
        elif visits < 2 and all_zero:
            action_idx = ACTION_IDX["ENTER_HALF"] if confidence > 75 else ACTION_IDX["ENTER_QUARTER"]
            policy_mode = "WARMUP"
        elif _random.random() < self.epsilon:
            action_idx = _random.randint(0, len(ACTIONS) - 1)
            policy_mode = "EXPLORE"
            exploring = True
        else:
            action_idx = self._preferential_argmax(q_values)

        action = IDX_ACTION[action_idx]
        trusted = self.total_updates >= WARMUP_MIN_UPDATES and visits >= TRUSTED_STATE_VISITS and confidence >= 55

        if action == "SKIP" and not trusted:
            action = "ENTER_QUARTER"
            action_idx = ACTION_IDX[action]
            policy_mode = "WARMUP"

        return action, action_idx, {
            "q_values": [round(float(v), 4) for v in q_values],
            "state_visits": visits,
            "policy_mode": policy_mode,
            "confidence": confidence,
            "trusted": trusted,
            "exploring": exploring,
        }

    def update(self, state, action_idx, reward, next_state):
        q_curr = self._get_q(state)
        q_next = self._get_q(next_state)

        q_curr[action_idx] = q_curr[action_idx] + ALPHA * (
            reward + GAMMA * max(q_next) - q_curr[action_idx]
        )
        self.table[state] = q_curr

        action_name = IDX_ACTION.get(action_idx, "ENTER_QUARTER")
        self.action_counts[action_name] = int(self.action_counts.get(action_name, 0) or 0) + 1
        self.epsilon = max(EPSILON_MIN, self.epsilon * EPSILON_DECAY)
        self.total_updates += 1

        if self.total_updates % 25 == 0:
            self._save()
            print(
                f"💾 Q-Table saved"
                f" | States:{len(self.table)}"
                f" | Updates:{self.total_updates}"
                f" | ε={self.epsilon:.3f}"
            )

    def get_best_action(self, state):
        q_values = self._get_q(state)
        idx = self._preferential_argmax(q_values)
        return IDX_ACTION[idx], q_values[idx]

    def get_stats(self):
        trusted_states = sum(1 for s in self.state_visits.values() if int(s or 0) >= TRUSTED_STATE_VISITS)
        return {
            "n_states": len(self.table),
            "epsilon": round(self.epsilon, 4),
            "total_updates": self.total_updates,
            "trusted_states": trusted_states,
            "action_counts": self.action_counts,
            "warmup_complete": self.total_updates >= WARMUP_MIN_UPDATES,
        }


# =========================================
# REWARD FUNCTION
# =========================================


def compute_reward(result, profit, rr_ratio, quality_score, exec_grade, recovery_speed=0.0, drawdown_control=0.0, win_streak_bonus=0.0, execution_quality=0.0, **_):
    pnl = 0.0
    if result == "WIN":
        pnl = abs(float(profit or 0) / 100.0)
    elif result == "LOSS":
        pnl = -abs(float(profit or 0) / 100.0)

    rr_quality = min(max(float(rr_ratio or 0.0) - 1.0, 0.0), 2.0)
    if result == "LOSS" and float(rr_ratio or 0.0) < 1.5:
        rr_quality = -0.35

    grade_bonus = {"ELITE": 0.35, "A+": 0.25, "A": 0.15, "B+": 0.08, "B": 0.04, "C": -0.02}.get(str(exec_grade or "").upper(), 0.0)
    reward = (
        pnl
        + rr_quality
        + float(execution_quality or 0.0)
        + float(recovery_speed or 0.0)
        + float(drawdown_control or 0.0)
        + float(win_streak_bonus or 0.0)
        + grade_bonus
    )
    return round(reward, 3)


# =========================================
# SINGLETON + API
# =========================================


_qtable = None


def get_qtable() -> QTable:
    global _qtable
    if _qtable is None:
        _qtable = QTable()
    return _qtable


def rl_get_action(state_key):
    qt = get_qtable()
    action, action_idx, meta = qt.choose_action(state_key)
    lot_mult = LOT_MULT.get(action, 1.0)
    print(
        f"🎮 RL ACTION: {action}"
        f" | LotMult:{lot_mult}"
        f" | Mode:{meta['policy_mode']}"
        f" | Visits:{meta['state_visits']}"
        f" | Conf:{meta['confidence']}"
        f" | ε={qt.epsilon:.3f}"
    )
    return {
        "action": action,
        "action_idx": action_idx,
        "lot_mult": lot_mult,
        "confidence": meta["confidence"],
        "policy_mode": meta["policy_mode"],
        "state_visits": meta["state_visits"],
        "trusted": meta["trusted"],
        "q_values": meta["q_values"],
        "epsilon": round(qt.epsilon, 4),
    }


def rl_update(state_key, action_idx, result, profit, rr_ratio, quality_score, exec_grade, next_state_key):
    reward = compute_reward(result, profit, rr_ratio, quality_score, exec_grade)
    qt = get_qtable()
    qt.update(state_key, action_idx, reward, next_state_key)
    print(f"🎮 RL UPDATE: reward={reward:+.2f} | States:{len(qt.table)}")
    return reward

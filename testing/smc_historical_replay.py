"""Bounded historical replay of the current SMC market-analysis components.

This is an offline research tool, not an execution simulator. It never trains
or replaces model artifacts and it does not connect to MT5.
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import io
import json
import sys
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from brain.trade_dna import FEATURE_NAMES, get_ml_features
from core.adaptive_sl_tp_engine import calculate_adaptive_sl_tp
from core.atr_manager import calculate_atr
from core.candle_trigger import check_candle_trigger
from core.liquidity_intelligence import get_liquidity_bias
from core.main_helpers import derive_signal, smc_strength_from_details
from core.market_regime import detect_market_regime
from core.market_structure import get_market_structure
from core.professional_swing_structure import (
    analyze_swing_structure,
    evaluate_entry_readiness,
)
from core.settings import SYMBOL, get_min_sl_dollars
from core.smc_entry_engine import check_smc_entry_sequence
from core.session_intelligence import get_session
from ml.feature_engine import extract_live_features

DATA_DIR = Path("data") / "market_data" / "XAUUSD_all_timeframes_2004-2026"
FRAME_FILES = {
    "M5": ("XAU_5m_data.csv", 5),
    "M15": ("XAU_15m_data.csv", 15),
    "H1": ("XAU_1h_data.csv", 60),
    "H4": ("XAU_4h_data.csv", 240),
}
CSV_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def _read_frame(path: Path, tail_rows: Optional[int] = None) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        sep=";",
        usecols=CSV_COLUMNS,
        dtype={
            "Open": "float32",
            "High": "float32",
            "Low": "float32",
            "Close": "float32",
            "Volume": "float32",
        },
    )
    frame["Date"] = pd.to_datetime(frame["Date"], format="%Y.%m.%d %H:%M", errors="raise")
    if tail_rows is not None:
        frame = frame.tail(tail_rows).copy()
    return frame.reset_index(drop=True)


def _as_rates(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    return [
        {
            "open": float(row.Open),
            "high": float(row.High),
            "low": float(row.Low),
            "close": float(row.Close),
            "tick_volume": float(row.Volume),
            "time": int(row.Date.timestamp()),
        }
        for row in frame.itertuples(index=False)
    ]


def _rates_asof(
    frame: pd.DataFrame,
    open_times: Sequence[int],
    decision_time: int,
    timeframe_seconds: int,
    limit: int = 120,
) -> Tuple[List[Dict[str, Any]], int]:
    end = bisect.bisect_right(open_times, decision_time - timeframe_seconds)
    start = max(0, end - limit)
    return _as_rates(frame.iloc[start:end]), end


def _outcome(
    rates: Sequence[Dict[str, Any]],
    first_bar: int,
    signal: str,
    entry: float,
    sl_distance: float,
    tp_distance: float,
    max_bars: int = 500,
) -> Tuple[str, Optional[int], Optional[float]]:
    stop = entry - sl_distance if signal == "BUY" else entry + sl_distance
    target = entry + tp_distance if signal == "BUY" else entry - tp_distance
    last = min(len(rates), first_bar + max_bars)
    for index in range(first_bar, last):
        candle = rates[index]
        if signal == "BUY":
            hit_stop = candle["low"] <= stop
            hit_target = candle["high"] >= target
        else:
            hit_stop = candle["high"] >= stop
            hit_target = candle["low"] <= target
        if hit_stop and hit_target:
            return "LOSS", index, stop
        if hit_stop:
            return "LOSS", index, stop
        if hit_target:
            return "WIN", index, target
    return "TIMEOUT", last - 1 if last > first_bar else None, None


def replay_smc(
    *,
    data_dir: Path = DATA_DIR,
    bars: int = 5_000,
    assume_utc: bool = False,
    max_hold_bars: int = 500,
) -> Dict[str, Any]:
    if not assume_utc:
        raise ValueError(
            "Candle timezone is unknown. Pass assume_utc=True only as an explicit provisional assumption."
        )
    if bars < 1:
        raise ValueError("bars must be positive")

    loaded = {}
    for timeframe, (filename, _) in FRAME_FILES.items():
        path = data_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing {timeframe} candle file: {path}")
        # M5 tail includes warm-up bars before the requested replay period.
        loaded[timeframe] = _read_frame(
            path,
            tail_rows=bars + 130 if timeframe == "M5" else None,
        )

    m5 = loaded["M5"]
    requested_start = max(0, len(m5) - bars)
    frames = {}
    open_times = {}
    for timeframe, frame in loaded.items():
        frame = frame.copy()
        # Provisional UTC interpretation, explicitly recorded in the report.
        frame["Date"] = frame["Date"].dt.tz_localize("UTC")
        frames[timeframe] = frame
        open_times[timeframe] = [int(value.timestamp()) for value in frame["Date"]]

    m5_rates = _as_rates(frames["M5"])
    samples = []
    rejected = 0
    timeouts = 0
    active_until = requested_start

    for index in range(max(requested_start, 120), len(m5_rates) - 1):
        if index < active_until:
            continue

        decision_time = int(frames["M5"].iloc[index].Date.timestamp()) + 5 * 60
        rates = {}
        for timeframe, (_, minutes) in FRAME_FILES.items():
            rates[timeframe], _ = _rates_asof(
                frames[timeframe],
                open_times[timeframe],
                decision_time,
                minutes * 60,
                limit={"M5": 120, "M15": 100, "H1": 80, "H4": 60}[timeframe],
            )

        if any(len(rates[tf]) < minimum for tf, minimum in (
            ("M5", 60), ("M15", 20), ("H1", 20), ("H4", 10)
        )):
            continue

        price = rates["M5"][-1]["close"]
        # Use the exact bar close, including hour/day rollover.
        as_of = (
            frames["M5"].iloc[index].Date + pd.Timedelta(minutes=5)
        ).to_pydatetime().astimezone(timezone.utc)

        with contextlib.redirect_stdout(io.StringIO()):
            structure = get_market_structure(
                SYMBOL,
                rates_h1=rates["H1"][-80:],
                rates_h4=rates["H4"][-60:],
            )
            structure_analysis = analyze_swing_structure(
                rates["M5"],
                current_price=price,
            )
            liquidity = get_liquidity_bias(
                SYMBOL,
                rates_m15=rates["M15"][-96:],
                rates_m5=rates["M5"][-20:],
                rates_h1=rates["H1"][-50:],
                current_price=price,
                as_of=as_of,
            )
        signal = derive_signal(
            structure_analysis.get("structure_bias", structure.get("bias", "NEUTRAL")),
            liquidity.get("bias", "NEUTRAL"),
        )
        if signal == "NONE":
            signal = derive_signal(structure.get("bias"), liquidity.get("bias"))
        if signal not in {"BUY", "SELL"}:
            continue

        readiness = evaluate_entry_readiness(structure_analysis, entry_price=price)
        if not readiness.get("ready"):
            continue

        with contextlib.redirect_stdout(io.StringIO()):
            smc_confirmed, entry_grade, smc_details = check_smc_entry_sequence(
                SYMBOL,
                signal,
                rates_h1=rates["H1"][-60:],
                rates_m5=rates["M5"][-120:],
                rates_m15=rates["M15"][-60:],
                verbose=False,
            )
            candle = check_candle_trigger(
                SYMBOL,
                signal,
                "SMC",
                rates=rates["M5"][-120:],
                rates_m15=rates["M15"][-12:],
                verbose=False,
                deduplicate_closed_candles=False,
            )
        if not smc_confirmed or not candle.get("confirmed"):
            rejected += 1
            continue

        atr = calculate_atr(rates["M5"][-120:])
        with contextlib.redirect_stdout(io.StringIO()):
            regime = detect_market_regime(
                SYMBOL,
                rates_m15=rates["M15"][-100:],
                rates_h1=rates["H1"][-50:],
            )
        quality_score = round(max(
            float(smc_details.get("grade_score", 0) or 0),
            float(candle.get("score", 0) or 0),
            50.0,
        ), 2)
        structure_strength = max(
            float(structure.get("confidence", 0.5) or 0.5),
            float(structure_analysis.get("structure_strength", 0) or 0) / 100.0,
        )
        session = get_session(as_of.hour)
        with contextlib.redirect_stdout(io.StringIO()):
            adaptive = calculate_adaptive_sl_tp(
                atr=atr,
                strategy="SMC",
                lot=0.01,
                confidence=0.5,
                quality_score=quality_score,
                market_regime=regime,
                session=session,
                structure_strength=structure_strength,
                liquidity=float(liquidity.get("score", 0) or 0) / 100.0,
                volatility=0.5,
                spread=0,
                execution_grade="B",
                min_sl=get_min_sl_dollars(),
                entry_price=price,
                signal=signal,
                structure_analysis=structure_analysis,
            )
        sl_distance = float(adaptive["sl_distance"])
        tp_distance = float(adaptive["tp_distance"])
        if sl_distance <= 0 or tp_distance <= 0:
            rejected += 1
            continue

        next_bar = m5_rates[index + 1]
        entry = float(next_bar["open"])
        outcome, exit_index, exit_price = _outcome(
            m5_rates,
            index + 1,
            signal,
            entry,
            sl_distance,
            tp_distance,
            max_bars=max_hold_bars,
        )
        if outcome == "TIMEOUT":
            timeouts += 1
        if exit_index is not None:
            active_until = exit_index + 1

        confidence_pct = 50.0
        features, record = extract_live_features(
            symbol=SYMBOL,
            strategy="SMC",
            signal=signal,
            market_regime=regime,
            session=session,
            quality_score=quality_score,
            confidence_pct=confidence_pct,
            choch_state=structure.get("structure", "UNKNOWN"),
            liq_map_score=liquidity.get("score", 0),
            exec_grade="B",
            rr_ratio=adaptive.get("risk_reward", 0),
            spread_pts=0,
            mtf_strength=3 if structure.get("mtf_aligned") else 2 if structure.get("bias") in {"BUY", "SELL"} else 0,
            mtf_structural=1 if structure.get("mtf_aligned") else 0,
            atr=atr,
            key_levels={
                "PDH": liquidity.get("asian_high", 0),
                "PDL": liquidity.get("asian_low", 0),
            },
            current_price=price,
            as_of=as_of,
        )
        samples.append({
            "entry_time": as_of.isoformat(),
            "signal": signal,
            "entry": round(entry, 5),
            "sl_distance": round(sl_distance, 5),
            "tp_distance": round(tp_distance, 5),
            "result": outcome,
            "exit_time": (
                pd.to_datetime(m5_rates[exit_index]["time"], unit="s", utc=True).isoformat()
                if exit_index is not None else None
            ),
            "exit_price": round(exit_price, 5) if exit_price is not None else None,
            "features": [float(value) for value in features],
            "feature_count": len(FEATURE_NAMES),
            "smc_confirmed": bool(smc_confirmed),
            "candle_confirmed": bool(candle.get("confirmed")),
        })

    wins = sum(item["result"] == "WIN" for item in samples)
    losses = sum(item["result"] == "LOSS" for item in samples)
    report = {
        "status": "RESEARCH_ONLY",
        "symbol": SYMBOL,
        "strategy": "SMC",
        "bars_requested": bars,
        "bars_processed": len(m5_rates) - requested_start,
        "timezone_assumption": "UTC (provisional; source timezone unverified)",
        "first_bar": frames["M5"].iloc[requested_start].Date.isoformat(),
        "last_bar": frames["M5"].iloc[-1].Date.isoformat(),
        "feature_names": FEATURE_NAMES,
        "feature_count": len(FEATURE_NAMES),
        "samples": len(samples),
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "rejected_candidates": rejected,
        "win_rate": round(wins / (wins + losses) * 100, 2) if wins + losses else None,
        "execution_costs": "NOT MODELED: historical source has OHLCV only",
        "market_news": "NOT MODELED",
        "provisional_feature_values": [
            "confidence_pct is fixed at neutral 50",
            "spread_pts and slippage are zero because source has no bid/ask",
            "daily high/low distances are zero",
            "risk, composite score, latency, and duration are zero",
        ],
        "feature_builder": "ml.feature_engine.extract_live_features",
        "feature_parity_with_live_builder": True,
        "feature_values_provisional": True,
        "ml_training_allowed": False,
        "model_artifacts_modified": False,
        "samples_data": samples,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded offline SMC historical replay")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--assume-utc", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--max-hold-bars", type=int, default=500)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    try:
        report = replay_smc(
            data_dir=args.data_dir,
            bars=args.bars,
            assume_utc=args.assume_utc,
            max_hold_bars=args.max_hold_bars,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Replay not run: {exc}", file=sys.stderr)
        return 2

    output = args.output or (
        Path("data")
        / "backtests"
        / f"smc_historical_replay_{args.bars}bars.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Replay complete | bars={report['bars_processed']} "
        f"samples={report['samples']} wins={report['wins']} "
        f"losses={report['losses']} timeouts={report['timeouts']}"
    )
    print(f"UTC assumption is provisional; costs/news are not modeled.")
    print(f"ML training allowed: {report['ml_training_allowed']}")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

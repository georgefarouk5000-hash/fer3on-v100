# =========================================
# FER3ON V5.2 — BACKTESTING ENGINE
# Walk-Forward + Monte Carlo + Full Stats
# =========================================

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    import math as np
    HAS_NUMPY = False
    print("⚠️  numpy not found — install: pip install numpy")
import os, json, csv
from datetime import datetime, timezone
from testing.statistics import full_stats_analysis, format_stats_report

# =========================================
# PHASE 5 — OPPORTUNITY ALLOCATOR INTEGRATION
# =========================================
try:
    from core.opportunity_allocator import rank_opportunity
    _ALLOCATOR_AVAILABLE = True
except Exception as _alloc_err:
    _ALLOCATOR_AVAILABLE = False
    print(f"⚠️ Opportunity allocator import warning: {_alloc_err}")

BACKTEST_DIR = "data/backtests"


# =========================================
# TRADE SIMULATION RECORD
# =========================================

def _simulate_trade(entry, sl, tp, rates, start_idx, max_bars=500):
    """
    يُشغّل trade simulation على rates array.
    يُعيد: result (WIN/LOSS/TIMEOUT), exit_price, bars_held
    """
    for i in range(start_idx+1, min(start_idx+max_bars, len(rates))):
        h = rates[i]["high"]
        l = rates[i]["low"]
        if h >= tp:
            return "WIN",  tp,    i - start_idx
        if l <= sl:
            return "LOSS", sl,    i - start_idx
    # timeout
    last_close = rates[min(start_idx+max_bars, len(rates)-1)]["close"]
    return "TIMEOUT", last_close, max_bars


# =========================================
# SIMPLE SIGNAL GENERATOR للـ Backtest
# (هدفه إعادة إنتاج إشارات V5.2 على بيانات تاريخية)
# =========================================

def _generate_backtest_signal(rates, idx, atr_mult_sl=1.2, atr_mult_tp=3.0):
    """
    يُولّد إشارة بسيطة بناءً على:
      - EMA 9/21 crossover (للاتجاه)
      - RSI extremes (للتوقيت)
      - ATR-based SL/TP

    يُعيد: signal, entry, sl, tp, quality, confidence أو None
    """
    if idx < 55: return None

    window  = rates[idx-50:idx+1]
    closes  = [c["close"] for c in window]
    highs   = [c["high"]  for c in window]
    lows    = [c["low"]   for c in window]

    # EMA
    def ema(arr, p):
        k = 2/(p+1); e = arr[0]
        for v in arr[1:]: e = v*k + e*(1-k)
        return e

    e9  = ema(closes, 9)
    e21 = ema(closes, 21)

    # ATR
    tr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
          for i in range(1, len(window))]
    atr = np.mean(tr[-14:]) if tr else 1

    # RSI
    gains  = [max(closes[i]-closes[i-1],0) for i in range(1,len(closes))]
    losses_l = [max(closes[i-1]-closes[i],0) for i in range(1,len(closes))]
    ag = np.mean(gains[-14:]) or 0.001
    al = np.mean(losses_l[-14:]) or 0.001
    rsi = 100-(100/(1+ag/al))

    price = closes[-1]

    # =========================================================
    # PHASE 5 — QUALITY & CONFIDENCE CALCULATION
    # (for opportunity allocator ranking)
    # =========================================================
    # Quality: how aligned is price with the trend
    ema_distance = abs(price - e21) / atr if atr > 0 else 0
    quality_from_trend = min(100, max(0, 100 - ema_distance * 5))  # closer = better
    
    # RSI as confidence signal
    if rsi > 30 and rsi < 70:
        rsi_confidence = 50 + abs(rsi - 50)  # farther from 50 = more extreme = more confident
    else:
        rsi_confidence = 50
    
    # Trend strength (EMA spread)
    ema_spread = abs(e9 - e21) / price * 100 if price > 0 else 0
    trend_strength = min(100, ema_spread * 50)  # wider spread = stronger trend
    
    # Combined quality score
    quality_score = round((quality_from_trend * 0.5 + trend_strength * 0.5), 1)
    confidence_pct = round((rsi_confidence * 0.7 + trend_strength * 0.3), 1)

    if e9 > e21 and rsi > 30 and rsi < 65:
        entry = price
        sl    = round(entry - atr*atr_mult_sl, 2)
        tp    = round(entry + atr*atr_mult_tp, 2)
        if tp-entry > entry-sl:
            return {
                "signal": "BUY",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "atr": atr,
                "quality_score": quality_score,
                "confidence_pct": confidence_pct,
                "rsi": rsi,
                "e9": e9,
                "e21": e21,
            }

    elif e9 < e21 and rsi < 70 and rsi > 35:
        entry = price
        sl    = round(entry + atr*atr_mult_sl, 2)
        tp    = round(entry - atr*atr_mult_tp, 2)
        if entry-tp > sl-entry:
            return {
                "signal": "SELL",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "atr": atr,
                "quality_score": quality_score,
                "confidence_pct": confidence_pct,
                "rsi": rsi,
                "e9": e9,
                "e21": e21,
            }

    return None


# =========================================
# FULL BACKTEST
# =========================================

def run_backtest(rates, symbol="XAUUSD", initial_balance=10000,
                 risk_pct=0.5, label="FULL"):
    """
    يُشغّل backtest كامل على rates array.
    يُعيد: stats dict + trades list
    """
    balance   = initial_balance
    trades    = []
    last_idx  = 0
    equity    = [initial_balance]

    for idx in range(55, len(rates)-1):
        if idx < last_idx + 3:   # منع الدخول المتكرر
            continue

        sig = _generate_backtest_signal(rates, idx)
        if sig is None:
            continue

        entry   = sig["entry"]
        sl      = sig["sl"]
        tp      = sig["tp"]
        atr     = sig["atr"]
        signal  = sig["signal"]
        quality_score = sig.get("quality_score", 50)
        confidence_pct = sig.get("confidence_pct", 50)

        # =========================================================
        # PHASE 5 — APPLY OPPORTUNITY ALLOCATOR
        # Rank signal and apply sizing multiplier
        # =========================================================
        allocator_grade = "NONE"
        lot_multiplier = 1.0
        should_reject = False
        
        if _ALLOCATOR_AVAILABLE:
            try:
                rank = rank_opportunity(
                    quality_score=quality_score,
                    confidence_pct=confidence_pct,
                    market_regime="TRENDING",  # Simplified for backtest
                    session="LONDON",           # Simplified for backtest
                    smc_strength=5.0,          # Default
                    mtf_strength=5,            # Default
                    execution_grade="B+",       # Simplified
                    daily_bias_alignment=True, # Simplified
                )
                
                allocator_grade = rank.grade
                lot_multiplier = rank.lot_multiplier
                should_reject = rank.should_reject
                
                if should_reject:
                    # Allocator rejected this opportunity as too weak
                    continue
                    
            except Exception as _alloc_err:
                # If allocator fails, proceed with full sizing (fail-open for backtest)
                pass

        sl_dist = abs(entry - sl)
        tp_dist = abs(tp - entry)

        if sl_dist <= 0:
            continue

        rr = tp_dist / sl_dist
        if rr < 1.5:
            continue

        # حجم اللوت (تبسيط للـ backtest)
        # Apply allocator sizing multiplier
        risk_amount = balance * risk_pct / 100
        lot = round(risk_amount / (sl_dist * 100), 2)
        lot = max(0.01, min(lot, 5.0))
        
        # Apply allocator multiplier
        lot = round(lot * lot_multiplier, 2)
        lot = max(0.01, min(lot, 5.0))

        result, exit_price, bars = _simulate_trade(rates, sl, tp, rates, idx)

        if result == "WIN":
            profit_pts = tp_dist if signal=="BUY" else tp_dist
            profit     = round(profit_pts * lot * 100, 2)
        elif result == "LOSS":
            profit = round(-sl_dist * lot * 100, 2)
        else:  # TIMEOUT
            diff   = exit_price - entry if signal=="BUY" else entry - exit_price
            profit = round(diff * lot * 100, 2)

        balance += profit
        equity.append(balance)
        last_idx = idx

        trades.append({
            "idx":       idx,
            "signal":    signal,
            "entry":     round(entry,2),
            "sl":        round(sl,2),
            "tp":        round(tp,2),
            "exit":      round(exit_price,2),
            "result":    result,
            "profit":    profit,
            "rr":        round(rr,2),
            "lot":       lot,
            "atr":       round(atr,2),
            "balance":   round(balance,2),
            "quality_score": quality_score,
            "confidence_pct": confidence_pct,
            "allocator_grade": allocator_grade,
            "lot_multiplier": lot_multiplier,
        })

    # حساب الإحصاءات
    stats = _compute_bt_stats(trades, initial_balance, balance, equity, label)
    return stats, trades


def _compute_bt_stats(trades, initial_balance, final_balance, equity, label):
    if not trades:
        return {"label":label,"error":"NO_TRADES"}

    wins   = [t for t in trades if t["result"]=="WIN"]
    losses = [t for t in trades if t["result"]=="LOSS"]
    profits = [t["profit"] for t in trades]

    total    = len(trades)
    n_win    = len(wins)
    win_rate = round(n_win/total*100, 1) if total>0 else 0

    gross_win  = sum(t["profit"] for t in wins)
    gross_loss = abs(sum(t["profit"] for t in losses)) or 0.001
    pf = round(gross_win/gross_loss, 3)

    # Max Drawdown
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak: peak = e
        dd = peak - e
        if dd > max_dd: max_dd = dd

    max_dd_pct = round(max_dd/initial_balance*100, 2)
    net_profit = round(final_balance - initial_balance, 2)

    # Sharpe
    if len(profits) > 1:
        m = np.mean(profits); s = np.std(profits, ddof=1)
        sharpe = round(m/s*np.sqrt(252), 3) if s>0 else 0
    else:
        sharpe = 0

    avg_win  = round(gross_win/n_win, 2)    if n_win  else 0
    avg_loss = round(gross_loss/len(losses),2) if losses else 0
    expect   = round((n_win/total)*avg_win - (len(losses)/total)*avg_loss, 2)
    recovery = round(net_profit/max_dd, 3)  if max_dd>0 else 99.0
    avg_rr   = round(np.mean([t["rr"] for t in trades]),2)

    return {
        "label":          label,
        "total_trades":   total,
        "win_rate":       win_rate,
        "net_profit":     net_profit,
        "net_profit_pct": round(net_profit/initial_balance*100, 2),
        "profit_factor":  pf,
        "max_drawdown":   round(max_dd, 2),
        "max_dd_pct":     max_dd_pct,
        "sharpe_ratio":   sharpe,
        "expectancy":     expect,
        "recovery_factor": recovery,
        "avg_win":        avg_win,
        "avg_loss":       avg_loss,
        "avg_rr":         avg_rr,
        "initial_balance": initial_balance,
        "final_balance":  round(final_balance, 2),
        "equity_curve":   equity,
    }


# =========================================
# WALK-FORWARD TESTING
# =========================================

def walk_forward_test(rates, n_windows=5, train_pct=0.70,
                      symbol="XAUUSD", initial_balance=10000, risk_pct=0.5):
    """
    Walk-Forward Testing:
    يقسم البيانات إلى n_windows نوافذ متتالية.
    كل نافذة: 70% تدريب + 30% اختبار.
    """
    n = len(rates)
    window_size = n // n_windows
    window_results = []

    print(f"\n📊 WALK-FORWARD TEST | Windows:{n_windows} | Bars:{n}")

    all_oos_trades = []  # Out-of-Sample trades مجمّعة

    for w in range(n_windows):
        start = w * window_size
        end   = min(start + window_size, n)
        train_end = start + int((end-start)*train_pct)

        train_rates = rates[start:train_end]
        test_rates  = rates[train_end:end]

        if len(test_rates) < 100:
            continue

        # Backtest على نافذة الاختبار
        oos_stats, oos_trades = run_backtest(
            test_rates, symbol, initial_balance, risk_pct,
            label=f"WF-{w+1}-OOS"
        )
        window_results.append(oos_stats)
        all_oos_trades.extend(oos_trades)

        print(
            f"  Window {w+1}/{n_windows}:"
            f" WR={oos_stats.get('win_rate',0)}%"
            f" PF={oos_stats.get('profit_factor',0)}"
            f" Net={oos_stats.get('net_profit',0):+.0f}"
        )

    # إحصاءات مجمّعة على كل الـ OOS
    if all_oos_trades:
        combined = _compute_bt_stats(
            all_oos_trades, initial_balance,
            initial_balance + sum(t["profit"] for t in all_oos_trades),
            [initial_balance + sum(t["profit"] for t in all_oos_trades[:i+1])
             for i in range(len(all_oos_trades))],
            label="WF-COMBINED"
        )
    else:
        combined = {"error": "NO_OOS_TRADES"}

    # Consistency Score: % نوافذ رابحة
    profitable_windows = sum(1 for r in window_results if r.get("net_profit",0) > 0)
    consistency = round(profitable_windows / len(window_results) * 100, 1) if window_results else 0

    print(
        f"\n✅ WALK-FORWARD DONE:"
        f" Consistency={consistency}%"
        f" Combined PF={combined.get('profit_factor',0)}"
    )

    return {
        "method":           "Walk-Forward",
        "n_windows":        n_windows,
        "window_results":   window_results,
        "combined":         combined,
        "consistency_pct":  consistency,
        "profitable_windows": profitable_windows,
        "total_windows":    len(window_results),
    }


# =========================================
# MONTE CARLO TESTING
# =========================================

def monte_carlo_test(trades_profits, n_simulations=1000,
                     initial_balance=10000, confidence_level=0.95):
    """
    Monte Carlo Testing:
    يُعيد توزيع النتائج بعد عشوائية ترتيب الصفقات.

    يحسب:
      - Worst-case Max Drawdown (95th percentile)
      - Best / Worst / Median outcomes
      - Probability of Ruin
    """
    if len(trades_profits) < 10:
        return {"error": "Need 10+ trades for Monte Carlo"}

    profits_arr    = np.array(trades_profits)
    final_balances = []
    max_drawdowns  = []
    ruined         = 0   # حالات الخسارة الكاملة

    print(f"\n🎲 MONTE CARLO | Sims:{n_simulations} | Trades:{len(profits_arr)}")

    rng = np.random.default_rng(42)

    for sim in range(n_simulations):
        shuffled = rng.permutation(profits_arr)
        equity   = initial_balance
        peak     = equity
        max_dd   = 0

        for p in shuffled:
            equity += p
            if equity > peak: peak = equity
            dd = peak - equity
            if dd > max_dd: max_dd = dd
            if equity <= 0:
                ruined += 1
                break

        final_balances.append(equity)
        max_drawdowns.append(max_dd)

    final_arr = np.array(final_balances)
    dd_arr    = np.array(max_drawdowns)

    ruin_prob = round(ruined / n_simulations * 100, 2)

    result = {
        "method":          "Monte Carlo",
        "n_simulations":   n_simulations,
        "n_trades":        len(profits_arr),
        "initial_balance": initial_balance,

        # Final Balance distribution
        "median_balance":  round(float(np.median(final_arr)), 2),
        "mean_balance":    round(float(np.mean(final_arr)), 2),
        "best_balance":    round(float(np.percentile(final_arr, 95)), 2),
        "worst_balance":   round(float(np.percentile(final_arr, 5)),  2),
        "p10_balance":     round(float(np.percentile(final_arr, 10)), 2),
        "p90_balance":     round(float(np.percentile(final_arr, 90)), 2),

        # Drawdown distribution
        "median_drawdown": round(float(np.median(dd_arr)), 2),
        "worst_drawdown":  round(float(np.percentile(dd_arr, int(confidence_level*100))), 2),
        "p95_drawdown":    round(float(np.percentile(dd_arr, 95)), 2),
        "max_drawdown_ever": round(float(np.max(dd_arr)), 2),

        # Risk
        "ruin_probability": ruin_prob,
        "confidence_level": confidence_level,

        # Grade
        "grade": _mc_grade(ruin_prob, float(np.median(final_arr)), initial_balance)
    }

    print(
        f"✅ MC DONE | MedianBal:{result['median_balance']:.0f}"
        f" | WorstDD:{result['worst_drawdown']:.0f}"
        f" | Ruin:{ruin_prob}%"
    )
    return result


def _mc_grade(ruin_prob, median_balance, initial):
    if ruin_prob > 20:           return "DANGEROUS ❌"
    if ruin_prob > 5:            return "RISKY ⚠️"
    gain_pct = (median_balance-initial)/initial*100
    if gain_pct > 20 and ruin_prob < 2:  return "EXCELLENT ✨"
    if gain_pct > 10:            return "GOOD 👍"
    if gain_pct > 0:             return "ACCEPTABLE ✅"
    return "MARGINAL ⚠️"


# =========================================
# FULL TEST SUITE — يشغّل كل شيء
# =========================================

def run_full_test_suite(rates=None, symbol="XAUUSD", initial_balance=10000):
    """
    يُشغّل الجناح الكامل:
      1. Full Backtest
      2. Walk-Forward (5 نوافذ)
      3. Monte Carlo (1000 محاكاة)
      4. Statistical Analysis

    يُعيد dict كامل يُحفظ في disk
    """
    if rates is None or len(rates) < 200:
        return {"error": "Need 200+ bars for full test suite"}

    print(f"\n🔬 FULL TEST SUITE | Symbol:{symbol} | Bars:{len(rates)}")

    # 1. Full Backtest
    bt_stats, bt_trades = run_backtest(
        rates, symbol, initial_balance, risk_pct=0.5, label="FULL_BT"
    )

    # 2. Walk-Forward
    wf_result = walk_forward_test(rates, n_windows=5,
                                  initial_balance=initial_balance)

    # 3. Monte Carlo على profits من Full Backtest
    mc_profits = [t["profit"] for t in bt_trades]
    mc_result  = monte_carlo_test(mc_profits, n_simulations=1000,
                                  initial_balance=initial_balance)

    # 4. Statistical Summary
    stats_trades = []
    for t in bt_trades:
        stats_trades.append({
            "profit_f":     t["profit"],
            "result_clean": t["result"],
            "strategy":     "BT",
            "session":      "BT",
            "market_regime":"BT",
        })
    stat_result = full_stats_analysis(stats_trades)

    # حفظ
    report = {
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "symbol":         symbol,
        "backtest":       bt_stats,
        "walk_forward":   wf_result,
        "monte_carlo":    mc_result,
        "statistics":     stat_result,
    }

    os.makedirs(BACKTEST_DIR, exist_ok=True)
    fname = os.path.join(BACKTEST_DIR, f"test_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            # حذف equity_curve من التخزين لتوفير المساحة
            r_save = {k: v for k, v in report.items()}
            if "backtest" in r_save and "equity_curve" in r_save["backtest"]:
                r_save["backtest"]["equity_curve"] = f"[{len(bt_stats.get('equity_curve',[]))} points]"
            json.dump(r_save, f, indent=2, ensure_ascii=False)
        print(f"💾 Test suite saved: {fname}")
    except Exception as e:
        print(f"⚠️  Save error: {e}")

    print(f"\n{'='*50}")
    print(f"📊 FULL TEST SUITE RESULTS")
    print(f"BT: WR={bt_stats.get('win_rate',0)}% PF={bt_stats.get('profit_factor',0)} Net={bt_stats.get('net_profit',0):+.0f}")
    print(f"WF: Consistency={wf_result.get('consistency_pct',0)}%")
    print(f"MC: MedianBal={mc_result.get('median_balance',0):.0f} Ruin={mc_result.get('ruin_probability',0)}%")
    print(f"Grade: {mc_result.get('grade','N/A')}")
    print(f"{'='*50}\n")

    return report

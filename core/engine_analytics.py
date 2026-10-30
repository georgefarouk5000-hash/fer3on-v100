from core.ai_memory import load_memory_records


def analyze_engines():
    rows = load_memory_records()
    if not rows:
        return "📊 No trade data yet"

    engines = {
        "DAILY": {"wins": 0, "losses": 0, "profit": 0.0, "win_p": [], "loss_p": []},
        "SMC":   {"wins": 0, "losses": 0, "profit": 0.0, "win_p": [], "loss_p": []},
    }

    for row in rows:
        strat = str(row.get("strategy", "") or "").upper()
        if strat not in engines:
            continue
        result = str(row.get("result", "")).upper()
        try:
            profit = float(row.get("profit", 0) or 0)
        except Exception:
            profit = 0.0

        engines[strat]["profit"] += profit

        if result == "WIN":
            engines[strat]["wins"] += 1
            engines[strat]["win_p"].append(profit)
        elif result == "LOSS":
            engines[strat]["losses"] += 1
            engines[strat]["loss_p"].append(abs(profit))

    lines = ["📊 ENGINE PERFORMANCE:"]
    for name, d in engines.items():
        total = d["wins"] + d["losses"]
        if total == 0:
            continue
        wr = round(d["wins"] / total * 100, 1)
        avg_win = round(sum(d["win_p"]) / len(d["win_p"]), 2) if d["win_p"] else 0
        avg_loss = round(sum(d["loss_p"]) / len(d["loss_p"]), 2) if d["loss_p"] else 0
        total_win = sum(d["win_p"])
        total_loss = sum(d["loss_p"])
        pf = round(total_win / total_loss, 2) if total_loss > 0 else 0
        lines.append(
            f"  {name:5s} | {total:3d}T"
            f" WR:{wr}%"
            f" P:{round(d['profit'],1)}$"
            f" AvgW:{avg_win}$"
            f" AvgL:{avg_loss}$"
            f" PF:{pf}"
        )
    return "\n".join(lines) if len(lines) > 1 else "📊 No trades yet"

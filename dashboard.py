import streamlit as st
import pandas as pd
import plotly.express as px
import time
import os

from core.mt5_compat import mt5, MT5_AVAILABLE

from core.engine_analytics import (
    analyze_engines
)

from core.analytics import (
    analyze_trades
)

from core.ai_memory import (
    initialize_memory,
    save_trade_memory,
    analyze_memory,
    deal_exists,
)

from core.adaptive_ai import (
    market_is_safe
)

from core.news_filter import (
    is_news_time
)

# =========================================
# PAGE CONFIG
# =========================================

st.set_page_config(

    page_title="Institutional AI Bot",

    layout="wide"

)

# =========================================
# TITLE
# =========================================

st.title(
    "🤖 Institutional AI Trading Dashboard"
)

# =========================================
# MT5 INIT
# =========================================

if mt5 is None:

    st.error(
        "❌ MetaTrader5 package غير مثبت. ثبّت requirements.txt على Windows أولاً."
    )

    st.stop()

if not mt5.initialize():

    st.error(
        "❌ MT5 Connection Failed"
    )

    st.stop()

# =========================================
# AUTO REFRESH
# =========================================

refresh = st.sidebar.slider(

    "Refresh Seconds",

    1,

    30,

    5

)

st.sidebar.header(
    "BOT STATUS"
)

st.sidebar.write(
    f"Refresh: {refresh}s"
)

st.sidebar.write(
    "MT5: Connected"
)

# =========================================
# ACCOUNT INFO
# =========================================

account = mt5.account_info()

if account is not None:

    col1, col2, col3, col4 = st.columns(4)

    balance = round(getattr(account, "balance", 0.0), 2)
    equity = round(getattr(account, "equity", balance), 2)
    profit = round(getattr(account, "profit", equity - balance), 2)
    margin = round(getattr(account, "margin", 0.0), 2)

    col1.metric(
        "Balance",
        balance
    )

    col2.metric(
        "Equity",
        equity
    )

    col3.metric(
        "Profit",
        profit
    )

    col4.metric(
        "Margin",
        margin
    )

# =========================================
# ENGINE ANALYTICS
# =========================================

st.subheader(
    "🧠 Engine Analytics"
)

engine_stats = analyze_engines()

if not isinstance(engine_stats, dict):

    st.warning("⚠️ Engine analytics data unavailable right now")

    engine_stats = {}

engine_data = []

for engine, data in engine_stats.items():

    engine_data.append({

        "Engine": engine,

        "Trades": data["trades"],

        "Wins": data["wins"],

        "WinRate": data["winrate"],

        "Profit": round(
            data["profit"],
            2
        )

    })

engine_df = pd.DataFrame(
    engine_data
)

if not engine_df.empty:

    best_engine = engine_df.loc[
        engine_df["Profit"].idxmax()
    ]

    st.success(

        f"🏆 Best Engine: "
        f"{best_engine['Engine']} | "
        f"Profit = {best_engine['Profit']}"

    )

st.dataframe(

    engine_df,

    use_container_width=True

)

# =========================================
# AI MEMORY
# =========================================

st.subheader(
    "🧠 AI Memory"
)

memory = analyze_memory()

st.json(memory)

# =========================================
# GENERAL ANALYTICS
# =========================================

st.subheader(
    "📊 General Analytics"
)

stats = analyze_trades()

st.json(stats)

# =========================================
# LIVE MARKET STATUS
# =========================================

st.subheader(
    "🌍 Live Market Status"
)

status_col1, status_col2, status_col3 = st.columns(3)

# =========================================
# MARKET SAFETY
# =========================================

market_safe = market_is_safe()

if market_safe:

    status_col1.success(
        "✅ Market Safe"
    )

else:

    status_col1.error(
        "⛔ Unsafe Market"
    )

# =========================================
# NEWS STATUS
# =========================================

news_status = is_news_time()

if news_status:

    status_col2.warning(
        "📰 News Active"
    )

else:

    status_col2.success(
        "✅ No Major News"
    )

# =========================================
# MT5 STATUS
# =========================================

terminal = mt5.terminal_info()

if terminal is not None:

    status_col3.success(
        "🟢 MT5 Connected"
    )

else:

    status_col3.error(
        "🔴 MT5 Offline"
    )
    
# =========================================
# OPEN POSITIONS
# =========================================

st.subheader(
    "📌 Open Positions"
)

positions = mt5.positions_get()

if positions:

    total_open_profit = sum(

        pos.profit

        for pos in positions

    )

    st.metric(

        "📈 Open PnL",

        round(total_open_profit, 2)

    )

if positions:

    positions_data = []

    for pos in positions:

        positions_data.append({

            "Ticket": pos.ticket,

            "Symbol": pos.symbol,

            "Volume": pos.volume,

            "Profit": round(
                pos.profit,
                2
            ),

            "SL": pos.sl,

            "TP": pos.tp,

            "Magic": pos.magic,

            "Comment": pos.comment

        })

    pos_df = pd.DataFrame(
        positions_data
    )

    st.dataframe(

        pos_df,

        use_container_width=True

    )

else:

    st.info(
        "No Open Positions"
    )

# =========================================
# LAST TRADES
# =========================================

st.subheader(
    "📜 Trade History"
)

file_name = "data/history/mt5_trade_history.csv"

if os.path.exists(file_name):

    df = pd.read_csv(file_name)

    if "profit" in df.columns:

        total_profit = pd.to_numeric(

            df["profit"],

            errors="coerce"

        ).sum()

        st.metric(

            "💰 Total Profit",

            round(total_profit, 2)

        )

    st.dataframe(

        df.tail(20),

        use_container_width=True

    )

# =========================================
# EQUITY CURVE
# =========================================

# =========================================
# ENGINE COMPARISON
# =========================================

st.subheader(
    "⚔ Engine Comparison"
)

comparison_data = []

for engine, data in engine_stats.items():

    comparison_data.append({

        "Engine": engine,

        "Profit": data["profit"],

        "WinRate": data["winrate"],

        "Trades": data["trades"]

    })

comparison_df = pd.DataFrame(
    comparison_data
)

# =========================================
# PROFIT CHART
# =========================================

if not comparison_df.empty:

    profit_fig = px.bar(

        comparison_df,

        x="Engine",

        y="Profit",

        title="Engine Profit Comparison"

    )

    st.plotly_chart(

        profit_fig,

        use_container_width=True

    )

    # =========================================
    # WINRATE CHART
    # =========================================

    winrate_fig = px.bar(

        comparison_df,

        x="Engine",

        y="WinRate",

        title="Engine WinRate Comparison"

    )

    st.plotly_chart(

        winrate_fig,

        use_container_width=True

    )

else:

    st.info("No engine comparison data yet")
st.subheader(
    "📈 Equity Curve"
)

if os.path.exists(file_name):

    chart_df = pd.read_csv(
        file_name
    )

    if "profit" in chart_df.columns:

        chart_df["profit"] = pd.to_numeric(

            chart_df["profit"],

            errors="coerce"

        )

        chart_df["equity"] = (

            chart_df["profit"]

            .cumsum()

        )

        chart_df["peak"] = (

        chart_df["equity"]

         .cummax()

        )

        chart_df["drawdown"] = (

        chart_df["equity"]

        -

        chart_df["peak"]

        )

        max_dd = round(

        chart_df["drawdown"].min(),

         2

        )

        st.metric(

            "📉 Max Drawdown",

        max_dd

        )

        fig = px.line(

            chart_df,

            y="equity",

            title="AI Bot Equity Curve"

        )

        st.plotly_chart(

            fig,

            use_container_width=True

        )
# =========================================
# AUTO REFRESH
# =========================================

from streamlit_autorefresh import st_autorefresh

st_autorefresh(
    interval=refresh * 1000,
    key="dashboard_refresh"
)
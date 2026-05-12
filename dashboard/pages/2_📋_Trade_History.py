"""
Trade History Page - With Interactive Charts
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

from database.db import DatabaseManager
from core.data_fetcher import DataFetcher
from config.settings import INITIAL_CAPITAL

st.set_page_config(page_title="Trade History", page_icon="📋", layout="wide")
db = DatabaseManager()
data_fetcher = DataFetcher()

st.title("📋 Trade History")
st.markdown("---")

all_trades = db.get_all_trades()

if not all_trades:
    st.info("No trades yet. Use the Zone Scanner to find and take trades!")
    st.stop()

df = pd.DataFrame(all_trades)

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    status = st.selectbox("Status", ["All", "OPEN", "CLOSED"])
with col2:
    symbols = ["All"] + list(df['symbol'].unique())
    symbol_filter = st.selectbox("Symbol", symbols)
with col3:
    strategies = ["All"] + list(df['strategy'].dropna().unique())
    strategy = st.selectbox("Strategy", strategies)

filtered = df.copy()
if status != "All":
    filtered = filtered[filtered['status'] == status]
if symbol_filter != "All":
    filtered = filtered[filtered['symbol'] == symbol_filter]
if strategy != "All":
    filtered = filtered[filtered['strategy'] == strategy]

st.metric("Showing", f"{len(filtered)} trades")


def create_trade_chart(trade_row):
    """Create candlestick chart with trade levels overlay."""
    symbol = trade_row['symbol']
    entry_price = trade_row['entry_price']
    stop_loss = trade_row.get('stop_loss', 0)
    target = trade_row.get('target', 0)
    exit_price = trade_row.get('exit_price')
    side = trade_row['side']
    trade_status = trade_row['status']
    entry_time = trade_row.get('entry_time', '')

    # Determine lookback period
    if trade_status == "CLOSED" and trade_row.get('exit_time'):
        # For closed trades, show data from before entry to after exit
        period = "5d"
    else:
        # For open trades, show recent data
        period = "5d"

    # Fetch chart data
    try:
        data = data_fetcher.get_data(symbol, "15m", period)
        if data is None or data.empty:
            return None
    except Exception:
        return None

    # Create candlestick chart
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f'{symbol} - Trade View', 'Volume'),
        row_heights=[0.8, 0.2]
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=list(range(len(data))),
        open=data['Open'], high=data['High'],
        low=data['Low'], close=data['Close'],
        name='Price',
        increasing_line_color='#26A69A',
        decreasing_line_color='#EF5350'
    ), row=1, col=1)

    # Volume bars
    colors = ['#26A69A' if c >= o else '#EF5350'
              for c, o in zip(data['Close'], data['Open'])]
    fig.add_trace(go.Bar(
        x=list(range(len(data))), y=data['Volume'],
        marker_color=colors, opacity=0.5, name='Volume'
    ), row=2, col=1)

    # Entry price line
    fig.add_hline(
        y=entry_price, line_dash="solid", line_color="#2196F3", line_width=2,
        annotation_text=f"Entry: ₹{entry_price:.2f}",
        annotation_position="right", row=1, col=1
    )

    # Stop Loss line
    if stop_loss and stop_loss > 0:
        fig.add_hline(
            y=stop_loss, line_dash="dash", line_color="#F44336", line_width=2,
            annotation_text=f"SL: ₹{stop_loss:.2f}",
            annotation_position="right", row=1, col=1
        )

    # Target line
    if target and target > 0:
        fig.add_hline(
            y=target, line_dash="dash", line_color="#4CAF50", line_width=2,
            annotation_text=f"Target: ₹{target:.2f}",
            annotation_position="right", row=1, col=1
        )

    # Exit price line (for closed trades)
    if trade_status == "CLOSED" and exit_price:
        exit_color = "#4CAF50" if (trade_row.get('pnl', 0) or 0) > 0 else "#F44336"
        fig.add_hline(
            y=exit_price, line_dash="dot", line_color=exit_color, line_width=2,
            annotation_text=f"Exit: ₹{exit_price:.2f}",
            annotation_position="left", row=1, col=1
        )

    # Current market price (for open trades)
    if trade_status == "OPEN":
        try:
            current_price = data_fetcher.get_current_price(symbol)
            if current_price > 0:
                fig.add_hline(
                    y=current_price, line_dash="dashdot", line_color="#FFD700",
                    line_width=2,
                    annotation_text=f"CMP: ₹{current_price:.2f}",
                    annotation_position="left", row=1, col=1
                )
        except Exception:
            pass

    # Zone shading (derive from entry/SL)
    if side == "BUY" and stop_loss and stop_loss > 0:
        # Demand zone: between SL and entry
        zone_bottom = stop_loss
        zone_top = entry_price
        fig.add_hrect(
            y0=zone_bottom, y1=zone_top,
            fillcolor="rgba(38,166,154,0.1)",
            line=dict(color="rgba(38,166,154,0.4)", width=1),
            row=1, col=1
        )
    elif side == "SELL" and stop_loss and stop_loss > 0:
        # Supply zone: between entry and SL
        zone_bottom = entry_price
        zone_top = stop_loss
        fig.add_hrect(
            y0=zone_bottom, y1=zone_top,
            fillcolor="rgba(239,83,80,0.1)",
            line=dict(color="rgba(239,83,80,0.4)", width=1),
            row=1, col=1
        )

    # Layout
    fig.update_layout(
        height=450,
        showlegend=False,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        margin=dict(l=40, r=40, t=40, b=20),
        paper_bgcolor='#0E1117',
        plot_bgcolor='#0E1117'
    )
    fig.update_xaxes(showgrid=True, gridcolor='#1E1E1E')
    fig.update_yaxes(showgrid=True, gridcolor='#1E1E1E')

    return fig


# Display trades with charts
for idx, row in filtered.iterrows():
    trade = row.to_dict()
    pnl = trade.get('pnl', 0) or 0
    pnl_str = f"₹{pnl:+,.2f}" if trade['status'] == 'CLOSED' else "OPEN"

    # Trade header
    icon = "🟢" if trade['side'] == "BUY" else "🔴"
    status_icon = "✅" if pnl > 0 else "❌" if pnl < 0 else "⏳"

    header = (
        f"{icon} {trade['symbol']} | {trade['side']} | "
        f"Entry: ₹{trade['entry_price']:.2f} | "
        f"{status_icon} {pnl_str}"
    )

    with st.expander(header, expanded=False):
        # Trade details
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📍 Entry", f"₹{trade['entry_price']:.2f}")
        c2.metric("🛑 Stop Loss", f"₹{trade.get('stop_loss', 0):.2f}")
        c3.metric("🎯 Target", f"₹{trade.get('target', 0):.2f}")
        if trade['status'] == 'CLOSED':
            c4.metric("💰 P&L", f"₹{pnl:+,.2f}",
                      delta=f"{trade.get('pnl_percent', 0):.2f}%")
        else:
            c4.metric("📊 Status", "OPEN")

        # Additional info
        col_a, col_b = st.columns(2)
        with col_a:
            st.caption(f"**Strategy:** {trade.get('strategy', 'N/A')}")
            st.caption(f"**Quantity:** {trade.get('quantity', 0)}")
            st.caption(f"**Entry Time:** {trade.get('entry_time', 'N/A')}")
        with col_b:
            if trade['status'] == 'CLOSED':
                st.caption(f"**Exit Time:** {trade.get('exit_time', 'N/A')}")
                st.caption(f"**Exit Price:** ₹{trade.get('exit_price', 0):.2f}")

        # Reasoning
        if trade.get('reason'):
            with st.container():
                st.text(trade['reason'][:500])

        # Chart
        st.markdown("#### 📈 Chart")
        with st.spinner(f"Loading chart for {trade['symbol']}..."):
            fig = create_trade_chart(trade)
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{idx}")
            else:
                st.warning("Could not load chart data for this symbol.")

st.markdown("---")

# Download button
csv = filtered.to_csv(index=False)
st.download_button(
    "📥 Download CSV", data=csv,
    file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)
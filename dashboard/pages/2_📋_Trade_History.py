"""
Trade History Page - With Interactive Trade Journey Charts
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz

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


def parse_time(time_str):
    """Parse timestamp string to datetime."""
    if not time_str:
        return None
    try:
        if isinstance(time_str, datetime):
            return time_str
        # Try various formats
        for fmt in ["%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue
        return pd.to_datetime(time_str)
    except Exception:
        return None


def create_trade_chart(trade_row, timeframe="5m"):
    """Create chart like Zone Scanner style - zone rectangle + Entry/SL/Target lines.
    User can switch timeframes to see when market touched the zone."""
    symbol = trade_row['symbol']
    entry_price = trade_row['entry_price']
    stop_loss = trade_row.get('stop_loss', 0) or 0
    target = trade_row.get('target', 0) or 0
    exit_price = trade_row.get('exit_price')
    side = trade_row['side']
    trade_status = trade_row['status']

    entry_time = parse_time(trade_row.get('entry_time', ''))
    exit_time = parse_time(trade_row.get('exit_time', ''))

    # Fetch data
    period_map = {"2m": "1d", "3m": "2d", "5m": "5d", "15m": "5d"}
    period = period_map.get(timeframe, "5d")

    try:
        data = data_fetcher.get_data(symbol, timeframe, period)
        if data is None or data.empty:
            return None
    except Exception:
        return None

    # Find entry and exit candle indices
    entry_idx = None
    exit_idx = None

    if entry_time:
        for i, ts in enumerate(data.index):
            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
            et_naive = entry_time.replace(tzinfo=None) if entry_time.tzinfo else entry_time
            if ts_naive >= et_naive:
                entry_idx = i
                break

    if exit_time:
        for i, ts in enumerate(data.index):
            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts
            xt_naive = exit_time.replace(tzinfo=None) if exit_time.tzinfo else exit_time
            if ts_naive >= xt_naive:
                exit_idx = i
                break

    if entry_idx is None:
        entry_idx = max(0, len(data) - 40)
    if exit_idx is None and trade_status == "CLOSED":
        exit_idx = len(data) - 1

    # Show from 15 candles before entry to end
    chart_start = max(0, entry_idx - 15)
    chart_end = min(len(data), (exit_idx + 10) if exit_idx else len(data))
    chart_data = data.iloc[chart_start:chart_end].reset_index(drop=True)
    entry_idx_rel = entry_idx - chart_start
    exit_idx_rel = (exit_idx - chart_start) if exit_idx else None

    if chart_data.empty:
        return None

    fig = go.Figure()
    x_vals = list(range(len(chart_data)))

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=x_vals,
        open=chart_data['Open'], high=chart_data['High'],
        low=chart_data['Low'], close=chart_data['Close'],
        name='Price',
        increasing_line_color='#26A69A',
        decreasing_line_color='#EF5350'
    ))

    # === ZONE RECTANGLE (like Zone Scanner) ===
    # Zone extends from entry_idx to end of chart
    zone_color = "rgba(38,166,154,0.15)" if side == "BUY" else "rgba(239,83,80,0.15)"
    zone_border = "rgba(38,166,154,0.8)" if side == "BUY" else "rgba(239,83,80,0.8)"

    if side == "BUY" and stop_loss > 0:
        # Demand zone: SL to Entry
        fig.add_shape(type="rect",
                      x0=entry_idx_rel, x1=len(chart_data) - 1,
                      y0=stop_loss, y1=entry_price,
                      fillcolor=zone_color, line=dict(color=zone_border, width=1))
        # Zone label
        fig.add_annotation(x=entry_idx_rel + 2, y=entry_price,
                           text=f"DEMAND ZONE", showarrow=False,
                           font=dict(size=9, color=zone_border))
    elif side == "SELL" and stop_loss > 0:
        # Supply zone: Entry to SL
        fig.add_shape(type="rect",
                      x0=entry_idx_rel, x1=len(chart_data) - 1,
                      y0=entry_price, y1=stop_loss,
                      fillcolor=zone_color, line=dict(color=zone_border, width=1))
        fig.add_annotation(x=entry_idx_rel + 2, y=entry_price,
                           text=f"SUPPLY ZONE", showarrow=False,
                           font=dict(size=9, color=zone_border))

    # === Entry / SL / Target lines (like Zone Scanner) ===
    fig.add_hline(y=entry_price, line_dash="dash", line_color="#2196F3", line_width=1,
                  annotation_text=f"Entry: {entry_price}", annotation_position="right")
    if stop_loss > 0:
        fig.add_hline(y=stop_loss, line_dash="dash", line_color="#F44336", line_width=1,
                      annotation_text=f"SL: {stop_loss}", annotation_position="right")
    if target > 0:
        fig.add_hline(y=target, line_dash="dash", line_color="#4CAF50", line_width=1,
                      annotation_text=f"Target: {target}", annotation_position="right")

    # === EXIT MARKER (for closed trades) ===
    if trade_status == "CLOSED" and exit_idx_rel is not None and exit_price:
        pnl = trade_row.get('pnl', 0) or 0
        exit_color = "#4CAF50" if pnl > 0 else "#F44336"
        fig.add_trace(go.Scatter(
            x=[exit_idx_rel], y=[exit_price],
            mode='markers+text', marker=dict(size=14, color=exit_color, symbol='x'),
            text=["TARGET HIT" if pnl > 0 else "SL HIT"],
            textposition="top center", textfont=dict(size=9, color=exit_color),
            showlegend=False
        ))

    # === CURRENT PRICE (for open trades) ===
    if trade_status == "OPEN" and len(chart_data) > 0:
        current_price = float(chart_data['Close'].iloc[-1])
        fig.add_trace(go.Scatter(
            x=[len(chart_data) - 1], y=[current_price],
            mode='markers+text', marker=dict(size=10, color="#FFD700", symbol='diamond'),
            text=[f"CMP: {current_price:.1f}"],
            textposition="top center", textfont=dict(size=9, color="#FFD700"),
            showlegend=False
        ))

    # Layout
    fig.update_layout(
        height=500, showlegend=False,
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        margin=dict(l=40, r=40, t=40, b=20),
        paper_bgcolor='#0E1117', plot_bgcolor='#0E1117'
    )
    fig.update_xaxes(showgrid=True, gridcolor='#1E1E1E')
    fig.update_yaxes(showgrid=True, gridcolor='#1E1E1E')

    return fig


# Display trades with charts
for idx, row in filtered.iterrows():
    trade = row.to_dict()
    pnl = trade.get('pnl', 0) or 0
    pnl_str = f"₹{pnl:+,.2f}" if trade['status'] == 'CLOSED' else "OPEN"

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
        c2.metric("🛑 Stop Loss", f"₹{trade.get('stop_loss', 0) or 0:.2f}")
        c3.metric("🎯 Target", f"₹{trade.get('target', 0) or 0:.2f}")
        if trade['status'] == 'CLOSED':
            c4.metric("💰 P&L", f"₹{pnl:+,.2f}",
                      delta=f"{(trade.get('pnl_percent') or 0):.2f}%")
        else:
            c4.metric("📊 Status", "OPEN")

        # Info columns
        col_a, col_b = st.columns(2)
        with col_a:
            st.caption(f"**Strategy:** {trade.get('strategy', 'N/A')}")
            st.caption(f"**Quantity:** {trade.get('quantity', 0)}")
            st.caption(f"**Entry Time:** {trade.get('entry_time', 'N/A')}")
        with col_b:
            if trade['status'] == 'CLOSED':
                st.caption(f"**Exit Time:** {trade.get('exit_time', 'N/A')}")
                st.caption(f"**Exit Price:** ₹{(trade.get('exit_price') or 0):.2f}")

        # Reasoning
        if trade.get('reason'):
            with st.container():
                st.text(str(trade['reason'])[:500])

        # Delete button
        col_del, col_tf, _ = st.columns([1, 2, 3])
        with col_del:
            if st.button("🗑️ Delete Trade", key=f"del_{idx}", type="secondary"):
                db.delete_trade(trade['id'])
                st.success(f"Trade #{trade['id']} deleted!")
                st.rerun()

        # Timeframe selector and Chart
        st.markdown("#### 📈 Trade Journey Chart")
        with col_tf:
            tf = st.radio("Timeframe", ["5m", "3m", "15m"],
                          horizontal=True, key=f"tf_{idx}")

        with st.spinner(f"Loading {tf} chart for {trade['symbol']}..."):
            fig = create_trade_chart(trade, timeframe=tf)
            if fig:
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{idx}_{tf}")
            else:
                st.warning("Could not load chart data. Market may be closed or data unavailable.")

st.markdown("---")
csv = filtered.to_csv(index=False)
st.download_button(
    "📥 Download CSV", data=csv,
    file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)

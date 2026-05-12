"""
Trading Bot Dashboard - Home Page
==================================
Multi-page Streamlit app. Pages are auto-discovered from dashboard/pages/ folder.

Run with: streamlit run dashboard/app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL, SYMBOLS, NIFTY_50

st.set_page_config(page_title="Trading Bot", page_icon="📈", layout="wide")
db = DatabaseManager()

# === HOME PAGE ===
st.title("📈 Trading Bot Dashboard")
st.markdown("### Supply & Demand Zone Trading System")
st.markdown("---")

# Quick Stats
metrics = db.get_performance_metrics()
open_trades = db.get_open_trades()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💰 Capital", f"₹{INITIAL_CAPITAL:,.0f}")
col2.metric("📊 Total Trades", metrics['total_trades'])
col3.metric("🏆 Win Rate", f"{metrics['win_rate']:.1f}%")
col4.metric("💹 Total P&L", f"₹{metrics['total_pnl']:,.2f}")
col5.metric("📍 Open Positions", len(open_trades))

st.markdown("---")

# Navigation
st.subheader("🧭 Quick Navigation")

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("""
    ### 🎯 Zone Scanner
    Find supply/demand zones across Nifty 50 stocks using multi-timeframe analysis.
    
    **→ Go to sidebar → Zone Scanner**
    """)

with col_b:
    st.markdown("""
    ### 📋 Trade History
    View all your paper trades with filters by symbol, strategy, and status.
    
    **→ Go to sidebar → Trade History**
    """)

with col_c:
    st.markdown("""
    ### 📈 Performance
    Track your equity curve, win rate, profit factor, and drawdown.
    
    **→ Go to sidebar → Performance**
    """)

st.markdown("---")

# Strategy Overview
st.subheader("📐 Strategy: Supply & Demand Zones")
st.markdown("""
| Setting | Value |
|---------|-------|
| **Timeframes** | 15m (zones) → 5m (trend) → 2m (entry) |
| **Risk:Reward** | 1:3 |
| **Min Score** | 80/100 |
| **Scoring** | Freshness (40) + Leg-out (30) + Base (30) |
| **Watchlist** | Nifty 50 (50 stocks) |
| **Capital** | ₹1,00,000 (paper) |
""")

st.markdown("---")

# Open Positions
if open_trades:
    st.subheader("🟢 Open Positions")
    import pandas as pd
    df_open = pd.DataFrame(open_trades)
    cols = ['symbol', 'side', 'quantity', 'entry_price', 'stop_loss', 'target', 'strategy']
    available_cols = [c for c in cols if c in df_open.columns]
    st.dataframe(df_open[available_cols])

# Sidebar
with st.sidebar:
    st.markdown("## 📈 Trading Bot")
    st.markdown(f"**Stocks:** {len(NIFTY_50)} (Nifty 50)")
    st.markdown(f"**Strategy:** S&D Zones")
    st.markdown(f"**Mode:** Paper Trading")
    st.markdown("---")
    st.markdown("### Pages")
    st.markdown("- 🎯 Zone Scanner")
    st.markdown("- 📋 Trade History")
    st.markdown("- 📈 Performance")
    st.markdown("---")
    if st.button("🗑️ Clear All Trades"):
        db.clear_all_trades()
        st.success("Cleared!")
        st.rerun()
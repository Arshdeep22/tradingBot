"""
Performance Analytics Page
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL

st.set_page_config(page_title="Performance", page_icon="📈", layout="wide")
db = DatabaseManager()

st.title("📈 Performance Analytics")
st.markdown("---")

metrics = db.get_performance_metrics()
closed_trades = db.get_closed_trades()

# KPIs — row 1
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total P&L", f"₹{metrics['total_pnl']:,.2f}",
          delta=f"{metrics['total_pnl']/INITIAL_CAPITAL*100:.2f}%" if metrics['total_pnl'] != 0 else None)
c2.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
c3.metric("Total Trades", metrics['total_trades'])
pf = metrics['profit_factor']
c4.metric("Profit Factor", f"{pf:.2f}" if pf != float('inf') else "∞")
c5.metric("Max Drawdown", f"₹{metrics['max_drawdown']:,.2f}")

# KPIs — row 2: risk-adjusted returns
c6, c7, _, _, _ = st.columns(5)
sharpe = metrics.get('sharpe_ratio', 0.0)
sortino = metrics.get('sortino_ratio', 0.0)
c6.metric("Sharpe Ratio", f"{sharpe:.2f}" if sharpe != float('inf') else "∞",
          help="Annualised Sharpe (>1 = good, >2 = great). Uses per-trade P&L as returns proxy.")
c7.metric("Sortino Ratio", f"{sortino:.2f}" if sortino != float('inf') else "∞",
          help="Like Sharpe but only penalises downside volatility. Higher is better.")

st.markdown("---")

if closed_trades:
    df = pd.DataFrame(closed_trades)

    col_l, col_r = st.columns(2)

    with col_l:
        df['cum_pnl'] = df['pnl'].cumsum()
        df['equity'] = INITIAL_CAPITAL + df['cum_pnl']
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(len(df))), y=df['equity'],
                                 mode='lines+markers', line=dict(color='#636EFA', width=2)))
        fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash", line_color="gray")
        fig.update_layout(title="Equity Curve", height=300, xaxis_title="Trade #", yaxis_title="₹")
        st.plotly_chart(fig, key="eq")

    with col_r:
        if metrics['total_trades'] > 0:
            fig2 = go.Figure(data=[go.Pie(
                labels=['Winners', 'Losers'],
                values=[metrics['winning_trades'], metrics['losing_trades']],
                marker_colors=['#00CC96', '#EF553B'], hole=0.4)])
            fig2.update_layout(title="Win/Loss", height=300)
            st.plotly_chart(fig2, key="pie")

    # PnL bar
    colors = ['green' if x > 0 else 'red' for x in df['pnl']]
    fig3 = go.Figure(data=[go.Bar(x=list(range(len(df))), y=df['pnl'], marker_color=colors)])
    fig3.update_layout(title="P&L Per Trade", height=250, xaxis_title="Trade #", yaxis_title="₹")
    st.plotly_chart(fig3, key="pnl")

    # Stats
    st.subheader("Key Statistics")
    sortino_display = f"{metrics['sortino_ratio']:.2f}" if metrics['sortino_ratio'] != float('inf') else "∞"
    st.table(pd.DataFrame({
        "Metric": ["Avg Win", "Avg Loss", "Max Profit", "Max Loss", "Avg P&L", "Sharpe Ratio", "Sortino Ratio"],
        "Value": [f"₹{metrics['avg_win']:,.2f}", f"₹{metrics['avg_loss']:,.2f}",
                  f"₹{metrics['max_profit']:,.2f}", f"₹{metrics['max_loss']:,.2f}",
                  f"₹{metrics['avg_pnl']:,.2f}", f"{metrics['sharpe_ratio']:.2f}", sortino_display]
    }))
else:
    st.info("No closed trades yet. Take trades from the Zone Scanner to see analytics!")
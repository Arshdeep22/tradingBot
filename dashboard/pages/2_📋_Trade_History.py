"""
Trade History Page
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
from datetime import datetime

from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL

st.set_page_config(page_title="Trade History", page_icon="📋", layout="wide")
db = DatabaseManager()

st.title("📋 Trade History")
st.markdown("---")

all_trades = db.get_all_trades()

if all_trades:
    df = pd.DataFrame(all_trades)

    col1, col2, col3 = st.columns(3)
    with col1:
        status = st.selectbox("Status", ["All", "OPEN", "CLOSED"])
    with col2:
        symbols = ["All"] + list(df['symbol'].unique())
        symbol = st.selectbox("Symbol", symbols)
    with col3:
        strategies = ["All"] + list(df['strategy'].dropna().unique())
        strategy = st.selectbox("Strategy", strategies)

    filtered = df.copy()
    if status != "All":
        filtered = filtered[filtered['status'] == status]
    if symbol != "All":
        filtered = filtered[filtered['symbol'] == symbol]
    if strategy != "All":
        filtered = filtered[filtered['strategy'] == strategy]

    st.metric("Showing", f"{len(filtered)} trades")
    st.dataframe(filtered, height=500)

    csv = filtered.to_csv(index=False)
    st.download_button("📥 Download CSV", data=csv,
                       file_name=f"trades_{datetime.now().strftime('%Y%m%d')}.csv",
                       mime="text/csv")
else:
    st.info("No trades yet. Use the Zone Scanner to find and take trades!")
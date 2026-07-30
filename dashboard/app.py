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

st.set_page_config(page_title="Trading Bot Agent", page_icon="🤖", layout="wide")

# === HOME PAGE ===
st.title("🤖 Autonomous Trading Agent")
st.markdown("### Monitoring & Debugging Console")
st.markdown("---")

st.subheader("🧭 Available Pages")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("""
    ### 🤖 Agent Monitor
    Live view of the autonomous optimizer:
    - Current iteration & phase (A / B / C)
    - Recent runs, decisions, and trades
    - Streaming runtime logs
    - Tool-invocation activity

    **→ Open from sidebar → *Agent Monitor***
    """)

with col_b:
    st.markdown("""
    ### 🗄️ Agent DB Explorer
    Raw access to every table in `database/agent.db`:
    - Runs, trades, decisions, memory, embeddings
    - Filter, sort, paginate any table
    - Inspect trajectories and blocked approaches

    **→ Open from sidebar → *Agent DB Explorer***
    """)

st.markdown("---")

# Sidebar
with st.sidebar:
    st.markdown("## 🤖 Trading Agent")
    st.markdown("**Mode:** Autonomous Optimizer")
    st.markdown("**DB:** `database/agent.db`")
    st.markdown("---")
    st.markdown("### Pages")
    st.markdown("- 🤖 Agent Monitor")
    st.markdown("- 🗄️ Agent DB Explorer")
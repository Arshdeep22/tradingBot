"""Trade Monitor Page — Live trade management with bot runner controls."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
from datetime import datetime

import streamlit as st

from core.data_fetcher import DataFetcher
from core.bot_runner import BotRunner
from database.db import DatabaseManager

st.set_page_config(page_title="Trade Monitor", page_icon="📈", layout="wide")

db = DatabaseManager()
data_fetcher = DataFetcher()

# ── Session-state setup ────────────────────────────────────────────────────
if "bot_runner" not in st.session_state:
    st.session_state.bot_runner = BotRunner(db, data_fetcher, interval_seconds=60)
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False
if "bot_events" not in st.session_state:
    st.session_state.bot_events = []

runner: BotRunner = st.session_state.bot_runner

# ── Header ─────────────────────────────────────────────────────────────────
st.title("📈 Trade Monitor")
st.caption("Live trade management: breakeven, trailing stops, time-based exits")

# ── Bot controls ───────────────────────────────────────────────────────────
st.subheader("Bot Runner")
col_status, col_start, col_stop, col_run_once = st.columns([2, 1, 1, 1])

_is_running = st.session_state.bot_running
with col_status:
    if _is_running:
        st.success("🟢 RUNNING — polls every 60s")
    else:
        st.error("🔴 STOPPED")

with col_start:
    if st.button("▶ Start", disabled=_is_running, use_container_width=True):
        st.session_state.bot_running = True
        runner.running = True
        st.rerun()

with col_stop:
    if st.button("⏹ Stop", disabled=not _is_running, use_container_width=True):
        st.session_state.bot_running = False
        runner.stop()
        st.rerun()

with col_run_once:
    if st.button("🔄 Run Once", use_container_width=True):
        with st.spinner("Running management cycle..."):
            new_events = runner.run_once()
        st.session_state.bot_events = new_events + st.session_state.bot_events
        if new_events:
            st.success(f"✅ {len(new_events)} event(s) applied")
        else:
            st.info("No actions needed — all trades within limits")
        st.rerun()

# Auto-cycle when running
if st.session_state.bot_running:
    new_events = runner.run_once()
    st.session_state.bot_events = new_events + st.session_state.bot_events
    time.sleep(1)   # brief pause before rerun (prevents hammering yfinance)
    st.rerun()

st.markdown("---")

# ── Open trades table ──────────────────────────────────────────────────────
st.subheader("Open Trades")
open_trades = db.get_open_trades_with_management_state()

if not open_trades:
    st.info("No open trades. Use the Zone Scanner to enter a trade.")
else:
    # Build display rows with live price
    rows = []
    for t in open_trades:
        try:
            price = data_fetcher.get_current_price(t["symbol"]) or t["entry_price"]
        except Exception:
            price = t["entry_price"]

        ep = t["entry_price"]
        current_sl = t.get("current_sl") or t["stop_loss"]
        side = t["side"]
        qty = t["quantity"]
        pnl_pct = ((price - ep) / ep * 100) if side == "BUY" else ((ep - price) / ep * 100)
        pnl_val = (price - ep) * qty if side == "BUY" else (ep - price) * qty

        entry_time = t.get("entry_time", "")[:16] if t.get("entry_time") else "—"

        rows.append({
            "ID": t["id"],
            "Symbol": t["symbol"],
            "Side": side,
            "Qty": qty,
            "Entry": f"₹{ep:.2f}",
            "Current": f"₹{price:.2f}",
            "SL": f"₹{current_sl:.2f}",
            "Target": f"₹{t['target']:.2f}",
            "P&L": f"{'▲' if pnl_val >= 0 else '▼'} ₹{abs(pnl_val):.0f} ({pnl_pct:+.2f}%)",
            "BE": "✅" if t.get("breakeven_applied") else "—",
            "Partial": "✅" if t.get("partial_taken") else "—",
            "Since": entry_time,
        })

    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df.set_index("ID"), use_container_width=True)

    # Manual close button per trade
    st.markdown("**Manual close:**")
    for t in open_trades:
        col_sym, col_close = st.columns([4, 1])
        col_sym.write(f"{t['symbol']} ({t['side']}) — Entry ₹{t['entry_price']:.2f}")
        with col_close:
            if st.button(f"Close {t['id']}", key=f"close_{t['id']}"):
                try:
                    price = data_fetcher.get_current_price(t["symbol"]) or t["entry_price"]
                except Exception:
                    price = t["entry_price"]
                db.close_trade_by_id(t["id"], price, reason="Manual close from Trade Monitor")
                st.success(f"Closed {t['symbol']} @ ₹{price:.2f}")
                st.rerun()

st.markdown("---")

# ── Recent events log ──────────────────────────────────────────────────────
st.subheader("Recent Events")
all_events = runner.recent_events(20) + st.session_state.bot_events[:20]
all_events = all_events[:20]

if not all_events:
    st.caption("No events yet — click Run Once or wait for the next cycle.")
else:
    for ev in all_events:
        _icon = {"FULL_EXIT": "🔴", "PARTIAL_EXIT": "🟡", "NONE": "⚪"}.get(ev.action, "🔵")
        st.markdown(
            f"{_icon} **{ev.symbol}** | {ev.action} @ ₹{ev.price:.2f} — _{ev.reason}_"
        )

st.markdown("---")
st.caption(
    f"Last refreshed: {datetime.now().strftime('%H:%M:%S')} | "
    f"Interval: {runner.interval_seconds}s | "
    "Auto-refresh active when bot is running"
)

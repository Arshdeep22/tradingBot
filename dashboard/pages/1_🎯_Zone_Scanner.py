"""
Zone Scanner Page - Dedicated full-page zone scanner
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.data_fetcher import DataFetcher
from strategies.zone_scanner import ZoneScanner, Zone
from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL, SYMBOLS, NIFTY_50
from core.llm_advisor import StrategyMemory

st.set_page_config(page_title="Zone Scanner", page_icon="🎯", layout="wide")

# Initialize
data_fetcher = DataFetcher()
zone_scanner = ZoneScanner(timeframe="15m")
db = DatabaseManager()
_memory = StrategyMemory()


def create_chart(data, zones, symbol):
    """Candlestick chart with zones (no volume)"""
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=list(range(len(data))), open=data['Open'], high=data['High'],
        low=data['Low'], close=data['Close'], name='Price',
        increasing_line_color='#26A69A', decreasing_line_color='#EF5350'
    ))

    for zone in zones:
        fc = "rgba(38,166,154,0.15)" if zone.zone_type == "DEMAND" else "rgba(239,83,80,0.15)"
        lc = "rgba(38,166,154,0.8)" if zone.zone_type == "DEMAND" else "rgba(239,83,80,0.8)"

        fig.add_shape(type="rect", x0=zone.formed_at_index, x1=len(data)-1,
                      y0=zone.zone_bottom, y1=zone.zone_top,
                      fillcolor=fc, line=dict(color=lc, width=1))

        fig.add_annotation(x=zone.formed_at_index+2,
                           y=zone.zone_top if zone.zone_type=="DEMAND" else zone.zone_bottom,
                           text=f"{zone.zone_type} ({zone.score})", showarrow=False,
                           font=dict(size=9, color=lc))

        fig.add_hline(y=zone.entry, line_dash="dash", line_color="#2196F3", line_width=1,
                      annotation_text=f"Entry: {zone.entry}", annotation_position="right")
        fig.add_hline(y=zone.stop_loss, line_dash="dash", line_color="#F44336", line_width=1,
                      annotation_text=f"SL: {zone.stop_loss}", annotation_position="right")
        fig.add_hline(y=zone.target, line_dash="dash", line_color="#4CAF50", line_width=1,
                      annotation_text=f"Target: {zone.target}", annotation_position="right")

    fig.update_layout(height=500, showlegend=False, xaxis_rangeslider_visible=False,
                      template="plotly_dark", margin=dict(l=40, r=40, t=40, b=20),
                      paper_bgcolor='#0E1117', plot_bgcolor='#0E1117')
    fig.update_xaxes(showgrid=True, gridcolor='#1E1E1E')
    fig.update_yaxes(showgrid=True, gridcolor='#1E1E1E')
    return fig


# === PAGE START ===
st.title("🎯 Zone Scanner")
st.caption("Multi-Timeframe Supply & Demand Zone Detection (15m → 5m → 2m)")

# Sidebar
with st.sidebar:
    st.header("Scanner Settings")

    watchlist = st.radio("Watchlist", ["Default (5)", "Nifty 50 (All)"], key="wl")
    available = SYMBOLS if watchlist == "Default (5)" else NIFTY_50

    selected = st.multiselect("Select Symbols", available,
                              default=available[:5] if len(available) > 5 else available,
                              key="zs_symbols")

    st.markdown("---")

    _has_ai = bool(_memory.best_params)
    _lp = _memory.live_params() if _has_ai else {"min_score": 80, "rr_ratio": 3.0, "max_base_candles": 5}
    use_ai_params = st.toggle("🤖 Use AI-Optimized Params", value=_has_ai, key="zs_ai", disabled=not _has_ai,
                              help="Uses the best parameters found by AI backtesting. Run AI Refinement on Test Strategy page first.")

    _score_default = _lp["min_score"] if use_ai_params else 80
    _rr_default = _lp["rr_ratio"] if use_ai_params else 3.0

    min_score = st.slider("Min Score", 50, 100, _score_default, 5, key="zs_min")
    rr_ratio = st.select_slider("Risk:Reward", options=[2.0, 2.5, 3.0, 4.0, 5.0], value=_rr_default, key="zs_rr")
    mtf_mode = st.checkbox("Multi-Timeframe (15m→5m→2m)", value=True, key="zs_mtf")

    if use_ai_params and _has_ai:
        st.info(f"Score={_lp['min_score']} | R:R={_lp['rr_ratio']} | Base={_lp['max_base_candles']} "
                f"(backtest WR: {_memory.best_win_rate:.1f}%)")

    st.markdown("---")
    scan = st.button("🔍 SCAN FOR ZONES", type="primary", use_container_width=True)

# Main
if scan:
    zone_scanner.min_score = min_score
    zone_scanner.rr_ratio = rr_ratio
    if use_ai_params and _has_ai:
        zone_scanner.max_base_candles = _lp["max_base_candles"]

    all_zones = []
    all_data = {}
    progress = st.progress(0, text="Scanning...")

    for idx, symbol in enumerate(selected):
        progress.progress((idx + 1) / len(selected), text=f"Scanning {symbol}...")
        try:
            if mtf_mode:
                zones = zone_scanner.multi_timeframe_scan(data_fetcher, symbol)
                data = data_fetcher.get_data(symbol, "15m", "5d")
            else:
                data = data_fetcher.get_data(symbol, "15m", "5d")
                zones = zone_scanner.detect_zones(data, symbol) if data is not None else []

            if data is not None:
                all_data[symbol] = data
            all_zones.extend(zones)
        except Exception as e:
            st.warning(f"Error scanning {symbol}: {e}")

    progress.empty()
    all_zones.sort(key=lambda z: z.score, reverse=True)
    st.session_state['zs_zones'] = all_zones
    st.session_state['zs_data'] = all_data

# Display
zones = st.session_state.get('zs_zones', [])
data_dict = st.session_state.get('zs_data', {})

if zones:
    st.success(f"✅ Found **{len(zones)}** qualifying zones across {len(data_dict)} stocks")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Demand", len([z for z in zones if z.zone_type == "DEMAND"]))
    c2.metric("🔴 Supply", len([z for z in zones if z.zone_type == "SUPPLY"]))
    c3.metric("🏆 Best", f"{zones[0].score}/100")
    c4.metric("📊 Total", len(zones))
    st.markdown("---")

    for i, zone in enumerate(zones):
        with st.expander(f"{'🟢' if zone.zone_type=='DEMAND' else '🔴'} #{i+1} | {zone.symbol} | {zone.zone_type} | Score: {zone.score}", expanded=(i < 3)):
            if zone.symbol in data_dict:
                st.plotly_chart(create_chart(data_dict[zone.symbol], [zone], zone.symbol), key=f"c_{i}")

            col1, col2, col3 = st.columns(3)
            col1.metric("📍 Entry", f"₹{zone.entry:.2f}")
            col2.metric("🛑 Stop Loss", f"₹{zone.stop_loss:.2f}")
            col3.metric("🎯 Target", f"₹{zone.target:.2f}")

            st.text(zone.reasoning)

            col_a, col_b, _ = st.columns([1, 1, 4])
            with col_a:
                if st.button("✅ Take Trade", key=f"t_{i}"):
                    qty = max(1, int((INITIAL_CAPITAL * 0.01) / max(abs(zone.entry - zone.stop_loss), 1)))
                    db.save_trade(symbol=zone.symbol,
                                  side="BUY" if zone.zone_type == "DEMAND" else "SELL",
                                  quantity=qty, entry_price=zone.entry,
                                  stop_loss=zone.stop_loss, target=zone.target,
                                  strategy="Supply Demand Zones", reason=zone.reasoning)
                    st.success(f"✅ Trade placed!")
            with col_b:
                if st.button("❌ Skip", key=f"s_{i}"):
                    pass

elif 'zs_zones' in st.session_state:
    st.warning("No qualifying zones found. Try lowering min score or scanning more stocks.")
else:
    st.info("👈 Configure settings and click **SCAN FOR ZONES** to start.")
    st.markdown("""
    ### How it works:
    1. Select stocks (Default 5 or full Nifty 50)
    2. Enable **Multi-Timeframe** for best results
    3. Click SCAN — agent analyzes 15m → 5m → 2m
    4. Review zones with charts, Entry/SL/Target
    5. Click "Take Trade" to paper trade the best ones
    """)
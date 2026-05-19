"""Zone Scanner Page — Professional Supply & Demand Zone Scanner"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.data_fetcher import DataFetcher
from core.market_data import fetch_market_conditions
from strategies.zone_scanner import ProfessionalZoneScanner, DEFAULT_CONFIG
from strategies.zone_mtf import detect_trend
from strategies.market_conditions import MarketRegime
from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL, SYMBOLS, NIFTY_50
from core.llm_advisor import StrategyMemory

st.set_page_config(page_title="Zone Scanner", page_icon="🎯", layout="wide")

data_fetcher = DataFetcher()
db = DatabaseManager()
_memory = StrategyMemory()


def create_chart(data, zones, symbol):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=list(range(len(data))), open=data["Open"], high=data["High"],
        low=data["Low"], close=data["Close"], name="Price",
        increasing_line_color="#26A69A", decreasing_line_color="#EF5350",
    ))
    for zone in zones:
        fc = "rgba(38,166,154,0.15)" if zone.zone_type == "DEMAND" else "rgba(239,83,80,0.15)"
        lc = "rgba(38,166,154,0.8)" if zone.zone_type == "DEMAND" else "rgba(239,83,80,0.8)"
        fig.add_shape(type="rect", x0=zone.formed_at_index, x1=len(data) - 1,
                      y0=zone.zone_bottom, y1=zone.zone_top,
                      fillcolor=fc, line=dict(color=lc, width=1))
        fig.add_annotation(x=zone.formed_at_index + 2, y=zone.zone_top,
                           text=f"{zone.pattern} ({zone.score}/60)", showarrow=False,
                           font=dict(size=9, color=lc))
        if zone.entry:
            fig.add_hline(y=zone.entry, line_dash="dash", line_color="#2196F3", line_width=1,
                          annotation_text=f"E:{zone.entry:.2f}", annotation_position="right")
        if zone.stop_loss:
            fig.add_hline(y=zone.stop_loss, line_dash="dash", line_color="#F44336", line_width=1,
                          annotation_text=f"SL:{zone.stop_loss:.2f}", annotation_position="right")
        if zone.target_2:
            fig.add_hline(y=zone.target_2, line_dash="dash", line_color="#4CAF50", line_width=1,
                          annotation_text=f"T2:{zone.target_2:.2f}", annotation_position="right")
    fig.update_layout(height=400, showlegend=False, xaxis_rangeslider_visible=False,
                      template="plotly_dark", margin=dict(l=40, r=40, t=30, b=20),
                      paper_bgcolor="#0E1117", plot_bgcolor="#0E1117")
    fig.update_xaxes(showgrid=True, gridcolor="#1E1E1E")
    fig.update_yaxes(showgrid=True, gridcolor="#1E1E1E")
    return fig


# === PAGE ===
st.title("🎯 Zone Scanner")
st.caption("Professional Supply & Demand Zone Detection  |  1H trend → 15m zones → 5m entry")

with st.sidebar:
    st.header("Scanner Settings")
    watchlist = st.radio("Watchlist", ["Default (5)", "Nifty 50 (All)"], key="wl")
    available = SYMBOLS if watchlist == "Default (5)" else NIFTY_50
    selected = st.multiselect("Select Symbols", available,
                              default=available[:5] if len(available) > 5 else available,
                              key="zs_symbols")
    st.markdown("---")

    _has_ai = bool(_memory.best_params)
    _lp = _memory.live_params() if _has_ai else {"min_score": 40, "rr_ratio": 2.0, "max_base_candles": 3}
    use_ai = st.toggle("🤖 AI-Optimized Params", value=_has_ai, key="zs_ai", disabled=not _has_ai)

    _score_default = min(60, max(20, int(_lp["min_score"]))) if use_ai else 40
    _rr_options = [1.5, 2.0, 2.5, 3.0, 4.0]
    _rr_default = float(_lp["rr_ratio"]) if use_ai and float(_lp["rr_ratio"]) in _rr_options else 2.0

    min_score = st.slider("Min Score (out of 60)", 20, 60, _score_default, 5, key="zs_min")
    rr_ratio = st.select_slider("Min Risk:Reward", options=_rr_options, value=_rr_default, key="zs_rr")
    mtf_mode = st.checkbox("Multi-Timeframe (1H→15m→5m)", value=True, key="zs_mtf")

    st.markdown("**Pattern Filter:**")
    col_p1, col_p2 = st.columns(2)
    show_dbr = col_p1.checkbox("DBR", value=True, key="dbr", help="Demand Reversal")
    show_rbd = col_p2.checkbox("RBD", value=True, key="rbd", help="Supply Reversal")
    show_rbr = col_p1.checkbox("RBR", value=True, key="rbr", help="Demand Continuation")
    show_dbd = col_p2.checkbox("DBD", value=True, key="dbd", help="Supply Continuation")

    st.markdown("---")
    scan = st.button("🔍 SCAN FOR ZONES", type="primary", use_container_width=True)
    is_news_day = st.checkbox("📰 News Day Override (RBI/Budget/Election)", value=False, key="news_day")

if scan:
    # Fetch market conditions (VIX + Nifty) before scanning
    with st.spinner("Checking market conditions..."):
        conditions = fetch_market_conditions(
            config=DEFAULT_CONFIG,
            is_news_day=st.session_state.get("news_day", False),
        )
    st.session_state["zs_conditions"] = conditions

    # Show regime banner
    _regime_colors = {
        "NORMAL": ("🟢", "green"),
        "HIGH_VOLATILITY": ("🟡", "orange"),
        "EXTREME_VOLATILITY": ("🔴", "red"),
        "STRONG_TREND_UP": ("📈", "green"),
        "STRONG_TREND_DOWN": ("📉", "red"),
        "GAP_DAY": ("⚡", "orange"),
        "NEWS_DAY": ("📰", "red"),
    }
    _icon, _color = _regime_colors.get(conditions.regime.value, ("⚪", "gray"))
    _vix_str = f"VIX {conditions.vix:.1f}" if conditions.vix else "VIX N/A"
    _nifty_str = f"Nifty {conditions.nifty_change_pct:+.2f}%"
    st.info(f"{_icon} Market: **{conditions.regime.value}** | {_vix_str} | {_nifty_str} | "
            f"SL×{conditions.sl_multiplier:.1f} | Size×{conditions.size_multiplier:.1f}")

    if not conditions.can_trade:
        st.error(f"🚫 Trading blocked: {conditions.skip_reason}")
        st.stop()

    scanner = ProfessionalZoneScanner(
        min_score_to_trade=min_score,
        default_rr_ratio=rr_ratio,
        min_rr_ratio=rr_ratio,
    )
    allowed = (["DBR"] if show_dbr else []) + (["RBD"] if show_rbd else []) + \
              (["RBR"] if show_rbr else []) + (["DBD"] if show_dbd else [])

    all_zones, all_data, trend_map = [], {}, {}
    progress = st.progress(0, text="Scanning...")

    for idx, symbol in enumerate(selected):
        progress.progress((idx + 1) / len(selected), text=f"Scanning {symbol}...")
        try:
            if mtf_mode:
                zones = scanner.multi_timeframe_scan(
                    data_fetcher, symbol, market_conditions=conditions
                )
                data = data_fetcher.get_data(symbol, "15m", "5d")
            else:
                data = data_fetcher.get_data(symbol, "15m", "5d")
                zones = scanner.detect_and_score(data, symbol) if data is not None else []

            trend = "SIDEWAYS"
            if data is not None and len(data) >= 50:
                trend = detect_trend(data.rename(columns={"Open": "open", "High": "high",
                                                          "Low": "low", "Close": "close"}))
            trend_map[symbol] = trend
            if data is not None:
                all_data[symbol] = data
            all_zones.extend([z for z in zones if z.pattern in allowed])
        except Exception as e:
            st.warning(f"Error scanning {symbol}: {e}")

    progress.empty()
    all_zones.sort(key=lambda z: z.score, reverse=True)
    st.session_state["zs_zones"] = all_zones
    st.session_state["zs_data"] = all_data
    st.session_state["zs_trends"] = trend_map

zones = st.session_state.get("zs_zones", [])
data_dict = st.session_state.get("zs_data", {})
trend_info = st.session_state.get("zs_trends", {})
last_conditions = st.session_state.get("zs_conditions", None)

# Show last market regime summary if available (persists between scans)
if last_conditions and "zs_zones" in st.session_state:
    _icon, _color = {"NORMAL": ("🟢", "normal"), "HIGH_VOLATILITY": ("🟡", "warning"),
                     "EXTREME_VOLATILITY": ("🔴", "error")}.get(
        last_conditions.regime.value, ("⚪", "info"))
    _vix_str = f"VIX {last_conditions.vix:.1f}" if last_conditions.vix else "VIX N/A"
    st.caption(f"{_icon} Last scan regime: **{last_conditions.regime.value}** | "
               f"{_vix_str} | Nifty {last_conditions.nifty_change_pct:+.2f}%")

if zones:
    st.success(f"✅ Found **{len(zones)}** qualifying zones across {len(data_dict)} stocks")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 Demand", len([z for z in zones if z.zone_type == "DEMAND"]))
    c2.metric("🔴 Supply", len([z for z in zones if z.zone_type == "SUPPLY"]))
    c3.metric("🏆 Best Score", f"{zones[0].score}/60")
    c4.metric("📊 Total", len(zones))
    st.markdown("---")

    for i, zone in enumerate(zones):
        trend_raw = trend_info.get(zone.symbol, "SIDEWAYS")
        trend_icon = "📈" if trend_raw == "UP" else "📉" if trend_raw == "DOWN" else "➡️"
        sl_dist = abs(zone.entry - zone.stop_loss)
        rr = round(abs(zone.target_2 - zone.entry) / sl_dist, 2) if sl_dist > 0 and zone.target_2 else 0.0
        header = (f"{'🟢' if zone.zone_type == 'DEMAND' else '🔴'} #{i+1} | {zone.symbol} | "
                  f"{zone.pattern} | {zone.score}/60 | R:R {rr:.1f} | {trend_icon} {trend_raw}")

        with st.expander(header, expanded=(i < 3)):
            if zone.symbol in data_dict:
                st.plotly_chart(create_chart(data_dict[zone.symbol], [zone], zone.symbol), key=f"c_{i}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📍 Entry", f"₹{zone.entry:.2f}")
            c2.metric("🛑 Stop Loss", f"₹{zone.stop_loss:.2f}")
            c3.metric("🎯 Target 1", f"₹{zone.target_1:.2f}")
            c4.metric("🎯 Target 2", f"₹{zone.target_2:.2f}")
            cs, cw = st.columns(2)
            cs.metric("📦 Position Size", f"{zone.position_size} shares")
            cw.metric("📏 Zone Width", f"{zone.zone_height_pct:.2f}%")

            st.markdown(
                f"**Scores:** | Dep | Base | Fresh | Arrival | Time | Trend | Total |\n"
                f"|:---:|:---:|:---:|:---:|:---:|:---:|:---:|\n"
                f"| {zone.departure_score}/10 | {zone.base_score}/10 | "
                f"{zone.freshness_score}/10 | {zone.arrival_score}/10 | "
                f"{zone.time_score}/10 | {zone.trend_score}/10 | **{zone.score}/60** |"
            )
            st.text(zone.reasoning)

            # Confirmation candle badge (Phase 2 feature — shows if populated)
            if getattr(zone, "confirmation_pattern", "") and zone.confirmation_pattern != "NONE":
                st.success(f"✅ Confirmation: **{zone.confirmation_pattern}** "
                           f"(strength {zone.confirmation_strength}/5)")
            elif getattr(zone, "confirmation_available", False):
                st.warning("⚠️ Price at zone — no confirmation candle yet")

            ca, cb, _ = st.columns([1, 1, 4])
            with ca:
                if st.button("✅ Take Trade", key=f"t_{i}"):
                    # Build reason string including confirmation if available
                    reason = zone.reasoning or f"{zone.pattern} score={zone.score}"
                    if getattr(zone, "confirmation_pattern", "") not in ("", "NONE"):
                        reason += f" | Confirmed: {zone.confirmation_pattern}"
                    db.save_trade(symbol=zone.symbol,
                                  side="BUY" if zone.zone_type == "DEMAND" else "SELL",
                                  quantity=zone.position_size or 1,
                                  entry_price=zone.entry, stop_loss=zone.stop_loss,
                                  target=zone.target_2, strategy="Professional Zone Scanner",
                                  reason=reason,
                                  base_candles=zone.base_candles,
                                  current_sl=zone.stop_loss)
                    st.success("✅ Trade placed!")
            with cb:
                if st.button("❌ Skip", key=f"s_{i}"):
                    pass

elif "zs_zones" in st.session_state:
    st.warning("No qualifying zones found. Try lowering the min score or scanning more stocks.")
else:
    st.info("👈 Configure settings and click **SCAN FOR ZONES** to start.")
    st.markdown("""
### How it works
1. Select stocks and set **Min Score** (0–60, default 40)
2. Filter by pattern: **DBR** / **RBD** (reversals) · **RBR** / **DBD** (continuations)
3. Enable **Multi-Timeframe** for 1H trend confirmation
4. Click **SCAN** — pipeline detects → freshness → filters → scores zones
5. Review 6-dimension breakdown and entry / SL / T1 / T2 levels
6. Click **Take Trade** to paper-trade the best setup
    """)

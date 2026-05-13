"""
Test Strategy Page - Backtest any registered strategy
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from core.data_fetcher import DataFetcher
from core.backtester import Backtester, BacktestReport, TradeResult
from strategies import STRATEGY_REGISTRY, ZoneScanner
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.rsi_reversal import RSIReversalStrategy
from config.settings import SYMBOLS, NIFTY_50

st.set_page_config(page_title="Test Strategy", page_icon="🧪", layout="wide")
data_fetcher = DataFetcher()


def create_backtest_chart(report):
    building_data = report.building_data
    testing_data = report.testing_data
    if building_data is None or testing_data is None:
        return go.Figure()

    split_idx = len(building_data)
    total_len = split_idx + len(testing_data)
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=list(range(split_idx)),
        open=building_data['Open'], high=building_data['High'],
        low=building_data['Low'], close=building_data['Close'],
        name='Building Period',
        increasing_line_color='rgba(38,166,154,0.5)',
        decreasing_line_color='rgba(239,83,80,0.5)',
        increasing_fillcolor='rgba(38,166,154,0.3)',
        decreasing_fillcolor='rgba(239,83,80,0.3)',
    ))

    fig.add_trace(go.Candlestick(
        x=list(range(split_idx, total_len)),
        open=testing_data['Open'], high=testing_data['High'],
        low=testing_data['Low'], close=testing_data['Close'],
        name='Testing Period',
        increasing_line_color='#26A69A', decreasing_line_color='#EF5350',
    ))

    fig.add_vline(x=split_idx, line_dash="dash", line_color="#FFD700", line_width=2,
                  annotation_text="Build | Test →", annotation_position="top")

    # Draw entry/SL/target lines for each setup (works for any strategy)
    for setup in report.setups:
        lc = "rgba(38,166,154,0.8)" if setup.side == "BUY" else "rgba(239,83,80,0.8)"
        fig.add_hline(y=setup.entry, line_dash="dot", line_color="#2196F3", line_width=1)
        fig.add_hline(y=setup.stop_loss, line_dash="dot", line_color="#F44336", line_width=1)
        fig.add_hline(y=setup.target, line_dash="dot", line_color="#4CAF50", line_width=1)

    for result in report.trade_results:
        if result.triggered:
            trigger_x = split_idx + result.candles_to_trigger
            fig.add_annotation(x=trigger_x, y=result.trigger_price, text="▶ ENTRY",
                               showarrow=True, arrowhead=2, arrowcolor="#2196F3",
                               font=dict(size=8, color="#2196F3"))
            if result.outcome in ["TARGET_HIT", "SL_HIT"]:
                exit_x = split_idx + result.candles_to_trigger + result.candles_to_exit
                ec = "#4CAF50" if result.outcome == "TARGET_HIT" else "#F44336"
                et = "✓ TARGET" if result.outcome == "TARGET_HIT" else "✗ SL"
                fig.add_annotation(x=exit_x, y=result.exit_price, text=et,
                                   showarrow=True, arrowhead=2, arrowcolor=ec,
                                   font=dict(size=8, color=ec))

    fig.update_layout(height=500, showlegend=False, xaxis_rangeslider_visible=False,
                      template="plotly_dark", margin=dict(l=40, r=80, t=40, b=20),
                      paper_bgcolor='#0E1117', plot_bgcolor='#0E1117',
                      title=dict(text=f"{report.symbol} — Backtest", font=dict(size=14)))
    fig.update_xaxes(showgrid=True, gridcolor='#1E1E1E')
    fig.update_yaxes(showgrid=True, gridcolor='#1E1E1E')
    return fig


def create_summary_chart(reports):
    symbols = [r.symbol for r in reports]
    wins = [r.targets_hit for r in reports]
    losses = [r.sl_hit for r in reports]
    pend = [r.pending for r in reports]
    fig = go.Figure()
    fig.add_trace(go.Bar(name='Target Hit', x=symbols, y=wins, marker_color='#4CAF50'))
    fig.add_trace(go.Bar(name='SL Hit', x=symbols, y=losses, marker_color='#F44336'))
    fig.add_trace(go.Bar(name='Pending', x=symbols, y=pend, marker_color='#FFC107'))
    fig.update_layout(barmode='stack', height=300, template="plotly_dark",
                      paper_bgcolor='#0E1117', plot_bgcolor='#0E1117',
                      margin=dict(l=40, r=40, t=40, b=20), title="Outcomes by Symbol",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


def create_pnl_chart(reports):
    all_trades = []
    for report in reports:
        for result in report.trade_results:
            if result.triggered and result.outcome != "PENDING":
                all_trades.append(result)
    if not all_trades:
        fig = go.Figure()
        fig.add_annotation(text="No completed trades", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(size=16, color="gray"))
        fig.update_layout(template="plotly_dark", paper_bgcolor='#0E1117', plot_bgcolor='#0E1117', height=300)
        return fig
    running = 0
    cum_pnl, labels, colors = [], [], []
    for i, trade in enumerate(all_trades):
        running += trade.pnl
        cum_pnl.append(running)
        labels.append(f"T{i+1}")
        colors.append('#4CAF50' if trade.pnl >= 0 else '#F44336')
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=cum_pnl, mode='lines+markers',
                             line=dict(color='#2196F3', width=2),
                             marker=dict(color=colors, size=8),
                             fill='tozeroy', fillcolor='rgba(33,150,243,0.1)'))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig.update_layout(height=300, template="plotly_dark", paper_bgcolor='#0E1117',
                      plot_bgcolor='#0E1117', margin=dict(l=40, r=40, t=40, b=20),
                      title="Cumulative P&L (per share)", xaxis_title="Trade #", yaxis_title="P&L (₹)")
    return fig


def outcome_badge(outcome):
    if outcome == "TARGET_HIT":
        return "✅ Target Hit"
    elif outcome == "SL_HIT":
        return "❌ SL Hit"
    elif outcome == "PENDING":
        return "⏳ Pending"
    return "⚪ Not Triggered"


# ==================== PAGE ====================
st.title("🧪 Test Strategy")
st.caption("Backtest any strategy — Build setups on past data, forward-test on subsequent data")

with st.sidebar:
    st.header("⚙️ Backtest Settings")

    # ---- Strategy selector ----
    st.subheader("🎯 Strategy")
    strategy_name = st.selectbox("Select Strategy", list(STRATEGY_REGISTRY.keys()), key="bt_strategy")
    is_zone_scanner = (strategy_name == "Supply & Demand Zones")

    st.markdown("---")
    st.subheader("📊 Symbols")
    watchlist = st.radio("Watchlist", ["Default (5)", "Nifty 50", "Custom"], key="bt_wl")
    if watchlist == "Default (5)":
        available = SYMBOLS
    elif watchlist == "Nifty 50":
        available = NIFTY_50
    else:
        custom_input = st.text_input("Symbols (comma-separated)", "RELIANCE.NS, TCS.NS")
        available = [s.strip() for s in custom_input.split(",") if s.strip()]

    selected_symbols = st.multiselect("Select", available,
                                      default=available[:3] if len(available) >= 3 else available,
                                      key="bt_symbols")
    st.markdown("---")
    st.subheader("📅 Dates")
    st.info("💡 ~60 days of 15m data available from yfinance")
    today = datetime.now().date()
    max_lb = today - timedelta(days=58)
    c1, c2 = st.columns(2)
    with c1:
        build_start = st.date_input("Build Start", value=today - timedelta(days=14),
                                    min_value=max_lb, max_value=today - timedelta(days=3), key="bt_bs")
    with c2:
        split_date = st.date_input("Test Start", value=today - timedelta(days=3),
                                   min_value=build_start + timedelta(days=2), max_value=today, key="bt_sp")
    build_days = (split_date - build_start).days
    test_days = (today - split_date).days
    st.caption(f"📐 Build: {build_days}d | Test: {test_days}d")
    st.markdown("---")

    # ---- Strategy-specific parameters ----
    st.subheader("🎛️ Parameters")

    if is_zone_scanner:
        from core.llm_advisor import StrategyMemory
        _mem = StrategyMemory()
        _has_ai = bool(_mem.best_params)
        _lp = _mem.live_params() if _has_ai else {"min_score": 80, "rr_ratio": 3.0, "max_base_candles": 5}

        use_ai_params = st.toggle("🤖 Use AI-Optimized Params", value=_has_ai, key="bt_ai",
                                  disabled=not _has_ai,
                                  help="Pre-fills sliders with the best params found by AI. Run AI Refinement first.")
        if use_ai_params and _has_ai:
            st.caption(f"Score={_lp['min_score']} | R:R={_lp['rr_ratio']} | Base={_lp['max_base_candles']} "
                       f"(WR: {_mem.best_win_rate:.1f}%)")

        min_score = st.slider("Min Score", 50, 100,
                              _lp["min_score"] if use_ai_params else 80, 5, key="bt_ms")
        rr_ratio = st.select_slider("R:R", options=[2.0, 2.5, 3.0, 4.0, 5.0],
                                     value=_lp["rr_ratio"] if use_ai_params else 3.0, key="bt_rr")
        strategy_params = {"min_score": min_score, "rr_ratio": rr_ratio}

    elif strategy_name == "RSI Reversal":
        rsi_period = st.slider("RSI Period", 5, 50, 14, 1, key="bt_rsi_p")
        oversold = st.slider("Oversold Level", 10, 45, 30, 5, key="bt_rsi_os")
        overbought = st.slider("Overbought Level", 55, 90, 70, 5, key="bt_rsi_ob")
        rr_ratio_rsi = st.select_slider("R:R Ratio", options=[1.5, 2.0, 2.5, 3.0, 4.0], value=2.0, key="bt_rsi_rr")
        strategy_params = {
            "rsi_period": rsi_period, "oversold_level": oversold,
            "overbought_level": overbought, "rr_ratio": rr_ratio_rsi,
        }
        use_ai_params = False

    elif strategy_name == "EMA Crossover":
        fast_period = st.slider("Fast EMA Period", 3, 50, 9, 1, key="bt_ema_f")
        slow_period = st.slider("Slow EMA Period", 5, 100, 21, 1, key="bt_ema_s")
        strategy_params = {"fast_period": fast_period, "slow_period": slow_period}
        use_ai_params = False

    else:
        strategy_params = {}
        use_ai_params = False

    st.markdown("---")
    run_bt = st.button("🚀 RUN BACKTEST", type="primary", use_container_width=True)


def _build_strategy(name, params, use_ai=False, ai_lp=None):
    """Instantiate the correct strategy from registry params."""
    if name == "Supply & Demand Zones":
        s = ZoneScanner(min_score=params["min_score"], rr_ratio=params["rr_ratio"])
        if use_ai and ai_lp:
            s.max_base_candles = ai_lp.get("max_base_candles", 5)
        return s
    elif name == "RSI Reversal":
        return RSIReversalStrategy(**params)
    elif name == "EMA Crossover":
        return EMACrossoverStrategy(**params)
    else:
        return STRATEGY_REGISTRY[name](**params)


# ==================== RUN ====================
if run_bt:
    if not selected_symbols:
        st.error("Select at least one symbol.")
        st.stop()

    total_days = (today - build_start).days + 2
    if total_days <= 5:
        yf_period = "5d"
    elif total_days <= 10:
        yf_period = "10d"
    elif total_days <= 30:
        yf_period = "1mo"
    else:
        yf_period = "60d"

    _ai_lp = _lp if (is_zone_scanner and use_ai_params) else None
    strategy = _build_strategy(strategy_name, strategy_params, use_ai_params, _ai_lp)
    backtester = Backtester(strategy=strategy)

    all_reports = []
    progress = st.progress(0, text="Running backtest...")

    for idx, symbol in enumerate(selected_symbols):
        progress.progress((idx + 1) / len(selected_symbols), text=f"Testing {symbol}...")
        try:
            data = data_fetcher.get_data(symbol, "15m", yf_period)
            if data is None or len(data) < 20:
                st.warning(f"⚠️ Insufficient data for {symbol}")
                continue
            if data.index.tz is not None:
                split_ts = pd.Timestamp(split_date, tz=data.index.tz)
                build_ts = pd.Timestamp(build_start, tz=data.index.tz)
            else:
                split_ts = pd.Timestamp(split_date)
                build_ts = pd.Timestamp(build_start)
            filtered = data[data.index >= build_ts].copy()
            if len(filtered) < 20:
                st.warning(f"⚠️ Not enough data for {symbol}")
                continue
            report = backtester.run(filtered, split_ts, symbol)
            all_reports.append(report)
        except Exception as e:
            st.warning(f"⚠️ Error with {symbol}: {e}")

    progress.empty()
    st.session_state['bt_reports'] = all_reports
    st.session_state['bt_strategy_name'] = strategy_name

# ==================== DISPLAY ====================
reports = st.session_state.get('bt_reports', [])
active_strategy_name = st.session_state.get('bt_strategy_name', strategy_name)

if reports:
    # Aggregate stats
    total_zones = sum(r.total_zones_found for r in reports)
    total_triggered = sum(r.zones_triggered for r in reports)
    total_wins = sum(r.targets_hit for r in reports)
    total_losses = sum(r.sl_hit for r in reports)
    total_pending = sum(r.pending for r in reports)
    overall_pnl = sum(r.total_pnl for r in reports)
    overall_wr = (total_wins / total_triggered * 100) if total_triggered > 0 else 0

    st.markdown(f"## 📊 Backtest Summary — *{active_strategy_name}*")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Setups Found", total_zones)
    m2.metric("Triggered", total_triggered)
    m3.metric("✅ Wins", total_wins)
    m4.metric("❌ Losses", total_losses)
    m5.metric("Win Rate", f"{overall_wr:.1f}%")
    m6.metric("Net P&L/share", f"₹{overall_pnl:.2f}", delta=f"{'+'if overall_pnl>=0 else ''}{overall_pnl:.2f}")

    st.markdown("---")

    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(create_summary_chart(reports), use_container_width=True, key="sum_chart")
    with col_right:
        st.plotly_chart(create_pnl_chart(reports), use_container_width=True, key="pnl_chart")

    st.markdown("---")
    st.markdown("## 📈 Detailed Results")

    for ri, report in enumerate(reports):
        icon = "🟢" if report.win_rate >= 50 else "🔴"
        lbl = f"{icon} {report.symbol} | Setups: {report.total_zones_found} | WR: {round(report.win_rate)}%"
        with st.expander(lbl, expanded=(ri == 0)):
            if report.building_data is not None and report.testing_data is not None:
                st.plotly_chart(create_backtest_chart(report), use_container_width=True, key=f"bt_c_{ri}")
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Setups", report.total_zones_found)
            sc2.metric("Triggered", report.zones_triggered)
            sc3.metric("Win Rate", f"{report.win_rate:.1f}%")
            sc4.metric("P&L/share", f"₹{report.total_pnl:.2f}")
            if report.trade_results:
                st.markdown("#### Trade Details")
                rows = []
                for tr in report.trade_results:
                    rows.append({
                        "Side": tr.setup.side,
                        "Score": tr.setup.score,
                        "Entry": round(tr.setup.entry, 2),
                        "SL": round(tr.setup.stop_loss, 2),
                        "Target": round(tr.setup.target, 2),
                        "Triggered": "Yes" if tr.triggered else "No",
                        "Outcome": outcome_badge(tr.outcome),
                        "P&L": round(tr.pnl, 2) if tr.triggered else None,
                        "R:R": round(tr.rr_achieved, 1) if tr.triggered else None,
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No setups found in building period.")

    # ==================== AI REFINEMENT (ZoneScanner only) ====================
    if active_strategy_name == "Supply & Demand Zones":
        st.markdown("---")
        st.markdown("## 🤖 AI Strategy Refinement")
        st.caption("AI learns across sessions — every run is remembered until the win-rate target is hit")

        from core.llm_advisor import StrategyMemory
        memory = StrategyMemory()

        mem_col1, mem_col2, mem_col3 = st.columns([2, 2, 1])
        with mem_col1:
            st.info(f"📚 Memory: **{memory.total_iterations}** past iterations | Best WR: **{memory.best_win_rate:.1f}%**")
        with mem_col2:
            if memory.best_params:
                bp = memory.best_params
                st.caption(f"Best known: score={bp.get('min_score')} R:R={bp.get('rr_ratio')} build={bp.get('build_days')}d test={bp.get('test_days')}d")
        with mem_col3:
            if st.button("🗑️ Clear Memory", key="clear_mem"):
                memory.clear()
                st.success("Memory cleared.")
                st.rerun()

        ctrl1, ctrl2, ctrl3 = st.columns(3)
        with ctrl1:
            target_wr = st.slider("🎯 Target Win Rate %", 50, 90, 70, 5, key="ai_target")
        with ctrl2:
            max_iterations = st.select_slider("Max Iterations", options=[1, 2, 3, 5, 8, 10], value=5, key="ai_iters")
        with ctrl3:
            run_ai = st.button("🤖 Run AI Refinement", type="primary", use_container_width=True)

        if run_ai:
            try:
                from core.llm_advisor import create_llm_from_secrets, StrategyAdvisor, StrategyMemory
                from core.backtester import Backtester

                llm = create_llm_from_secrets(dict(st.secrets))
                advisor = StrategyAdvisor(llm)
                memory = StrategyMemory()

                full_data_cache = {}
                for sym in selected_symbols:
                    d = data_fetcher.get_data(sym, "15m", "60d")
                    if d is not None and len(d) >= 20:
                        full_data_cache[sym] = d

                start_params = {
                    "min_score": strategy_params.get("min_score", 80),
                    "rr_ratio": strategy_params.get("rr_ratio", 3.0),
                    "max_base_candles": 5,
                    "build_days": build_days,
                    "test_days": test_days,
                }
                if memory.best_params and memory.best_win_rate > overall_wr:
                    start_params.update(memory.best_params)

                current_params = start_params

                def _build_results_summary(rpts):
                    tz = sum(r.total_zones_found for r in rpts)
                    tt = sum(r.zones_triggered for r in rpts)
                    tw = sum(r.targets_hit for r in rpts)
                    tl = sum(r.sl_hit for r in rpts)
                    tp = sum(r.pending for r in rpts)
                    wr = (tw / tt * 100) if tt > 0 else 0
                    pnl = sum(r.total_pnl for r in rpts)
                    res = {
                        "total_zones": tz, "triggered": tt, "targets_hit": tw,
                        "sl_hit": tl, "pending": tp, "win_rate": wr, "total_pnl": pnl,
                        "avg_rr": sum(r.avg_rr_achieved for r in rpts) / max(len(rpts), 1),
                        "max_win": max((r.max_win for r in rpts), default=0),
                        "max_loss": min((r.max_loss for r in rpts), default=0),
                        "trade_details": [],
                    }
                    for r in rpts:
                        for tr in r.trade_results:
                            res["trade_details"].append({
                                "type": tr.setup.side, "score": tr.setup.score,
                                "outcome": tr.outcome, "pnl": tr.pnl, "rr": tr.rr_achieved,
                            })
                    return res, tz, tt, tw, tl, wr, pnl

                def _run_with_params(params):
                    s = ZoneScanner(min_score=params["min_score"], rr_ratio=params["rr_ratio"])
                    if "max_base_candles" in params:
                        s.max_base_candles = params["max_base_candles"]
                    bt = Backtester(strategy=s)
                    bd = params.get("build_days", 10)
                    td = params.get("test_days", 3)
                    rpts = []
                    for sym, raw in full_data_cache.items():
                        try:
                            data_end = raw.index[-1]
                            new_split = data_end - pd.Timedelta(days=td)
                            new_build = new_split - pd.Timedelta(days=bd)
                            filt = raw[raw.index >= new_build].copy()
                            if len(filt) < 20:
                                continue
                            rep = bt.run(filt, new_split, sym)
                            rpts.append(rep)
                        except Exception:
                            continue
                    return rpts

                initial_results, *baseline_metrics = _build_results_summary(reports)
                tz0, tt0, tw0, tl0, wr0, pnl0 = baseline_metrics

                memory.add(current_params, initial_results, "Baseline", selected_symbols)

                iteration_history = [{
                    "iteration": 0,
                    "min_score": current_params["min_score"],
                    "rr_ratio": current_params["rr_ratio"],
                    "build_days": current_params["build_days"],
                    "test_days": current_params["test_days"],
                    "win_rate": wr0, "pnl": pnl0,
                    "zones": tz0, "triggered": tt0,
                }]

                all_iterations = [{
                    "iteration": 0,
                    "params": dict(current_params),
                    "win_rate": wr0, "pnl": pnl0,
                    "zones_found": tz0, "triggered": tt0,
                    "wins": tw0, "losses": tl0,
                    "analysis": "Baseline (your initial parameters)",
                    "reasoning": "", "confidence": 0,
                }]

                target_reached = wr0 >= target_wr
                ai_progress = st.progress(0, text="AI analyzing results...")

                for iteration in range(1, max_iterations + 1):
                    if target_reached:
                        break

                    ai_progress.progress(
                        iteration / max_iterations,
                        text=f"Iteration {iteration}/{max_iterations}: AI analyzing ({memory.total_iterations} runs in memory)..."
                    )

                    llm_response = advisor.analyze_and_suggest(
                        initial_results, current_params, iteration_history,
                        memory_history=memory.recent_history(30),
                        target_win_rate=target_wr,
                    )

                    suggestions = llm_response.get("suggestions", {})
                    if not suggestions:
                        st.warning(f"Iteration {iteration}: AI returned no suggestions.")
                        break

                    new_params = dict(current_params)
                    for key in ("min_score", "rr_ratio", "max_base_candles", "build_days", "test_days"):
                        if key in suggestions:
                            new_params[key] = suggestions[key]

                    ai_progress.progress(
                        iteration / max_iterations,
                        text=f"Iteration {iteration}: build={new_params['build_days']}d test={new_params['test_days']}d score={new_params['min_score']} R:R={new_params['rr_ratio']}..."
                    )

                    new_reports = _run_with_params(new_params)
                    initial_results, *metrics = _build_results_summary(new_reports)
                    nz, nt, nw, nl, nwr, npnl = metrics

                    memory.add(new_params, initial_results,
                               llm_response.get("analysis", ""), selected_symbols)

                    target_reached = nwr >= target_wr
                    current_params = new_params
                    iteration_history.append({
                        "iteration": iteration,
                        "min_score": new_params["min_score"],
                        "rr_ratio": new_params["rr_ratio"],
                        "build_days": new_params["build_days"],
                        "test_days": new_params["test_days"],
                        "win_rate": nwr, "pnl": npnl,
                        "zones": nz, "triggered": nt,
                    })

                    all_iterations.append({
                        "iteration": iteration,
                        "params": dict(new_params),
                        "win_rate": nwr, "pnl": npnl,
                        "zones_found": nz, "triggered": nt,
                        "wins": nw, "losses": nl,
                        "analysis": llm_response.get("analysis", ""),
                        "reasoning": llm_response.get("reasoning", ""),
                        "confidence": llm_response.get("confidence", 0),
                        "primary_issue": llm_response.get("primary_issue", ""),
                        "target_reached": target_reached,
                    })

                ai_progress.empty()
                if target_reached:
                    st.balloons()
                    st.success(f"🎯 Target {target_wr}% win rate reached!")
                st.session_state['ai_iterations'] = all_iterations

            except Exception as e:
                st.error(f"AI Refinement failed: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

        if 'ai_iterations' in st.session_state and st.session_state['ai_iterations']:
            iterations = st.session_state['ai_iterations']

            st.markdown("### 📊 Iteration Comparison")
            iter_rows = []
            for it in iterations:
                iter_rows.append({
                    "Iter": it["iteration"],
                    "Score": it["params"].get("min_score", "-"),
                    "R:R": it["params"].get("rr_ratio", "-"),
                    "Base": it["params"].get("max_base_candles", "-"),
                    "Build(d)": it["params"].get("build_days", "-"),
                    "Test(d)": it["params"].get("test_days", "-"),
                    "Zones": it.get("zones_found", "-"),
                    "Triggered": it.get("triggered", "-"),
                    "Wins": it.get("wins", "-"),
                    "Losses": it.get("losses", "-"),
                    "Win Rate": f"{it['win_rate']:.1f}%",
                    "P&L": f"₹{it['pnl']:.2f}",
                })
            st.dataframe(pd.DataFrame(iter_rows), use_container_width=True, hide_index=True)

            fig_iter = go.Figure()
            iters_x = [f"Iter {it['iteration']}" for it in iterations]
            wr_y = [it["win_rate"] for it in iterations]
            pnl_y = [it["pnl"] for it in iterations]
            fig_iter.add_trace(go.Scatter(x=iters_x, y=wr_y, mode='lines+markers', name='Win Rate %',
                                          line=dict(color='#4CAF50', width=3), marker=dict(size=10), yaxis='y'))
            fig_iter.add_trace(go.Scatter(x=iters_x, y=pnl_y, mode='lines+markers', name='P&L (₹)',
                                          line=dict(color='#2196F3', width=3), marker=dict(size=10), yaxis='y2'))
            fig_iter.update_layout(
                height=350, template="plotly_dark",
                paper_bgcolor='#0E1117', plot_bgcolor='#0E1117',
                title="Strategy Improvement Over Iterations",
                yaxis=dict(title="Win Rate %", side="left", color="#4CAF50"),
                yaxis2=dict(title="P&L (₹)", side="right", overlaying="y", color="#2196F3"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=40, r=40, t=60, b=20)
            )
            st.plotly_chart(fig_iter, use_container_width=True, key="iter_chart")

            st.markdown("### 🧠 AI Analysis Per Iteration")
            for it in iterations[1:]:
                label = f"Iteration {it['iteration']} — WR: {it['win_rate']:.1f}% | P&L: ₹{it['pnl']:.2f}"
                if it.get("target_reached"):
                    label = "🎯 " + label
                with st.expander(label, expanded=(it['iteration'] == len(iterations) - 1)):
                    st.markdown(f"**Issue diagnosed:** {it.get('primary_issue', 'N/A')}")
                    st.markdown(f"**Analysis:** {it.get('analysis', 'N/A')}")
                    st.markdown(f"**Reasoning:** {it.get('reasoning', 'N/A')}")
                    st.markdown(f"**Confidence:** {'⭐' * it.get('confidence', 0)} ({it.get('confidence', 0)}/10)")
                    p = it["params"]
                    st.caption(f"Build={p.get('build_days','?')}d | Test={p.get('test_days','?')}d | Score={p.get('min_score')} | R:R={p.get('rr_ratio')} | Base={p.get('max_base_candles')}")

            best = max(iterations, key=lambda x: x["win_rate"])
            if best["iteration"] > 0:
                st.success(
                    f"🏆 **Best this session — Iteration {best['iteration']}** — "
                    f"Win Rate: {best['win_rate']:.1f}% | P&L: ₹{best['pnl']:.2f} | "
                    f"Params: Score={best['params'].get('min_score')}, R:R={best['params'].get('rr_ratio')}, "
                    f"Build={best['params'].get('build_days')}d, Test={best['params'].get('test_days')}d"
                )
                st.info(f"📚 All-time best across sessions: **{memory.best_win_rate:.1f}%** — saved to memory ({memory.total_iterations} total runs)")

elif 'bt_reports' in st.session_state:
    st.warning("No results. Adjust parameters or select different symbols/dates.")
else:
    st.info("Configure settings and click **RUN BACKTEST** to test your strategy.")
    st.markdown("""
    ### How it works:
    1. **Strategy** — pick from the dropdown (Supply & Demand Zones, RSI Reversal, EMA Crossover)
    2. **Build Period** — strategy detects setups on historical 15m candles
    3. **Test Period** — forward price action checks if setups get triggered
    4. **Results** — see target hits, stop losses, and win rate
    5. **AI Refinement** — available for Supply & Demand Zones; LLM optimizes parameters automatically

    ### Adding a new strategy:
    1. Create `strategies/my_strategy.py` — inherit `BaseStrategy`, implement `generate_signal()` and `get_parameters()`
    2. Add one line in `strategies/__init__.py`: `"My Strategy": MyStrategy` in `STRATEGY_REGISTRY`
    3. It will appear in the dropdown automatically
    """)

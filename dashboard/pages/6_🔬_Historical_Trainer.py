"""
Historical Trainer Page
------------------------
Run and monitor the walk-forward historical training job from the dashboard.
Uses the Professional Zone Scanner with 6-dimension scoring (0-60 scale).
Shows multi-run comparison table for convergence testing.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import threading
import time
import glob
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Historical Trainer", page_icon="🔬", layout="wide")

_PROGRESS_FILE = ".streamlit/training_progress.json"


def _write_progress(pct: float, msg: str, error: bool = False):
    os.makedirs(".streamlit", exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    with open(_PROGRESS_FILE, "w") as f:
        json.dump({"pct": pct, "msg": msg, "done": pct >= 100 or error, "error": error, "ts": ts}, f)


def _start_training(quick: bool, no_ai: bool):
    def _worker():
        from historical_trainer import run_training
        try:
            _write_progress(0, "Starting training...")
            report = run_training(
                quick=quick, no_ai=no_ai,
                progress_cb=lambda pct, msg: _write_progress(pct, msg),
            )
            msg = "Complete! WR=%.1f%% RR=%.2f over %d trades" % (
                report['overall_win_rate'], report.get('average_rr', 0), report['total_triggered'])
            _write_progress(100, msg)
        except Exception as e:
            _write_progress(-1, "Error: %s" % str(e), error=True)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    st.session_state["training_thread"] = t
    st.session_state["training_start"] = datetime.now()


def _is_training() -> bool:
    t = st.session_state.get("training_thread")
    return t is not None and t.is_alive()


def _read_progress() -> dict:
    try:
        with open(_PROGRESS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"pct": 0, "msg": "Starting...", "done": False, "error": False}


def _load_all_reports() -> list:
    reports = []
    for path in sorted(glob.glob("reports/training/*_training_report.json")):
        try:
            with open(path) as f:
                r = json.load(f)
            r["_path"] = path
            reports.append(r)
        except Exception:
            pass
    return reports


def _learning_curve_chart(weekly_summary: list) -> go.Figure:
    if not weekly_summary:
        return go.Figure()
    weeks = ["W%d %s" % (w['week_num'], w['start_date']) for w in weekly_summary]
    wr = [w["win_rate"] for w in weekly_summary]
    rr = [w.get("avg_rr", 0) for w in weekly_summary]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weeks, y=wr, mode="lines+markers+text",
        text=["%.0f%%" % v for v in wr], textposition="top center",
        name="Win Rate %",
        line=dict(color="#26A69A", width=2),
        marker=dict(size=8, color=[
            "#4CAF50" if v >= 60 else "#FF9800" if v >= 45 else "#EF5350" for v in wr
        ]),
    ))
    fig.add_trace(go.Scatter(
        x=weeks, y=rr, mode="lines+markers",
        name="Avg RR", line=dict(color="#7C4DFF", width=2, dash="dot"),
        marker=dict(size=6), yaxis="y2",
    ))
    fig.add_hline(y=60, line_dash="dash", line_color="#FFD700", line_width=1,
                  annotation_text="60% target", annotation_position="right")
    fig.update_layout(
        height=320, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=40, r=80, t=30, b=60),
        yaxis=dict(title="Win Rate %", range=[0, 100]),
        yaxis2=dict(title="Avg RR", overlaying="y", side="right", range=[0, 5]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def _pnl_chart(daily_results: list) -> go.Figure:
    if not daily_results:
        return go.Figure()
    dates = [d["date"] for d in daily_results]
    cum_pnl = []
    running = 0.0
    for d in daily_results:
        running += d["pnl"]
        cum_pnl.append(running)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=cum_pnl, mode="lines", fill="tozeroy",
                             line=dict(color="#26A69A", width=2)))
    fig.update_layout(height=270, template="plotly_dark",
                      paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                      margin=dict(l=40, r=40, t=20, b=60),
                      yaxis=dict(title="Cumulative P&L (Rs)"), showlegend=False)
    return fig


def _convergence_chart(reports: list):
    if len(reports) < 2:
        return None
    labels = ["Run %d" % (i+1) for i in range(len(reports))]
    wrs = [r["overall_win_rate"] for r in reports]
    rrs = [r.get("average_rr", 0) for r in reports]
    trades = [r["total_triggered"] for r in reports]
    colors = ["#4CAF50" if wr >= 60 else "#FF9800" if wr >= 45 else "#EF5350" for wr in wrs]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=wrs, marker_color=colors,
        text=["%.1f%%\nRR=%.2f\n(%d trades)" % (wr, rr, t) for wr, rr, t in zip(wrs, rrs, trades)],
        textposition="outside",
    ))
    fig.add_hline(y=60, line_dash="dash", line_color="#FFD700", annotation_text="60% target")
    fig.update_layout(height=300, template="plotly_dark",
                      paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
                      margin=dict(l=40, r=40, t=20, b=40),
                      yaxis=dict(title="Win Rate %", range=[0, max(wrs) + 20]),
                      showlegend=False)
    return fig


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("🔬 Historical Walk-Forward Trainer")
st.caption(
    "Simulate the Professional Zone Scanner on up to 60 days of real 15m data. "
    "Each day: zones are detected up to 11:02 AM IST → setups test against the next 3 trading days. "
    "Uses 6-dimension scoring (0-60): Departure, Base, Freshness, Arrival, Time, Trend. "
    "Learned params feed directly into the live bot's strategy_memory.json."
)

# ── Live progress ─────────────────────────────────────────────────────────────
currently_training = _is_training()
prog = _read_progress() if currently_training else {}

if currently_training or (prog.get("pct", 0) == 100 and not prog.get("error")):
    st.subheader("Training In Progress" if currently_training else "Last Run Complete")
    pct = max(0.0, min(100.0, prog.get("pct", 0)))
    msg = prog.get("msg", "Running...")
    err = prog.get("error", False)
    st.progress(pct / 100)
    if err:
        st.error("Training failed: %s" % msg)
    else:
        col_pct, col_time = st.columns([3, 1])
        col_pct.write("**%.0f%%** — %s" % (pct, msg))
        if "training_start" in st.session_state:
            elapsed = datetime.now() - st.session_state["training_start"]
            col_time.caption("Elapsed: %dm %ds" % (elapsed.seconds // 60, elapsed.seconds % 60))
    if currently_training and not prog.get("done", False):
        st.caption("Page auto-refreshes every 2 seconds while training...")
    elif prog.get("done") and not err and not currently_training:
        st.success("Training complete — see results below.")
    st.divider()

# ── Past runs ─────────────────────────────────────────────────────────────────
reports = _load_all_reports()

if reports:
    st.subheader("Training History — %d run%s" % (len(reports), "s" if len(reports) > 1 else ""))

    table_rows = []
    for i, r in enumerate(reports):
        table_rows.append({
            "Run": "#%d" % (i + 1),
            "Timestamp": r.get("run_id", "")[:16].replace("T", " "),
            "Days": r.get("trading_days", 0),
            "Symbols": len(r.get("symbols_used", [])),
            "Trades": r.get("total_triggered", 0),
            "Win Rate": "%.1f%%" % r.get("overall_win_rate", 0),
            "Avg RR": "%.2f" % r.get("average_rr", 0),
            "P&L": "Rs%+.0f" % r.get("total_pnl", 0),
            "Opt Runs": r.get("optimizer_runs", 0),
            "Claude": r.get("claude_calls", 0),
            "Quick": "Y" if r.get("quick_mode") else "-",
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    conv = _convergence_chart(reports)
    if conv:
        st.subheader("Convergence Test")
        st.caption("Win rate and RR should improve run-to-run. Flat/declining = overfitting risk.")
        st.plotly_chart(conv, use_container_width=True)

    st.subheader("Inspect a Run")
    run_options = [
        "Run #%d — %s (WR %.1f%%, RR %.2f, %d trades)" % (
            i+1, r.get('run_id', '')[:16],
            r.get('overall_win_rate', 0), r.get('average_rr', 0), r.get('total_triggered', 0))
        for i, r in enumerate(reports)
    ]
    sel_idx = st.selectbox("Select run", range(len(run_options)),
                           format_func=lambda i: run_options[i], index=len(reports) - 1)
    sel = reports[sel_idx]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Win Rate", "%.1f%%" % sel.get("overall_win_rate", 0))
    c2.metric("Avg RR", "%.2f" % sel.get("average_rr", 0))
    c3.metric("Trades", sel.get("total_triggered", 0))
    c4.metric("P&L", "Rs%+.0f" % sel.get("total_pnl", 0))
    c5.metric("Training Days", sel.get("trading_days", 0))

    cl, cr = st.columns(2)
    with cl:
        st.subheader("Weekly Learning Curve")
        st.plotly_chart(_learning_curve_chart(sel.get("weekly_summary", [])), use_container_width=True)
    with cr:
        st.subheader("Cumulative P&L")
        st.plotly_chart(_pnl_chart(sel.get("daily_results", [])), use_container_width=True)

    with st.expander("Final Learned Parameters & Insights"):
        cp, ci = st.columns(2)
        with cp:
            st.write("**Zone Scanner Config:**")
            zp = sel.get("final_zone_params", {})
            st.json(zp)
        with ci:
            st.write("**Scoring System:**")
            st.markdown(
                "Zones scored 0-60 (6 dimensions x 10):\n"
                "1. **Departure** - Leg-out quality\n"
                "2. **Base** - Base tightness\n"
                "3. **Freshness** - Untested zone\n"
                "4. **Arrival** - Leg-in quality\n"
                "5. **Time** - Zone age\n"
                "6. **Trend** - HTF alignment"
            )
            if zp.get("min_score_to_trade"):
                st.info("Min score to trade: **%d/60**" % zp["min_score_to_trade"])

        fs = sel.get("final_summary", {})
        if fs.get("executive_summary"):
            st.info(fs["executive_summary"])
        for ins in fs.get("key_insights", []):
            st.write("- %s" % ins)
        if fs.get("best_performing_setup"):
            st.write("Best setup: %s" % fs["best_performing_setup"])
        if fs.get("recommended_live_approach"):
            st.success("Recommended approach: %s" % fs["recommended_live_approach"])

    with st.expander("Trade Outcome Breakdown"):
        outcome_agg = {"TARGET_HIT": 0, "SL_HIT": 0, "EXPIRED": 0}
        side_agg = {"BUY": {"wins": 0, "losses": 0}, "SELL": {"wins": 0, "losses": 0}}
        regime_agg = {}
        score_wins = []
        score_losses = []

        for d in sel.get("daily_results", []):
            for t in d.get("trades", []):
                outcome = t.get("outcome", "")
                if outcome in outcome_agg:
                    outcome_agg[outcome] += 1
                side = t.get("side", "BUY")
                if side in side_agg:
                    if outcome == "TARGET_HIT":
                        side_agg[side]["wins"] += 1
                    elif outcome == "SL_HIT":
                        side_agg[side]["losses"] += 1
                regime = t.get("regime", "unknown")
                if regime not in regime_agg:
                    regime_agg[regime] = {"wins": 0, "losses": 0, "total": 0}
                regime_agg[regime]["total"] += 1
                if outcome == "TARGET_HIT":
                    regime_agg[regime]["wins"] += 1
                elif outcome == "SL_HIT":
                    regime_agg[regime]["losses"] += 1
                score = t.get("score", 0)
                if score > 0:
                    if outcome == "TARGET_HIT":
                        score_wins.append(score)
                    elif outcome == "SL_HIT":
                        score_losses.append(score)

        oc1, oc2, oc3 = st.columns(3)
        oc1.metric("Targets Hit", outcome_agg["TARGET_HIT"])
        oc2.metric("SL Hit", outcome_agg["SL_HIT"])
        oc3.metric("Expired", outcome_agg["EXPIRED"])

        st.write("**By Side:**")
        side_rows = []
        for side, sdata in side_agg.items():
            total = sdata["wins"] + sdata["losses"]
            wr = sdata["wins"] / total * 100 if total > 0 else 0
            side_rows.append({"Side": side, "Wins": sdata["wins"], "Losses": sdata["losses"], "Win Rate": "%.1f%%" % wr})
        if side_rows:
            st.dataframe(pd.DataFrame(side_rows), use_container_width=True, hide_index=True)

        st.write("**By Market Regime:**")
        regime_rows = []
        for regime, rdata in regime_agg.items():
            total = rdata["wins"] + rdata["losses"]
            wr = rdata["wins"] / total * 100 if total > 0 else 0
            regime_rows.append({"Regime": regime, "Total": rdata["total"], "Wins": rdata["wins"], "Losses": rdata["losses"], "Win Rate": "%.1f%%" % wr})
        if regime_rows:
            st.dataframe(pd.DataFrame(regime_rows), use_container_width=True, hide_index=True)

        if score_wins or score_losses:
            st.write("**Zone Score Analysis:**")
            avg_win_score = sum(score_wins) / len(score_wins) if score_wins else 0
            avg_loss_score = sum(score_losses) / len(score_losses) if score_losses else 0
            sc1, sc2 = st.columns(2)
            sc1.metric("Avg Score (Winners)", "%.1f/60" % avg_win_score)
            sc2.metric("Avg Score (Losers)", "%.1f/60" % avg_loss_score)

    st.divider()
else:
    st.info("No training runs yet. Start your first run below.")

# Start new run
st.subheader("Start New Training Run")
st.caption(
    "Quick mode (~5-10 min): 10 symbols, smaller param grid. "
    "Full mode (~30-60 min): 20 symbols, full grid. "
    "Run multiple times - improving WR confirms learning is working."
)

col_opts, col_btn = st.columns([3, 1])
with col_opts:
    quick_mode = st.checkbox("Quick mode (10 symbols, smaller grid)", value=True)
    no_ai_mode = st.checkbox("No-AI mode (skip Claude calls - grid only)", value=False)

with col_btn:
    st.write("")
    disabled = currently_training
    if st.button("Start Training", disabled=disabled, type="primary", use_container_width=True):
        _start_training(quick=quick_mode, no_ai=no_ai_mode)
        st.rerun()

# Auto-refresh while training
if currently_training and not prog.get("done", False):
    time.sleep(2)
    st.rerun()

with st.expander("How it works"):
    st.markdown("""
**Professional Zone Scanner Walk-Forward Simulation:**

Each trading day D:
1. Detect supply/demand zones on data up to 11:02 AM IST
2. Score each zone on 6 dimensions (0-60 total)
3. Simulate triggering over next 3 trading days
4. Record outcomes: TARGET_HIT, SL_HIT, or EXPIRED

**Optimization Schedule:**
- Every 5 days: Mini-optimizer searches param grid
- Every 10 days: Claude analyzes patterns and adjusts params
- Final: Claude writes summary, saves best params

**Key Tunable Parameters:**
- min_score_to_trade: Minimum zone score (out of 60)
- default_rr_ratio: Default risk:reward ratio
- min_rr_ratio: Minimum acceptable R:R
- sl_atr_multiplier: Stop loss width (x ATR)
- max_sl_pct: Maximum SL as pct of entry
- max_base_candles: Detection sensitivity
""")

"""
Historical Trainer Page
------------------------
Run and monitor the walk-forward historical training job from the dashboard.
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


# ── Training thread helpers ───────────────────────────────────────────────────

def _write_progress(pct: float, msg: str, error: bool = False):
    os.makedirs(".streamlit", exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    with open(_PROGRESS_FILE, "w") as f:
        json.dump({
            "pct": pct, "msg": msg, "done": pct >= 100 or error,
            "error": error, "ts": ts,
        }, f)


def _start_training(quick: bool, no_ai: bool):
    def _worker():
        from historical_trainer import run_training
        try:
            _write_progress(0, "Starting training...")
            report = run_training(
                quick=quick, no_ai=no_ai,
                progress_cb=lambda pct, msg: _write_progress(pct, msg),
            )
            _write_progress(100, f"Complete! WR={report['overall_win_rate']:.1f}% over {report['total_triggered']} trades")
        except Exception as e:
            _write_progress(-1, f"Error: {e}", error=True)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    st.session_state["training_thread"] = t
    st.session_state["training_start"] = datetime.now()
    st.session_state["training_pct"] = 0
    st.session_state["training_msg"] = "Starting training..."


def _is_training() -> bool:
    t = st.session_state.get("training_thread")
    return t is not None and t.is_alive()


def _read_progress() -> dict:
    try:
        with open(_PROGRESS_FILE) as f:
            return json.load(f)
    except Exception:
        return {"pct": 0, "msg": "Starting...", "done": False, "error": False}


# ── Report loading ────────────────────────────────────────────────────────────

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


# ── Charts ────────────────────────────────────────────────────────────────────

def _learning_curve_chart(weekly_summary: list) -> go.Figure:
    if not weekly_summary:
        return go.Figure()
    weeks  = [f"W{w['week_num']} {w['start_date']}" for w in weekly_summary]
    wr     = [w["win_rate"]  for w in weekly_summary]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=weeks, y=wr, mode="lines+markers+text",
        text=[f"{v:.0f}%" for v in wr], textposition="top center",
        name="Win Rate %",
        line=dict(color="#26A69A", width=2),
        marker=dict(size=8, color=[
            "#4CAF50" if v >= 60 else "#FF9800" if v >= 45 else "#EF5350" for v in wr
        ]),
    ))
    fig.add_hline(y=70, line_dash="dash", line_color="#FFD700", line_width=1,
                  annotation_text="70% target", annotation_position="right")
    fig.update_layout(
        height=300, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=40, r=80, t=30, b=60),
        yaxis=dict(title="Win Rate %", range=[0, 100]),
        showlegend=False,
    )
    return fig


def _pnl_chart(daily_results: list) -> go.Figure:
    if not daily_results:
        return go.Figure()
    dates   = [d["date"] for d in daily_results]
    cum_pnl = []
    running = 0.0
    for d in daily_results:
        running += d["pnl"]
        cum_pnl.append(running)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=cum_pnl, mode="lines",
        fill="tozeroy",
        line=dict(color="#26A69A", width=2),
    ))
    fig.update_layout(
        height=270, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=40, r=40, t=20, b=60),
        yaxis=dict(title="Cumulative P&L (₹)"),
        showlegend=False,
    )
    return fig


def _convergence_chart(reports: list) -> go.Figure:
    if len(reports) < 2:
        return None
    labels = [f"Run {i+1}" for i in range(len(reports))]
    wrs    = [r["overall_win_rate"] for r in reports]
    trades = [r["total_triggered"]  for r in reports]
    colors = ["#4CAF50" if wr >= 60 else "#FF9800" if wr >= 45 else "#EF5350" for wr in wrs]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=wrs, marker_color=colors,
        text=[f"{wr:.1f}%\n({t} trades)" for wr, t in zip(wrs, trades)],
        textposition="outside",
    ))
    fig.add_hline(y=70, line_dash="dash", line_color="#FFD700", annotation_text="70% target")
    fig.update_layout(
        height=280, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=40, r=40, t=20, b=40),
        yaxis=dict(title="Win Rate %", range=[0, max(wrs) + 20]),
        showlegend=False,
    )
    return fig


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("🔬 Historical Walk-Forward Trainer")
st.caption(
    "Simulate the full AI recommender cycle on up to 60 days of real 15m data. "
    "Each day: strategies analyze data up to 11:02 AM IST → setups test against the afternoon session. "
    "Learned params feed directly into the live bot's `strategy_memory.json`."
)

# ── Live progress (always rendered near the top) ──────────────────────────────
currently_training = _is_training()
prog = _read_progress() if currently_training else {}

if currently_training or (prog.get("pct", 0) == 100 and not prog.get("error")):
    st.subheader("Training In Progress" if currently_training else "Last Run Complete")
    pct = max(0.0, min(100.0, prog.get("pct", 0)))
    msg = prog.get("msg", "Running...")
    err = prog.get("error", False)

    st.progress(pct / 100)
    if err:
        st.error(f"Training failed: {msg}")
    else:
        col_pct, col_time = st.columns([3, 1])
        col_pct.write(f"**{pct:.0f}%** — {msg}")
        if "training_start" in st.session_state:
            elapsed = datetime.now() - st.session_state["training_start"]
            col_time.caption(f"Elapsed: {elapsed.seconds // 60}m {elapsed.seconds % 60}s | Updated: {prog.get('ts', '—')}")

    if currently_training and not prog.get("done", False):
        st.caption("Page auto-refreshes every 2 seconds while training...")
    elif prog.get("done") and not err and not currently_training:
        st.success("Training complete — see results below.")

    st.divider()

# ── Past runs ─────────────────────────────────────────────────────────────────
reports = _load_all_reports()

if reports:
    st.subheader(f"Training History — {len(reports)} run{'s' if len(reports) > 1 else ''}")

    table_rows = []
    for i, r in enumerate(reports):
        table_rows.append({
            "Run":        f"#{i + 1}",
            "Timestamp":  r.get("run_id", "")[:16].replace("T", " "),
            "Days":       r.get("trading_days", 0),
            "Symbols":    len(r.get("symbols_used", [])),
            "Trades":     r.get("total_triggered", 0),
            "Win Rate":   f"{r.get('overall_win_rate', 0):.1f}%",
            "P&L":        f"₹{r.get('total_pnl', 0):+.0f}",
            "Opt Runs":   r.get("optimizer_runs", 0),
            "Claude":     r.get("claude_calls", 0),
            "Quick":      "✓" if r.get("quick_mode") else "—",
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    conv = _convergence_chart(reports)
    if conv:
        st.subheader("Convergence Test")
        st.caption("Win rate should improve run-to-run if learning is working. Flat/declining = overfitting risk.")
        st.plotly_chart(conv, use_container_width=True)

    st.subheader("Inspect a Run")
    run_options = [
        f"Run #{i+1} — {r.get('run_id','')[:16]} (WR {r.get('overall_win_rate',0):.1f}%, {r.get('total_triggered',0)} trades)"
        for i, r in enumerate(reports)
    ]
    sel_idx = st.selectbox("", range(len(run_options)), format_func=lambda i: run_options[i],
                           index=len(reports) - 1)
    sel = reports[sel_idx]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Win Rate",      f"{sel.get('overall_win_rate', 0):.1f}%")
    c2.metric("Trades",        sel.get("total_triggered", 0))
    c3.metric("P&L",           f"₹{sel.get('total_pnl', 0):+.0f}")
    c4.metric("Training Days", sel.get("trading_days", 0))

    cl, cr = st.columns(2)
    with cl:
        st.subheader("Weekly Learning Curve")
        st.plotly_chart(_learning_curve_chart(sel.get("weekly_summary", [])), use_container_width=True)
    with cr:
        st.subheader("Cumulative P&L")
        st.plotly_chart(_pnl_chart(sel.get("daily_results", [])), use_container_width=True)

    with st.expander("Final Learned Parameters & Insights"):
        cp, cw = st.columns(2)
        with cp:
            st.write("**Zone params:**")
            st.json(sel.get("final_zone_params", {}))
        with cw:
            st.write("**Strategy weights (unknown regime):**")
            w = sel.get("final_weights", {})
            st.json(w.get("unknown", w))
        fs = sel.get("final_summary", {})
        if fs.get("executive_summary"):
            st.info(fs["executive_summary"])
        for ins in fs.get("key_insights", []):
            st.write(f"• {ins}")
        if fs.get("recommended_live_approach"):
            st.success(f"**Recommended approach:** {fs['recommended_live_approach']}")

    with st.expander("Strategy Breakdown"):
        strat_agg: dict = {}
        for d in sel.get("daily_results", []):
            for t in d.get("trades", []):
                sn = t["strategy"]
                if sn not in strat_agg:
                    strat_agg[sn] = {"triggered": 0, "wins": 0, "losses": 0, "pnl": 0.0}
                sa = strat_agg[sn]
                if t["outcome"] in ("TARGET_HIT", "SL_HIT"):
                    sa["triggered"] += 1
                if t["outcome"] == "TARGET_HIT":  sa["wins"]  += 1
                elif t["outcome"] == "SL_HIT":    sa["losses"] += 1
                sa["pnl"] += t["pnl"]
        strat_rows = []
        for sn, sa in strat_agg.items():
            trig = sa["triggered"]
            wr   = sa["wins"] / trig * 100 if trig > 0 else 0.0
            strat_rows.append({
                "Strategy": sn, "Triggered": trig,
                "Wins": sa["wins"], "Losses": sa["losses"],
                "Win Rate": f"{wr:.1f}%", "P&L": f"₹{sa['pnl']:+.0f}",
            })
        if strat_rows:
            st.dataframe(pd.DataFrame(strat_rows), use_container_width=True, hide_index=True)

    st.divider()
else:
    st.info("No training runs yet. Start your first run below.")

# ── Start new run ─────────────────────────────────────────────────────────────
st.subheader("Start New Training Run")
st.caption(
    "Quick mode (~5–10 min): 10 symbols, smaller param grid. "
    "Full mode (~30–60 min): 20 symbols, full grid. "
    "Run multiple times — improving WR confirms learning is working."
)

col_opts, col_btn = st.columns([3, 1])
with col_opts:
    quick_mode = st.checkbox("Quick mode (10 symbols, smaller grid)", value=True)
    no_ai_mode = st.checkbox("No-AI mode (skip Claude calls — grid only)", value=False)

with col_btn:
    st.write("")  # vertical spacing
    disabled = currently_training
    if st.button("▶ Start Training", disabled=disabled, type="primary", use_container_width=True):
        _start_training(quick=quick_mode, no_ai=no_ai_mode)
        st.rerun()

# ── Auto-refresh while training ───────────────────────────────────────────────
# This runs AFTER the entire page is rendered so nothing gets cut off
if currently_training and not prog.get("done", False):
    time.sleep(2)
    st.rerun()

# ── How it works ──────────────────────────────────────────────────────────────
with st.expander("How it works"):
    st.markdown("""
**Walk-forward simulation loop:**

| Step | What happens |
|------|-------------|
| Day 1..N | For each historical trading day D, all 3 strategies analyze data up to 11:02 AM IST → find setups → simulate triggering in the 11:02 AM–3:30 PM afternoon session |
| Every 5 days | Mini-optimizer runs param grids (no Claude) → picks best zone params by win rate |
| Every 10 days | Claude synthesizes 10-day trade outcomes → adjusts regime-specific slot weights |
| Final | Claude writes comprehensive summary → saves learned params to `strategy_memory.json` + `strategy_weights.json` |

**Multiple runs = convergence test:**
- Run 1: default params → baseline WR
- Run 2: Run 1's learned params → WR should improve
- Run 3+: WR stabilises = converged. Declining WR = overfitting risk.

**Where results go:** `.streamlit/strategy_memory.json` and `.streamlit/strategy_weights.json` — the live bot reads these on startup.
""")

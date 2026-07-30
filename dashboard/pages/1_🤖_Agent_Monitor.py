"""
Autonomous Optimizer Monitor
-----------------------------
Real-time view of the self-improving agent loop.
Reads session_state.json and latest backtest results — no live process needed.
Auto-refreshes every 5 seconds when the agent appears to be running.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import time
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Agent Monitor", page_icon="🤖", layout="wide")

# ── Paths ──────────────────────────────────────────────────────────────────────
_STATE_FILE   = "autonomous_optimizer/context/session_state.json"
_RESULT_FILE  = "reports/training/latest_backtest_result.json"
_MEMORY_FILE  = ".streamlit/strategy_memory.json"


# ── Loaders ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=4)
def _load_state() -> dict:
    try:
        with open(_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=4)
def _load_latest_result() -> dict:
    try:
        with open(_RESULT_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(ttl=30)
def _load_strategy_memory() -> dict:
    try:
        with open(_MEMORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _state_age_seconds() -> float:
    try:
        return time.time() - Path(_STATE_FILE).stat().st_mtime
    except Exception:
        return 9999.0


# ── Charts ─────────────────────────────────────────────────────────────────────
def _trajectory_chart(state: dict) -> go.Figure:
    wr   = state.get("wr_trajectory", [])
    pnl  = state.get("pnl_trajectory", [])
    comp = state.get("composite_score_trajectory", [])
    tc   = state.get("trade_count_trajectory", [])

    n = max(len(wr), len(pnl), len(comp))
    if n == 0:
        return go.Figure()

    xs = list(range(1, n + 1))

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        subplot_titles=("Win Rate %", "P&L per Iteration (₹)", "Composite Score"),
        vertical_spacing=0.08,
        row_heights=[0.35, 0.35, 0.30],
    )

    # Win rate with 55% / 70% target bands
    if wr:
        xs_wr = list(range(1, len(wr) + 1))
        fig.add_trace(go.Scatter(
            x=xs_wr, y=wr, mode="lines+markers", name="Win Rate",
            line=dict(color="#26A69A", width=2),
            marker=dict(size=5, color=["#4CAF50" if v >= 70 else "#FF9800" if v >= 55 else "#EF5350" for v in wr]),
        ), row=1, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#4CAF50", line_width=1,
                      annotation_text="Tier2 70%", annotation_position="right", row=1, col=1)
        fig.add_hline(y=55, line_dash="dot", line_color="#FF9800", line_width=1,
                      annotation_text="Tier1 55%", annotation_position="right", row=1, col=1)

    # P&L bars
    if pnl:
        xs_pnl = list(range(1, len(pnl) + 1))
        colors = ["#4CAF50" if v >= 0 else "#EF5350" for v in pnl]
        fig.add_trace(go.Bar(
            x=xs_pnl, y=pnl, name="P&L", marker_color=colors, showlegend=False,
        ), row=2, col=1)
        fig.add_hline(y=0, line_color="#888", line_width=1, row=2, col=1)

    # Composite score
    if comp:
        xs_c = list(range(1, len(comp) + 1))
        fig.add_trace(go.Scatter(
            x=xs_c, y=comp, mode="lines", name="Composite",
            line=dict(color="#7C4DFF", width=2), fill="tozeroy",
            fillcolor="rgba(124,77,255,0.1)",
        ), row=3, col=1)

    fig.update_layout(
        height=520, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=50, r=80, t=40, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        xaxis3=dict(title="Iteration"),
    )
    return fig


def _approach_outcome_chart(approaches: list) -> go.Figure:
    if not approaches:
        return go.Figure()
    counts = {"improved": 0, "degraded": 0, "neutral": 0, "critic_rejected": 0}
    for a in approaches:
        r = a.get("result", "neutral")
        if r in counts:
            counts[r] += 1
        else:
            counts["neutral"] += 1
    labels = list(counts.keys())
    values = list(counts.values())
    colors = ["#4CAF50", "#EF5350", "#9E9E9E", "#FF9800"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        marker_colors=colors,
        textinfo="label+percent+value",
        textfont_size=12,
    ))
    fig.update_layout(
        height=280, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=False,
    )
    return fig


def _root_cause_chart(approaches: list) -> go.Figure:
    if not approaches:
        return go.Figure()
    cats: dict[str, int] = {}
    for a in approaches:
        c = a.get("root_cause_category", a.get("description", "unknown"))
        c = c.split("_")[0] if "_" in c else c[:18]
        cats[c] = cats.get(c, 0) + 1
    sorted_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:10]
    labels = [x[0] for x in sorted_cats]
    values = [x[1] for x in sorted_cats]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color="#26A69A",
        text=values, textposition="outside",
    ))
    fig.update_layout(
        height=280, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=10, r=40, t=10, b=10),
        xaxis=dict(title="Count"),
        showlegend=False,
    )
    return fig


def _weekly_pnl_chart(result: dict) -> go.Figure:
    weeks = result.get("weekly_summaries", [])
    if not weeks:
        return go.Figure()
    labels = ["W%d" % (i + 1) for i in range(len(weeks))]
    pnls   = [w.get("pnl", 0) for w in weeks]
    wrs    = [w.get("win_rate", 0) for w in weeks]
    colors = ["#4CAF50" if p >= 0 else "#EF5350" for p in pnls]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=labels, y=pnls, name="P&L (₹)", marker_color=colors,
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=labels, y=wrs, mode="lines+markers", name="Win Rate %",
        line=dict(color="#FFD700", width=2), marker=dict(size=7),
    ), secondary_y=True)
    # 70% target line on secondary axis (add_hline doesn't support secondary_y on subplots)
    fig.add_trace(go.Scatter(
        x=[labels[0], labels[-1]], y=[70, 70], mode="lines", name="70% target",
        line=dict(color="#4CAF50", width=1, dash="dash"),
        showlegend=False,
    ), secondary_y=True)
    fig.update_layout(
        height=260, template="plotly_dark",
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
        margin=dict(l=40, r=60, t=20, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="P&L (₹)", secondary_y=False)
    fig.update_yaxes(title_text="Win Rate %", range=[0, 100], secondary_y=True)
    return fig


# ── Page ───────────────────────────────────────────────────────────────────────
st.title("🤖 Autonomous Optimizer Monitor")

state_data  = _load_state()
result_data = _load_latest_result()
memory_data = _load_strategy_memory()

s = state_data.get("state", {})
wm = state_data.get("working_memory", [])
lt = state_data.get("long_term_memory", {})

age = _state_age_seconds()
is_running = age < 120  # assume running if state file updated in last 2 min

# ── Status bar ─────────────────────────────────────────────────────────────────
status_col, refresh_col = st.columns([5, 1])
with status_col:
    if not state_data:
        st.warning("No session state found. Start the optimizer first: `python -m autonomous_optimizer`")
    elif is_running:
        st.success("🟢 Agent is RUNNING — state updated %.0fs ago" % age)
    else:
        ts_str = ""
        try:
            ts_str = datetime.fromtimestamp(Path(_STATE_FILE).stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        st.info("⚫ Agent is idle (last seen %s)" % ts_str)
with refresh_col:
    auto_refresh = st.toggle("Auto-refresh", value=is_running)

st.divider()

if not state_data:
    st.stop()

# ── Top KPIs ───────────────────────────────────────────────────────────────────
iteration   = s.get("iteration", 0)
phase       = s.get("phase", "A")
consec      = s.get("consecutive_dual_success", 0)
best_wr     = s.get("best_win_rate", 0.0)
best_pnl    = s.get("best_pnl", 0.0)
best_comp   = s.get("best_composite", 0.0)
best_trades = s.get("best_trade_count", 0)
blocked_ct  = len(lt.get("blocked_approaches", []))

cur_wr     = result_data.get("overall_win_rate", 0.0)
cur_pnl    = result_data.get("total_pnl", 0.0)
cur_trades = result_data.get("total_triggered", 0)
days_run   = result_data.get("days_run", 0)

k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
k1.metric("Iteration",        str(iteration))
k2.metric("Phase",            phase,          help="A → B → C as strategy improves")
k3.metric("Consecutive ✅",   "%d/3" % consec, help="Dual-success (Tier1+Tier2) runs in a row needed to declare goal achieved")
k4.metric("Best WR",          "%.1f%%" % best_wr)
k5.metric("Best P&L",         "₹%+.0f" % best_pnl)
k6.metric("Last WR",          "%.1f%%" % cur_wr,
          delta="%.1f%%" % (cur_wr - best_wr) if best_wr > 0 else None)
k7.metric("Last P&L",         "₹%+.0f" % cur_pnl)
k8.metric("Blocked approaches", str(blocked_ct), help="Approaches LLM is not allowed to retry")

st.divider()

# ── Trajectories ───────────────────────────────────────────────────────────────
left, right = st.columns([3, 1])
with left:
    st.subheader("Performance Trajectories")
    st.plotly_chart(_trajectory_chart(s), use_container_width=True)

with right:
    st.subheader("Iteration Outcomes")
    approaches = s.get("approaches_tried", [])
    st.plotly_chart(_approach_outcome_chart(approaches), use_container_width=True)

    st.subheader("Root Cause Distribution")
    st.plotly_chart(_root_cause_chart(wm), use_container_width=True)

st.divider()

# ── Latest backtest result ──────────────────────────────────────────────────────
st.subheader("Latest Backtest Result")
if result_data:
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Win Rate",   "%.1f%%" % cur_wr,
              delta="%.1f%% vs Tier2 target" % (cur_wr - 70))
    r2.metric("P&L",        "₹%+.0f" % cur_pnl)
    r3.metric("Trades",     str(cur_trades))
    r4.metric("Days",       str(days_run))
    trades_per_day = cur_trades / days_run if days_run > 0 else 0
    r5.metric("Trades/day", "%.1f" % trades_per_day,
              delta="OK" if trades_per_day <= 3 else "HIGH",
              delta_color="normal" if trades_per_day <= 3 else "inverse")

    st.subheader("Weekly P&L + Win Rate")
    st.plotly_chart(_weekly_pnl_chart(result_data), use_container_width=True)
else:
    st.info("No backtest result yet — run at least one iteration.")

st.divider()

# ── Working memory — last N iterations in detail ───────────────────────────────
st.subheader("Working Memory — Last %d Iterations" % len(wm))
if wm:
    rows = []
    for rec in reversed(wm):
        rows.append({
            "Iter":       rec.get("iteration", ""),
            "Phase":      rec.get("phase", ""),
            "Hypothesis": rec.get("hypothesis_slug", ""),
            "Root Cause": rec.get("root_cause_category", ""),
            "WR %":       "%.1f" % rec.get("win_rate", 0),
            "P&L":        "₹%+.0f" % rec.get("pnl", 0),
            "Trades":     rec.get("trade_count", 0),
            "Score":      "%.4f" % rec.get("composite_score", 0),
            "Reverted":   "↩ yes" if rec.get("reverted") else "✓ kept",
        })
    df = pd.DataFrame(rows)

    def _style_row(row):
        if row["Reverted"] == "↩ yes":
            return ["color: #888"] * len(row)
        wr = float(row["WR %"])
        if wr >= 70:
            return ["color: #4CAF50"] * len(row)
        if wr >= 55:
            return ["color: #FF9800"] * len(row)
        return ["color: #EF5350"] * len(row)

    st.dataframe(df.style.apply(_style_row, axis=1), use_container_width=True, hide_index=True)

    with st.expander("Hypothesis descriptions"):
        for rec in reversed(wm):
            icon = "↩" if rec.get("reverted") else "✓"
            wr = rec.get("win_rate", 0)
            color = "green" if wr >= 70 else "orange" if wr >= 55 else "red"
            st.markdown(
                f"**[{icon} Iter {rec.get('iteration')} | Phase {rec.get('phase')}]** "
                f":{color}[WR {wr:.1f}% | ₹{rec.get('pnl', 0):+.0f}]  \n"
                f"`{rec.get('hypothesis_slug', '')}` — {rec.get('hypothesis_description', '')}"
            )
else:
    st.info("Working memory is empty — no completed iterations yet.")

st.divider()

# ── Long-term memory ────────────────────────────────────────────────────────────
st.subheader("Long-Term Memory")
ltab1, ltab2, ltab3 = st.tabs(["Phase Summaries", "All Hypotheses", "Blocked Approaches"])

with ltab1:
    summaries = lt.get("phase_summaries", [])
    if summaries:
        for ps in summaries:
            with st.expander("Phase %s — %d iterations | best composite %.4f" % (
                    ps.get("phase", "?"), ps.get("iterations_run", 0), ps.get("best_composite", 0))):
                st.write(ps.get("insight", ""))
                c1, c2 = st.columns(2)
                c1.write("**Breakthroughs:** " + (", ".join(ps.get("breakthroughs", [])) or "none"))
                c2.write("**Dead ends:** " + (", ".join(ps.get("dead_ends", [])) or "none"))
    else:
        st.info("No phase summaries yet (generated every 10 iterations).")

with ltab2:
    hyps = lt.get("hypothesis_embeddings", [])
    if hyps:
        hrows = []
        for h in reversed(hyps):
            hrows.append({
                "Iter":   h.get("iteration", ""),
                "Slug":   h.get("slug", ""),
                "Result": h.get("result", ""),
                "Description": h.get("description", ""),
            })
        hdf = pd.DataFrame(hrows)

        def _style_result(val):
            if "improv" in str(val):   return "color: #4CAF50"
            if "degrad" in str(val) or "fail" in str(val): return "color: #EF5350"
            if "critic" in str(val):   return "color: #FF9800"
            return "color: #888"

        st.dataframe(
            hdf.style.map(_style_result, subset=["Result"]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No hypothesis history yet.")

with ltab3:
    blocked = lt.get("blocked_approaches", [])
    if blocked:
        for b in blocked:
            st.markdown("- %s" % b)
    else:
        st.success("No blocked approaches — agent has full freedom.")

st.divider()

# ── Current strategy params ────────────────────────────────────────────────────
st.subheader("Current Live Strategy Params")
best_params = memory_data.get("best_params", {})
if best_params:
    pcols = st.columns(len(best_params))
    for i, (k, v) in enumerate(best_params.items()):
        pcols[i].metric(k.replace("_", " ").title(), str(v))
    with st.expander("Full strategy memory"):
        mem_iters = memory_data.get("iterations", [])
        if mem_iters:
            mem_rows = []
            for m in reversed(mem_iters[-20:]):
                mem_rows.append({
                    "Timestamp": m.get("timestamp", "")[:19],
                    "Source":    m.get("source", "nightly"),
                    "WR %":      "%.1f" % m.get("win_rate", 0),
                    "P&L":       "₹%+.0f" % m.get("pnl", 0),
                    "Analysis":  m.get("analysis", "")[:80],
                })
            st.dataframe(pd.DataFrame(mem_rows), use_container_width=True, hide_index=True)
else:
    st.info("No strategy memory yet. Run the optimizer or historical trainer first.")

st.divider()

# ── All attempted approaches (full log) ────────────────────────────────────────
with st.expander("Full approach log (%d total)" % len(approaches)):
    if approaches:
        arows = []
        for a in reversed(approaches):
            arows.append({
                "Iter":        a.get("iteration", ""),
                "Slug":        a.get("slug", ""),
                "Result":      a.get("result", ""),
                "Reverted":    "yes" if a.get("reverted") else "no",
                "Description": a.get("description", ""),
            })
        st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True)

# ── Auto-refresh ───────────────────────────────────────────────────────────────
if auto_refresh and is_running:
    time.sleep(5)
    st.cache_data.clear()
    st.rerun()

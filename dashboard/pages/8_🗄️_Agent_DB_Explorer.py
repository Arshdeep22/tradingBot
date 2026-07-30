"""
Agent DB Explorer
-----------------
Streamlit UI to browse everything the two-agent system persists in
`database/agent.db` — no CLI / sqlite3 shell required.

Layout:
  * Sidebar: agent filter (optimizer / trading_bot / both), run_id filter,
    row-count sliders, refresh button.
  * Main tabs:
      1. Overview             — high-level counts + quick stats.
      2. Optimizer memory     — session_state, working_memory, phase_summaries,
                                approaches_tried, trajectories.
      3. Trading agent        — trading_agent_config, memory (lessons),
                                runs, per-run decisions + trades.
      4. Logs                 — runtime_logs (filter by agent + run_id).
      5. Tool invocations     — every tool call, filterable by tool + agent + run.

Every table is shown as a `st.dataframe` so you can sort, resize columns,
and download CSV via the built-in toolbar.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

# Make the repo root importable so `autonomous_optimizer.storage` resolves
# when Streamlit is launched from anywhere.
_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Agent DB Explorer", page_icon="🗄️",
                   layout="wide")

DB_PATH = str(_ROOT / "database" / "agent.db")


# ── data loaders (cached) ──────────────────────────────────────────────────
def _connect() -> Optional[sqlite3.Connection]:
    if not os.path.exists(DB_PATH):
        return None
    c = sqlite3.connect(DB_PATH, timeout=5)
    c.row_factory = sqlite3.Row
    return c


@st.cache_data(ttl=3)
def load_table(table: str, *, where: str = "",
               params: tuple = (), order: str = "id DESC",
               limit: Optional[int] = None) -> pd.DataFrame:
    conn = _connect()
    if conn is None:
        return pd.DataFrame()
    q = f"SELECT * FROM {table}"
    if where:
        q += f" WHERE {where}"
    if order:
        q += f" ORDER BY {order}"
    if limit:
        q += f" LIMIT {int(limit)}"
    try:
        df = pd.read_sql_query(q, conn, params=params)
    except Exception as e:
        conn.close()
        st.error(f"Query failed on {table}: {e}")
        return pd.DataFrame()
    conn.close()
    return df


@st.cache_data(ttl=3)
def table_exists(name: str) -> bool:
    conn = _connect()
    if conn is None:
        return False
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    conn.close()
    return row is not None


@st.cache_data(ttl=3)
def row_count(table: str, where: str = "", params: tuple = ()) -> int:
    conn = _connect()
    if conn is None:
        return 0
    q = f"SELECT COUNT(*) FROM {table}"
    if where:
        q += f" WHERE {where}"
    try:
        n = conn.execute(q, params).fetchone()[0]
    except Exception:
        n = 0
    conn.close()
    return int(n)


@st.cache_data(ttl=3)
def distinct_values(table: str, column: str,
                    limit: int = 200) -> list[str]:
    conn = _connect()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM {table} "
            f"WHERE {column} IS NOT NULL "
            f"ORDER BY {column} DESC LIMIT ?", (limit,),
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    return [r[0] for r in rows if r[0] is not None]


# ── page ───────────────────────────────────────────────────────────────────
st.title("🗄️ Agent DB Explorer")
st.caption(f"Reading from `{DB_PATH}` — everything the optimizer and "
           "trading agent persist. No log files, no JSON files.")

if not os.path.exists(DB_PATH):
    st.error(f"Database not found at `{DB_PATH}`. Run the optimizer or "
             "trading agent at least once to create it.")
    st.stop()

# ── sidebar filters ────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")
    agent_filter = st.selectbox(
        "Agent", options=["both", "optimizer", "trading_bot"], index=0,
        help="Filter logs and tool_invocations by which agent produced them.",
    )

    run_ids = distinct_values("trading_agent_runs", "run_id", limit=50)
    run_id_filter = st.selectbox(
        "Trading-agent run_id",
        options=["(any)"] + run_ids,
        help="Drill down to a single trading-agent backtest run.",
    )
    run_id_val: Optional[str] = (
        None if run_id_filter == "(any)" else run_id_filter
    )

    st.divider()
    log_limit = st.slider("Log rows to show", 20, 2000, 200, step=20)
    tool_limit = st.slider("Tool-call rows to show", 20, 2000, 200, step=20)

    st.divider()
    if st.button("🔄 Refresh (clear cache)"):
        st.cache_data.clear()
        st.rerun()


# ── tabs ───────────────────────────────────────────────────────────────────
tab_overview, tab_opt, tab_bot, tab_logs, tab_tools = st.tabs([
    "Overview", "Optimizer memory", "Trading agent",
    "Runtime logs", "Tool invocations",
])


# ══════════════════════════════════════════════════════════════════════════
# Overview
# ══════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.subheader("At a glance")

    c1, c2, c3, c4 = st.columns(4)
    opt_state = load_table("session_state", where="id = 1", order="", limit=1)
    if not opt_state.empty:
        c1.metric("Optimizer iteration", int(opt_state.iloc[0]["iteration"]))
        c2.metric("Phase", opt_state.iloc[0]["phase"])
        c3.metric("Best composite",
                  f"{float(opt_state.iloc[0]['best_composite']):.3f}")
        c4.metric("Dual-success streak",
                  int(opt_state.iloc[0]["consecutive_dual_success"]))
    else:
        c1.metric("Optimizer iteration", "0")
        c2.metric("Phase", "A")
        c3.metric("Best composite", "0.000")
        c4.metric("Dual-success streak", "0")

    st.subheader("Row counts")
    tables = [
        # Optimizer
        "session_state", "working_memory", "phase_summaries",
        "hypothesis_embeddings", "blocked_approaches",
        "approaches_tried", "trajectories",
        # Trading agent
        "trading_agent_config", "trading_agent_memory",
        "trading_agent_runs", "trading_agent_decisions",
        "trading_agent_trades",
        # Shared
        "runtime_logs", "tool_invocations",
    ]
    counts = []
    for t in tables:
        if table_exists(t):
            counts.append({"table": t, "rows": row_count(t)})
    st.dataframe(pd.DataFrame(counts), use_container_width=True,
                 hide_index=True)

    st.subheader("Recent trading-agent runs")
    runs = load_table("trading_agent_runs",
                       order="started_at DESC", limit=20)
    if runs.empty:
        st.info("No trading-agent runs yet.")
    else:
        show_cols = [c for c in [
            "run_id", "mode", "started_at", "ended_at", "days",
            "win_rate", "total_pnl", "trade_count", "trades_per_day",
            "triggered_by", "ok", "error",
        ] if c in runs.columns]
        st.dataframe(runs[show_cols], use_container_width=True,
                     hide_index=True)


# ══════════════════════════════════════════════════════════════════════════
# Optimizer memory
# ══════════════════════════════════════════════════════════════════════════
with tab_opt:
    st.subheader("session_state")
    st.dataframe(load_table("session_state", where="id = 1", order="",
                             limit=1), use_container_width=True,
                 hide_index=True)

    st.subheader("Working memory (recent iterations)")
    st.dataframe(load_table("working_memory",
                             order="id DESC", limit=50),
                 use_container_width=True, hide_index=True)

    st.subheader("Phase summaries")
    st.dataframe(load_table("phase_summaries",
                             order="id DESC", limit=50),
                 use_container_width=True, hide_index=True)

    st.subheader("Approaches tried (audit trail)")
    st.dataframe(load_table("approaches_tried",
                             order="id DESC", limit=200),
                 use_container_width=True, hide_index=True)

    st.subheader("Blocked approaches")
    st.dataframe(load_table("blocked_approaches",
                             order="id DESC", limit=100),
                 use_container_width=True, hide_index=True)

    st.subheader("Trajectories (per-iteration metrics)")
    traj = load_table("trajectories", order="id ASC", limit=1000)
    if not traj.empty:
        st.line_chart(traj[["win_rate", "composite_score"]],
                      use_container_width=True)
        st.line_chart(traj[["pnl"]], use_container_width=True)
        with st.expander("Show raw trajectory rows"):
            st.dataframe(traj, use_container_width=True, hide_index=True)
    else:
        st.info("No trajectory samples yet.")

    st.subheader("Hypothesis embeddings")
    embed = load_table("hypothesis_embeddings",
                        order="id DESC", limit=50)
    if not embed.empty and "embedding_json" in embed.columns:
        # Embeddings can be huge — hide the JSON blob by default.
        show = embed.drop(columns=["embedding_json"])
        st.dataframe(show, use_container_width=True, hide_index=True)
    else:
        st.dataframe(embed, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════
# Trading agent
# ══════════════════════════════════════════════════════════════════════════
with tab_bot:
    st.subheader("Config (edited by the optimizer)")
    cfg = load_table("trading_agent_config", where="id = 1",
                     order="", limit=1)
    if cfg.empty:
        st.info("No trading-agent config yet.")
    else:
        row = cfg.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Mode", row.get("mode", "?"))
        c2.metric("LLM model", str(row.get("llm_model", "?"))[:30])
        c3.metric("Updated at", str(row.get("updated_at", "?")))
        with st.expander("System prompt (verbatim)"):
            st.code(row.get("system_prompt", "") or "(empty)", language="text")
        st.write("**Risk params**")
        st.json(row.get("risk_params_json", "{}"))
        st.write("**Strategy params**")
        st.json(row.get("strategy_params_json", "{}"))
        st.write("**Symbols**")
        st.json(row.get("symbols_json", "[]"))

    st.subheader("Lessons (memory the optimizer writes for the bot)")
    lessons = load_table("trading_agent_memory",
                          order="id DESC", limit=200)
    st.dataframe(lessons, use_container_width=True, hide_index=True)

    st.subheader("Runs")
    runs = load_table("trading_agent_runs",
                       order="started_at DESC", limit=200)
    st.dataframe(runs, use_container_width=True, hide_index=True)

    if run_id_val:
        st.divider()
        st.subheader(f"🔬 Drill-down for run_id = `{run_id_val}`")

        run_summary = load_table(
            "trading_agent_runs", where="run_id = ?",
            params=(run_id_val,), order="", limit=1,
        )
        if not run_summary.empty:
            r = run_summary.iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Mode", r["mode"])
            m2.metric("Win rate", f"{float(r['win_rate'] or 0):.1f}%")
            m3.metric("Total P&L",
                      f"₹{float(r['total_pnl'] or 0):,.2f}")
            m4.metric("Trades", int(r["trade_count"] or 0))

        st.write("**Decisions** (every LLM call this run made)")
        st.dataframe(load_table(
            "trading_agent_decisions", where="run_id = ?",
            params=(run_id_val,), order="id ASC", limit=1000,
        ), use_container_width=True, hide_index=True)

        st.write("**Trades**")
        st.dataframe(load_table(
            "trading_agent_trades", where="run_id = ?",
            params=(run_id_val,), order="id ASC", limit=1000,
        ), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════
# Runtime logs
# ══════════════════════════════════════════════════════════════════════════
with tab_logs:
    st.subheader("runtime_logs")
    clauses, params = [], []
    if agent_filter != "both":
        clauses.append("agent = ?")
        params.append(agent_filter)
    if run_id_val:
        clauses.append("run_id = ?")
        params.append(run_id_val)
    where = " AND ".join(clauses) if clauses else ""

    logs = load_table("runtime_logs", where=where,
                      params=tuple(params),
                      order="id DESC", limit=log_limit)
    st.caption(
        f"Filter: agent={agent_filter}, "
        f"run_id={'(any)' if run_id_val is None else run_id_val}. "
        f"Showing {len(logs)} rows."
    )
    # Reorder columns for readability if present.
    preferred = ["ts", "level", "agent", "run_id",
                 "logger_name", "message", "iteration"]
    cols = [c for c in preferred if c in logs.columns] + \
           [c for c in logs.columns if c not in preferred]
    st.dataframe(logs[cols] if cols else logs,
                 use_container_width=True, hide_index=True, height=520)


# ══════════════════════════════════════════════════════════════════════════
# Tool invocations
# ══════════════════════════════════════════════════════════════════════════
with tab_tools:
    st.subheader("tool_invocations")

    all_tools = distinct_values("tool_invocations", "tool_name", limit=100)
    tool_choice = st.selectbox("Tool filter",
                                ["(any)"] + all_tools)
    show_failed_only = st.checkbox("Only failed calls (ok=0)")

    clauses, params = [], []
    if agent_filter != "both":
        clauses.append("agent = ?")
        params.append(agent_filter)
    if run_id_val:
        clauses.append("run_id = ?")
        params.append(run_id_val)
    if tool_choice != "(any)":
        clauses.append("tool_name = ?")
        params.append(tool_choice)
    if show_failed_only:
        clauses.append("ok = 0")
    where = " AND ".join(clauses) if clauses else ""

    tools = load_table("tool_invocations", where=where,
                       params=tuple(params),
                       order="id DESC", limit=tool_limit)
    st.caption(
        f"Filter: agent={agent_filter}, "
        f"run_id={'(any)' if run_id_val is None else run_id_val}, "
        f"tool={tool_choice}, failed_only={show_failed_only}. "
        f"Showing {len(tools)} rows."
    )
    preferred = ["ts", "agent", "run_id", "tool_name", "action",
                 "ok", "error", "iteration", "args_json", "result_json"]
    cols = [c for c in preferred if c in tools.columns] + \
           [c for c in tools.columns if c not in preferred]
    st.dataframe(tools[cols] if cols else tools,
                 use_container_width=True, hide_index=True, height=520)

    with st.expander("💡 Common queries"):
        st.markdown("""
- **Which trading-bot tool failed in run X?**
  Set agent=`trading_bot`, run_id=`<the run>`, check *Only failed*.
- **Every action the optimizer took at iteration N?**
  Set agent=`optimizer`, then sort by `iteration` in the table.
- **How often did the LLM fall back?**
  Set tool=`llm_advisor`, then look at result blob for `"source":"fallback"`.
""")
"""
AI Trade Recommendations Page
------------------------------
Scans all 50 Nifty stocks for Supply & Demand zone setups,
sends the top 20 candidates to Claude (via SAP AI Core),
and displays the 10 highest-probability trades with reasoning,
entry/SL/target, and a price chart.

Fallback: when AI is unavailable, shows top 10 by zone score.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from typing import Optional
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from core.data_fetcher import DataFetcher
from strategies.zone_scanner import ZoneScanner
from database.db import DatabaseManager
from config.settings import INITIAL_CAPITAL, NIFTY_50
from core.llm_advisor import StrategyMemory, create_llm_from_secrets

st.set_page_config(page_title="AI Recommendations", page_icon="🤖", layout="wide")

data_fetcher = DataFetcher()
db = DatabaseManager()
_memory = StrategyMemory()

# ── Helpers ─────────────────────────────────────────────────────────────────

def _badge(text: str, colour: str) -> str:
    return (
        f'<span style="background:{colour};color:white;padding:2px 10px;'
        f'border-radius:12px;font-size:12px;font-weight:bold">{text}</span>'
    )


def _conviction_badge(conviction: str) -> str:
    colours = {"HIGH": "#4CAF50", "MEDIUM": "#FF9800", "LOW": "#9E9E9E"}
    return _badge(conviction, colours.get(conviction.upper(), "#9E9E9E"))


def _side_badge(side: str) -> str:
    return _badge(side, "#4CAF50" if side == "BUY" else "#EF5350")


def _prob_colour(prob: int) -> str:
    if prob >= 70:
        return "#4CAF50"
    if prob >= 50:
        return "#FF9800"
    return "#EF5350"


# ── Chart ────────────────────────────────────────────────────────────────────

def create_mini_chart(data, setup):
    """Compact candlestick — last 60 candles with entry / SL / target lines."""
    tail = data.tail(60).reset_index(drop=True)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=list(range(len(tail))),
        open=tail["Open"], high=tail["High"],
        low=tail["Low"],  close=tail["Close"],
        increasing_line_color="#26A69A", decreasing_line_color="#EF5350",
        showlegend=False,
    ))
    fig.add_hline(y=setup.entry,     line_dash="dash", line_color="#2196F3", line_width=1.5,
                  annotation_text=f"Entry ₹{setup.entry:,.0f}",     annotation_position="right", annotation_font_size=10)
    fig.add_hline(y=setup.stop_loss, line_dash="dash", line_color="#F44336", line_width=1.5,
                  annotation_text=f"SL ₹{setup.stop_loss:,.0f}",    annotation_position="right", annotation_font_size=10)
    fig.add_hline(y=setup.target,    line_dash="dash", line_color="#4CAF50", line_width=1.5,
                  annotation_text=f"Target ₹{setup.target:,.0f}",   annotation_position="right", annotation_font_size=10)
    fig.update_layout(
        height=300, showlegend=False, xaxis_rangeslider_visible=False,
        template="plotly_dark", margin=dict(l=10, r=90, t=10, b=10),
        paper_bgcolor="#0E1117", plot_bgcolor="#0E1117",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#1E1E1E", showticklabels=False)
    fig.update_yaxes(showgrid=True, gridcolor="#1E1E1E")
    return fig


# ── Scan ─────────────────────────────────────────────────────────────────────

def scan_all_nifty50(min_score: int):
    """Return (sorted all_setups, data_cache {symbol: DataFrame})."""
    lp = _memory.live_params() if _memory.best_params else {
        "min_score": 75, "rr_ratio": 3.0, "max_base_candles": 5
    }
    scanner = ZoneScanner(
        min_score=min_score,
        rr_ratio=lp["rr_ratio"],
        max_base_candles=lp["max_base_candles"],
    )

    all_setups = []
    data_cache = {}
    progress = st.progress(0.0, text="Starting scan…")

    for i, symbol in enumerate(NIFTY_50):
        progress.progress(
            (i + 1) / len(NIFTY_50),
            text=f"Scanning {symbol}… ({i + 1}/{len(NIFTY_50)})",
        )
        try:
            data = data_fetcher.get_data(symbol, "15m", "10d")
            if data is not None and len(data) > 20:
                setups = scanner.get_trade_setups(data, symbol)
                if setups:
                    all_setups.extend(setups)
                    data_cache[symbol] = data
        except Exception:
            pass

    progress.empty()
    all_setups.sort(key=lambda s: s.score, reverse=True)
    return all_setups, data_cache


# ── AI call ──────────────────────────────────────────────────────────────────

def ask_ai(candidates) -> Optional[dict]:
    """Send top candidates to Claude and get ranked top 10 with reasoning."""
    try:
        llm = create_llm_from_secrets(st.secrets)
    except Exception as e:
        st.session_state["_rec_ai_err"] = f"LLM init failed: {e}"
        return None

    setups_payload = []
    for i, s in enumerate(candidates):
        risk   = abs(s.entry - s.stop_loss)
        reward = abs(s.target - s.entry)
        rr = round(reward / risk, 1) if risk > 0 else 0
        setups_payload.append({
            "id":             i,
            "symbol":         s.symbol,
            "side":           s.side,
            "entry":          s.entry,
            "stop_loss":      s.stop_loss,
            "target":         s.target,
            "rr_ratio":       rr,
            "zone_score":     s.score,
            "zone_reasoning": s.reasoning,
        })

    system = (
        "You are an expert NSE equity trader specialising in Supply & Demand zone trading on 15-minute charts. "
        "Evaluate the given trade setups and select the TOP 10 with the highest probability of success. "
        "Consider zone quality score, R:R ratio, and zone reasoning. "
        "Respond ONLY with valid JSON — no markdown fences, no extra text."
    )

    user = f"""Here are {len(setups_payload)} trade setups detected across Nifty 50 stocks on 15-minute charts.

Select exactly 10 with the highest win probability.

SETUPS:
{json.dumps(setups_payload, indent=2)}

Respond with this exact JSON structure (no markdown, no extra keys):
{{
  "market_context": "2-3 sentence overview of which setups look strongest and why",
  "recommendations": [
    {{
      "id": <same id from SETUPS>,
      "rank": 1,
      "win_probability": 82,
      "conviction": "HIGH",
      "reasoning": ["bullet 1", "bullet 2", "bullet 3"],
      "risks": "key risk in one sentence",
      "entry_advice": "e.g. Limit order at zone entry, or wait for bullish confirmation candle"
    }}
  ]
}}"""

    try:
        raw = llm.chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=4096,
            temperature=0.2,
        )
        text = raw.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
            ).strip()
        return json.loads(text)
    except Exception as e:
        st.session_state["_rec_ai_err"] = str(e)
        return None


# ── Card renderer ────────────────────────────────────────────────────────────

def render_card(rank: int, setup, ai_rec: Optional[dict], chart_data, idx: int):
    symbol_short = setup.symbol.replace(".NS", "")
    risk   = abs(setup.entry - setup.stop_loss)
    reward = abs(setup.target - setup.entry)
    rr     = round(reward / risk, 1) if risk > 0 else 0

    with st.container(border=True):
        # ── Header ──────────────────────────────────────────────────────────
        if ai_rec:
            prob       = ai_rec.get("win_probability", 0)
            conviction = ai_rec.get("conviction", "MEDIUM")
            header = (
                f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
                f'<span style="font-size:22px;font-weight:bold">#{rank}</span>'
                f'<span style="font-size:20px;font-weight:bold">{symbol_short}</span>'
                f'{_side_badge(setup.side)}'
                f'<span style="font-size:18px;font-weight:bold;color:{_prob_colour(prob)}">'
                f'{prob}% win probability</span>'
                f'{_conviction_badge(conviction)}'
                f'</div>'
            )
        else:
            header = (
                f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px">'
                f'<span style="font-size:22px;font-weight:bold">#{rank}</span>'
                f'<span style="font-size:20px;font-weight:bold">{symbol_short}</span>'
                f'{_side_badge(setup.side)}'
                f'<span style="color:#9E9E9E;font-size:14px">Zone Score: {setup.score}/100</span>'
                f'</div>'
            )
        st.markdown(header, unsafe_allow_html=True)

        # ── Price metrics ────────────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📍 Entry",     f"₹{setup.entry:,.2f}")
        c2.metric("🛑 Stop Loss", f"₹{setup.stop_loss:,.2f}", delta=f"-₹{risk:.2f}",   delta_color="inverse")
        c3.metric("🎯 Target",    f"₹{setup.target:,.2f}",    delta=f"+₹{reward:.2f}", delta_color="normal")
        c4.metric("⚖ R:R",       f"1 : {rr}")

        # ── Reasoning ───────────────────────────────────────────────────────
        if ai_rec:
            reasoning    = ai_rec.get("reasoning", [])
            risks        = ai_rec.get("risks", "")
            entry_advice = ai_rec.get("entry_advice", "")
            if reasoning:
                st.markdown("**AI Reasoning:**")
                for bullet in reasoning:
                    st.markdown(f"&nbsp;&nbsp;• {bullet}")
            if risks:
                st.markdown(f"⚠️ **Risk:** {risks}")
            if entry_advice:
                st.markdown(f"📌 **Entry:** {entry_advice}")
        else:
            st.caption(setup.reasoning)

        # ── Chart ────────────────────────────────────────────────────────────
        if chart_data is not None:
            st.plotly_chart(
                create_mini_chart(chart_data, setup),
                use_container_width=True,
                key=f"rec_chart_{idx}",
            )
        else:
            st.caption("Chart data unavailable for this symbol.")

        # ── Take Trade ───────────────────────────────────────────────────────
        _, btn_col, _ = st.columns([3, 2, 3])
        with btn_col:
            if st.button("✅ Take Trade", key=f"rec_take_{idx}", use_container_width=True):
                qty = max(1, int((INITIAL_CAPITAL * 0.01) / max(risk, 0.01)))
                db.save_pending_order(
                    symbol=setup.symbol,
                    side=setup.side,
                    quantity=qty,
                    entry_price=setup.entry,
                    stop_loss=setup.stop_loss,
                    target=setup.target,
                    strategy="AI Recommendations",
                    reason=setup.reasoning,
                )
                st.success(f"✅ Pending order placed for {symbol_short}!")


# ── Page ─────────────────────────────────────────────────────────────────────

st.title("🤖 AI Trade Recommendations")
st.caption("Scans all 50 Nifty stocks · AI selects top 10 by win probability · Entry, SL & Target with reasoning")

# Session state
if "rec_result" not in st.session_state:
    st.session_state["rec_result"]   = None
if "_rec_ai_err" not in st.session_state:
    st.session_state["_rec_ai_err"] = None

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    min_score = st.slider(
        "Min Zone Score", 60, 95, 75, 5,
        help="Higher = fewer but stronger zones. 75 is a good balance.",
        key="rec_min_score",
    )

    if _memory.best_params:
        st.caption(f"🤖 AI-optimised params loaded (best WR: {_memory.best_win_rate:.1f}%)")
    else:
        st.caption("No AI-optimised params yet — using defaults.")

    st.markdown("---")
    scan_btn = st.button("🔍 Scan Nifty 50", type="primary", use_container_width=True)

    cached = st.session_state["rec_result"]
    if cached:
        age_s = int((datetime.now() - cached["ts"]).total_seconds())
        age_label = "just now" if age_s < 60 else f"{age_s // 60} min ago"
        st.caption(f"Last scanned: {age_label}")
        st.caption(f"Total setups found: {cached['total_setups']}")
        if cached.get("ai_output"):
            st.caption(f"AI ranked {min(20, cached['total_setups'])} candidates → top 10 shown")
        else:
            st.caption("Showing top 10 by zone score (AI unavailable)")

# ── Scan trigger ─────────────────────────────────────────────────────────────
if scan_btn:
    st.session_state["_rec_ai_err"] = None
    with st.spinner(""):
        all_setups, data_cache = scan_all_nifty50(min_score)

    if not all_setups:
        st.warning("No qualifying zones found across Nifty 50. Try lowering the Min Zone Score.")
        st.stop()

    candidates = all_setups[:20]
    ai_output  = None

    with st.spinner(f"Asking AI to evaluate {len(candidates)} candidates…"):
        ai_output = ask_ai(candidates)

    st.session_state["rec_result"] = {
        "all_setups":   all_setups,
        "data_cache":   data_cache,
        "candidates":   candidates,
        "ai_output":    ai_output,
        "total_setups": len(all_setups),
        "ts":           datetime.now(),
    }
    st.rerun()

# ── Display ───────────────────────────────────────────────────────────────────
result = st.session_state["rec_result"]

if result is None:
    st.info("👈 Click **Scan Nifty 50** in the sidebar to find today's best trade setups.")
    st.markdown("""
    ### How this works
    1. **Scan** — fetches 10 days of 15m data for all 50 Nifty stocks and detects Supply & Demand zones
    2. **Rank** — sends the top 20 candidates to Claude AI for probability scoring
    3. **Review** — top 10 displayed with win probability %, reasoning, entry/SL/target, and chart
    4. **Trade** — click **Take Trade** to create a pending order tracked in Trade History

    > Pending orders are automatically triggered by the bot when price returns to the zone entry level.
    """)
    st.stop()

candidates  = result["candidates"]
data_cache  = result["data_cache"]
ai_output   = result.get("ai_output")
ai_err      = st.session_state.get("_rec_ai_err")

# ── Build display list ────────────────────────────────────────────────────────
if ai_output and "recommendations" in ai_output:
    market_ctx = ai_output.get("market_context", "")
    if market_ctx:
        st.info(f"📊 **Market Context:** {market_ctx}")

    recs = sorted(ai_output["recommendations"], key=lambda r: r.get("rank", 99))
    display_items = []
    used_ids = set()

    for rec in recs[:10]:
        cid = rec.get("id", -1)
        if isinstance(cid, int) and 0 <= cid < len(candidates):
            display_items.append((candidates[cid], rec))
            used_ids.add(cid)

    # Top up to 10 if AI returned fewer
    for i, s in enumerate(candidates):
        if len(display_items) >= 10:
            break
        if i not in used_ids:
            display_items.append((s, None))

    st.success(
        f"✅ Scanned **{len(NIFTY_50)} Nifty stocks** · Found **{result['total_setups']} setups** · "
        f"AI selected top **{len(display_items)}** recommendations"
    )
else:
    # Fallback — no AI
    if ai_err:
        st.warning(f"⚠️ AI unavailable ({str(ai_err)[:140]}…) — showing top 10 by zone score")
    else:
        st.warning("⚠️ AI unavailable — showing top 10 by zone score")

    display_items = [(s, None) for s in candidates[:10]]
    st.success(
        f"✅ Scanned **{len(NIFTY_50)} Nifty stocks** · Found **{result['total_setups']} setups** · "
        f"Showing top **{len(display_items)}** by zone score"
    )

st.markdown("---")

if not display_items:
    st.warning("No setups to display. Try lowering the Min Zone Score and rescanning.")
    st.stop()

for i, (setup, ai_rec) in enumerate(display_items):
    render_card(
        rank=i + 1,
        setup=setup,
        ai_rec=ai_rec,
        chart_data=data_cache.get(setup.symbol),
        idx=i,
    )
    if i < len(display_items) - 1:
        st.markdown("")

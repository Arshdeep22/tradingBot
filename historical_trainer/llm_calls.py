"""
Claude/LLM integration for pattern synthesis and final summaries.
Focused on Professional Zone Scanner strategy with 6-dimension scoring.
"""

import json
import logging

logger = logging.getLogger(__name__)


def claude_synthesis(llm, day_batch: list, day_index: int,
                     current_params: dict, current_weights: dict = None) -> dict:
    """Send a 10-day batch of Zone outcomes to Claude for pattern synthesis."""
    total = sum(len(e.get("trades", [])) for e in day_batch)
    wins = sum(1 for e in day_batch for t in e.get("trades", []) if t["outcome"] == "TARGET_HIT")
    losses = sum(1 for e in day_batch for t in e.get("trades", []) if t["outcome"] == "SL_HIT")
    expired = sum(1 for e in day_batch for t in e.get("trades", []) if t["outcome"] == "EXPIRED")
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0

    # Collect side stats
    buy_wins = sum(1 for e in day_batch for t in e.get("trades", [])
                   if t["outcome"] == "TARGET_HIT" and t.get("side") == "BUY")
    sell_wins = sum(1 for e in day_batch for t in e.get("trades", [])
                    if t["outcome"] == "TARGET_HIT" and t.get("side") == "SELL")
    total_pnl = sum(t["pnl"] for e in day_batch for t in e.get("trades", [])
                    if t["outcome"] in ("TARGET_HIT", "SL_HIT", "EXPIRED"))

    # Collect RR stats
    rr_vals = [t.get("rr_achieved", 0) for e in day_batch for t in e.get("trades", [])
               if t.get("rr_achieved", 0) != 0]
    avg_rr = sum(rr_vals) / len(rr_vals) if rr_vals else 0.0

    # Collect score stats
    scores = [t.get("score", 0) for e in day_batch for t in e.get("trades", [])
              if t.get("score", 0) > 0]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Regime distribution
    regimes = {}
    for e in day_batch:
        for t in e.get("trades", []):
            regime = t.get("regime", "unknown")
            regimes[regime] = regimes.get(regime, 0) + 1

    rows = ["| Day | Symbol | Side | Score | RR | Outcome | P&L | Regime |",
            "|-----|--------|------|-------|-----|---------|-----|--------|"]
    for e in day_batch[-50:]:
        for t in e.get("trades", []):
            rows.append(
                f"| {e['date']} | {t['symbol']} | "
                f"{t['side']} | {t.get('score', '?')}/60 | {t.get('rr_achieved', '?')} | "
                f"{t['outcome']} | ₹{t['pnl']:.0f} | {t.get('regime', '?')} |"
            )

    system = (
        "You are an expert Supply & Demand Zone trading advisor analyzing historical walk-forward simulation. "
        "The strategy uses a Professional Zone Scanner with 6-dimension scoring (0-60 scale): "
        "Departure, Base, Freshness, Arrival, Time, Trend. "
        "Key tunable params: min_score_to_trade (threshold), default_rr_ratio, min_rr_ratio, "
        "sl_atr_multiplier, max_sl_pct, max_base_candles. "
        "Identify patterns in zone quality and suggest parameter adjustments. "
        "Be data-driven and specific. Respond ONLY with valid JSON."
    )

    user = (
        f"## Walk-Forward Training — Days {max(1, day_index - 9)} to {day_index} (10-day batch)\n\n"
        f"## Batch Summary\n"
        f"Total trades: {total} | Wins: {wins} | Losses: {losses} | Expired: {expired} | Win Rate: {wr:.1f}%\n"
        f"Buy wins: {buy_wins} | Sell wins: {sell_wins} | Total P&L: ₹{total_pnl:.0f}\n"
        f"Avg RR achieved: {avg_rr:.2f} | Avg zone score: {avg_score:.1f}/60\n"
        f"Regimes: {json.dumps(regimes)}\n\n"
        f"## Trade Log (last 50 rows)\n"
        f"{chr(10).join(rows)}\n\n"
        f"## Current Zone Params\n"
        f"{json.dumps(current_params, indent=2)}\n\n"
        f"## Task\n"
        f"Analyze which zone setups worked vs failed. Consider:\n"
        f"- Is the min_score_to_trade threshold right? (0-60 scale, 6 dimensions × 10)\n"
        f"- Is the R:R ratio producing good trades or too restrictive?\n"
        f"- Is the SL sizing appropriate (sl_atr_multiplier)?\n"
        f"- Are continuation (RBR/DBD) or reversal (DBR/RBD) patterns performing differently?\n\n"
        f"Respond with EXACTLY this JSON (no markdown):\n"
        "{\n"
        '  "analysis": "2-3 sentence pattern analysis with specific numbers",\n'
        '  "wins_pattern": "what made winning zones succeed (mention scores, patterns, regimes)",\n'
        '  "losses_pattern": "what caused losing zones (mention scores, patterns, regimes)",\n'
        '  "suggested_params": {\n'
        '    "min_score_to_trade": 40,\n'
        '    "default_rr_ratio": 3.0,\n'
        '    "min_rr_ratio": 2.0,\n'
        '    "sl_atr_multiplier": 1.0,\n'
        '    "max_sl_pct": 1.5,\n'
        '    "max_base_candles": 3\n'
        "  },\n"
        '  "confidence": 7\n'
        "}"
    )

    try:
        raw = llm.chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=1500, temperature=0.2,
        )
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
            ).strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Claude synthesis failed (day {day_index}): {e}")
        return {}


def claude_final_summary(llm, weekly_summary: list, params_history: list,
                         total_triggered: int, overall_wr: float,
                         avg_rr: float = 0.0) -> dict:
    """Final comprehensive Claude summary after all training iterations."""
    rows = ["| Week | Dates | Trades | WR | Avg RR | P&L |",
            "|------|-------|--------|----|--------|-----|"]
    for w in weekly_summary:
        rows.append(
            f"| {w['week_num']} | {w['start_date']}–{w['end_date']} | "
            f"{w['triggered']} | {w['win_rate']:.1f}% | {w.get('avg_rr', 0):.2f} | ₹{w['pnl']:+.0f} |"
        )

    system = (
        "You are an expert Supply & Demand Zone trading advisor writing a comprehensive learning summary. "
        "The strategy is a Professional Zone Scanner using 6-dimension scoring (0-60): "
        "Departure (leg-out quality), Base (tightness), Freshness (untested), "
        "Arrival (leg-in quality), Time (age), Trend (alignment). "
        "Key params: min_score_to_trade, default_rr_ratio, min_rr_ratio, sl_atr_multiplier, max_sl_pct, max_base_candles. "
        "Identify structural insights from walk-forward simulation. "
        "Be specific and actionable. Respond ONLY with valid JSON."
    )

    user = (
        f"## Historical Walk-Forward Training Complete (Professional Zone Scanner)\n\n"
        f"## Overall Results\n"
        f"Total trades simulated: {total_triggered} | Overall Win Rate: {overall_wr:.1f}% | Avg RR: {avg_rr:.2f}\n\n"
        f"## Weekly Learning Curve\n"
        f"{chr(10).join(rows)}\n\n"
        f"## Parameter Evolution ({len(params_history)} optimizer runs)\n"
        f"{json.dumps(params_history[-10:], indent=2)}\n\n"
        f"## Task\n"
        f"Write a comprehensive summary of what was learned about zone trading and provide\n"
        f"final recommended zone params for the live bot.\n\n"
        f"Consider:\n"
        f"- Which score threshold produced the best risk-adjusted returns?\n"
        f"- What R:R ratio works best for zone entries?\n"
        f"- Is the SL too tight (getting stopped out) or too wide (large losses)?\n"
        f"- Did the parameters converge or are they still shifting?\n\n"
        f"Respond with EXACTLY this JSON (no markdown):\n"
        "{\n"
        '  "executive_summary": "3-4 sentence overview of key findings",\n'
        '  "key_insights": ["insight 1", "insight 2", "insight 3"],\n'
        '  "best_performing_setup": "description of the most successful zone pattern found",\n'
        '  "recommended_live_approach": "how to apply these learnings to live trading",\n'
        '  "recommended_params": {\n'
        '    "min_score_to_trade": 40,\n'
        '    "default_rr_ratio": 3.0,\n'
        '    "min_rr_ratio": 2.0,\n'
        '    "sl_atr_multiplier": 1.0,\n'
        '    "max_sl_pct": 1.5,\n'
        '    "max_base_candles": 3\n'
        "  },\n"
        '  "confidence_in_params": 8\n'
        "}"
    )

    try:
        raw = llm.chat(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=2000, temperature=0.2,
        )
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
            ).strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Final Claude summary failed: {e}")
        return {"executive_summary": f"Summary generation failed: {e}", "key_insights": []}
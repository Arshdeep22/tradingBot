"""
Claude/LLM integration for pattern synthesis and final summaries.
Focused on Zone Scanner strategy only.
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
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0

    # Collect side stats
    buy_wins = sum(1 for e in day_batch for t in e.get("trades", [])
                   if t["outcome"] == "TARGET_HIT" and t.get("side") == "BUY")
    sell_wins = sum(1 for e in day_batch for t in e.get("trades", [])
                    if t["outcome"] == "TARGET_HIT" and t.get("side") == "SELL")
    total_pnl = sum(t["pnl"] for e in day_batch for t in e.get("trades", [])
                    if t["outcome"] in ("TARGET_HIT", "SL_HIT"))

    rows = ["| Day | Symbol | Side | Outcome | P&L |",
            "|-----|--------|------|---------|-----|"]
    for e in day_batch[-50:]:
        for t in e.get("trades", []):
            rows.append(
                f"| {e['date']} | {t['symbol']} | "
                f"{t['side']} | {t['outcome']} | ₹{t['pnl']:.0f} |"
            )

    system = (
        "You are an expert Supply & Demand Zone trading advisor analyzing historical walk-forward simulation. "
        "Identify patterns in zone quality and suggest parameter adjustments. "
        "Be data-driven and specific. Respond ONLY with valid JSON."
    )

    user = (
        f"## Walk-Forward Training — Days {max(1, day_index - 9)} to {day_index} (10-day batch)\n\n"
        f"## Batch Summary\n"
        f"Total trades: {total} | Wins: {wins} | Losses: {losses} | Win Rate: {wr:.1f}%\n"
        f"Buy wins: {buy_wins} | Sell wins: {sell_wins} | Total P&L: ₹{total_pnl:.0f}\n\n"
        f"## Trade Log (last 50 rows)\n"
        f"{chr(10).join(rows)}\n\n"
        f"## Current Zone Params\n"
        f"{json.dumps(current_params, indent=2)}\n\n"
        f"## Task\n"
        f"Analyze which zone setups worked vs failed and suggest parameter adjustments.\n\n"
        f"Respond with EXACTLY this JSON (no markdown):\n"
        "{\n"
        '  "analysis": "2-3 sentence pattern analysis with specific numbers",\n'
        '  "wins_pattern": "what made winning zones succeed",\n'
        '  "losses_pattern": "what caused losing zones",\n'
        '  "suggested_params": {\n'
        '    "min_score": 75, "rr_ratio": 2.5, "max_base_candles": 4\n'
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
                         total_triggered: int, overall_wr: float) -> dict:
    """Final comprehensive Claude summary after all training iterations."""
    rows = ["| Week | Dates | Trades | WR | P&L |",
            "|------|-------|--------|----|-----|"]
    for w in weekly_summary:
        rows.append(
            f"| {w['week_num']} | {w['start_date']}–{w['end_date']} | "
            f"{w['triggered']} | {w['win_rate']:.1f}% | ₹{w['pnl']:+.0f} |"
        )

    system = (
        "You are an expert Supply & Demand Zone trading advisor writing a comprehensive learning summary. "
        "Identify structural insights from walk-forward simulation. "
        "Be specific and actionable. Respond ONLY with valid JSON."
    )

    user = (
        f"## Historical Walk-Forward Training Complete (Zone Scanner Only)\n\n"
        f"## Overall Results\n"
        f"Total trades simulated: {total_triggered} | Overall Win Rate: {overall_wr:.1f}%\n\n"
        f"## Weekly Learning Curve\n"
        f"{chr(10).join(rows)}\n\n"
        f"## Parameter Evolution ({len(params_history)} optimizer runs)\n"
        f"{json.dumps(params_history[-10:], indent=2)}\n\n"
        f"## Task\n"
        f"Write a comprehensive summary of what was learned about zone trading and provide\n"
        f"final recommended zone params for the live bot.\n\n"
        f"Respond with EXACTLY this JSON (no markdown):\n"
        "{\n"
        '  "executive_summary": "3-4 sentence overview of key findings",\n'
        '  "key_insights": ["insight 1", "insight 2", "insight 3"],\n'
        '  "best_performing_setup": "description of the most successful zone pattern found",\n'
        '  "recommended_live_approach": "how to apply these learnings to live trading",\n'
        '  "recommended_params": {\n'
        '    "min_score": 75, "rr_ratio": 2.5, "max_base_candles": 4\n'
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
"""
Weekly Reviewer
----------------
Runs every Sunday at 7:00 PM IST via GitHub Actions.
Synthesizes 7 days of learning journal entries + optimization reports
into structural recommendations for the following week.

Usage:
    python weekly_reviewer.py
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("logs", exist_ok=True)
os.makedirs("reports/weekly", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/weekly_reviewer.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

from core.learning_journal import LearningJournal
from core.ai_recommender import create_llm_from_env
from core.llm_advisor import StrategyMemory


def ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def _week_id(dt: datetime) -> str:
    return dt.strftime("%Y-W%V")


def _load_optimization_reports(days_back: int = 7) -> list[dict]:
    """Load nightly optimization reports for the past N days."""
    reports = []
    now = ist_now()
    for i in range(days_back):
        date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        path = f"reports/{date_str}_optimization.json"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    reports.append(json.load(f))
            except Exception as e:
                logger.warning(f"Could not load {path}: {e}")
    return reports


def _build_summary_table(entries: list[dict]) -> str:
    """Build a markdown table of daily entries for the weekly prompt."""
    if not entries:
        return "No daily entries available."
    header = "| Date | DoW | Regime | Strategy | Trades | Wins | Win% | P&L |"
    sep    = "|------|-----|--------|----------|--------|------|------|-----|"
    rows = [header, sep]
    for e in sorted(entries, key=lambda x: x.get("date", "")):
        rows.append(
            f"| {e.get('date','?')} | {e.get('day_of_week','?')[:3]} "
            f"| {e.get('regime','?')} | {e.get('strategy_used','?')[:20]} "
            f"| {e.get('trades_today',0)} | {e.get('wins',0)} "
            f"| {e.get('win_rate',0):.0f}% | ₹{e.get('total_pnl',0):.0f} |"
        )
    return "\n".join(rows)


def _build_symbol_table(symbol_perf: dict) -> str:
    """Build a sorted markdown table of per-symbol performance."""
    if not symbol_perf:
        return "No symbol data available."
    header = "| Symbol | Trades | Wins | Win% |"
    sep    = "|--------|--------|------|------|"
    rows = [header, sep]
    for sym, stats in sorted(symbol_perf.items(),
                              key=lambda x: x[1]["win_rate"], reverse=True):
        if stats["total"] < 2:
            continue
        rows.append(
            f"| {sym.replace('.NS','')} | {stats['total']} "
            f"| {stats['wins']} | {stats['win_rate']:.0f}% |"
        )
    return "\n".join(rows) if len(rows) > 2 else "Insufficient per-symbol data."


def _load_previous_reviews(n: int = 3) -> list[dict]:
    """Load the most recent N weekly review files."""
    weekly_dir = "reports/weekly"
    reviews = []
    if not os.path.exists(weekly_dir):
        return reviews
    files = sorted(
        [f for f in os.listdir(weekly_dir) if f.endswith("_review.json")],
        reverse=True
    )
    for fname in files[:n]:
        try:
            with open(os.path.join(weekly_dir, fname)) as f:
                reviews.append(json.load(f))
        except Exception:
            pass
    return reviews


def ask_claude_weekly_review(llm, entries: list, opt_reports: list,
                              symbol_perf: dict, memory: StrategyMemory,
                              previous_reviews: list) -> dict:
    """Send weekly data to Claude for structural review."""
    now = ist_now()
    week_id = _week_id(now)
    start_date = (now - timedelta(days=6)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")

    total_trades = sum(e.get("trades_today", 0) for e in entries)
    total_wins   = sum(e.get("wins", 0) for e in entries)
    total_pnl    = sum(e.get("total_pnl", 0.0) for e in entries)
    overall_wr   = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    regime_counts: dict = {}
    for e in entries:
        r = e.get("regime", "unknown")
        regime_counts[r] = regime_counts.get(r, 0) + 1
    regime_dist = ", ".join(f"{k}: {v}d" for k, v in regime_counts.items())

    day_stats = LearningJournal().day_of_week_stats()
    dow_rows = " | ".join(f"{d}: {wr:.0f}%" for d, wr in day_stats.items()) if day_stats else "N/A"

    prev_summaries = ""
    if previous_reviews:
        prev_summaries = "\n".join(
            f"[{r.get('week','?')}] {r.get('executive_summary','')[:200]}"
            for r in previous_reviews
        )

    system = (
        "You are an autonomous trading strategy architect performing a weekly review. "
        "Identify STRUCTURAL improvements — not daily tweaks. "
        "Your recommendations should change how the bot operates next week, "
        "not just adjust a single parameter. "
        "Respond ONLY with valid JSON, no markdown."
    )

    user = f"""## Week {week_id} Review ({start_date} → {end_date})

### Daily Performance
{_build_summary_table(entries)}

### Weekly Totals
Trades: {total_trades} | Wins: {total_wins} | Overall win rate: {overall_wr}% | P&L: ₹{total_pnl:.0f}

### Regime Distribution
{regime_dist}

### Day-of-Week Averages
{dow_rows}

### Per-Symbol Performance (all recorded)
{_build_symbol_table(symbol_perf)}

### Current Strategy Memory (best params)
{json.dumps(memory.best_params, indent=2) if memory.best_params else "None yet"}
Best win rate in memory: {memory.best_win_rate:.1f}%

### Previous Weekly Reviews (context)
{prev_summaries if prev_summaries else "No previous reviews."}

## Task
1. Which symbols consistently lose? Should we remove them from the scan pool?
2. Which symbols consistently win? Should we weight them higher?
3. Is regime detection working? Any evidence of misclassification?
4. Day-of-week patterns — is there a day to avoid or emphasize?
5. Should the parameter search space be adjusted for next week's optimization?
6. Any structural change that could materially improve next week's performance?

Respond with this exact JSON:
{{
  "week": "{week_id}",
  "executive_summary": "3-4 sentence week summary",
  "overall_win_rate": {overall_wr},
  "win_rate_trend": "improving|declining|stable",
  "target_progress": "e.g. 68% — 2% below 70% target",
  "regime_assessment": "is regime detection helping? brief evidence",
  "symbol_changes": {{
    "remove_from_watchlist": [],
    "remove_reason": "",
    "focus_list": [],
    "focus_reason": ""
  }},
  "dow_pattern": "e.g. Fridays underperform — avoid new entries after 2 PM",
  "param_search_adjustments": {{
    "zone_min_score_range": [70, 85],
    "zone_rr_range": [2.0, 3.0],
    "reasoning": "why"
  }},
  "structural_recommendations": [
    {{
      "change": "description",
      "expected_impact": "quantified expectation",
      "priority": "high|medium|low"
    }}
  ],
  "primary_strategy_next_week": "Supply & Demand Zones",
  "confidence": 7,
  "apply_to_memory": false
}}"""

    raw = llm.chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=2048,
        temperature=0.2,
    )
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            lines[1:-1] if lines and lines[-1].strip().startswith("```") else lines[1:]
        ).strip()
    return json.loads(text)


def main():
    now = ist_now()
    week_id = _week_id(now)

    logger.info("=" * 60)
    logger.info(f"Weekly Reviewer — {week_id} ({now.strftime('%Y-%m-%d %H:%M IST')})")
    logger.info("=" * 60)

    journal = LearningJournal()
    entries = journal.get_last_n_days(7)
    logger.info(f"Loaded {len(entries)} daily journal entries")

    if len(entries) < 3:
        logger.warning("Fewer than 3 days of data — skipping weekly review (not enough signal).")
        return

    opt_reports = _load_optimization_reports(days_back=7)
    logger.info(f"Loaded {len(opt_reports)} nightly optimization reports")

    symbol_perf = journal.symbol_performance()
    logger.info(f"Symbol performance data for {len(symbol_perf)} symbols")

    memory = StrategyMemory()
    previous_reviews = _load_previous_reviews(3)
    logger.info(f"Loaded {len(previous_reviews)} previous weekly reviews for context")

    logger.info("Asking Claude for structural recommendations...")
    review = None
    try:
        llm = create_llm_from_env()
        review = ask_claude_weekly_review(
            llm, entries, opt_reports, symbol_perf, memory, previous_reviews
        )
        logger.info(f"Review complete. Win rate trend: {review.get('win_rate_trend')}")
    except KeyError as e:
        logger.warning(f"AICORE env var missing ({e}) — generating summary without Claude")
    except Exception as e:
        logger.warning(f"Claude call failed ({e}) — generating summary without Claude")

    # Fallback: build a basic summary without Claude
    if review is None:
        total_trades = sum(e.get("trades_today", 0) for e in entries)
        total_wins   = sum(e.get("wins", 0) for e in entries)
        total_pnl    = sum(e.get("total_pnl", 0.0) for e in entries)
        review = {
            "week": week_id,
            "executive_summary": f"Week {week_id}: {total_trades} trades, {total_wins} wins, ₹{total_pnl:.0f} P&L. (Claude unavailable — manual review needed)",
            "overall_win_rate": round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0,
            "win_rate_trend": "unknown",
            "target_progress": "N/A",
            "regime_assessment": "N/A",
            "structural_recommendations": [],
            "confidence": 0,
        }

    # Save to reports/weekly/
    out_path = f"reports/weekly/{week_id}_review.json"
    with open(out_path, "w") as f:
        json.dump(review, f, indent=2)
    logger.info(f"Weekly review saved to {out_path}")

    # Also write a human-readable markdown summary
    md_path = f"reports/weekly/{week_id}_review.md"
    with open(md_path, "w") as f:
        f.write(f"# Weekly Review — {week_id}\n\n")
        f.write(f"**Win rate:** {review.get('overall_win_rate', 0):.1f}% | "
                f"**Trend:** {review.get('win_rate_trend','?')} | "
                f"**Progress:** {review.get('target_progress','?')}\n\n")
        f.write(f"## Summary\n{review.get('executive_summary','')}\n\n")
        f.write(f"## Regime Assessment\n{review.get('regime_assessment','')}\n\n")
        recs = review.get("structural_recommendations", [])
        if recs:
            f.write("## Structural Recommendations\n\n")
            for r in recs:
                f.write(f"**[{r.get('priority','?').upper()}]** {r.get('change','')}\n")
                f.write(f"  Expected: {r.get('expected_impact','')}\n\n")
    logger.info(f"Markdown summary saved to {md_path}")

    logger.info("=" * 60)
    logger.info(f"Weekly review complete for {week_id}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

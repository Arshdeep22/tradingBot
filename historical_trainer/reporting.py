"""
Report generation: weekly summaries, JSON and Markdown output.
Aligned with Professional Zone Scanner (6-dimension scoring, 0-60 scale).
"""

import json
import os
import logging

from core.llm_advisor import StrategyMemory

logger = logging.getLogger(__name__)


def compute_weekly_summary(all_days: list, daily_results: list) -> list:
    """Compute week-by-week performance summaries (5 trading days per week)."""
    weekly_summary: list = []
    week_size = 5
    for w_start in range(0, len(all_days), week_size):
        wdays = daily_results[w_start:w_start + week_size]
        if not wdays:
            continue
        w_wins = sum(d["wins"] for d in wdays)
        w_losses = sum(d["losses"] for d in wdays)
        w_expired = sum(d.get("expired", 0) for d in wdays)
        w_pnl = sum(d["pnl"] for d in wdays)
        w_trig = sum(d["triggered"] for d in wdays)
        w_wr = w_wins / (w_wins + w_losses) * 100 if (w_wins + w_losses) > 0 else 0.0

        # Compute avg RR for the week
        w_rr_vals = [t.get("rr_achieved", 0) for d in wdays for t in d.get("trades", [])
                     if t.get("rr_achieved", 0) != 0]
        w_avg_rr = sum(w_rr_vals) / len(w_rr_vals) if w_rr_vals else 0.0

        weekly_summary.append({
            "week_num": len(weekly_summary) + 1,
            "start_date": wdays[0]["date"],
            "end_date": wdays[-1]["date"],
            "trading_days": len(wdays),
            "triggered": w_trig,
            "wins": w_wins,
            "losses": w_losses,
            "expired": w_expired,
            "win_rate": round(w_wr, 1),
            "avg_rr": round(w_avg_rr, 2),
            "pnl": round(w_pnl, 2),
        })
    return weekly_summary


def save_strategy_memory(current_zone_params: dict, overall_wr: float,
                         total_pnl: float, total_triggered: int,
                         total_wins: int, total_losses: int,
                         avg_rr: float,
                         final_summary: dict, data_dict: dict,
                         all_days: list):
    """Persist learned params to strategy_memory.json."""
    memory = StrategyMemory()
    memory.add(
        params=current_zone_params,
        results={
            "win_rate": overall_wr,
            "total_pnl": total_pnl,
            "total_zones": total_triggered,
            "triggered": total_triggered,
            "targets_hit": total_wins,
            "sl_hit": total_losses,
            "avg_rr_achieved": avg_rr,
            "scoring_system": "6-dimension (0-60)",
        },
        analysis=final_summary.get(
            "executive_summary",
            f"Historical trainer: {overall_wr:.1f}% WR, {avg_rr:.2f} avg RR over {len(all_days)} trading days"
        ),
        symbols=list(data_dict.keys()),
    )


def save_training_report(report: dict) -> tuple:
    """
    Save training report as JSON and Markdown.
    Returns (json_path, md_path).
    """
    os.makedirs("reports/training", exist_ok=True)
    report_id = report["run_id"]

    # JSON report
    json_path = f"reports/training/{report_id}_training_report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Training report -> {json_path}")

    # Markdown report
    md_path = f"reports/training/{report_id}_training_report.md"
    md_content = _build_markdown(report)
    with open(md_path, "w") as f:
        f.write(md_content)
    logger.info(f"Markdown report -> {md_path}")

    return json_path, md_path


def _build_markdown(report: dict) -> str:
    """Build markdown content from report dict."""
    report_id = report["run_id"]
    current_zone_params = report["final_zone_params"]
    weekly_summary = report["weekly_summary"]
    final_summary = report["final_summary"]
    total_triggered = report["total_triggered"]
    overall_wr = report["overall_win_rate"]
    avg_rr = report.get("average_rr", 0.0)
    total_pnl = report["total_pnl"]
    quick = report["quick_mode"]
    all_days_count = report["trading_days"]

    lines = []
    lines.append(f"# Historical Training Report — {report_id}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Strategy: Professional Zone Scanner (6-dimension scoring, 0-60 scale)")
    lines.append(f"- Period: {report['training_period']['start']} → {report['training_period']['end']} ({all_days_count} trading days)")
    lines.append(f"- Symbols: {len(report['symbols_used'])} | Quick: {quick}")
    lines.append(f"- Trades simulated: {total_triggered} | WR: {overall_wr:.1f}% | Avg RR: {avg_rr:.2f} | P&L: ₹{total_pnl:+.0f}")
    lines.append(f"- Optimizer runs: {report['optimizer_runs']} | Claude synthesis calls: {report['claude_calls']}")
    lines.append("")
    lines.append("## Final Zone Parameters")
    lines.append(f"| Parameter | Value |")
    lines.append(f"|-----------|-------|")
    for key, val in current_zone_params.items():
        lines.append(f"| {key} | {val} |")
    lines.append("")
    lines.append("## Learning Curve (Week by Week)")
    lines.append("| Week | Dates | Trades | WR | Avg RR | P&L |")
    lines.append("|------|-------|--------|----|--------|-----|")
    for w in weekly_summary:
        lines.append(
            f"| {w['week_num']} | {w['start_date']}–{w['end_date']} | "
            f"{w['triggered']} | {w['win_rate']:.1f}% | {w.get('avg_rr', 0):.2f} | ₹{w['pnl']:+.0f} |"
        )

    if final_summary:
        lines.append("")
        lines.append("## Key Insights")
        lines.append(final_summary.get("executive_summary", ""))
        for insight in final_summary.get("key_insights", []):
            lines.append(f"- {insight}")
        if final_summary.get("best_performing_setup"):
            lines.append("")
            lines.append(f"**Best setup:** {final_summary['best_performing_setup']}")
        if final_summary.get("recommended_live_approach"):
            lines.append("")
            lines.append(f"**Recommended approach:** {final_summary['recommended_live_approach']}")

    lines.append("")
    lines.append("## Scoring System")
    lines.append("Zones scored on 6 dimensions (0-10 each, max 60):")
    lines.append("1. **Departure** — Leg-out quality (body size, count, volume)")
    lines.append("2. **Base** — Base tightness (fewer candles = better)")
    lines.append("3. **Freshness** — Untested zone (never touched = better)")
    lines.append("4. **Arrival** — Leg-in quality (gradual arrival = better)")
    lines.append("5. **Time** — Age of zone (newer = better)")
    lines.append("6. **Trend** — Alignment with higher-TF trend")

    return "\n".join(lines)
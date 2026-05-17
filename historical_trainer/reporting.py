"""
Report generation: weekly summaries, JSON and Markdown output.
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
        w_pnl = sum(d["pnl"] for d in wdays)
        w_trig = sum(d["triggered"] for d in wdays)
        w_wr = w_wins / (w_wins + w_losses) * 100 if (w_wins + w_losses) > 0 else 0.0
        weekly_summary.append({
            "week_num": len(weekly_summary) + 1,
            "start_date": wdays[0]["date"],
            "end_date": wdays[-1]["date"],
            "trading_days": len(wdays),
            "triggered": w_trig,
            "wins": w_wins,
            "losses": w_losses,
            "win_rate": round(w_wr, 1),
            "pnl": round(w_pnl, 2),
        })
    return weekly_summary


def save_strategy_memory(current_zone_params: dict, overall_wr: float,
                         total_pnl: float, total_triggered: int,
                         total_wins: int, total_losses: int,
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
        },
        analysis=final_summary.get(
            "executive_summary",
            f"Historical trainer: {overall_wr:.1f}% WR over {len(all_days)} trading days"
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
    total_pnl = report["total_pnl"]
    quick = report["quick_mode"]
    all_days_count = report["trading_days"]

    lines = []
    lines.append(f"# Historical Training Report -- {report_id}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Strategy: Supply & Demand Zones (Zone Scanner)")
    lines.append(f"- Period: {report['training_period']['start']} -> {report['training_period']['end']} ({all_days_count} trading days)")
    lines.append(f"- Symbols: {len(report['symbols_used'])} | Quick: {quick}")
    lines.append(f"- Trades simulated: {total_triggered} | WR: {overall_wr:.1f}% | P&L: Rs{total_pnl:+.0f}")
    lines.append(f"- Optimizer runs: {report['optimizer_runs']} | Claude synthesis calls: {report['claude_calls']}")
    lines.append(f"- Final Zone params: {current_zone_params}")
    lines.append("")
    lines.append("## Learning Curve (Week by Week)")
    lines.append("| Week | Dates | Trades | WR | P&L |")
    lines.append("|------|-------|--------|----|-----|")
    for w in weekly_summary:
        lines.append(
            f"| {w['week_num']} | {w['start_date']}-{w['end_date']} | "
            f"{w['triggered']} | {w['win_rate']:.1f}% | Rs{w['pnl']:+.0f} |"
        )

    if final_summary:
        lines.append("")
        lines.append("## Key Insights")
        lines.append(final_summary.get("executive_summary", ""))
        for insight in final_summary.get("key_insights", []):
            lines.append(f"- {insight}")

    lines.append("")
    lines.append("## Final Parameters")
    lines.append(
        f"Zone: min_score={current_zone_params.get('min_score')}, "
        f"rr_ratio={current_zone_params.get('rr_ratio')}, "
        f"max_base_candles={current_zone_params.get('max_base_candles')}"
    )

    return "\n".join(lines)
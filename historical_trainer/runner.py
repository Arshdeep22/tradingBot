"""
Main orchestration: run_training() and CLI main().
Zone Scanner only — no multi-strategy weight management.
"""

import sys
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

from core.llm_advisor import create_llm_from_secrets
from core.ai_recommender import create_llm_from_env

from .constants import TRAINING_SYMBOLS_QUICK, TRAINING_SYMBOLS_FULL
from .time_utils import extract_trading_days
from .data_loader import fetch_all_data
from .grid_search import run_mini_optimizer
from .simulation import run_day
from .llm_calls import claude_synthesis, claude_final_summary
from .reporting import (
    compute_weekly_summary, save_strategy_memory,
    save_training_report,
)

logger = logging.getLogger(__name__)


def _initialize_llm():
    """Try to initialize LLM from env vars or secrets file."""
    llm = None
    try:
        llm = create_llm_from_env()
        logger.info("LLM: connected via environment variables")
        return llm
    except (KeyError, Exception):
        pass

    try:
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".streamlit", "secrets.toml"
        )
        import tomllib
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)
        llm = create_llm_from_secrets(secrets)
        logger.info("LLM: connected via .streamlit/secrets.toml")
        return llm
    except Exception as e:
        logger.warning(f"LLM unavailable (env vars and secrets.toml both failed: {e})")
        return None


def _build_report(run_ts, all_days, data_dict, quick, no_ai, daily_results,
                  total_triggered, total_wins, total_losses, overall_wr, total_pnl,
                  params_history, current_zone_params,
                  weekly_summary, final_summary):
    """Assemble the final report dictionary."""
    report_id = run_ts.strftime("%Y-%m-%dT%H%M")
    return {
        "run_id": report_id,
        "run_timestamp": run_ts.isoformat(),
        "training_period": {"start": str(all_days[0]), "end": str(all_days[-1])},
        "trading_days": len(all_days),
        "symbols_used": list(data_dict.keys()),
        "quick_mode": quick,
        "no_ai": no_ai,
        "total_setups_found": sum(len(d["trades"]) for d in daily_results),
        "total_triggered": total_triggered,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "overall_win_rate": round(overall_wr, 1),
        "total_pnl": round(total_pnl, 2),
        "optimizer_runs": len([p for p in params_history if p["trigger"] == "mini_optimizer"]),
        "claude_calls": len([p for p in params_history if p["trigger"] == "claude_synthesis"]),
        "final_zone_params": current_zone_params,
        "weekly_summary": weekly_summary,
        "params_history": params_history,
        "final_summary": final_summary,
        "daily_results": daily_results,
    }


def run_training(quick=False, no_ai=False, progress_cb=None):
    """
    Run the full walk-forward historical training (Zone Scanner only).

    Args:
        quick:       Smaller symbol set + reduced grid (faster, for testing)
        no_ai:       Skip all Claude calls (grid math only)
        progress_cb: Optional callback(pct: float, msg: str) for dashboard progress

    Returns:
        Completed report dict (also written to reports/training/).
    """
    def _progress(pct, msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        stamped = "[" + ts + "] " + msg
        logger.info("[%.0f%%] %s", pct, stamped)
        if progress_cb:
            try:
                progress_cb(pct, stamped)
            except Exception:
                pass

    start_ts = datetime.now(timezone.utc)
    _progress(0, "Starting historical walk-forward training (Zone Scanner)...")

    # Fetch data
    symbols = TRAINING_SYMBOLS_QUICK if quick else TRAINING_SYMBOLS_FULL
    _progress(2, "Fetching 60 days of 15m data for %d symbols..." % len(symbols))
    data_dict = fetch_all_data(
        symbols,
        progress_cb=lambda pct, msg: progress_cb(pct, msg) if progress_cb else None
    )
    if len(data_dict) < 3:
        raise RuntimeError(
            "Too few symbols with valid data (%d/%d)." % (len(data_dict), len(symbols))
        )

    # Extract trading days
    all_days = extract_trading_days(data_dict)
    if len(all_days) < 5:
        raise RuntimeError("Only %d trading days in data. Need at least 5." % len(all_days))
    _progress(13, "Data ready: %d symbols, %d trading days (%s -> %s)" % (
        len(data_dict), len(all_days), all_days[0], all_days[-1]))

    # Initialize state
    current_zone_params = {"min_score": 75, "rr_ratio": 2.5, "max_base_candles": 4}
    params_history = []
    daily_results = []
    batched_days = []

    llm = None if no_ai else _initialize_llm()
    total_days = len(all_days)

    # Walk-forward loop
    for day_idx, day in enumerate(all_days):
        pct = 5 + (day_idx / total_days) * 75
        _progress(pct, "Day %d/%d: %s" % (day_idx + 1, total_days, day))

        day_trades = run_day(day, data_dict, current_zone_params, all_days=all_days)
        triggered = [t for t in day_trades if t["outcome"] in ("TARGET_HIT", "SL_HIT", "EXPIRED")]
        wins = sum(1 for t in triggered if t["outcome"] == "TARGET_HIT")
        losses = sum(1 for t in triggered if t["outcome"] == "SL_HIT")
        day_pnl = sum(t["pnl"] for t in triggered)
        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0

        daily_entry = {
            "date": str(day), "day_idx": day_idx + 1, "trades": day_trades,
            "triggered": len(triggered), "wins": wins, "losses": losses,
            "win_rate": round(wr, 1), "pnl": round(day_pnl, 2),
            "params": dict(current_zone_params),
        }
        daily_results.append(daily_entry)
        batched_days.append(daily_entry)
        logger.info("  Day %d: %d setups -> %d triggered, WR=%.1f%%, P&L=%.0f",
                    day_idx + 1, len(day_trades), len(triggered), wr, day_pnl)

        # Mini-optimizer every 5 days
        if (day_idx + 1) % 5 == 0:
            _progress(pct, "Day %d: Running mini-optimizer..." % (day_idx + 1))
            try:
                new_params = run_mini_optimizer(data_dict, day, quick)
                if new_params:
                    current_zone_params = new_params
                    params_history.append({
                        "day_idx": day_idx + 1, "date": str(day),
                        "trigger": "mini_optimizer",
                        "zone_params": dict(new_params),
                    })
                    logger.info("  Mini-optimizer updated: %s", new_params)
            except Exception as e:
                logger.warning("  Mini-optimizer failed: %s", e)

        # Claude synthesis every 10 days
        if llm and (day_idx + 1) >= 10 and (day_idx + 1) % 10 == 0:
            _progress(pct, "Day %d: Claude synthesis on last 10 days..." % (day_idx + 1))
            batch = batched_days[max(0, len(batched_days) - 10):]
            try:
                synthesis = claude_synthesis(
                    llm, batch, day_idx + 1, current_zone_params
                )
                if synthesis.get("suggested_params"):
                    current_zone_params = synthesis["suggested_params"]
                    params_history.append({
                        "day_idx": day_idx + 1, "date": str(day),
                        "trigger": "claude_synthesis",
                        "analysis": synthesis.get("analysis", ""),
                        "zone_params": dict(synthesis["suggested_params"]),
                    })
                    logger.info("  Claude: %s", synthesis.get("analysis", "")[:80])
            except Exception as e:
                logger.warning("  Claude synthesis failed: %s", e)

    # Weekly summaries
    _progress(82, "Computing weekly summaries...")
    weekly_summary = compute_weekly_summary(all_days, daily_results)

    # Compute totals
    total_triggered = sum(d["triggered"] for d in daily_results)
    total_wins = sum(d["wins"] for d in daily_results)
    total_losses = sum(d["losses"] for d in daily_results)
    total_pnl = sum(d["pnl"] for d in daily_results)
    overall_wr = (total_wins / (total_wins + total_losses) * 100
                  if (total_wins + total_losses) > 0 else 0.0)

    # Final Claude summary
    final_summary = {}
    if llm:
        _progress(87, "Running final Claude summary...")
        try:
            final_summary = claude_final_summary(
                llm, weekly_summary, params_history, total_triggered, overall_wr
            )
            if final_summary.get("recommended_params"):
                current_zone_params = final_summary["recommended_params"]
            logger.info("Final summary: %s", final_summary.get("executive_summary", "")[:100])
        except Exception as e:
            logger.warning("Final summary failed: %s", e)

    # Persist learned params
    _progress(92, "Saving learned params to strategy_memory.json...")
    save_strategy_memory(
        current_zone_params, overall_wr, total_pnl, total_triggered,
        total_wins, total_losses, final_summary, data_dict, all_days
    )

    # Save report
    _progress(95, "Saving training report...")
    run_ts = datetime.now(timezone.utc)
    report = _build_report(
        run_ts, all_days, data_dict, quick, no_ai, daily_results,
        total_triggered, total_wins, total_losses, overall_wr, total_pnl,
        params_history, current_zone_params,
        weekly_summary, final_summary
    )
    save_training_report(report)

    elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
    _progress(100, "Training complete! WR=%.1f%% over %d trades (%.0fs)" % (
        overall_wr, total_triggered, elapsed))
    return report


def main():
    """CLI entry point."""
    quick = "--quick" in sys.argv
    no_ai = "--no-ai" in sys.argv

    logger.info("=" * 60)
    logger.info("Historical Walk-Forward Trainer (Zone Scanner)")
    if quick:
        logger.info("  Mode: QUICK (10 symbols, reduced grid)")
    if no_ai:
        logger.info("  Mode: NO-AI (skipping Claude calls)")
    logger.info("=" * 60)

    try:
        report = run_training(quick=quick, no_ai=no_ai)
        logger.info("Training complete. WR=%.1f%%", report["overall_win_rate"])
        logger.info("Report: reports/training/%s_training_report.json", report["run_id"])
    except Exception as e:
        logger.error("Training failed: %s", e, exc_info=True)
        sys.exit(1)
"""
Main orchestration: run_training() and CLI main().
Professional Zone Scanner — full pipeline with 6-dimension scoring.

KEY FIXES (v2):
- Zone blacklist passed across days to prevent re-trading same zones
- Reduced max trades per day for quality over quantity
- Better convergence logic for optimizer
"""

import sys
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Callable

from core.llm_advisor import create_llm_from_secrets
from core.ai_recommender import create_llm_from_env

from .constants import TRAINING_SYMBOLS_QUICK, TRAINING_SYMBOLS_FULL, DEFAULT_ZONE_PARAMS
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
                  total_triggered, total_wins, total_losses, total_expired,
                  overall_wr, total_pnl, avg_rr,
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
        "strategy": "Professional Zone Scanner",
        "scoring_range": "0-60 (6 dimensions × 10)",
        "total_setups_found": sum(len(d["trades"]) for d in daily_results),
        "total_triggered": total_triggered,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_expired": total_expired,
        "overall_win_rate": round(overall_wr, 1),
        "average_rr": round(avg_rr, 2),
        "total_pnl": round(total_pnl, 2),
        "optimizer_runs": len([p for p in params_history if p["trigger"] == "mini_optimizer"]),
        "claude_calls": len([p for p in params_history if p["trigger"] == "claude_synthesis"]),
        "final_zone_params": current_zone_params,
        "weekly_summary": weekly_summary,
        "params_history": params_history,
        "final_summary": final_summary,
        "daily_results": daily_results,
    }


def _blend_params(current: dict, new: dict, blend_factor: float = 0.6) -> dict:
    """
    Blend new optimizer params toward current params to prevent oscillation.
    blend_factor = 0.6 means 60% new, 40% current.
    Only blends numeric params, non-numeric stays as new.
    """
    blended = {}
    for key in new:
        if key in current and isinstance(new[key], (int, float)) and isinstance(current[key], (int, float)):
            blended_val = current[key] * (1 - blend_factor) + new[key] * blend_factor
            # Round to appropriate precision
            if isinstance(new[key], int):
                blended[key] = int(round(blended_val))
            else:
                blended[key] = round(blended_val, 2)
        else:
            blended[key] = new[key]
    return blended


def _write_json_result(report: dict) -> None:
    """Write a simplified BacktestResult-compatible JSON to reports/training/latest_backtest_result.json."""
    import json as _json
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports", "training"
    )
    os.makedirs(out_dir, exist_ok=True)
    weekly_summaries = [
        {"pnl": w.get("pnl", 0.0), "win_rate": w.get("win_rate", 0.0)}
        for w in report.get("weekly_summary", [])
    ]
    result = {
        "overall_win_rate": report.get("overall_win_rate", 0.0),
        "total_pnl": report.get("total_pnl", 0.0),
        "total_triggered": report.get("total_triggered", 0),
        "days_run": report.get("trading_days", 0),
        "weekly_summaries": weekly_summaries,
    }
    out_path = os.path.join(out_dir, "latest_backtest_result.json")
    with open(out_path, "w") as f:
        _json.dump(result, f, indent=2)
    logger.info("JSON result written to %s", out_path)


def run_training(quick=False, no_ai=False, progress_cb=None, last_n_days: Optional[int] = None):
    """
    Run the full walk-forward historical training (Professional Zone Scanner).

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
    _progress(0, "Starting historical walk-forward training (Professional Zone Scanner v2)...")

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
    if last_n_days:
        all_days = all_days[-last_n_days:]
    if len(all_days) < 5:
        raise RuntimeError("Only %d trading days in data. Need at least 5." % len(all_days))
    _progress(13, "Data ready: %d symbols, %d trading days (%s -> %s)" % (
        len(data_dict), len(all_days), all_days[0], all_days[-1]))

    # Initialize state with full zone params
    current_zone_params = dict(DEFAULT_ZONE_PARAMS)
    params_history = []
    daily_results = []
    batched_days = []

    # Zone blacklist: persists across all days to prevent re-trading same zones
    traded_zones = set()

    llm = None if no_ai else _initialize_llm()
    total_days = len(all_days)

    # Walk-forward loop
    for day_idx, day in enumerate(all_days):
        pct = 5 + (day_idx / total_days) * 75
        _progress(pct, "Day %d/%d: %s" % (day_idx + 1, total_days, day))

        # Pass traded_zones for zone blacklist
        day_trades = run_day(
            day, data_dict, current_zone_params,
            all_days=all_days, traded_zones=traded_zones
        )
        triggered = [t for t in day_trades if t["outcome"] in ("TARGET_HIT", "SL_HIT", "EXPIRED")]
        wins = sum(1 for t in triggered if t["outcome"] == "TARGET_HIT")
        losses = sum(1 for t in triggered if t["outcome"] == "SL_HIT")
        expired = sum(1 for t in triggered if t["outcome"] == "EXPIRED")
        day_pnl = sum(t["pnl"] for t in triggered)
        wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
        day_rr_vals = [t.get("rr_achieved", 0) for t in triggered if t.get("rr_achieved", 0) != 0]
        day_avg_rr = sum(day_rr_vals) / len(day_rr_vals) if day_rr_vals else 0.0

        daily_entry = {
            "date": str(day), "day_idx": day_idx + 1, "trades": day_trades,
            "triggered": len(triggered), "wins": wins, "losses": losses,
            "expired": expired,
            "win_rate": round(wr, 1), "pnl": round(day_pnl, 2),
            "avg_rr": round(day_avg_rr, 2),
            "params": dict(current_zone_params),
        }
        daily_results.append(daily_entry)
        batched_days.append(daily_entry)
        logger.info("  Day %d: %d setups -> %d triggered, WR=%.1f%%, RR=%.2f, P&L=%.0f",
                    day_idx + 1, len(day_trades), len(triggered), wr, day_avg_rr, day_pnl)

        # Mini-optimizer every 5 days (with convergence blending)
        if (day_idx + 1) % 5 == 0:
            _progress(pct, "Day %d: Running mini-optimizer..." % (day_idx + 1))
            try:
                new_params = run_mini_optimizer(data_dict, day, quick)
                if new_params:
                    # Blend toward new params (prevents oscillation)
                    blended = _blend_params(current_zone_params, new_params, blend_factor=0.7)
                    current_zone_params = blended
                    params_history.append({
                        "day_idx": day_idx + 1, "date": str(day),
                        "trigger": "mini_optimizer",
                        "zone_params": dict(blended),
                    })
                    logger.info("  Mini-optimizer updated (blended): %s", blended)
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
    total_expired = sum(d.get("expired", 0) for d in daily_results)
    total_pnl = sum(d["pnl"] for d in daily_results)
    overall_wr = (total_wins / (total_wins + total_losses) * 100
                  if (total_wins + total_losses) > 0 else 0.0)
    all_rr = [t.get("rr_achieved", 0) for d in daily_results for t in d["trades"]
              if t.get("rr_achieved", 0) != 0]
    avg_rr = sum(all_rr) / len(all_rr) if all_rr else 0.0

    # Final Claude summary
    final_summary = {}
    if llm:
        _progress(87, "Running final Claude summary...")
        try:
            final_summary = claude_final_summary(
                llm, weekly_summary, params_history, total_triggered, overall_wr, avg_rr
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
        total_wins, total_losses, avg_rr, final_summary, data_dict, all_days
    )

    # Save report
    _progress(95, "Saving training report...")
    run_ts = datetime.now(timezone.utc)
    report = _build_report(
        run_ts, all_days, data_dict, quick, no_ai, daily_results,
        total_triggered, total_wins, total_losses, total_expired,
        overall_wr, total_pnl, avg_rr,
        params_history, current_zone_params,
        weekly_summary, final_summary
    )
    save_training_report(report)

    elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
    _progress(100, "Training complete! WR=%.1f%% RR=%.2f over %d trades (%.0fs)" % (
        overall_wr, avg_rr, total_triggered, elapsed))
    return report


def main():
    """CLI entry point."""
    quick = "--quick" in sys.argv
    no_ai = "--no-ai" in sys.argv
    json_output = "--json-output" in sys.argv

    days_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith("--days="):
            days_arg = int(arg.split("=")[1])

    logger.info("=" * 60)
    logger.info("Historical Walk-Forward Trainer (Professional Zone Scanner v2)")
    if quick:
        logger.info("  Mode: QUICK (10 symbols, reduced grid)")
    if no_ai:
        logger.info("  Mode: NO-AI (skipping Claude calls)")
    if days_arg:
        logger.info("  Days: last %d trading days", days_arg)
    logger.info("=" * 60)

    try:
        report = run_training(quick=quick, no_ai=no_ai, last_n_days=days_arg)
        logger.info("Training complete. WR=%.1f%% avg_RR=%.2f",
                    report["overall_win_rate"], report["average_rr"])
        logger.info("Report: reports/training/%s_training_report.json", report["run_id"])
        if json_output:
            _write_json_result(report)
    except Exception as e:
        logger.error("Training failed: %s", e, exc_info=True)
        sys.exit(1)
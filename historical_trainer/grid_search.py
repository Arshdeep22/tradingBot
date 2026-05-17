"""
Grid search runner for Zone Scanner parameter tuning.
"""

import logging
from datetime import date, timedelta

from core.backtester import Backtester
from strategies.zone_scanner import ZoneScanner

from .constants import ZONE_GRID, QUICK_ZONE_GRID, TEST_DAYS
from .time_utils import eod_dt, slice_data

logger = logging.getLogger(__name__)


def run_zone_grid(data_dict: dict, split_date, grid: list) -> list:
    """Run grid search over Zone Scanner parameters."""
    results = []
    for min_score, rr_ratio, max_base in grid:
        strategy = ZoneScanner(min_score=min_score, rr_ratio=rr_ratio, max_base_candles=max_base)
        bt = Backtester(strategy=strategy)
        agg = {"triggers": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        for sym, df in data_dict.items():
            try:
                r = bt.run(df, split_date, sym)
                agg["triggers"] += r.zones_triggered
                agg["wins"]     += r.targets_hit
                agg["losses"]   += r.sl_hit
                agg["pnl"]      += r.total_pnl
            except Exception:
                pass
        wr = agg["wins"] / agg["triggers"] * 100 if agg["triggers"] > 0 else 0.0
        results.append({
            "strategy": "Supply & Demand Zones",
            "params": {"min_score": min_score, "rr_ratio": rr_ratio, "max_base_candles": max_base},
            "triggers": agg["triggers"], "wins": agg["wins"], "losses": agg["losses"],
            "win_rate": round(wr, 1), "total_pnl": round(agg["pnl"], 2),
        })
    return results


def run_mini_optimizer(data_dict: dict, up_to_day: date, quick: bool) -> dict:
    """
    Run grid search on accumulated data up to up_to_day.
    Returns best_zone_params dict.
    """
    eod = eod_dt(up_to_day)
    sliced = {
        sym: slice_data(df, eod)
        for sym, df in data_dict.items()
    }
    sliced = {sym: df for sym, df in sliced.items() if len(df) >= 20}
    if len(sliced) < 3:
        return {}

    # Split date: TEST_DAYS before the most recent bar in sliced data
    latest = max(df.index[-1] for df in sliced.values())
    if hasattr(latest, 'to_pydatetime'):
        latest = latest.to_pydatetime()
    split = latest - timedelta(days=TEST_DAYS)

    zone_grid = QUICK_ZONE_GRID if quick else ZONE_GRID
    zone_results = run_zone_grid(sliced, split, zone_grid)

    # Best by win_rate with sufficient triggers
    def _best(results):
        valid = [r for r in results if r["triggers"] >= 15]
        if valid:
            return max(valid, key=lambda r: r["win_rate"])
        valid = [r for r in results if r["triggers"] >= 8]
        if valid:
            return max(valid, key=lambda r: r["win_rate"])
        return max(results, key=lambda r: r["triggers"]) if results else None

    best_zone = _best(zone_results)
    best_zone_params = best_zone["params"] if best_zone else {}
    zone_wr = best_zone["win_rate"] if best_zone else 0.0

    logger.info(f"Mini-optimizer: Zone WR={zone_wr:.1f}% → params {best_zone_params}")
    return best_zone_params
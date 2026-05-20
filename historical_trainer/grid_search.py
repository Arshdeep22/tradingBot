"""
Grid search runner for Professional Zone Scanner parameter tuning.
Searches over the key tunable dimensions of the zone strategy.

KEY FIXES (v2):
- Wider SL multiplier range (1.3-1.8 instead of 0.8-1.2)
- Lower RR targets (1.5-2.5 instead of 2.5-3.5)
- Better scoring: penalize low trade counts, require minimum trades
- Longer TEST_DAYS (30 instead of 15) for statistical significance
"""

import logging
from datetime import date, timedelta

from core.backtester import Backtester
from strategies.zone_scanner import ProfessionalZoneScanner

from .constants import ZONE_GRID, QUICK_ZONE_GRID, TEST_DAYS, DEFAULT_ZONE_PARAMS
from .time_utils import eod_dt, slice_data

logger = logging.getLogger(__name__)


def _build_scanner_from_grid_point(grid_point: tuple) -> ProfessionalZoneScanner:
    """
    Build a ProfessionalZoneScanner from a grid search point.
    Grid point: (min_score_to_trade, default_rr_ratio, min_rr_ratio, sl_atr_multiplier, max_sl_pct, max_base_candles)
    """
    min_score_to_trade, default_rr_ratio, min_rr_ratio, sl_atr_multiplier, max_sl_pct, max_base_candles = grid_point

    config = {
        # Disable features not needed for backtesting
        "enable_stock_selection": False,
        "enable_market_conditions": False,
        "check_confirmation": False,
        # Detection
        "max_base_candles": max_base_candles,
        "min_body_ratio": 0.60,
        "min_volume_ratio": 1.5,
        "min_legin_multiplier": 0.8,
        "detect_dbr": True, "detect_rbd": True, "detect_rbr": True, "detect_dbd": True,
        # Filters
        "max_zone_width_pct": 1.5,
        "min_zone_width_pct": 0.1,
        "max_distance_from_cmp": 3.0,
        # Scoring
        "min_score_to_trade": min_score_to_trade,
        # Trade Levels
        "sl_atr_multiplier": sl_atr_multiplier,
        "max_sl_pct": max_sl_pct,
        "default_rr_ratio": default_rr_ratio,
        "min_rr_ratio": min_rr_ratio,
        "risk_per_trade_pct": 1.0,
        "capital": 100000,
    }
    return ProfessionalZoneScanner(**config)


def run_zone_grid(data_dict: dict, split_date, grid: list) -> list:
    """Run grid search over Professional Zone Scanner parameters."""
    results = []
    for grid_point in grid:
        min_score_to_trade, default_rr_ratio, min_rr_ratio, sl_atr_multiplier, max_sl_pct, max_base_candles = grid_point

        strategy = _build_scanner_from_grid_point(grid_point)
        bt = Backtester(strategy=strategy)
        agg = {"triggers": 0, "wins": 0, "losses": 0, "expired": 0, "pnl": 0.0, "rr_sum": 0.0}

        for sym, df in data_dict.items():
            try:
                r = bt.run(df, split_date, sym)
                agg["triggers"] += r.zones_triggered
                agg["wins"] += r.targets_hit
                agg["losses"] += r.sl_hit
                agg["expired"] += r.expired
                agg["pnl"] += r.total_pnl
                agg["rr_sum"] += r.avg_rr_achieved * r.zones_triggered if r.zones_triggered > 0 else 0
            except Exception:
                pass

        wr = agg["wins"] / agg["triggers"] * 100 if agg["triggers"] > 0 else 0.0
        avg_rr = agg["rr_sum"] / agg["triggers"] if agg["triggers"] > 0 else 0.0

        results.append({
            "strategy": "Professional Zone Scanner",
            "params": {
                "min_score_to_trade": min_score_to_trade,
                "default_rr_ratio": default_rr_ratio,
                "min_rr_ratio": min_rr_ratio,
                "sl_atr_multiplier": sl_atr_multiplier,
                "max_sl_pct": max_sl_pct,
                "max_base_candles": max_base_candles,
            },
            "triggers": agg["triggers"],
            "wins": agg["wins"],
            "losses": agg["losses"],
            "expired": agg["expired"],
            "win_rate": round(wr, 1),
            "avg_rr": round(avg_rr, 2),
            "total_pnl": round(agg["pnl"], 2),
        })
    return results


def run_mini_optimizer(data_dict: dict, up_to_day: date, quick: bool) -> dict:
    """
    Run grid search on accumulated data up to up_to_day.
    Returns best_zone_params dict matching DEFAULT_ZONE_PARAMS keys.
    
    v2 improvements:
    - Longer lookback (TEST_DAYS=30)
    - Better scoring that prioritizes profitable expectancy
    - Requires minimum trade count for statistical confidence
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

    # Best by EXPECTANCY-based composite score
    # Expectancy = (WR * avg_win_RR) - ((1-WR) * avg_loss_RR)
    # Simplified: WR * avg_RR gives a good proxy when avg_RR includes losses
    def _best(results):
        # Require minimum trades for statistical confidence
        min_trades = 8 if not quick else 5
        valid = [r for r in results if r["triggers"] >= min_trades]
        if not valid:
            valid = [r for r in results if r["triggers"] >= 3]
        if not valid:
            valid = results

        if not valid:
            return None

        best_result = None
        best_score = -999

        for r in valid:
            wr = r["win_rate"] / 100.0  # 0-1
            avg_rr = r["avg_rr"]
            triggers = r["triggers"]

            # Expectancy: (WR × avg_win) - ((1-WR) × 1.0)
            # Since avg_rr already includes losses (negative RR), we can use:
            # Score = avg_rr (captures both WR and RR quality)
            # But also penalize very few trades (unreliable)
            
            # Composite: 40% win_rate + 40% avg_rr quality + 20% P&L
            wr_component = wr  # 0-1
            
            # RR component: normalize to 0-1 range (2.0 RR = perfect)
            rr_component = max(0, min(avg_rr / 2.0, 1.0))
            
            # P&L component: positive is good
            pnl_component = 1.0 if r["total_pnl"] > 0 else 0.0
            
            # Trade count penalty: too few trades = unreliable
            count_factor = min(triggers / 15.0, 1.0)  # Full weight at 15+ trades
            
            composite = (wr_component * 0.4 + rr_component * 0.4 + pnl_component * 0.2) * count_factor

            if composite > best_score:
                best_score = composite
                best_result = r

        return best_result

    best_zone = _best(zone_results)
    if not best_zone:
        return {}

    best_zone_params = best_zone["params"]
    zone_wr = best_zone["win_rate"]
    zone_rr = best_zone["avg_rr"]

    logger.info(
        f"Mini-optimizer: Zone WR={zone_wr:.1f}% avg_RR={zone_rr:.2f} "
        f"triggers={best_zone['triggers']} → params {best_zone_params}"
    )
    return best_zone_params
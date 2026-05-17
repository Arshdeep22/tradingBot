"""
Per-day walk-forward simulation logic.
Extends test window to 3 trading days for realistic holding periods.
Includes simple regime detection and trade quality filters.
Uses only Zone Scanner strategy.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import numpy as np

from core.backtester import Backtester
from strategies.zone_scanner import ZoneScanner

from .time_utils import split_dt, eod_dt, slice_data

logger = logging.getLogger(__name__)

# 3 trading days on 15m = ~75 bars
MAX_HOLDING_BARS = 75


def detect_regime(data: pd.DataFrame) -> str:
    """
    Simple regime detection using EMA slope + ATR percentile.
    Returns one of: "trending_up", "trending_down", "ranging", "volatile", "unknown"
    """
    if data is None or len(data) < 30:
        return "unknown"

    close = data['Close']
    ema20 = close.ewm(span=20, adjust=False).mean()
    if len(ema20) < 11:
        return "unknown"

    ema_slope = (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100

    # ATR percentile: current ATR vs recent history
    high = data['High']
    low = data['Low']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(com=13, adjust=False).mean()

    if len(atr) < 20:
        return "unknown"

    current_atr = atr.iloc[-1]
    atr_median = atr.iloc[-50:].median() if len(atr) >= 50 else atr.median()
    atr_ratio = current_atr / atr_median if atr_median > 0 else 1.0

    if atr_ratio > 1.5:
        return "volatile"
    elif ema_slope > 0.5:
        return "trending_up"
    elif ema_slope < -0.5:
        return "trending_down"
    else:
        return "ranging"


def _ema_slope_for_symbol(data: pd.DataFrame) -> float:
    """Calculate EMA(20) slope percentage for trend alignment filter."""
    if data is None or len(data) < 25:
        return 0.0
    ema20 = data['Close'].ewm(span=20, adjust=False).mean()
    if len(ema20) < 11:
        return 0.0
    return (ema20.iloc[-1] - ema20.iloc[-10]) / ema20.iloc[-10] * 100


def _get_3day_test_window(day: date, all_days: list, data_dict: dict, symbol: str):
    """
    Get test data spanning up to 3 trading days forward from the given day.
    Returns a DataFrame slice from split_time on day to eod on day+2 trading days.
    """
    try:
        day_idx = all_days.index(day)
    except ValueError:
        return None

    end_day_idx = min(day_idx + 2, len(all_days) - 1)
    end_day = all_days[end_day_idx]

    split_time = split_dt(day)
    end_time = eod_dt(end_day)

    if symbol not in data_dict:
        return None

    full_df = data_dict[symbol]
    test_slice = full_df[(full_df.index >= split_time) & (full_df.index <= end_time)]
    return test_slice if len(test_slice) > 0 else None


def run_day(day: date, data_dict: dict, current_zone_params: dict,
            current_weights: dict = None, all_days: list = None) -> list:
    """
    Simulate one walk-forward trading day using Zone Scanner only.
    Returns a list of trade dicts for setups that triggered.
    Test window extends up to 3 trading days forward for each trade.
    """
    split_time = split_dt(day)
    eod_time = eod_dt(day)

    zp = current_zone_params or {"min_score": 75, "rr_ratio": 2.5, "max_base_candles": 4}
    zone_scanner = ZoneScanner(
        min_score=zp.get("min_score", 75),
        rr_ratio=zp.get("rr_ratio", 2.5),
        max_base_candles=zp.get("max_base_candles", 4),
    )

    # Detect regime from a representative symbol's data up to split_time
    regime = "unknown"
    for sym, df in data_dict.items():
        build_slice = slice_data(df, split_time)
        if len(build_slice) >= 30:
            regime = detect_regime(build_slice)
            break

    bt = Backtester(strategy=zone_scanner)
    day_trades = []
    max_trades_per_day = 12  # Maximum zone trades per day

    for symbol, full_df in data_dict.items():
        if len(day_trades) >= max_trades_per_day:
            break

        # Build data: everything up to split_time
        build_data = slice_data(full_df, split_time)
        if len(build_data) < 15:
            continue

        # Trade quality filter: trend alignment
        ema_slope = _ema_slope_for_symbol(build_data)

        try:
            # Get test window (3 trading days)
            if all_days:
                test_data_3d = _get_3day_test_window(day, all_days, data_dict, symbol)
            else:
                test_data_3d = slice_data(full_df, eod_time)
                test_data_3d = test_data_3d[test_data_3d.index >= split_time]

            if test_data_3d is None or len(test_data_3d) < 5:
                continue

            # Use backtester with 3-day window
            combined = pd.concat([build_data, test_data_3d])
            combined = combined[~combined.index.duplicated(keep='first')]
            report = bt.run(combined, split_time, symbol)

            first = next(
                (tr for tr in report.trade_results
                 if tr.triggered and tr.outcome in ("TARGET_HIT", "SL_HIT", "EXPIRED")),
                None,
            )
            if first is None:
                continue

            # Trend alignment filter
            if first.setup.side == "BUY" and ema_slope < -1.0:
                continue  # Skip demand zones in strong downtrend
            if first.setup.side == "SELL" and ema_slope > 1.0:
                continue  # Skip supply zones in strong uptrend

            trade = {
                "symbol": symbol,
                "strategy": "Supply & Demand Zones",
                "side": first.setup.side,
                "outcome": first.outcome,
                "pnl": round(first.pnl, 2),
                "entry": round(first.trigger_price, 2),
                "trigger_time": first.trigger_time,
                "exit_time": first.exit_time,
            }
            day_trades.append(trade)

        except Exception as e:
            logger.debug("  %s: %s", symbol, e)

    return day_trades
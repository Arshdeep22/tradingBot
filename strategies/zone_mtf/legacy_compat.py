"""
Legacy compatibility layer for the old zone_mtf.py interface.

Provides the old multi_timeframe_confirm() function that zone_scanner.py uses.
New code should use multi_timeframe_analysis() from the orchestrator instead.
"""
import pandas as pd
from typing import List

from strategies.zone_models import Zone
from strategies.zone_mtf.trend import detect_trend
from strategies.zone_mtf.entry_refinement import check_freshness_on_entry_tf


def check_trend_5m(data_5m: pd.DataFrame, zone: Zone) -> str:
    """Legacy: Check 5m trend direction. Delegates to detect_trend."""
    if data_5m is None or len(data_5m) < 20:
        return "SIDEWAYS"
    return detect_trend(data_5m, lookback=20, swing_window=3)


def multi_timeframe_confirm(zones_15m: List[Zone], data_5m: pd.DataFrame,
                            data_3m: pd.DataFrame, rr_ratio: float) -> List[Zone]:
    """
    Legacy: Apply multi-timeframe confirmation to 15m zones.

    Filters:
    - Rejects demand zones in 5m downtrend
    - Rejects supply zones in 5m uptrend
    - Checks freshness on 5m and 3m

    Args:
        zones_15m: Zones detected on 15m timeframe
        data_5m: 5-minute OHLCV data
        data_3m: 3-minute (or 2m/1m) OHLCV data
        rr_ratio: Risk-reward ratio for target calculation (unused in new system)

    Returns:
        List of confirmed zones with MTF annotations
    """
    confirmed = []

    for zone in zones_15m:
        # Check trend on 5m
        trend = check_trend_5m(data_5m, zone)

        # Reject counter-trend
        if zone.zone_type == "DEMAND" and trend == "DOWN":
            continue
        if zone.zone_type == "SUPPLY" and trend == "UP":
            continue

        # Check freshness on both timeframes
        fresh_5m = check_freshness_on_entry_tf(zone, data_5m)
        fresh_3m = (
            check_freshness_on_entry_tf(zone, data_3m)
            if data_3m is not None
            else True
        )

        if zone.is_fresh and fresh_5m and fresh_3m:
            trend_text = (
                "BULLISH" if trend == "UP"
                else "BEARISH" if trend == "DOWN"
                else "SIDEWAYS"
            )
            zone.reasoning = (zone.reasoning or "") + (
                f"\n• MTF Confirmed: Fresh on 15m/5m/3m"
                f"\n• 5m Trend: {trend_text}"
            )
            confirmed.append(zone)

    confirmed.sort(key=lambda z: z.score, reverse=True)
    return confirmed
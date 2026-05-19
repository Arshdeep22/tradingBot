"""
Strict freshness checking for supply/demand zones.

Uses professional wick-based logic:
- Zone is TESTED if price enters the zone (wick touches)
- Zone is BROKEN if price closes through the zone (remove entirely)
"""

from typing import List

import pandas as pd

from strategies.zone_models import Zone


def check_freshness(zones: List[Zone], data: pd.DataFrame) -> List[Zone]:
    """
    Check if zones are fresh using strict professional rules.

    DEMAND zone is TESTED (not fresh) if:
      - Any candle's LOW <= zone_top (price entered the zone)

    SUPPLY zone is TESTED (not fresh) if:
      - Any candle's HIGH >= zone_bottom (price entered the zone)

    DEMAND zone is BROKEN (remove it) if:
      - Any candle CLOSES below zone_bottom (price went through)

    SUPPLY zone is BROKEN (remove it) if:
      - Any candle CLOSES above zone_top (price went through)

    Args:
        zones: List of detected Zone objects
        data: Full OHLC DataFrame used for checking subsequent price action

    Returns:
        List of zones with is_fresh updated. Broken zones excluded entirely.
    """
    if not zones or data.empty:
        return []

    fresh_zones: List[Zone] = []
    total_candles = len(data)

    for zone in zones:
        # Determine where to start checking (after zone formation)
        check_start = (
            zone.formed_at_index + zone.base_candles + zone.leg_out_count + 1
        )

        # Ensure check_start is within bounds
        if check_start >= total_candles:
            # Zone just formed, no candles to check — it's fresh
            zone.is_fresh = True
            zone.age_candles = 0
            fresh_zones.append(zone)
            continue

        # Get candles after zone formation
        subsequent = data.iloc[check_start:]
        zone.age_candles = len(subsequent)

        is_broken = False
        is_tested = False

        if zone.zone_type == "DEMAND":
            # BROKEN: any candle closes below zone_bottom
            if (subsequent["close"] < zone.zone_bottom).any():
                is_broken = True
            # TESTED: any candle's low enters the zone (low <= zone_top)
            elif (subsequent["low"] <= zone.zone_top).any():
                is_tested = True

        elif zone.zone_type == "SUPPLY":
            # BROKEN: any candle closes above zone_top
            if (subsequent["close"] > zone.zone_top).any():
                is_broken = True
            # TESTED: any candle's high enters the zone (high >= zone_bottom)
            elif (subsequent["high"] >= zone.zone_bottom).any():
                is_tested = True

        # Skip broken zones entirely
        if is_broken:
            continue

        # Mark freshness
        zone.is_fresh = not is_tested
        fresh_zones.append(zone)

    return fresh_zones
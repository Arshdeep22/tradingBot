"""
Zone Detection
--------------
Core algorithms for detecting supply and demand zones from OHLCV data.
Handles demand zone detection, supply zone detection, and freshness checking.
"""

import pandas as pd
from typing import List, Optional

from .zone_models import Zone


def detect_demand_zone(data: pd.DataFrame, start_idx: int,
                       threshold: float, max_base_candles: int) -> Optional[Zone]:
    """
    Detect a demand zone starting at given index.
    Pattern: Large bearish candle(s) → Small base candle(s) → Large bullish candle (leg out)
    """
    n = len(data)

    # Check if current candle is a small base candle
    if data['body_pct'].iloc[start_idx] >= threshold:
        return None  # Not a base candle

    # Look for leg-out (bullish) AFTER the base
    base_start = start_idx
    base_end = start_idx

    # Find consecutive small candles (base)
    for j in range(start_idx, min(start_idx + max_base_candles + 1, n)):
        if data['body_pct'].iloc[j] < threshold:
            base_end = j
        else:
            break

    base_candles = base_end - base_start + 1

    if base_candles > max_base_candles:
        return None

    # Check for leg-out (large bullish candle after base)
    leg_out_idx = base_end + 1
    if leg_out_idx >= n:
        return None

    if not (data['is_bullish'].iloc[leg_out_idx] and
            data['body_pct'].iloc[leg_out_idx] >= threshold):
        return None

    # Check for leg-in (price was dropping before base)
    if base_start > 0:
        leg_in_idx = base_start - 1
        if not data['is_bearish'].iloc[leg_in_idx]:
            return None  # No drop before base

    # Define zone boundaries
    zone_top = data['High'].iloc[base_start:base_end + 1].max()
    zone_bottom = data['Low'].iloc[base_start:base_end + 1].min()

    # Leg-out candle body percentage
    leg_out_pct = data['body_pct'].iloc[leg_out_idx]

    # Get formation time
    formed_time = ""
    if hasattr(data, 'index') and hasattr(data.index, 'strftime'):
        try:
            formed_time = str(data.index[base_start])
        except Exception:
            formed_time = str(base_start)

    return Zone(
        zone_type="DEMAND",
        zone_top=round(zone_top, 2),
        zone_bottom=round(zone_bottom, 2),
        base_candles=base_candles,
        leg_out_pct=round(leg_out_pct, 3),
        is_fresh=True,  # Will be checked later
        score=0,
        freshness_score=0,
        legout_score=0,
        base_score=0,
        formed_at_index=base_start,
        formed_at_time=formed_time
    )


def detect_supply_zone(data: pd.DataFrame, start_idx: int,
                       threshold: float, max_base_candles: int) -> Optional[Zone]:
    """
    Detect a supply zone starting at given index.
    Pattern: Large bullish candle(s) → Small base candle(s) → Large bearish candle (leg out)
    """
    n = len(data)

    # Check if current candle is a small base candle
    if data['body_pct'].iloc[start_idx] >= threshold:
        return None

    # Look for leg-out (bearish) AFTER the base
    base_start = start_idx
    base_end = start_idx

    # Find consecutive small candles (base)
    for j in range(start_idx, min(start_idx + max_base_candles + 1, n)):
        if data['body_pct'].iloc[j] < threshold:
            base_end = j
        else:
            break

    base_candles = base_end - base_start + 1

    if base_candles > max_base_candles:
        return None

    # Check for leg-out (large bearish candle after base)
    leg_out_idx = base_end + 1
    if leg_out_idx >= n:
        return None

    if not (data['is_bearish'].iloc[leg_out_idx] and
            data['body_pct'].iloc[leg_out_idx] >= threshold):
        return None

    # Check for leg-in (price was rallying before base)
    if base_start > 0:
        leg_in_idx = base_start - 1
        if not data['is_bullish'].iloc[leg_in_idx]:
            return None  # No rally before base

    # Define zone boundaries
    zone_top = data['High'].iloc[base_start:base_end + 1].max()
    zone_bottom = data['Low'].iloc[base_start:base_end + 1].min()

    # Leg-out candle body percentage
    leg_out_pct = data['body_pct'].iloc[leg_out_idx]

    # Get formation time
    formed_time = ""
    if hasattr(data, 'index') and hasattr(data.index, 'strftime'):
        try:
            formed_time = str(data.index[base_start])
        except Exception:
            formed_time = str(base_start)

    return Zone(
        zone_type="SUPPLY",
        zone_top=round(zone_top, 2),
        zone_bottom=round(zone_bottom, 2),
        base_candles=base_candles,
        leg_out_pct=round(leg_out_pct, 3),
        is_fresh=True,
        score=0,
        freshness_score=0,
        legout_score=0,
        base_score=0,
        formed_at_index=base_start,
        formed_at_time=formed_time
    )


def check_freshness(zones: List[Zone], data: pd.DataFrame) -> List[Zone]:
    """Check if zones are fresh (never tested after formation). Returns only fresh zones."""
    fresh_zones = []

    for zone in zones:
        is_fresh = True
        # Check all candles AFTER zone formation
        for i in range(zone.formed_at_index + zone.base_candles + 1, len(data)):
            if zone.zone_type == "DEMAND":
                # Stale only if candle closes BELOW zone_bottom (broke through)
                candle_close = data['Close'].iloc[i]
                if candle_close < zone.zone_bottom:
                    is_fresh = False
                    break
            elif zone.zone_type == "SUPPLY":
                # Stale only if candle closes ABOVE zone_top (broke through)
                candle_close = data['Close'].iloc[i]
                if candle_close > zone.zone_top:
                    is_fresh = False
                    break

        zone.is_fresh = is_fresh
        if is_fresh:
            fresh_zones.append(zone)

    return fresh_zones
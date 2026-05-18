"""
Zone Multi-Timeframe Analysis
------------------------------
Multi-timeframe confirmation logic for supply and demand zones.
Confirms zones found on 15m using 5m trend and 3m entry refinement.
"""

import pandas as pd
from typing import List

from .zone_models import Zone


def check_trend_5m(data_5m: pd.DataFrame, zone: Zone) -> str:
    """
    Check 5m trend direction relative to zone.
    Returns: "UP", "DOWN", or "SIDEWAYS"
    """
    if data_5m is None or len(data_5m) < 20:
        return "SIDEWAYS"

    # Use last 20 candles for trend
    recent = data_5m.tail(20)

    # Simple trend: compare EMA 9 vs EMA 20
    ema_fast = recent['Close'].ewm(span=9, adjust=False).mean()
    ema_slow = recent['Close'].ewm(span=20, adjust=False).mean()

    if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
        return "UP"
    elif ema_fast.iloc[-1] < ema_slow.iloc[-1]:
        return "DOWN"
    else:
        return "SIDEWAYS"


def refine_on_3m(data_3m: pd.DataFrame, zone: Zone, rr_ratio: float) -> Zone:
    """
    Refine entry/SL/target using 3m chart for tighter levels.
    Looks for a more precise zone boundary on 3m.
    """
    if data_3m is None or len(data_3m) < 10:
        return zone

    refined = Zone(
        zone_type=zone.zone_type,
        zone_top=zone.zone_top,
        zone_bottom=zone.zone_bottom,
        base_candles=zone.base_candles,
        leg_out_pct=zone.leg_out_pct,
        is_fresh=zone.is_fresh,
        score=zone.score,
        freshness_score=zone.freshness_score,
        legout_score=zone.legout_score,
        base_score=zone.base_score,
        formed_at_index=zone.formed_at_index,
        formed_at_time=zone.formed_at_time,
        entry=zone.entry,
        stop_loss=zone.stop_loss,
        target=zone.target,
        reasoning=zone.reasoning,
        symbol=zone.symbol
    )

    data = data_3m.copy().reset_index(drop=True)

    # Look for a tighter zone on 3m within the 15m zone range
    data['body'] = abs(data['Close'] - data['Open'])
    data['body_pct'] = (data['body'] / data['Close']) * 100

    # Find candles within the zone
    in_zone = data[
        (data['Low'] >= zone.zone_bottom * 0.999) &
        (data['High'] <= zone.zone_top * 1.001)
    ]

    if len(in_zone) >= 1:
        # Tighter zone from 3m data
        tighter_top = in_zone['High'].max()
        tighter_bottom = in_zone['Low'].min()

        if zone.zone_type == "DEMAND":
            refined.entry = round(tighter_top, 2)
            refined.stop_loss = round(tighter_bottom * (1 - 0.004), 2)
            risk = refined.entry - refined.stop_loss
            refined.target = round(refined.entry + (rr_ratio * risk), 2)
        else:
            refined.entry = round(tighter_bottom, 2)
            refined.stop_loss = round(tighter_top * (1 + 0.004), 2)
            risk = refined.stop_loss - refined.entry
            refined.target = round(refined.entry - (rr_ratio * risk), 2)

    return refined


def check_fresh_on_timeframe(data: pd.DataFrame, zone: Zone) -> bool:
    """Check if zone is fresh on a given timeframe's data."""
    if data is None or len(data) < 5:
        return True  # Assume fresh if no data

    data = data.copy().reset_index(drop=True)

    # Check last 20 candles to see if price entered the zone
    recent = data.tail(20)

    for i in range(len(recent)):
        candle_low = recent['Low'].iloc[i]
        candle_high = recent['High'].iloc[i]

        if zone.zone_type == "DEMAND":
            if candle_low <= zone.zone_top and candle_low >= zone.zone_bottom:
                return False  # Zone was tested
        elif zone.zone_type == "SUPPLY":
            if candle_high >= zone.zone_bottom and candle_high <= zone.zone_top:
                return False  # Zone was tested

    return True


def multi_timeframe_confirm(zones_15m: List[Zone], data_5m: pd.DataFrame,
                            data_3m: pd.DataFrame, rr_ratio: float) -> List[Zone]:
    """
    Apply multi-timeframe confirmation to 15m zones.
    
    Filters:
    - Rejects demand zones in 5m downtrend
    - Rejects supply zones in 5m uptrend
    - Checks freshness on 5m and 3m
    - Refines entry on 3m
    
    Args:
        zones_15m: Zones detected on 15m timeframe
        data_5m: 5-minute OHLCV data
        data_3m: 3-minute (or 2m/1m) OHLCV data
        rr_ratio: Risk-reward ratio for target calculation
    
    Returns:
        List of confirmed zones with MTF annotations
    """
    confirmed_zones = []

    for zone in zones_15m:
        # Check trend on 5m
        trend = check_trend_5m(data_5m, zone)

        # Reject zones that trade against the 5m trend
        if zone.zone_type == "DEMAND" and trend == "DOWN":
            continue
        if zone.zone_type == "SUPPLY" and trend == "UP":
            continue

        # Refine on 3m
        refined_zone = refine_on_3m(data_3m, zone, rr_ratio) if data_3m is not None else zone

        # Check freshness across timeframes
        fresh_on_5m = check_fresh_on_timeframe(data_5m, zone)
        fresh_on_3m = check_fresh_on_timeframe(data_3m, zone) if data_3m is not None else True

        # Update zone with MTF info
        mtf_fresh = zone.is_fresh and fresh_on_5m and fresh_on_3m

        if mtf_fresh:
            refined_zone.is_fresh = True
            # Bonus reasoning for multi-timeframe confirmation
            trend_text = "BULLISH" if trend == "UP" else "BEARISH" if trend == "DOWN" else "SIDEWAYS"
            refined_zone.reasoning += (
                f"\n• MTF Confirmed: Fresh on 15m/5m/3m"
                f"\n• 5m Trend: {trend_text}"
                f"\n• Entry refined on 3m chart"
            )
            confirmed_zones.append(refined_zone)

    # Sort by score
    confirmed_zones.sort(key=lambda z: z.score, reverse=True)
    return confirmed_zones
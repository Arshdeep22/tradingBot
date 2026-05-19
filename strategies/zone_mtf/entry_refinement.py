"""
Entry timeframe (5m) refinement — arrival quality and freshness cross-check.

The entry TF gives a more granular view to:
1. Assess how price is approaching the zone (arrival quality)
2. Catch brief wick touches that 15m candles might miss
"""
import pandas as pd

from strategies.zone_models import Zone
from strategies.zone_trade_levels.confirmation import (
    detect_demand_confirmation,
    detect_supply_confirmation,
)


def assess_arrival_on_entry_tf(zone: Zone, data_5m: pd.DataFrame) -> int:
    """
    Look at last 5-10 candles on 5m for approach quality.

    A slow, controlled approach (small candles) = institutions accumulating.
    A fast momentum crash (large candles) = retail panic, less reliable bounce.

    Scoring (0-10):
        10 = Very slow approach (avg body < 40% of overall avg)
        8  = Slow approach (40-60%)
        7  = Normal-slow (60-80%)
        5  = Average approach (80-120%)
        3  = Fast approach (120-180%)
        1  = Momentum crash (>180%)

    Args:
        zone: The zone being evaluated
        data_5m: 5-minute OHLC DataFrame

    Returns:
        Refined arrival score (0-10)
    """
    if data_5m is None or len(data_5m) < 15:
        return 5  # Default neutral if insufficient data

    # Calculate body sizes
    bodies = (data_5m['close'] - data_5m['open']).abs()
    overall_avg = bodies.mean()

    if overall_avg <= 0:
        return 5

    # Last 8 candles (roughly last 40 minutes on 5m)
    recent_count = min(8, len(bodies))
    recent_avg = bodies.tail(recent_count).mean()
    ratio = recent_avg / overall_avg

    if ratio < 0.4:
        return 10
    elif ratio < 0.6:
        return 8
    elif ratio < 0.8:
        return 7
    elif ratio < 1.2:
        return 5
    elif ratio < 1.8:
        return 3
    else:
        return 1


def check_freshness_on_entry_tf(zone: Zone, data_5m: pd.DataFrame) -> bool:
    """
    Verify zone is fresh on 5m — catches brief wicks between 15m candles.

    A zone might appear fresh on 15m but a brief 5m wick may have
    already tested it. This cross-check provides extra confidence.

    Args:
        zone: The zone to check
        data_5m: 5-minute OHLC DataFrame (recent candles)

    Returns:
        True if zone is still fresh on entry TF, False if tested
    """
    if data_5m is None or len(data_5m) < 5:
        return True  # Assume fresh if no data

    # Check last 30 candles on 5m (last 2.5 hours)
    check_count = min(30, len(data_5m))
    recent = data_5m.tail(check_count)

    if zone.zone_type == "DEMAND":
        # Zone is tested if any 5m candle's low enters the zone
        zone_top = zone.zone_top
        zone_bottom = zone.zone_bottom
        for i in range(len(recent)):
            candle_low = float(recent['low'].iloc[i])
            if zone_bottom <= candle_low <= zone_top:
                return False  # Wick entered zone — tested
    elif zone.zone_type == "SUPPLY":
        # Zone is tested if any 5m candle's high enters the zone
        zone_top = zone.zone_top
        zone_bottom = zone.zone_bottom
        for i in range(len(recent)):
            candle_high = float(recent['high'].iloc[i])
            if zone_bottom <= candle_high <= zone_top:
                return False  # Wick entered zone — tested

    return True


def check_confirmation_on_entry_tf(zone: Zone, data_5m: pd.DataFrame, config: dict) -> Zone:
    """
    When price is within confirmation_check_pct of the zone edge, detect candle patterns.

    Populates zone.confirmation_available, confirmation_pattern, confirmation_strength.
    Only runs if price is close enough that a pattern is meaningful — skips silently otherwise.
    """
    if data_5m is None or len(data_5m) < 3:
        return zone

    # Require entry to be set (set by trade levels calculator)
    entry = zone.entry
    if not entry:
        return zone

    current_price = float(data_5m["close"].iloc[-1])
    check_pct = config.get("confirmation_check_pct", 0.5)
    distance_pct = abs(current_price - entry) / entry * 100

    if distance_pct > check_pct:
        return zone  # Too far from zone edge — pattern not yet meaningful

    zone.confirmation_available = True

    if zone.zone_type == "DEMAND":
        signal = detect_demand_confirmation(data_5m, zone.zone_top, zone.zone_bottom, config)
    else:
        signal = detect_supply_confirmation(data_5m, zone.zone_top, zone.zone_bottom, config)

    zone.confirmation_pattern = signal.pattern
    zone.confirmation_strength = signal.strength
    return zone

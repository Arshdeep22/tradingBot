"""
Zone Detection - Main Detector Module.

This is the orchestrator that ties together all components to detect zones.
It scans for large candles (leg-outs), looks backwards for bases and leg-ins,
classifies patterns, and creates Zone objects.
"""

import pandas as pd
from typing import List, Tuple, Dict

from strategies.zone_models import Zone
from strategies.zone_detection.config import DEFAULT_CONFIG
from strategies.zone_detection.preparation import prepare_candle_data, compute_thresholds
from strategies.zone_detection.components import (
    find_leg_out_candles,
    find_base,
    find_leg_in,
    classify_pattern,
)


def _get_base_boundaries(data: pd.DataFrame, base_start: int, base_end: int) -> Tuple[float, float]:
    """Get zone top (highest High) and bottom (lowest Low) from base candles."""
    base_slice = data.iloc[base_start:base_end + 1]
    zone_top = float(base_slice['High'].max())
    zone_bottom = float(base_slice['Low'].min())
    return (zone_top, zone_bottom)


def _get_formation_time(data: pd.DataFrame, idx: int) -> str:
    """Get formation timestamp as string from the dataframe index or columns."""
    try:
        if hasattr(data.index, 'strftime'):
            return str(data.index[idx])
        elif 'Date' in data.columns:
            return str(data['Date'].iloc[idx])
        elif 'Datetime' in data.columns:
            return str(data['Datetime'].iloc[idx])
        return str(idx)
    except (IndexError, TypeError):
        return str(idx)


def _is_pattern_enabled(config: Dict, pattern: str) -> bool:
    """Check if a specific pattern detection is enabled in config."""
    pattern_key = f"detect_{pattern.lower()}"
    return config.get(pattern_key, True)


def _create_zone(zone_type: str, pattern: str, zone_top: float, zone_bottom: float,
                 base_start: int, base_count: int, formed_at_time: str,
                 leg_out_result: Tuple, leg_in_result: Tuple,
                 data_length: int, mean_body_pct: float = 0.0) -> Zone:
    """Create a Zone object from detection results."""
    leg_out_count, leg_out_body_pct, leg_out_body_ratio, leg_out_volume_ratio, has_gap = leg_out_result
    leg_in_body_pct, leg_in_candle_count = leg_in_result
    age_candles = max(0, data_length - base_start - 1)

    return Zone(
        zone_type=zone_type,
        pattern=pattern,
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        base_candles=base_count,
        formed_at_index=base_start,
        formed_at_time=formed_at_time,
        leg_out_count=leg_out_count,
        leg_out_body_pct=leg_out_body_pct,
        leg_out_body_ratio=leg_out_body_ratio,
        leg_out_volume_ratio=leg_out_volume_ratio,
        has_gap=has_gap,
        mean_body_pct=mean_body_pct,
        leg_in_body_pct=leg_in_body_pct,
        leg_in_candle_count=leg_in_candle_count,
        is_fresh=True,  # Will be checked properly in Plan 2
        age_candles=age_candles,
    )


def _try_pattern(data: pd.DataFrame, leg_out_idx: int, leg_out_direction: str,
                 leg_in_direction: str, leg_out_result: Tuple,
                 base_start: int, base_end: int, base_count: int,
                 thresholds: Dict, config: Dict, data_length: int) -> Zone:
    """
    Try to validate a specific pattern by checking the leg-in direction.
    Returns a Zone object if valid, None otherwise.
    """
    # Check if this pattern is enabled
    zone_type, pattern = classify_pattern(leg_in_direction, leg_out_direction)
    if not _is_pattern_enabled(config, pattern):
        return None

    # Try to find leg-in in the expected direction
    leg_in_result = find_leg_in(data, base_start, leg_in_direction, thresholds, config)
    if leg_in_result is None:
        return None

    # Get zone boundaries from base candles
    zone_top, zone_bottom = _get_base_boundaries(data, base_start, base_end)

    # Avoid degenerate zones (zero or negative height)
    if zone_top <= zone_bottom:
        return None

    # Get formation time
    formed_at_time = _get_formation_time(data, base_start)

    # Create and return the zone
    return _create_zone(
        zone_type=zone_type,
        pattern=pattern,
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        base_start=base_start,
        base_count=base_count,
        formed_at_time=formed_at_time,
        leg_out_result=leg_out_result,
        leg_in_result=leg_in_result,
        data_length=data_length,
        mean_body_pct=thresholds.get('mean_body_pct', 0.0),
    )


def detect_zones(data: pd.DataFrame, config: Dict = None) -> List[Zone]:
    """
    Main detection function. Scans for all 4 zone patterns.

    Algorithm:
    1. Prepare candle data (body_pct, body_ratio, is_bullish, is_bearish, volume_ratio)
    2. Compute adaptive thresholds (what counts as "large" and "small" candle)
    3. Scan through candles looking for LARGE candles (potential leg-outs)
    4. For each large candle found:
       a. Look BACKWARDS for a base (1-3 small candles before it)
       b. Look BACKWARDS past the base for a leg-in
       c. Determine pattern type (DBR/RBD/RBR/DBD) based on leg directions
       d. If valid pattern -> create Zone object
    5. Check for multiple consecutive leg-out candles (strengthens zone)
    6. Check for gaps after base (strengthens zone)
    7. Return list of detected zones

    Args:
        data: OHLCV DataFrame with columns Open, High, Low, Close, Volume
        config: Dict with detection settings. Uses DEFAULT_CONFIG for missing keys.

    Returns:
        List of Zone objects (unscored, freshness not yet validated)
    """
    # Merge config with defaults
    if config is None:
        cfg = DEFAULT_CONFIG.copy()
    else:
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(config)

    # Validate minimum data
    if data is None or len(data) < cfg.get('min_data_length', 30):
        return []

    # Step 1: Prepare data (reset index to ensure integer-based access)
    df = data.copy().reset_index(drop=True)
    df = prepare_candle_data(df)

    # Step 2: Compute thresholds
    thresholds = compute_thresholds(df, cfg)

    # Step 3-4: Scan for zones
    zones: List[Zone] = []
    max_base = cfg.get('max_base_candles', 3)
    # Need room for: leg-in (1+) + base (1+) before the leg-out
    min_start_idx = max_base + 2
    data_length = len(df)

    # Determine scan range (optionally limit to recent candles)
    lookback = cfg.get('lookback_window')
    if lookback and lookback < data_length:
        scan_start = max(min_start_idx, data_length - lookback)
    else:
        scan_start = min_start_idx

    # Track which indices have been used as leg-out starts to avoid duplicates
    used_legout_starts = set()

    for i in range(scan_start, data_length):
        # Skip if already used
        if i in used_legout_starts:
            continue

        row = df.iloc[i]

        # Is this a large candle? (potential leg-out start)
        if row['body_pct'] < thresholds['large_candle_threshold']:
            continue

        # Determine leg-out direction
        if row['is_bullish']:
            leg_out_direction = "BULLISH"
        elif row['is_bearish']:
            leg_out_direction = "BEARISH"
        else:
            continue  # Doji - skip

        # Validate leg-out (count consecutive, check body ratio)
        leg_out_result = find_leg_out_candles(df, i, leg_out_direction, thresholds, cfg)
        if leg_out_result is None:
            continue

        leg_out_count = leg_out_result[0]

        # Look backwards for base (just before leg-out index)
        base_result = find_base(df, i - 1, thresholds, max_base)
        if base_result is None:
            continue

        base_start, base_end, base_count = base_result

        # Try both reversal and continuation patterns based on leg-out direction
        # For BULLISH leg-out: try DBR (bearish leg-in) and RBR (bullish leg-in)
        # For BEARISH leg-out: try RBD (bullish leg-in) and DBD (bearish leg-in)

        if leg_out_direction == "BULLISH":
            # Try DBR: bearish leg-in -> base -> bullish leg-out = DEMAND
            zone = _try_pattern(
                df, i, leg_out_direction, "BEARISH", leg_out_result,
                base_start, base_end, base_count, thresholds, cfg, data_length
            )
            if zone:
                zones.append(zone)
                # Mark leg-out indices as used
                for offset in range(leg_out_count):
                    used_legout_starts.add(i + offset)
                continue  # Don't double-detect same base

            # Try RBR: bullish leg-in -> base -> bullish leg-out = DEMAND (continuation)
            zone = _try_pattern(
                df, i, leg_out_direction, "BULLISH", leg_out_result,
                base_start, base_end, base_count, thresholds, cfg, data_length
            )
            if zone:
                zones.append(zone)
                for offset in range(leg_out_count):
                    used_legout_starts.add(i + offset)

        elif leg_out_direction == "BEARISH":
            # Try RBD: bullish leg-in -> base -> bearish leg-out = SUPPLY
            zone = _try_pattern(
                df, i, leg_out_direction, "BULLISH", leg_out_result,
                base_start, base_end, base_count, thresholds, cfg, data_length
            )
            if zone:
                zones.append(zone)
                for offset in range(leg_out_count):
                    used_legout_starts.add(i + offset)
                continue

            # Try DBD: bearish leg-in -> base -> bearish leg-out = SUPPLY (continuation)
            zone = _try_pattern(
                df, i, leg_out_direction, "BEARISH", leg_out_result,
                base_start, base_end, base_count, thresholds, cfg, data_length
            )
            if zone:
                zones.append(zone)
                for offset in range(leg_out_count):
                    used_legout_starts.add(i + offset)

    return zones
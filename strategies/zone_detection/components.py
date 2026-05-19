"""
Zone Detection - Component Functions.

Core detection components:
- find_leg_out_candles: Detect consecutive large candles (the explosive move)
- find_base: Detect small candles between leg-in and leg-out
- find_leg_in: Detect the move that brought price to the base
- classify_pattern: Determine DBR/RBD/RBR/DBD from leg directions
"""

import pandas as pd
from typing import List, Optional, Tuple, Dict


def find_leg_out_candles(data: pd.DataFrame, idx: int, direction: str,
                         thresholds: Dict, config: Dict) -> Optional[Tuple]:
    """
    Starting at idx, count consecutive large candles in given direction.

    A valid leg-out consists of one or more large-body candles moving
    strongly in one direction. More consecutive candles = stronger departure.

    Args:
        data: Prepared DataFrame with body_pct, body_ratio, is_bullish, etc.
        idx: Starting index of potential leg-out
        direction: "BULLISH" or "BEARISH"
        thresholds: Dict from compute_thresholds()
        config: Configuration dict

    Returns:
        Tuple (count, avg_body_pct, avg_body_ratio, avg_volume_ratio, has_gap)
        or None if the first candle doesn't meet minimum body_ratio
    """
    max_count = config.get('max_leg_out_candles', 5)
    large_threshold = thresholds['large_candle_threshold']
    min_body_ratio = config.get('min_body_ratio', 0.60)

    count = 0
    body_pcts: List[float] = []
    body_ratios: List[float] = []
    volume_ratios: List[float] = []
    has_gap = False

    for offset in range(max_count):
        check_idx = idx + offset
        if check_idx >= len(data):
            break

        row = data.iloc[check_idx]

        # Must be a large candle
        if row['body_pct'] < large_threshold:
            break

        # Must be in correct direction
        if direction == "BULLISH" and not row['is_bullish']:
            break
        if direction == "BEARISH" and not row['is_bearish']:
            break

        # First candle MUST meet minimum body ratio (full body, not wicky)
        if offset == 0 and row['body_ratio'] < min_body_ratio:
            return None

        count += 1
        body_pcts.append(float(row['body_pct']))
        body_ratios.append(float(row['body_ratio']))
        volume_ratios.append(float(row['volume_ratio']))

    if count == 0:
        return None

    # Gap detection: check if there's a price gap between
    # the candle before leg-out and first leg-out candle
    if idx > 0:
        prev_row = data.iloc[idx - 1]
        first_legout = data.iloc[idx]
        if direction == "BULLISH":
            # Gap up: leg-out Low > previous candle's High
            has_gap = bool(first_legout['Low'] > prev_row['High'])
        else:
            # Gap down: leg-out High < previous candle's Low
            has_gap = bool(first_legout['High'] < prev_row['Low'])

    avg_body_pct = sum(body_pcts) / len(body_pcts)
    avg_body_ratio = sum(body_ratios) / len(body_ratios)
    avg_volume_ratio = sum(volume_ratios) / len(volume_ratios)

    return (count, avg_body_pct, avg_body_ratio, avg_volume_ratio, has_gap)


def find_base(data: pd.DataFrame, end_idx: int, thresholds: Dict,
              max_base_candles: int = 3) -> Optional[Tuple]:
    """
    Look backwards from end_idx for 1-N small candles (the base).

    A base is a cluster of small-body candles that represent a pause/
    consolidation between the leg-in and leg-out. The zone boundaries
    are derived from the base candles' highs and lows.

    Args:
        data: Prepared DataFrame
        end_idx: Index to start looking from (typically leg_out_idx - 1)
        thresholds: Dict from compute_thresholds()
        max_base_candles: Maximum number of candles allowed in base

    Returns:
        Tuple (base_start_idx, base_end_idx, base_candle_count) or None
    """
    small_threshold = thresholds['small_candle_threshold']

    # Validate end_idx
    if end_idx < 0 or end_idx >= len(data):
        return None

    # The candle at end_idx must be a small candle (part of base)
    if data['body_pct'].iloc[end_idx] > small_threshold:
        return None

    # Count consecutive small candles going backwards
    base_count = 1
    base_start = end_idx

    for lookback in range(1, max_base_candles):
        check_idx = end_idx - lookback
        if check_idx < 0:
            break
        if data['body_pct'].iloc[check_idx] <= small_threshold:
            base_count += 1
            base_start = check_idx
        else:
            break

    return (base_start, end_idx, base_count)


def find_leg_in(data: pd.DataFrame, base_start_idx: int, direction: str,
                thresholds: Dict, config: Dict) -> Optional[Tuple]:
    """
    Look backwards from base for a meaningful move in given direction.

    The leg-in is the move that brought price INTO the base zone:
    - For DBR: leg-in is BEARISH (price dropped into the base)
    - For RBD: leg-in is BULLISH (price rallied into the base)
    - For RBR: leg-in is BULLISH (continuation - price rallied, paused)
    - For DBD: leg-in is BEARISH (continuation - price dropped, paused)

    Validation:
    - At least one candle in the correct direction
    - Body size must be >= min_legin_multiplier * mean_body_pct

    Args:
        data: Prepared DataFrame
        base_start_idx: First candle index of the base
        direction: "BULLISH" or "BEARISH" (expected leg-in direction)
        thresholds: Dict from compute_thresholds()
        config: Configuration dict

    Returns:
        Tuple (avg_body_pct, candle_count) or None if no valid leg-in found
    """
    min_legin_mult = config.get('min_legin_multiplier', 0.8)
    mean_body = thresholds['mean_body_pct']
    min_legin_body_pct = mean_body * min_legin_mult
    max_legin_candles = config.get('max_leg_in_candles', 3)

    # Start looking just before the base
    legin_start_idx = base_start_idx - 1
    if legin_start_idx < 0:
        return None

    # First candle before base must be in expected direction
    first_candle = data.iloc[legin_start_idx]

    if direction == "BULLISH" and not first_candle['is_bullish']:
        return None
    if direction == "BEARISH" and not first_candle['is_bearish']:
        return None

    # Must meet minimum body size
    if first_candle['body_pct'] < min_legin_body_pct:
        return None

    candle_count = 1
    body_pcts = [float(first_candle['body_pct'])]

    # Look for additional consecutive leg-in candles
    for lookback in range(1, max_legin_candles):
        check_idx = legin_start_idx - lookback
        if check_idx < 0:
            break
        row = data.iloc[check_idx]
        is_valid = False
        if direction == "BULLISH" and row['is_bullish'] and row['body_pct'] >= min_legin_body_pct:
            is_valid = True
        elif direction == "BEARISH" and row['is_bearish'] and row['body_pct'] >= min_legin_body_pct:
            is_valid = True

        if is_valid:
            candle_count += 1
            body_pcts.append(float(row['body_pct']))
        else:
            break

    avg_body_pct = sum(body_pcts) / len(body_pcts)
    return (avg_body_pct, candle_count)


def classify_pattern(leg_in_direction: str, leg_out_direction: str) -> Tuple[str, str]:
    """
    Determine pattern type and zone type based on leg directions.

    Pattern classification:
    - Bearish leg-in + Bullish leg-out -> ("DEMAND", "DBR") - Drop-Base-Rally
    - Bullish leg-in + Bearish leg-out -> ("SUPPLY", "RBD") - Rally-Base-Drop
    - Bullish leg-in + Bullish leg-out -> ("DEMAND", "RBR") - Rally-Base-Rally
    - Bearish leg-in + Bearish leg-out -> ("SUPPLY", "DBD") - Drop-Base-Drop

    Args:
        leg_in_direction: "BULLISH" or "BEARISH"
        leg_out_direction: "BULLISH" or "BEARISH"

    Returns:
        Tuple of (zone_type, pattern_name)
    """
    if leg_in_direction == "BEARISH" and leg_out_direction == "BULLISH":
        return ("DEMAND", "DBR")
    elif leg_in_direction == "BULLISH" and leg_out_direction == "BEARISH":
        return ("SUPPLY", "RBD")
    elif leg_in_direction == "BULLISH" and leg_out_direction == "BULLISH":
        return ("DEMAND", "RBR")
    elif leg_in_direction == "BEARISH" and leg_out_direction == "BEARISH":
        return ("SUPPLY", "DBD")
    else:
        return ("UNKNOWN", "UNKNOWN")
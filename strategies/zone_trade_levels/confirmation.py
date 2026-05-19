"""
Entry confirmation candle patterns (Method 2).
Detects reversal patterns inside a zone before entering.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class ConfirmationSignal:
    pattern: str        # e.g. "BULLISH_ENGULFING", "HAMMER", "NONE"
    strength: int       # 1–5
    confirmed: bool
    entry_price: float  # Close of confirmation candle
    candle_index: int   # Index in dataframe


# ---------------------------------------------------------------------------
# Single-candle patterns
# ---------------------------------------------------------------------------

def is_bullish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    prev_bearish = prev['close'] < prev['open']
    curr_bullish = curr['close'] > curr['open']
    curr_lo = min(curr['open'], curr['close'])
    curr_hi = max(curr['open'], curr['close'])
    prev_lo = min(prev['open'], prev['close'])
    prev_hi = max(prev['open'], prev['close'])
    engulfs = curr_lo <= prev_lo and curr_hi >= prev_hi
    return prev_bearish and curr_bullish and engulfs


def is_hammer(candle: pd.Series, min_wick_ratio: float = 2.0) -> bool:
    body = abs(candle['close'] - candle['open'])
    lower_wick = min(candle['open'], candle['close']) - candle['low']
    candle_range = candle['high'] - candle['low']
    if body == 0 or candle_range == 0:
        return False
    midpoint = (candle['high'] + candle['low']) / 2
    return lower_wick >= min_wick_ratio * body and candle['close'] > midpoint


def is_bearish_engulfing(prev: pd.Series, curr: pd.Series) -> bool:
    prev_bullish = prev['close'] > prev['open']
    curr_bearish = curr['close'] < curr['open']
    curr_lo = min(curr['open'], curr['close'])
    curr_hi = max(curr['open'], curr['close'])
    prev_lo = min(prev['open'], prev['close'])
    prev_hi = max(prev['open'], prev['close'])
    engulfs = curr_lo <= prev_lo and curr_hi >= prev_hi
    return prev_bullish and curr_bearish and engulfs


def is_shooting_star(candle: pd.Series, min_wick_ratio: float = 2.0) -> bool:
    body = abs(candle['close'] - candle['open'])
    upper_wick = candle['high'] - max(candle['open'], candle['close'])
    candle_range = candle['high'] - candle['low']
    if body == 0 or candle_range == 0:
        return False
    midpoint = (candle['high'] + candle['low']) / 2
    return upper_wick >= min_wick_ratio * body and candle['close'] < midpoint


# ---------------------------------------------------------------------------
# Three-candle patterns (require at least 3 rows)
# ---------------------------------------------------------------------------

def is_morning_star(candles: pd.DataFrame) -> bool:
    if len(candles) < 3:
        return False
    c0, c1, c2 = candles.iloc[-3], candles.iloc[-2], candles.iloc[-1]
    body0 = abs(c0['close'] - c0['open'])
    body1 = abs(c1['close'] - c1['open'])
    body2 = abs(c2['close'] - c2['open'])
    avg_body = (body0 + body2) / 2
    c0_bearish = c0['close'] < c0['open']
    c2_bullish = c2['close'] > c2['open']
    small_middle = body1 < 0.5 * avg_body if avg_body > 0 else False
    c0_midpoint = (c0['open'] + c0['close']) / 2
    closes_above_mid = c2['close'] > c0_midpoint
    return c0_bearish and c2_bullish and small_middle and closes_above_mid


def is_evening_star(candles: pd.DataFrame) -> bool:
    if len(candles) < 3:
        return False
    c0, c1, c2 = candles.iloc[-3], candles.iloc[-2], candles.iloc[-1]
    body0 = abs(c0['close'] - c0['open'])
    body1 = abs(c1['close'] - c1['open'])
    body2 = abs(c2['close'] - c2['open'])
    avg_body = (body0 + body2) / 2
    c0_bullish = c0['close'] > c0['open']
    c2_bearish = c2['close'] < c2['open']
    small_middle = body1 < 0.5 * avg_body if avg_body > 0 else False
    c0_midpoint = (c0['open'] + c0['close']) / 2
    closes_below_mid = c2['close'] < c0_midpoint
    return c0_bullish and c2_bearish and small_middle and closes_below_mid


# ---------------------------------------------------------------------------
# Zone confirmation detectors
# ---------------------------------------------------------------------------

def detect_demand_confirmation(
    data: pd.DataFrame,
    zone_top: float,
    zone_bottom: float,
    config: dict,
) -> ConfirmationSignal:
    """Scan last 3 candles for bullish confirmation inside a demand zone."""
    min_wick = config.get('min_hammer_wick_ratio', 2.0)
    allow_3c = config.get('allow_morning_star', True)
    min_strength = config.get('min_confirmation_strength', 3)

    if len(data) < 2:
        return ConfirmationSignal("NONE", 0, False, 0.0, -1)

    curr = data.iloc[-1]
    prev = data.iloc[-2]

    # Price must be at or inside zone
    if curr['low'] > zone_top:
        return ConfirmationSignal("NONE", 0, False, 0.0, len(data) - 1)

    best_pattern, best_strength = "NONE", 0

    if is_bullish_engulfing(prev, curr):
        best_pattern, best_strength = "BULLISH_ENGULFING", 5
    elif is_hammer(curr, min_wick):
        best_pattern, best_strength = "HAMMER", 5
    elif allow_3c and len(data) >= 3 and is_morning_star(data):
        best_pattern, best_strength = "MORNING_STAR", 4
    elif curr['close'] > curr['open'] and curr['close'] > zone_top:
        best_pattern, best_strength = "BULLISH_CLOSE", 3

    confirmed = best_strength >= min_strength
    return ConfirmationSignal(
        pattern=best_pattern,
        strength=best_strength,
        confirmed=confirmed,
        entry_price=round(float(curr['close']), 2),
        candle_index=len(data) - 1,
    )


def detect_supply_confirmation(
    data: pd.DataFrame,
    zone_top: float,
    zone_bottom: float,
    config: dict,
) -> ConfirmationSignal:
    """Scan last 3 candles for bearish confirmation inside a supply zone."""
    min_wick = config.get('min_hammer_wick_ratio', 2.0)
    allow_3c = config.get('allow_morning_star', True)
    min_strength = config.get('min_confirmation_strength', 3)

    if len(data) < 2:
        return ConfirmationSignal("NONE", 0, False, 0.0, -1)

    curr = data.iloc[-1]
    prev = data.iloc[-2]

    # Price must be at or inside zone
    if curr['high'] < zone_bottom:
        return ConfirmationSignal("NONE", 0, False, 0.0, len(data) - 1)

    best_pattern, best_strength = "NONE", 0

    if is_bearish_engulfing(prev, curr):
        best_pattern, best_strength = "BEARISH_ENGULFING", 5
    elif is_shooting_star(curr, min_wick):
        best_pattern, best_strength = "SHOOTING_STAR", 5
    elif allow_3c and len(data) >= 3 and is_evening_star(data):
        best_pattern, best_strength = "EVENING_STAR", 4
    elif curr['close'] < curr['open'] and curr['close'] < zone_bottom:
        best_pattern, best_strength = "BEARISH_CLOSE", 3

    confirmed = best_strength >= min_strength
    return ConfirmationSignal(
        pattern=best_pattern,
        strength=best_strength,
        confirmed=confirmed,
        entry_price=round(float(curr['close']), 2),
        candle_index=len(data) - 1,
    )

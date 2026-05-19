"""
Trend detection using market structure (HH/HL/LH/LL) + EMA confirmation.

Higher timeframe (1H) trend determines whether we look for demand or supply zones.
"""
import pandas as pd
from typing import List, Tuple


def find_swing_highs(data: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
    """
    Find local maxima (swing highs).

    A swing high is a bar whose high is the highest within `window` bars on each side.

    Args:
        data: DataFrame with 'high' column
        window: Number of bars on each side to compare

    Returns:
        List of (index_position, price) tuples sorted by position
    """
    if data is None or len(data) < (2 * window + 1):
        return []

    highs = data['high'].values
    swing_highs = []

    for i in range(window, len(highs) - window):
        is_swing = True
        for j in range(1, window + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing = False
                break
        if is_swing:
            swing_highs.append((i, float(highs[i])))

    return swing_highs


def find_swing_lows(data: pd.DataFrame, window: int = 5) -> List[Tuple[int, float]]:
    """
    Find local minima (swing lows).

    A swing low is a bar whose low is the lowest within `window` bars on each side.

    Args:
        data: DataFrame with 'low' column
        window: Number of bars on each side to compare

    Returns:
        List of (index_position, price) tuples sorted by position
    """
    if data is None or len(data) < (2 * window + 1):
        return []

    lows = data['low'].values
    swing_lows = []

    for i in range(window, len(lows) - window):
        is_swing = True
        for j in range(1, window + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing = False
                break
        if is_swing:
            swing_lows.append((i, float(lows[i])))

    return swing_lows


def get_ema_bias(data: pd.DataFrame, fast_period: int = 20,
                 slow_period: int = 50) -> str:
    """
    Determine EMA-based bias using fast/slow EMA crossover + price position.

    Args:
        data: DataFrame with 'close' column
        fast_period: Fast EMA period (default 20)
        slow_period: Slow EMA period (default 50)

    Returns:
        "UP" if EMA20 > EMA50 and price above EMA20
        "DOWN" if EMA20 < EMA50 and price below EMA20
        "SIDEWAYS" otherwise
    """
    if data is None or len(data) < slow_period:
        return "SIDEWAYS"

    close = data['close']
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()

    current_price = float(close.iloc[-1])
    current_ema_fast = float(ema_fast.iloc[-1])
    current_ema_slow = float(ema_slow.iloc[-1])

    if current_ema_fast > current_ema_slow and current_price > current_ema_fast:
        return "UP"
    elif current_ema_fast < current_ema_slow and current_price < current_ema_fast:
        return "DOWN"
    else:
        return "SIDEWAYS"


def _classify_structure(swing_highs: List[Tuple[int, float]],
                        swing_lows: List[Tuple[int, float]],
                        min_swings: int = 2) -> str:
    """
    Classify market structure from swing points.

    HH + HL = UPTREND structure
    LH + LL = DOWNTREND structure
    Mixed = SIDEWAYS
    """
    if len(swing_highs) < min_swings or len(swing_lows) < min_swings:
        return "SIDEWAYS"

    # Take last few swings for analysis
    recent_highs = swing_highs[-min_swings:]
    recent_lows = swing_lows[-min_swings:]

    # Check for Higher Highs
    higher_highs = all(
        recent_highs[i][1] > recent_highs[i - 1][1]
        for i in range(1, len(recent_highs))
    )
    # Check for Higher Lows
    higher_lows = all(
        recent_lows[i][1] > recent_lows[i - 1][1]
        for i in range(1, len(recent_lows))
    )
    # Check for Lower Highs
    lower_highs = all(
        recent_highs[i][1] < recent_highs[i - 1][1]
        for i in range(1, len(recent_highs))
    )
    # Check for Lower Lows
    lower_lows = all(
        recent_lows[i][1] < recent_lows[i - 1][1]
        for i in range(1, len(recent_lows))
    )

    if higher_highs and higher_lows:
        return "UP"
    elif lower_highs and lower_lows:
        return "DOWN"
    else:
        return "SIDEWAYS"


def detect_trend(data: pd.DataFrame, lookback: int = 50,
                 swing_window: int = 5) -> str:
    """
    Combine market structure (HH/HL/LH/LL) with EMA bias for robust trend detection.

    UPTREND: Higher Highs + Higher Lows + EMA bullish
    DOWNTREND: Lower Highs + Lower Lows + EMA bearish
    SIDEWAYS: Mixed signals or disagreement between structure and EMA

    Args:
        data: DataFrame with OHLC data (needs 'high', 'low', 'close')
        lookback: Number of bars to analyze for structure
        swing_window: Window for swing point detection

    Returns:
        "UP", "DOWN", or "SIDEWAYS"
    """
    if data is None or len(data) < lookback:
        return "SIDEWAYS"

    # Use the last `lookback` bars for structure analysis
    recent_data = data.iloc[-lookback:].reset_index(drop=True)

    # Find structure
    swing_highs = find_swing_highs(recent_data, window=swing_window)
    swing_lows = find_swing_lows(recent_data, window=swing_window)

    structure = _classify_structure(swing_highs, swing_lows)
    ema_bias = get_ema_bias(data)  # Use full data for EMA calculation

    # Agreement = strong signal; disagreement = sideways
    if structure == "UP" and ema_bias == "UP":
        return "UP"
    elif structure == "DOWN" and ema_bias == "DOWN":
        return "DOWN"
    elif structure == "UP" and ema_bias == "SIDEWAYS":
        return "UP"  # Structure leads, EMA catching up
    elif structure == "DOWN" and ema_bias == "SIDEWAYS":
        return "DOWN"  # Structure leads, EMA catching up
    else:
        return "SIDEWAYS"
"""
Zone Detection - Data Preparation & Threshold Computation.

Step 1: Prepare candle data with computed columns.
Step 2: Compute adaptive thresholds for large/small candle classification.
"""

import pandas as pd
import numpy as np
from typing import Dict


def prepare_candle_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Add computed columns to OHLCV dataframe for zone detection.

    Computed columns:
    - body: absolute body size |Close - Open|
    - body_pct: body as % of close price (body/close * 100)
    - candle_range: High - Low (total range of candle)
    - body_ratio: body / candle_range (0-1, how much is body vs wicks)
    - is_bullish: True if Close > Open
    - is_bearish: True if Close < Open
    - volume_sma20: 20-period simple moving average of volume
    - volume_ratio: Volume / volume_sma20 (> 1 means above average)

    Args:
        data: DataFrame with Open, High, Low, Close, Volume columns

    Returns:
        DataFrame with additional computed columns
    """
    df = data.copy()

    # Body calculations
    df['body'] = (df['Close'] - df['Open']).abs()
    df['body_pct'] = (df['body'] / df['Close']) * 100

    # Range and body ratio
    df['candle_range'] = df['High'] - df['Low']
    df['body_ratio'] = np.where(
        df['candle_range'] > 0,
        df['body'] / df['candle_range'],
        0.0
    )

    # Direction
    df['is_bullish'] = df['Close'] > df['Open']
    df['is_bearish'] = df['Close'] < df['Open']

    # Volume analysis
    if 'Volume' in df.columns and df['Volume'].sum() > 0:
        df['volume_sma20'] = df['Volume'].rolling(window=20, min_periods=5).mean()
        df['volume_ratio'] = np.where(
            df['volume_sma20'] > 0,
            df['Volume'] / df['volume_sma20'],
            1.0
        )
    else:
        df['volume_sma20'] = 1.0
        df['volume_ratio'] = 1.0

    return df


def compute_thresholds(data: pd.DataFrame, config: Dict) -> Dict:
    """
    Compute adaptive thresholds based on recent price data.

    These thresholds determine what counts as a "large" candle (potential leg-out)
    and what counts as a "small" candle (potential base).

    Method:
    - Large candle: body_pct >= mean + N*std (configurable N via large_candle_std_mult)
    - Small candle: body_pct <= mean (below average body size)

    Args:
        data: Prepared DataFrame with body_pct column
        config: Configuration dict

    Returns:
        Dict with:
        - large_candle_threshold: minimum body_pct to qualify as a leg-out
        - small_candle_threshold: maximum body_pct to qualify as a base candle
        - mean_body_pct: mean body percentage for reference
    """
    body_pcts = data['body_pct'].dropna()

    if len(body_pcts) < 10:
        # Fallback for insufficient data
        return {
            'large_candle_threshold': 0.5,
            'small_candle_threshold': 0.3,
            'mean_body_pct': 0.3,
        }

    mean_body = float(body_pcts.mean())
    std_body = float(body_pcts.std())
    std_mult = config.get('large_candle_std_mult', 1.5)

    # Large candle = mean + N * std
    large_threshold = mean_body + std_mult * std_body

    # Small candle = below mean (these form bases)
    small_threshold = mean_body

    # Safety floors to prevent degenerate thresholds
    large_threshold = max(large_threshold, 0.2)
    small_threshold = max(small_threshold, 0.05)

    return {
        'large_candle_threshold': large_threshold,
        'small_candle_threshold': small_threshold,
        'mean_body_pct': mean_body,
    }
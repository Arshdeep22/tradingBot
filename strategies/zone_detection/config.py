"""
Zone Detection Configuration - Default parameters for zone detection.
"""

from typing import Dict

DEFAULT_CONFIG: Dict = {
    'max_base_candles': 3,          # Max base candles (professional: 3)
    'min_body_ratio': 0.60,         # Leg-out must have body >= 60% of range
    'min_volume_ratio': 1.5,        # Leg-out volume >= 1.5x average
    'min_legin_multiplier': 0.8,    # Leg-in body must be >= 0.8x average body
    'large_candle_std_mult': 1.5,   # Std dev multiplier for large candle threshold
    'detect_dbr': True,             # Enable Drop-Base-Rally
    'detect_rbd': True,             # Enable Rally-Base-Drop
    'detect_rbr': True,             # Enable Rally-Base-Rally
    'detect_dbd': True,             # Enable Drop-Base-Drop
    'max_leg_out_candles': 5,       # Max consecutive leg-out candles to count
    'max_leg_in_candles': 3,        # Max candles to look back for leg-in
    'min_data_length': 30,          # Minimum candles required for analysis
    'lookback_window': None,        # If set, only scan last N candles
}
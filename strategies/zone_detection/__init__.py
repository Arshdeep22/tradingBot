"""
Zone Detection Package - Professional-grade supply/demand zone detection.

This package provides the complete zone detection algorithm that:
1. Scans for LARGE candles (leg-outs) first
2. Looks BACKWARDS for the base (small candles)
3. Looks BACKWARDS past the base for the leg-in
4. Classifies the pattern (DBR/RBD/RBR/DBD)
5. Creates Zone objects with full quality metrics
6. Checks freshness using strict wick-based rules

Usage:
    from strategies.zone_detection import detect_zones, check_freshness, DEFAULT_CONFIG

    zones = detect_zones(ohlcv_dataframe, config=DEFAULT_CONFIG)
    fresh_zones = check_freshness(zones, ohlcv_dataframe)
"""

from strategies.zone_detection.config import DEFAULT_CONFIG
from strategies.zone_detection.preparation import prepare_candle_data, compute_thresholds
from strategies.zone_detection.components import (
    find_leg_out_candles,
    find_base,
    find_leg_in,
    classify_pattern,
)
from strategies.zone_detection.detector import detect_zones
from strategies.zone_detection.freshness import check_freshness

# Legacy compatibility (for old zone_scanner.py - will be removed in Plan 6)
from strategies.zone_detection.legacy_compat import (
    detect_demand_zone,
    detect_supply_zone,
)

__all__ = [
    'DEFAULT_CONFIG',
    'prepare_candle_data',
    'compute_thresholds',
    'find_leg_out_candles',
    'find_base',
    'find_leg_in',
    'classify_pattern',
    'detect_zones',
    'check_freshness',
    # Legacy
    'detect_demand_zone',
    'detect_supply_zone',
]
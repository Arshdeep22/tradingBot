"""
Zone Multi-Timeframe Package — Professional 3-timeframe system.

Higher TF (1H): Trend detection using market structure + EMA
Trading TF (15m): Zone detection, freshness, filtering, scoring
Entry TF (5m): Arrival quality refinement, freshness cross-check

Usage:
    from strategies.zone_mtf import multi_timeframe_analysis, detect_trend

    zones = multi_timeframe_analysis(data_1h, data_15m, data_5m, config)
"""

from strategies.zone_mtf.trend import (
    detect_trend,
    find_swing_highs,
    find_swing_lows,
    get_ema_bias,
)
from strategies.zone_mtf.confluence import find_zone_confluence
from strategies.zone_mtf.entry_refinement import (
    assess_arrival_on_entry_tf,
    check_freshness_on_entry_tf,
)
from strategies.zone_mtf.orchestrator import (
    multi_timeframe_analysis,
    apply_trend_filter,
    DEFAULT_MTF_CONFIG,
)
from strategies.zone_mtf.legacy_compat import multi_timeframe_confirm

__all__ = [
    # Trend
    'detect_trend',
    'find_swing_highs',
    'find_swing_lows',
    'get_ema_bias',
    # Confluence
    'find_zone_confluence',
    # Entry refinement
    'assess_arrival_on_entry_tf',
    'check_freshness_on_entry_tf',
    # Orchestrator
    'multi_timeframe_analysis',
    'apply_trend_filter',
    'DEFAULT_MTF_CONFIG',
    # Legacy compatibility
    'multi_timeframe_confirm',
]
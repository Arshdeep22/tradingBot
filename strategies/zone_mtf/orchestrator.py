"""
MTF Orchestrator — Main multi-timeframe analysis pipeline.

Ties together all 3 timeframes:
1. Higher TF (1H) → Trend direction
2. Trading TF (15m) → Zone detection, freshness, filtering, scoring
3. Entry TF (5m) → Arrival refinement, freshness cross-check

This is the primary entry point for multi-timeframe zone analysis.
"""
import pandas as pd
from typing import List, Optional

from strategies.zone_models import Zone
from strategies.zone_detection import detect_zones, check_freshness
from strategies.zone_filters import apply_all_filters as filter_zones
from strategies.zone_scoring import score_zones
from strategies.zone_mtf.trend import detect_trend
from strategies.zone_mtf.confluence import find_zone_confluence
from strategies.zone_mtf.entry_refinement import (
    assess_arrival_on_entry_tf,
    check_freshness_on_entry_tf,
    check_confirmation_on_entry_tf,
)


# Default MTF configuration
DEFAULT_MTF_CONFIG = {
    'trend_tf': '1h',
    'zone_tf': '15m',
    'entry_tf': '5m',
    'trend_lookback': 50,
    'strict_trend_filter': False,
    'check_confluence': True,
}


def apply_trend_filter(zones: List[Zone], trend: str,
                       strict: bool = False) -> List[Zone]:
    """
    Optionally reject counter-trend zones.

    strict=True: Only with-trend zones allowed (demand in UP, supply in DOWN).
    strict=False: Let scoring handle it (counter-trend gets lower rank but not removed).

    Args:
        zones: List of zones to filter
        trend: Detected trend — "UP", "DOWN", or "SIDEWAYS"
        strict: If True, remove counter-trend zones entirely

    Returns:
        Filtered list of zones
    """
    if not strict or trend == "SIDEWAYS":
        return zones

    filtered = []
    for zone in zones:
        if trend == "UP" and zone.zone_type == "SUPPLY":
            continue  # Reject supply in uptrend (counter-trend)
        if trend == "DOWN" and zone.zone_type == "DEMAND":
            continue  # Reject demand in downtrend (counter-trend)
        filtered.append(zone)

    return filtered


def multi_timeframe_analysis(
    data_higher: Optional[pd.DataFrame],
    data_trading: Optional[pd.DataFrame],
    data_entry: Optional[pd.DataFrame],
    config: Optional[dict] = None,
) -> List[Zone]:
    """
    Full multi-timeframe analysis pipeline.

    Steps:
    1. Use higher-TF data (1H) → determine trend
    2. Use trading-TF data (15m) → detect zones, check freshness, filter, score
    3. Check zone confluence with higher-TF zones (optional)
    4. Use entry-TF data (5m) → refine arrival, cross-check freshness
    5. Apply trend filter (reject counter-trend if strict)
    6. Re-sort by final score

    Args:
        data_higher: 1H OHLC DataFrame (for trend + confluence)
        data_trading: 15m OHLC DataFrame (for zone detection)
        data_entry: 5m OHLC DataFrame (for entry refinement)
        config: Configuration dict (see DEFAULT_MTF_CONFIG)

    Returns:
        List of qualified zones sorted by score (best first)
    """
    cfg = {**DEFAULT_MTF_CONFIG, **(config or {})}

    # ─── Step 1: Determine trend from higher TF ──────────────────────
    trend = "SIDEWAYS"
    if data_higher is not None and not data_higher.empty:
        trend = detect_trend(data_higher, lookback=cfg['trend_lookback'])

    # Map trend to scoring format
    trend_for_scoring = {
        "UP": "UPTREND",
        "DOWN": "DOWNTREND",
        "SIDEWAYS": "SIDEWAYS",
    }.get(trend, "SIDEWAYS")

    # ─── Step 2: Detect zones on trading TF ──────────────────────────
    if data_trading is None or data_trading.empty:
        return []

    zones = detect_zones(data_trading, cfg)
    if not zones:
        return []

    # Check freshness
    zones = check_freshness(zones, data_trading)
    if not zones:
        return []

    # Apply basic filters
    zones = filter_zones(zones, data_trading, cfg)
    if not zones:
        return []

    # Score zones (with trend info)
    zones = score_zones(zones, data_trading, trend_for_scoring)

    # ─── Step 3: Check confluence with higher TF ─────────────────────
    if cfg.get('check_confluence', True) and data_higher is not None:
        zones = find_zone_confluence(zones, data_higher, cfg)

    # ─── Step 4: Entry TF refinement ─────────────────────────────────
    if data_entry is not None and not data_entry.empty:
        for zone in zones:
            # Refine arrival score using 5m data
            refined_arrival = assess_arrival_on_entry_tf(zone, data_entry)
            zone.arrival_score = refined_arrival

            # Cross-check freshness on 5m
            fresh_on_5m = check_freshness_on_entry_tf(zone, data_entry)
            if not fresh_on_5m:
                zone.is_fresh = False
                zone.freshness_score = 0

            # Recalculate total score after refinement
            zone.score = (
                zone.departure_score
                + zone.base_score
                + zone.freshness_score
                + zone.arrival_score
                + zone.time_score
                + zone.trend_score
            )

            # Check for confirmation candle pattern (only when price is near zone edge)
            if cfg.get("check_confirmation", True):
                zone = check_confirmation_on_entry_tf(zone, data_entry, cfg)

    # ─── Step 5: Apply trend filter ──────────────────────────────────
    strict = cfg.get('strict_trend_filter', False)
    zones = apply_trend_filter(zones, trend, strict=strict)

    # ─── Step 6: Re-sort by final score ──────────────────────────────
    zones.sort(key=lambda z: z.score, reverse=True)

    return zones
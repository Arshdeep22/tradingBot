"""
Zone confluence detection: Check if trading-TF zones overlap with higher-TF zones.

A+ Setup: A 15m zone sitting inside a 1H zone = maximum institutional support.
"""
import pandas as pd
from typing import List, Optional

from strategies.zone_models import Zone
from strategies.zone_detection import detect_zones


def _zones_overlap(zone_lower: Zone, zone_higher: Zone) -> bool:
    """
    Check if a lower-TF zone sits within (overlaps) a higher-TF zone.

    Overlap means the lower zone's price range intersects the higher zone's range.
    """
    # Normalize: get top and bottom for each zone
    lower_top = max(zone_lower.zone_top, zone_lower.zone_bottom)
    lower_bottom = min(zone_lower.zone_top, zone_lower.zone_bottom)
    higher_top = max(zone_higher.zone_top, zone_higher.zone_bottom)
    higher_bottom = min(zone_higher.zone_top, zone_higher.zone_bottom)

    # Overlap: lower zone must intersect higher zone
    return lower_bottom <= higher_top and lower_top >= higher_bottom


def _same_type(zone_lower: Zone, zone_higher: Zone) -> bool:
    """Check if both zones are the same type (both demand or both supply)."""
    return zone_lower.zone_type == zone_higher.zone_type


def find_zone_confluence(zones_trading: List[Zone], data_higher: pd.DataFrame,
                         config: Optional[dict] = None) -> List[Zone]:
    """
    Check if trading-TF zones (e.g., 15m) overlap with higher-TF zones (e.g., 1H).

    Zones with confluence get annotated with bonus information in their reasoning.
    This is an A+ setup indicator — zone within a zone = maximum institutional support.

    Args:
        zones_trading: List of zones from trading timeframe (15m)
        data_higher: OHLC DataFrame from higher timeframe (1H)
        config: Optional configuration dict

    Returns:
        Same list of zones with confluence annotation added
    """
    if not zones_trading or data_higher is None or data_higher.empty:
        return zones_trading

    cfg = config or {}

    # Detect zones on the higher timeframe
    higher_tf_config = {
        'min_body_pct': cfg.get('htf_min_body_pct', 0.5),
        'max_wick_ratio': cfg.get('htf_max_wick_ratio', 0.4),
        'min_move_pct': cfg.get('htf_min_move_pct', 0.3),
        'lookback': cfg.get('htf_lookback', 100),
    }

    try:
        zones_higher = detect_zones(data_higher, higher_tf_config)
    except Exception:
        # If detection fails, return zones unchanged
        return zones_trading

    if not zones_higher:
        return zones_trading

    # Check each trading-TF zone against higher-TF zones
    for zone in zones_trading:
        confluence_found = False
        confluence_zone = None

        for hz in zones_higher:
            # Only match same type (demand with demand, supply with supply)
            if _same_type(zone, hz) and _zones_overlap(zone, hz):
                confluence_found = True
                confluence_zone = hz
                break

        # Annotate zone with confluence info
        if confluence_found:
            confluence_note = (
                f"\n• HTF CONFLUENCE: {zone.zone_type} zone overlaps with "
                f"1H {confluence_zone.zone_type} zone "
                f"[{confluence_zone.zone_bottom:.2f}-{confluence_zone.zone_top:.2f}]"
                f"\n• A+ SETUP: Zone within a zone = maximum institutional support"
            )
            zone.reasoning = (zone.reasoning or "") + confluence_note

    return zones_trading
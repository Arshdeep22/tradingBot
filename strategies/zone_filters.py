"""
Zone quality filters for supply/demand zones.

Individual filter functions reject zones that don't meet quality criteria.
The apply_all_filters() orchestrator chains all filters together.
"""

from typing import List

import pandas as pd

from strategies.zone_models import Zone


# --- Default filter configuration ---
DEFAULT_FILTER_CONFIG = {
    "max_zone_width_pct": 1.5,
    "min_zone_width_pct": 0.1,
    "max_distance_from_cmp": 3.0,
    "min_body_ratio": 0.60,
    "overlap_threshold_pct": 1.0,
    "max_sl_pct": 1.5,
}


def filter_zone_width(zone: Zone, max_pct: float = 1.5, min_pct: float = 0.1) -> bool:
    """
    Reject zones that are too wide or too narrow.

    Width is measured as (zone_top - zone_bottom) / midpoint * 100.

    Returns:
        True if zone passes (acceptable width), False if rejected.
    """
    midpoint = (zone.zone_top + zone.zone_bottom) / 2.0
    if midpoint <= 0:
        return False
    width_pct = (zone.zone_top - zone.zone_bottom) / midpoint * 100.0
    return min_pct <= width_pct <= max_pct


def filter_distance_from_price(
    zone: Zone, current_price: float, max_distance_pct: float = 3.0
) -> bool:
    """
    Reject zones that are too far from current market price.

    Distance is measured from zone midpoint to current price.

    Returns:
        True if zone passes (within distance), False if rejected.
    """
    if current_price <= 0:
        return False
    zone_mid = (zone.zone_top + zone.zone_bottom) / 2.0
    distance_pct = abs(current_price - zone_mid) / current_price * 100.0
    return distance_pct <= max_distance_pct


def filter_sl_cap(
    zone: Zone, entry: float, stop_loss: float, max_sl_pct: float = 1.5
) -> bool:
    """
    Reject zones where the stop-loss distance exceeds the maximum allowed.

    Returns:
        True if zone passes (SL within cap), False if rejected.
    """
    if entry <= 0:
        return False
    sl_distance_pct = abs(entry - stop_loss) / entry * 100.0
    return sl_distance_pct <= max_sl_pct


def filter_freshness(zone: Zone) -> bool:
    """
    Reject zones that are not fresh.

    Returns:
        True if zone is fresh, False if tested/stale.
    """
    return zone.is_fresh


def filter_minimum_leg_out(zone: Zone, min_body_ratio: float = 0.60) -> bool:
    """
    Reject zones with weak leg-out candles (insufficient body ratio).

    Body ratio = body_size / total_range for the leg-out candle.
    A strong move away from the zone should have mostly body, little wick.

    Returns:
        True if zone passes (strong leg-out), False if rejected.
    """
    if zone.leg_out_body_ratio is None:
        # If not computed, allow through (backwards compatibility)
        return True
    return zone.leg_out_body_ratio >= min_body_ratio


def filter_minimum_legout_volume(
    zones: List[Zone],
    min_volume_ratio: float = 1.5,
) -> List[Zone]:
    """
    Reject zones where leg-out occurred on below-average volume.

    Volume > 1.5x average is a guide prerequisite for institutional zone validity.
    Zones with volume_ratio == 1.0 exactly are treated as "no data" (preparation.py
    sets this as the default when Volume is absent) and are passed through.
    """
    result = []
    for zone in zones:
        vol = zone.leg_out_volume_ratio
        if vol == 1.0 or vol >= min_volume_ratio:
            result.append(zone)
    return result


def filter_overlapping_zones(
    zones: List[Zone], overlap_threshold_pct: float = 1.0
) -> List[Zone]:
    """
    Remove overlapping zones, keeping the fresher/newer one.

    Two zones overlap if the overlap region is > overlap_threshold_pct
    of the smaller zone's width.

    Returns:
        List of non-overlapping zones (newer zones preferred).
    """
    if not zones:
        return []

    # Sort by formation index (newer first) so we keep newer zones
    sorted_zones = sorted(zones, key=lambda z: z.formed_at_index, reverse=True)
    result: List[Zone] = []

    for candidate in sorted_zones:
        is_overlapping = False
        for existing in result:
            # Only compare zones of the same type
            if candidate.zone_type != existing.zone_type:
                continue

            # Calculate overlap
            overlap_top = min(candidate.zone_top, existing.zone_top)
            overlap_bottom = max(candidate.zone_bottom, existing.zone_bottom)
            overlap_size = max(0, overlap_top - overlap_bottom)

            # Compare to smaller zone's width
            candidate_width = candidate.zone_top - candidate.zone_bottom
            existing_width = existing.zone_top - existing.zone_bottom
            smaller_width = min(candidate_width, existing_width)

            if smaller_width > 0:
                overlap_pct = (overlap_size / smaller_width) * 100.0
                if overlap_pct > overlap_threshold_pct:
                    is_overlapping = True
                    break

        if not is_overlapping:
            result.append(candidate)

    # Return in original order (by formed_at_index ascending)
    return sorted(result, key=lambda z: z.formed_at_index)


def apply_all_filters(
    zones: List[Zone], data: pd.DataFrame, config: dict = None
) -> List[Zone]:
    """
    Apply all filters in sequence. Returns only zones passing ALL filters.

    Args:
        zones: List of Zone objects (should already have freshness checked)
        data: OHLC DataFrame for context (used for current price)
        config: Filter configuration dict (uses DEFAULT_FILTER_CONFIG if None)

    Returns:
        List of zones that pass all quality filters.
    """
    if not zones:
        return []

    cfg = {**DEFAULT_FILTER_CONFIG, **(config or {})}

    # Get current price (last close)
    current_price = float(data["close"].iloc[-1]) if not data.empty else 0.0

    filtered: List[Zone] = []

    for zone in zones:
        # Filter 1: Zone width
        if not filter_zone_width(
            zone,
            max_pct=cfg["max_zone_width_pct"],
            min_pct=cfg["min_zone_width_pct"],
        ):
            continue

        # Filter 2: Distance from current price
        if not filter_distance_from_price(
            zone, current_price, max_distance_pct=cfg["max_distance_from_cmp"]
        ):
            continue

        # Filter 3: Freshness
        if not filter_freshness(zone):
            continue

        # Filter 4: Minimum leg-out quality
        if not filter_minimum_leg_out(zone, min_body_ratio=cfg["min_body_ratio"]):
            continue

        filtered.append(zone)

    # Filter 5: Leg-out volume (institutional confirmation)
    min_vol = cfg.get("min_volume_ratio", 1.5)
    filtered = filter_minimum_legout_volume(filtered, min_vol)
    if not filtered:
        return []

    # Filter 6: Remove overlapping zones
    filtered = filter_overlapping_zones(
        filtered, overlap_threshold_pct=cfg["overlap_threshold_pct"]
    )

    return filtered
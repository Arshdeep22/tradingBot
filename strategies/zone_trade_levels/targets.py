"""
Target calculation for zone trading.
Opposing zone targets, fixed R:R fallback, and partial profit levels.
"""

from typing import List, Optional
from strategies.zone_models import Zone


def find_opposing_zone_target(zone: Zone, all_zones: List[Zone]) -> Optional[float]:
    """
    Find nearest opposing zone as target.
    DEMAND: target = bottom of nearest SUPPLY zone above entry
    SUPPLY: target = top of nearest DEMAND zone below entry

    Returns target price or None if no opposing zone found.
    """
    entry = zone.zone_top if zone.zone_type == "DEMAND" else zone.zone_bottom

    if zone.zone_type == "DEMAND":
        # Look for supply zones above entry
        opposing = [
            z for z in all_zones
            if z.zone_type == "SUPPLY" and z.zone_bottom > entry
        ]
        if not opposing:
            return None
        # Nearest supply zone (lowest zone_bottom among those above)
        nearest = min(opposing, key=lambda z: z.zone_bottom)
        return round(nearest.zone_bottom, 2)
    else:
        # Look for demand zones below entry
        opposing = [
            z for z in all_zones
            if z.zone_type == "DEMAND" and z.zone_top < entry
        ]
        if not opposing:
            return None
        # Nearest demand zone (highest zone_top among those below)
        nearest = max(opposing, key=lambda z: z.zone_top)
        return round(nearest.zone_top, 2)


def calculate_rr_target(entry: float, stop_loss: float,
                        rr_ratio: float = 3.0) -> float:
    """
    Fixed R:R target as fallback.
    Target = Entry + (risk * rr_ratio) for demand (long)
    Target = Entry - (risk * rr_ratio) for supply (short)
    """
    risk = abs(entry - stop_loss)
    if entry > stop_loss:
        # Demand (long): target above entry
        return round(entry + (risk * rr_ratio), 2)
    else:
        # Supply (short): target below entry
        return round(entry - (risk * rr_ratio), 2)


def calculate_partial_target(entry: float, stop_loss: float) -> float:
    """
    Target 1 at 1:1 R:R (partial profit, move SL to breakeven).
    """
    return calculate_rr_target(entry, stop_loss, rr_ratio=1.0)


def _compute_rr_ratio(entry: float, stop_loss: float, target: float) -> float:
    """Compute reward-to-risk ratio for given levels."""
    risk = abs(entry - stop_loss)
    if risk == 0:
        return 0.0
    reward = abs(target - entry)
    return round(reward / risk, 2)


def calculate_targets(zone: Zone, all_zones: List[Zone], config: dict) -> dict:
    """
    Determine final targets with priority:
    1. Opposing zone target (if R:R >= min_rr_with_opposing)
    2. Fallback to fixed R:R (default 1:3)
    Also sets target_1 (partial at 1:1)

    Returns dict with target, target_1, rr_ratio, target_source.
    Requires zone.entry and zone.stop_loss to be set already.
    """
    entry = zone.entry
    stop_loss = zone.stop_loss

    use_opposing = config.get('use_opposing_zone_target', True)
    min_rr_opposing = config.get('min_rr_with_opposing', 2.0)
    default_rr = config.get('default_rr_ratio', 3.0)

    final_target = None
    target_source = "fixed_rr"

    # Try opposing zone target first
    if use_opposing:
        opposing_target = find_opposing_zone_target(zone, all_zones)
        if opposing_target is not None:
            rr = _compute_rr_ratio(entry, stop_loss, opposing_target)
            if rr >= min_rr_opposing:
                final_target = opposing_target
                target_source = "opposing_zone"

    # Fallback to fixed R:R
    if final_target is None:
        final_target = calculate_rr_target(entry, stop_loss, default_rr)
        target_source = "fixed_rr"

    # Partial profit target (1:1 R:R)
    target_1 = calculate_partial_target(entry, stop_loss)

    # Compute final R:R
    rr_ratio = _compute_rr_ratio(entry, stop_loss, final_target)

    return {
        'target': final_target,
        'target_1': target_1,
        'rr_ratio': rr_ratio,
        'target_source': target_source,
    }
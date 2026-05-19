"""
Main orchestrator for trade level calculations.
Brings together entry, stop loss, targets, and position sizing.
"""

from typing import List, Optional
import pandas as pd

from strategies.zone_models import Zone
from strategies.zone_trade_levels.entry_sl import (
    calculate_entry, compute_atr, calculate_stop_loss, validate_sl_distance
)
from strategies.zone_trade_levels.targets import calculate_targets
from strategies.zone_trade_levels.position_sizing import calculate_position_size


def calculate_trade_levels(zone: Zone, data: pd.DataFrame,
                           all_zones: List[Zone], config: dict) -> Optional[Zone]:
    """
    Calculate all trade levels for a zone.

    Steps:
    1. Set entry (zone edge)
    2. Compute ATR
    3. Set stop loss (ATR-based, capped)
    4. Validate SL cap (reject if still too wide)
    5. Set targets (opposing zone or fixed R:R)
    6. Calculate position size
    7. Validate minimum R:R ratio

    Returns Zone with trade levels populated, or None if invalid.
    """
    sl_atr_multiplier = config.get('sl_atr_multiplier', 1.0)
    max_sl_pct = config.get('max_sl_pct', 1.5)
    min_rr_ratio = config.get('min_rr_ratio', 2.0)
    risk_pct = config.get('risk_per_trade_pct', 1.0)
    capital = config.get('capital', 100000)

    # Step 1: Entry at zone edge
    zone.entry = calculate_entry(zone)

    # Step 2: Compute ATR from price data
    atr_value = compute_atr(data)

    # Step 3: Stop loss with ATR buffer, capped
    zone.stop_loss = calculate_stop_loss(
        zone, atr_value,
        atr_multiplier=sl_atr_multiplier,
        max_sl_pct=max_sl_pct
    )

    # Step 4: Validate SL distance (reject if too wide even after cap)
    if not validate_sl_distance(zone.entry, zone.stop_loss, max_sl_pct):
        return None

    # Step 5: Calculate targets
    target_result = calculate_targets(zone, all_zones, config)
    zone.target_1 = target_result['target_1']
    zone.target_2 = target_result['target']

    # Step 6: Validate minimum R:R ratio
    rr_ratio = target_result['rr_ratio']
    if rr_ratio < min_rr_ratio:
        return None

    # Step 7: Calculate position size
    zone.position_size = calculate_position_size(
        zone.entry, zone.stop_loss,
        capital=capital, risk_pct=risk_pct
    )

    # Reject if position size is 0 (would mean no valid trade)
    if zone.position_size <= 0:
        return None

    return zone


def calculate_trade_levels_batch(zones: List[Zone], data: pd.DataFrame,
                                  config: dict) -> List[Zone]:
    """
    Calculate trade levels for all zones, removing invalid ones.
    Uses all zones list for opposing zone target lookup.
    """
    valid_zones = []
    for zone in zones:
        result = calculate_trade_levels(zone, data, zones, config)
        if result is not None:
            valid_zones.append(result)
    return valid_zones
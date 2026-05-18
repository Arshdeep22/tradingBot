"""
Zone Scoring
------------
Scoring logic for supply and demand zones.
Handles score calculation, trade level computation, and reasoning generation.

Scoring Criteria:
- Freshness: 40 points (zone never tested)
- Leg-out Strength: 30 points (big exciting candle)
- Base Candles: 30 points (1-2 candles = max)
"""

from .zone_models import Zone


def score_zone(zone: Zone, exciting_threshold: float,
               stronger_threshold: float, strong_threshold: float) -> Zone:
    """
    Score a zone based on freshness, leg-out strength, and base tightness.
    
    Args:
        zone: Zone to score
        exciting_threshold: Body % threshold for 30-point leg-out
        stronger_threshold: Body % threshold for 20-point leg-out
        strong_threshold: Body % threshold for 10-point leg-out
    
    Returns:
        Zone with scores populated
    """
    # 1. Freshness Score (max 40)
    zone.freshness_score = 40 if zone.is_fresh else 0

    # 2. Leg-out Strength Score (max 30)
    if zone.leg_out_pct >= exciting_threshold:
        zone.legout_score = 30  # Strongest/Exciting
    elif zone.leg_out_pct >= stronger_threshold:
        zone.legout_score = 20  # Stronger
    elif zone.leg_out_pct >= strong_threshold:
        zone.legout_score = 10  # Strong
    else:
        zone.legout_score = 0  # Weak

    # 3. Base Candles Score (max 30)
    if zone.base_candles <= 2:
        zone.base_score = 30
    elif zone.base_candles <= 4:
        zone.base_score = 20
    elif zone.base_candles == 5:
        zone.base_score = 10
    else:
        zone.base_score = 0

    # Total Score
    zone.score = zone.freshness_score + zone.legout_score + zone.base_score

    return zone


def calculate_trade_levels(zone: Zone, rr_ratio: float, atr_val: float) -> Zone:
    """
    Calculate entry, stop loss, and target for a zone.
    Uses ATR-based buffer (1.5 x ATR) instead of fixed percentage
    to adapt to each stock's volatility.
    
    Args:
        zone: Zone to calculate levels for
        rr_ratio: Risk-reward ratio for target calculation
        atr_val: Current ATR value for SL buffer
    
    Returns:
        Zone with entry/stop_loss/target populated
    """
    if atr_val <= 0:
        atr_val = zone.zone_bottom * 0.004

    # Use 1.5x ATR as the buffer below/above zone
    sl_buffer = atr_val * 1.5

    if zone.zone_type == "DEMAND":
        # Buy at top of demand zone
        zone.entry = zone.zone_top
        # SL below bottom of zone with ATR-based buffer
        zone.stop_loss = round(zone.zone_bottom - sl_buffer, 2)
        # Target = Entry + rr_ratio * Risk
        risk = zone.entry - zone.stop_loss
        zone.target = round(zone.entry + (rr_ratio * risk), 2)

    elif zone.zone_type == "SUPPLY":
        # Sell at bottom of supply zone
        zone.entry = zone.zone_bottom
        # SL above top of zone with ATR-based buffer
        zone.stop_loss = round(zone.zone_top + sl_buffer, 2)
        # Target = Entry - rr_ratio * Risk
        risk = zone.stop_loss - zone.entry
        zone.target = round(zone.entry - (rr_ratio * risk), 2)

    return zone


def generate_reasoning(zone: Zone) -> Zone:
    """Generate human-readable reasoning for the zone."""

    # Leg-out description
    if zone.legout_score == 30:
        leg_desc = f"EXCITING leg-out candle ({zone.leg_out_pct:.1f}% body)"
    elif zone.legout_score == 20:
        leg_desc = f"STRONGER leg-out candle ({zone.leg_out_pct:.1f}% body)"
    else:
        leg_desc = f"STRONG leg-out candle ({zone.leg_out_pct:.1f}% body)"

    # Base description
    if zone.base_score == 30:
        base_desc = f"Very tight base ({zone.base_candles} candles)"
    elif zone.base_score == 20:
        base_desc = f"Compact base ({zone.base_candles} candles)"
    else:
        base_desc = f"Wider base ({zone.base_candles} candles)"

    # Freshness description
    fresh_desc = "FRESH zone (never tested)" if zone.is_fresh else "Zone has been tested"

    # Zone type description
    if zone.zone_type == "DEMAND":
        type_desc = "DEMAND zone (Buy opportunity)"
        action = "BUY"
    else:
        type_desc = "SUPPLY zone (Sell opportunity)"
        action = "SELL"

    # Risk/Reward
    risk = abs(zone.entry - zone.stop_loss)
    reward = abs(zone.target - zone.entry)
    rr = reward / risk if risk > 0 else 0

    zone.reasoning = (
        f"{type_desc} | Score: {zone.score}/100\n"
        f"• {fresh_desc} (+{zone.freshness_score} pts)\n"
        f"• {leg_desc} (+{zone.legout_score} pts)\n"
        f"• {base_desc} (+{zone.base_score} pts)\n"
        f"• Zone: {zone.zone_bottom} - {zone.zone_top}\n"
        f"• {action} @ {zone.entry} | SL: {zone.stop_loss} | Target: {zone.target}\n"
        f"• Risk:Reward = 1:{rr:.1f}"
    )

    return zone
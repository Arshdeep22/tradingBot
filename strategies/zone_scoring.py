"""
Zone Scoring — LEGACY REDIRECT
-------------------------------
This file is kept for backwards compatibility.
The scoring system has been moved to the `strategies.zone_scoring` package.

Old 100-point system (freshness 40 + legout 30 + base 30) is preserved here
for any code still importing from this module directly.

New code should import from `strategies.zone_scoring` package:
    from strategies.zone_scoring import score_zone, score_zones, generate_reasoning
"""

# ─── Legacy imports from old module (preserved for zone_scanner.py compatibility) ───

from strategies.zone_models import Zone


def score_zone(zone: Zone, exciting_threshold: float,
               stronger_threshold: float, strong_threshold: float) -> Zone:
    """
    LEGACY: Score a zone using the old 100-point system.
    
    Kept for backwards compatibility with zone_scanner.py until Plan 6 update.
    New code should use `strategies.zone_scoring.score_zone()` (6-dimension system).
    """
    # 1. Freshness Score (max 40)
    zone.freshness_score = 40 if zone.is_fresh else 0

    # 2. Leg-out Strength Score (max 30)
    leg_out_pct = getattr(zone, 'leg_out_pct', zone.leg_out_body_pct)
    if leg_out_pct >= exciting_threshold:
        legout_score = 30
    elif leg_out_pct >= stronger_threshold:
        legout_score = 20
    elif leg_out_pct >= strong_threshold:
        legout_score = 10
    else:
        legout_score = 0

    # 3. Base Candles Score (max 30)
    if zone.base_candles <= 2:
        zone.base_score = 30
    elif zone.base_candles <= 4:
        zone.base_score = 20
    elif zone.base_candles == 5:
        zone.base_score = 10
    else:
        zone.base_score = 0

    # Total Score (old system: /100)
    zone.score = zone.freshness_score + legout_score + zone.base_score

    return zone


def calculate_trade_levels(zone: Zone, rr_ratio: float, atr_val: float) -> Zone:
    """
    LEGACY: Calculate entry, stop loss, and target for a zone.
    Kept for backwards compatibility until Plan 5 replaces this.
    """
    if atr_val <= 0:
        atr_val = zone.zone_bottom * 0.004

    sl_buffer = atr_val * 1.5

    if zone.zone_type == "DEMAND":
        zone.entry = zone.zone_top
        zone.stop_loss = round(zone.zone_bottom - sl_buffer, 2)
        risk = zone.entry - zone.stop_loss
        zone.target_1 = round(zone.entry + (1.0 * risk), 2)
        zone.target_2 = round(zone.entry + (rr_ratio * risk), 2)
    elif zone.zone_type == "SUPPLY":
        zone.entry = zone.zone_bottom
        zone.stop_loss = round(zone.zone_top + sl_buffer, 2)
        risk = zone.stop_loss - zone.entry
        zone.target_1 = round(zone.entry - (1.0 * risk), 2)
        zone.target_2 = round(zone.entry - (rr_ratio * risk), 2)

    return zone


def generate_reasoning(zone: Zone) -> Zone:
    """
    LEGACY: Generate human-readable reasoning (old format).
    Kept for backwards compatibility until Plan 6 update.
    """
    legout_score = zone.score - zone.freshness_score - zone.base_score
    leg_out_pct = getattr(zone, 'leg_out_pct', zone.leg_out_body_pct)

    if legout_score >= 30:
        leg_desc = f"EXCITING leg-out ({leg_out_pct:.1f}% body)"
    elif legout_score >= 20:
        leg_desc = f"STRONGER leg-out ({leg_out_pct:.1f}% body)"
    else:
        leg_desc = f"STRONG leg-out ({leg_out_pct:.1f}% body)"

    if zone.base_score >= 30:
        base_desc = f"Very tight base ({zone.base_candles} candles)"
    elif zone.base_score >= 20:
        base_desc = f"Compact base ({zone.base_candles} candles)"
    else:
        base_desc = f"Wider base ({zone.base_candles} candles)"

    fresh_desc = "FRESH (never tested)" if zone.is_fresh else "Tested"

    type_desc = f"{zone.zone_type} zone"

    zone.reasoning = (
        f"{type_desc} | Score: {zone.score}/100\n"
        f"• {fresh_desc} (+{zone.freshness_score} pts)\n"
        f"• {leg_desc} (+{legout_score} pts)\n"
        f"• {base_desc} (+{zone.base_score} pts)\n"
        f"• Zone: {zone.zone_bottom:.2f} - {zone.zone_top:.2f}"
    )

    return zone
"""
Human-Readable Reasoning Generator for scored zones.

Produces a professional summary of why a zone scored what it did,
with individual dimension breakdowns.
"""

from strategies.zone_models import Zone


def _departure_reason(score: int, zone: Zone) -> str:
    """Describe departure strength in human terms."""
    if score >= 10:
        if zone.has_gap:
            return "Gap away from zone (maximum departure)"
        return f"{zone.leg_out_count} strong candles, ratio {zone.leg_out_body_ratio:.2f}, vol {zone.leg_out_volume_ratio:.1f}x"
    elif score >= 8:
        return f"{zone.leg_out_count} candles, body ratio {zone.leg_out_body_ratio:.2f}, vol {zone.leg_out_volume_ratio:.1f}x"
    elif score >= 6:
        return f"Strong candle, ratio {zone.leg_out_body_ratio:.2f}, vol {zone.leg_out_volume_ratio:.1f}x"
    elif score >= 5:
        return f"Good body ratio {zone.leg_out_body_ratio:.2f}, no volume confirm"
    elif score >= 4:
        return f"Decent departure, ratio {zone.leg_out_body_ratio:.2f}"
    else:
        return "Weak departure"


def _base_reason(score: int, zone: Zone) -> str:
    """Describe base quality in human terms."""
    if score >= 10:
        return f"Instant reversal ({zone.base_candles} candle base)"
    elif score >= 8:
        return f"Tight {zone.base_candles}-candle base"
    elif score >= 6:
        return f"Compact {zone.base_candles}-candle base"
    elif score >= 4:
        return f"Moderate {zone.base_candles}-candle base"
    else:
        return f"Wide {zone.base_candles}-candle base"


def _freshness_reason(score: int, zone: Zone) -> str:
    """Describe freshness in human terms."""
    if score >= 10:
        return f"Pristine, formed {zone.age_candles} candles ago"
    elif score >= 7:
        return f"Fresh, formed {zone.age_candles} candles ago"
    elif score >= 4:
        return f"Fresh but aging ({zone.age_candles} candles old)"
    else:
        return "Tested (not fresh)"


def _arrival_reason(score: int) -> str:
    """Describe arrival quality in human terms."""
    if score >= 10:
        return "Very slow, controlled approach"
    elif score >= 8:
        return "Slow approach (good)"
    elif score >= 7:
        return "Moderate approach speed"
    elif score >= 5:
        return "Average approach"
    elif score >= 3:
        return "Fast momentum approach"
    else:
        return "Crashing into zone (poor)"


def _time_reason(score: int, zone: Zone) -> str:
    """Describe time/age in human terms."""
    if score >= 10:
        return f"Very recent ({zone.age_candles} candles, same session)"
    elif score >= 8:
        return f"Recent ({zone.age_candles} candles)"
    elif score >= 6:
        return f"Moderate age ({zone.age_candles} candles)"
    elif score >= 4:
        return f"Aging ({zone.age_candles} candles)"
    else:
        return f"Old zone ({zone.age_candles} candles)"


def _trend_reason(score: int, zone: Zone) -> str:
    """Describe trend alignment in human terms."""
    if score >= 10:
        return "With trend (ideal alignment)"
    elif score >= 5:
        return "Sideways market (neutral)"
    else:
        return "Counter-trend (risky)"


def generate_reasoning(zone: Zone) -> Zone:
    """
    Generate human-readable explanation of a zone's score.

    Populates zone.reasoning with a professional multi-line summary
    showing each dimension's contribution.

    Args:
        zone: A scored Zone (score_zone must be called first)

    Returns:
        Zone with reasoning field populated
    """
    header = (
        f"{zone.zone_type} zone ({zone.pattern}) | "
        f"Score: {zone.score}/60"
    )

    lines = [
        header,
        f"  • Departure: {zone.departure_score}/10 — {_departure_reason(zone.departure_score, zone)}",
        f"  • Base: {zone.base_score}/10 — {_base_reason(zone.base_score, zone)}",
        f"  • Freshness: {zone.freshness_score}/10 — {_freshness_reason(zone.freshness_score, zone)}",
        f"  • Arrival: {zone.arrival_score}/10 — {_arrival_reason(zone.arrival_score)}",
        f"  • Time: {zone.time_score}/10 — {_time_reason(zone.time_score, zone)}",
        f"  • Trend: {zone.trend_score}/10 — {_trend_reason(zone.trend_score, zone)}",
    ]

    zone.reasoning = "\n".join(lines)

    # Append confirmation candle info if available
    if getattr(zone, "confirmation_available", False):
        pattern = getattr(zone, "confirmation_pattern", "NONE")
        strength = getattr(zone, "confirmation_strength", 0)
        if pattern and pattern != "NONE":
            zone.reasoning += f"\n  • Confirmation: {pattern} (strength {strength}/5) ✅"
        else:
            zone.reasoning += "\n  • Confirmation: Price at zone — no pattern yet ⚠️"

    return zone

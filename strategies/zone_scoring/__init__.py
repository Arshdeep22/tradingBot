"""
Zone Scoring Package — Professional 6-Dimension Scoring System.

Replaces the old 100-point scoring with a 60-point maximum system:
- Departure Strength (0-10)
- Base Quality (0-10)
- Freshness (0-10)
- Arrival Quality (0-10)
- Time/Age (0-10)
- Trend Alignment (0-10)

Minimum score to trade: 40/60
"""

from strategies.zone_scoring.dimensions import (
    score_departure,
    score_base,
    score_freshness,
    score_arrival,
    score_time,
    score_trend,
)
from strategies.zone_scoring.scorer import score_zone, score_zones
from strategies.zone_scoring.reasoning import generate_reasoning

__all__ = [
    "score_departure",
    "score_base",
    "score_freshness",
    "score_arrival",
    "score_time",
    "score_trend",
    "score_zone",
    "score_zones",
    "generate_reasoning",
]
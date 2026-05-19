"""
Main Zone Scorer — Orchestrates all 6 scoring dimensions.

Applies each dimension function to a zone and populates
individual scores and total score.
"""

from typing import List

import pandas as pd

from strategies.zone_models import Zone
from strategies.zone_scoring.dimensions import (
    score_arrival,
    score_base,
    score_departure,
    score_freshness,
    score_time,
    score_trend,
)


def score_zone(
    zone: Zone, data: pd.DataFrame, trend: str = "SIDEWAYS"
) -> Zone:
    """
    Apply all 6 scoring dimensions to a zone.

    Populates zone.departure_score, zone.base_score, zone.freshness_score,
    zone.arrival_score, zone.time_score, zone.trend_score, and zone.score (total).

    Args:
        zone: Zone to score
        data: OHLC DataFrame (used for arrival quality calculation)
        trend: Higher-timeframe trend — "UPTREND", "DOWNTREND", or "SIDEWAYS"

    Returns:
        Zone with all score fields populated
    """
    zone.departure_score = score_departure(zone)
    zone.base_score = score_base(zone)
    zone.freshness_score = score_freshness(zone)
    zone.arrival_score = score_arrival(zone, data)
    zone.time_score = score_time(zone)
    zone.trend_score = score_trend(zone, trend)

    zone.score = (
        zone.departure_score
        + zone.base_score
        + zone.freshness_score
        + zone.arrival_score
        + zone.time_score
        + zone.trend_score
    )

    return zone


def score_zones(
    zones: List[Zone], data: pd.DataFrame, trend: str = "SIDEWAYS"
) -> List[Zone]:
    """
    Score a list of zones and sort by score descending.

    Args:
        zones: List of Zone objects to score
        data: OHLC DataFrame
        trend: Higher-timeframe trend direction

    Returns:
        List of scored zones, sorted highest score first
    """
    scored = [score_zone(z, data, trend) for z in zones]
    scored.sort(key=lambda z: z.score, reverse=True)
    return scored
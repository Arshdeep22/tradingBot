"""
6-Dimension Scoring Functions for Supply/Demand Zones.

Each function scores one dimension from 0-10.
Total possible: 60 points. Minimum to trade: 40.
"""

import pandas as pd

from strategies.zone_models import Zone


def score_departure(zone: Zone) -> int:
    """
    Dimension 1: Departure Strength — How explosively price left the zone.

    Checks BOTH body size (vs mean) and body ratio (fullness).

    10 = Gap away OR 3+ consecutive large candles
    8  = 2 candles + body > 2× mean + ratio > 0.7
    6  = 1 candle + body > 2× mean + ratio > 0.7 + volume > 1.5×
    5  = 1 candle + body > 2× mean + ratio > 0.7
    4  = 1 candle + body > 1.5× mean (moderate move)
    2  = Detected but weak
    """
    if zone.has_gap or zone.leg_out_count >= 3:
        return 10

    ratio = zone.leg_out_body_ratio
    vol = zone.leg_out_volume_ratio
    mean = zone.mean_body_pct if zone.mean_body_pct > 0 else 1.0
    size_mult = zone.leg_out_body_pct / mean

    if zone.leg_out_count >= 2 and size_mult >= 2.0 and ratio >= 0.7:
        return 8

    if size_mult >= 2.0 and ratio >= 0.7 and vol >= 1.5:
        return 6

    if size_mult >= 2.0 and ratio >= 0.7:
        return 5

    if size_mult >= 1.5:
        return 4

    return 2


def score_base(zone: Zone) -> int:
    """
    Dimension 2: Base Quality — How tight/compact the consolidation is.

    Fewer candles = more explosive reversal = better quality.

    10 = 1 candle base (instant reversal)
    8  = 2 candle base
    6  = 3 candle base
    4  = 4-5 candle base
    2  = 6+ candles (wide base, weaker)
    """
    candles = zone.base_candles

    if candles <= 1:
        return 10
    elif candles == 2:
        return 8
    elif candles == 3:
        return 6
    elif candles <= 5:
        return 4
    else:
        return 2


def score_freshness(zone: Zone) -> int:
    """
    Dimension 3: Freshness — Has price ever returned to this zone?

    A tested zone is not traded (hard zero).

    10 = Never tested + ≤ 50 candles old (PRISTINE)
    7  = Never tested + 51-100 candles old (FRESH)
    4  = Never tested + > 100 candles old (AGING)
    0  = Tested even once — do not trade
    """
    if not zone.is_fresh:
        return 0

    if zone.age_candles <= 50:
        return 10

    if zone.age_candles <= 100:
        return 7

    return 4


def score_arrival(zone: Zone, data: pd.DataFrame) -> int:
    """
    Dimension 4: Arrival Quality — How price approaches the zone NOW.

    Compares average body size of last 5 candles vs overall average.
    Slow, controlled approach = better (institutions accumulating).
    Fast, momentum crash = worse (retail panic).

    10 = Recent avg body < 50% of overall avg (very slow approach)
    8  = Recent < 75%
    7  = Recent < 100%
    5  = Recent ≈ average (100-150%)
    3  = Recent > 150% (momentum approach)
    2  = Recent > 200% (crashing into zone)
    """
    if data is None or len(data) < 10:
        return 5  # Default neutral score if insufficient data

    # Calculate body sizes
    bodies = (data["close"] - data["open"]).abs()
    overall_avg = bodies.mean()

    if overall_avg <= 0:
        return 5

    # Last 5 candles average body
    recent_avg = bodies.tail(5).mean()
    ratio = recent_avg / overall_avg

    if ratio < 0.5:
        return 10
    elif ratio < 0.75:
        return 8
    elif ratio < 1.0:
        return 7
    elif ratio < 1.5:
        return 5
    elif ratio < 2.0:
        return 3
    else:
        return 2


def score_time(zone: Zone) -> int:
    """
    Dimension 5: Time/Age — How much "energy" remains in the zone.

    More recent zones are stronger because they represent
    fresh institutional interest that hasn't decayed.

    10 = Formed within 20 candles (same session)
    8  = 21-50 candles (1-2 days on 15m)
    6  = 51-100 candles (2-4 days)
    4  = 101-150 candles (4-7 days)
    2  = 151-200 candles (1-2 weeks)
    1  = 201+ candles (ancient — institutional orders likely cancelled)
    """
    age = zone.age_candles

    if age <= 20:
        return 10
    elif age <= 50:
        return 8
    elif age <= 100:
        return 6
    elif age <= 150:
        return 4
    elif age <= 200:
        return 2
    return 1


def score_trend(zone: Zone, trend: str) -> int:
    """
    Dimension 6: Trend Alignment — With or against higher-TF trend.

    Trading with the trend dramatically increases probability.

    10 = With trend (demand in uptrend / supply in downtrend)
    5  = Sideways (neutral)
    3  = Counter-trend (demand in downtrend / supply in uptrend)

    Args:
        zone: The zone being scored
        trend: "UPTREND", "DOWNTREND", or "SIDEWAYS"
    """
    trend_upper = trend.upper() if trend else "SIDEWAYS"

    if trend_upper == "UPTREND":
        if zone.zone_type == "DEMAND":
            return 10  # Buying in uptrend — ideal
        else:
            return 3   # Selling in uptrend — counter-trend
    elif trend_upper == "DOWNTREND":
        if zone.zone_type == "SUPPLY":
            return 10  # Selling in downtrend — ideal
        else:
            return 3   # Buying in downtrend — counter-trend
    else:
        return 5  # Sideways — neutral
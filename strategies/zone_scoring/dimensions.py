"""
6-Dimension Scoring Functions for Supply/Demand Zones (v3).

Each function scores one dimension from 0-10.
Total possible: 60 points. Minimum to trade: 38.

KEY FIXES (v3):
- Trend dimension: counter-trend scores 0, SIDEWAYS reduced from 6 to 4
  This makes ranging market zones harder to qualify (need 34+ from 5 dims)
- Departure: added intermediate scores for more granular differentiation
- Freshness: tighter age requirements (zones decay faster on 15m)
- Arrival: more weight on slow approach (institutional footprint)
"""

import pandas as pd

from strategies.zone_models import Zone


def score_departure(zone: Zone) -> int:
    """
    Dimension 1: Departure Strength — How explosively price left the zone.

    Checks BOTH body size (vs mean) and body ratio (fullness).

    10 = Gap away OR 3+ consecutive large candles
    9  = 2+ candles + body > 2.5× mean + high volume
    8  = 2 candles + body > 2× mean + ratio > 0.7
    7  = 1 candle + body > 2.5× mean + ratio > 0.7 + volume > 2×
    6  = 1 candle + body > 2× mean + ratio > 0.7 + volume > 1.5×
    5  = 1 candle + body > 2× mean + ratio > 0.7
    4  = 1 candle + body > 1.5× mean (moderate move)
    3  = body > 1.2× mean
    2  = Detected but weak
    """
    if zone.has_gap or zone.leg_out_count >= 3:
        return 10

    ratio = zone.leg_out_body_ratio
    vol = zone.leg_out_volume_ratio
    mean = zone.mean_body_pct if zone.mean_body_pct > 0 else 1.0
    size_mult = zone.leg_out_body_pct / mean

    if zone.leg_out_count >= 2 and size_mult >= 2.5 and vol >= 1.5:
        return 9

    if zone.leg_out_count >= 2 and size_mult >= 2.0 and ratio >= 0.7:
        return 8

    if size_mult >= 2.5 and ratio >= 0.7 and vol >= 2.0:
        return 7

    if size_mult >= 2.0 and ratio >= 0.7 and vol >= 1.5:
        return 6

    if size_mult >= 2.0 and ratio >= 0.7:
        return 5

    if size_mult >= 1.5:
        return 4

    if size_mult >= 1.2:
        return 3

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
    v3: Tighter age thresholds — 15m zones decay faster than daily.

    10 = Never tested + ≤ 30 candles old (same session, PRISTINE)
    8  = Never tested + 31-60 candles old (1-2 days, VERY FRESH)
    6  = Never tested + 61-100 candles old (2-4 days, FRESH)
    4  = Never tested + 101-150 candles old (AGING)
    2  = Never tested + > 150 candles old (STALE)
    0  = Tested even once — do not trade
    """
    if not zone.is_fresh:
        return 0

    if zone.age_candles <= 30:
        return 10

    if zone.age_candles <= 60:
        return 8

    if zone.age_candles <= 100:
        return 6

    if zone.age_candles <= 150:
        return 4

    return 2


def score_arrival(zone: Zone, data: pd.DataFrame) -> int:
    """
    Dimension 4: Arrival Quality — How price approaches the zone NOW.

    Compares average body size of last 5 candles vs overall average.
    Slow, controlled approach = better (institutions accumulating).
    Fast, momentum crash = worse (retail panic).

    10 = Recent avg body < 50% of overall avg (very slow approach)
    8  = Recent < 70%
    7  = Recent < 90%
    5  = Recent ≈ average (90-130%)
    3  = Recent > 130% (momentum approach)
    2  = Recent > 180% (crashing into zone — likely to break through)
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
    elif ratio < 0.7:
        return 8
    elif ratio < 0.9:
        return 7
    elif ratio < 1.3:
        return 5
    elif ratio < 1.8:
        return 3
    else:
        return 2


def score_time(zone: Zone) -> int:
    """
    Dimension 5: Time/Age — How much "energy" remains in the zone.

    v3: Slightly tighter — 15m zones lose energy faster than daily.

    10 = Formed within 15 candles (same session, just formed)
    9  = 16-30 candles (recent same-day)
    8  = 31-50 candles (1-2 days on 15m)
    6  = 51-80 candles (2-3 days)
    4  = 81-120 candles (3-5 days)
    2  = 121-180 candles (5-7 days)
    1  = 181+ candles (ancient — institutional orders likely cancelled)
    """
    age = zone.age_candles

    if age <= 15:
        return 10
    elif age <= 30:
        return 9
    elif age <= 50:
        return 8
    elif age <= 80:
        return 6
    elif age <= 120:
        return 4
    elif age <= 180:
        return 2
    return 1


def score_trend(zone: Zone, trend: str) -> int:
    """
    Dimension 6: Trend Alignment — With or against higher-TF trend.

    v3 CHANGES:
    - SIDEWAYS reduced from 6 to 4 — ranging markets showed poor follow-through
      in training (23% WR in ranging vs 55% in trending weeks)
    - This means a zone in SIDEWAYS needs 34+ from other 5 dimensions (max 50)
      to pass min_score=38, which is achievable but requires quality
    - Counter-trend still blocked at 0

    10 = With trend (demand in uptrend / supply in downtrend)
    4  = Sideways (neutral — acceptable but harder to qualify)
    0  = Counter-trend (demand in downtrend / supply in uptrend) — BLOCKED
    """
    trend_upper = trend.upper() if trend else "SIDEWAYS"

    if trend_upper == "UPTREND":
        if zone.zone_type == "DEMAND":
            return 10  # Buying in uptrend — ideal
        else:
            return 0   # Selling in uptrend — BLOCKED
    elif trend_upper == "DOWNTREND":
        if zone.zone_type == "SUPPLY":
            return 10  # Selling in downtrend — ideal
        else:
            return 0   # Buying in downtrend — BLOCKED
    else:
        return 4  # Sideways — acceptable but penalized (was 6)
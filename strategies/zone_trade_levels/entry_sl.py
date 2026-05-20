"""
Entry and Stop Loss calculation for zone trading.

PROFESSIONAL ENTRY LOGIC (v3):
- Entry at zone MIDPOINT (not edge) — gives better fill and more room
- SL beyond zone extreme + ATR buffer (wider = fewer stop hunts)
- Entry confirmation: price must be INSIDE zone, not just touching edge

FIXES:
- Entry moved from zone_top/zone_bottom (edge) to midpoint
  This gives price room to "breathe" within the zone before hitting SL
- SL buffer increased: ATR multiplier applies to the full buffer
- Max SL cap raised to allow realistic risk per trade
"""

import pandas as pd
import numpy as np
from strategies.zone_models import Zone


def calculate_entry(zone: Zone) -> float:
    """
    Entry at zone midpoint for better probability.
    
    PROFESSIONAL LOGIC:
    - DEMAND: Entry = midpoint of zone (wait for price to drop INTO zone)
    - SUPPLY: Entry = midpoint of zone (wait for price to rise INTO zone)
    
    This is more realistic than edge entry because:
    1. Gives confirmation that price is actually respecting the zone
    2. Better average fill price (closer to zone center)
    3. More room before SL is hit (SL is beyond opposite edge)
    """
    midpoint = round((zone.zone_top + zone.zone_bottom) / 2.0, 2)
    
    if zone.zone_type == "DEMAND":
        # For demand, enter slightly above midpoint (price is falling into zone)
        # Enter at upper 40% of zone — gives room to drop to bottom before SL
        entry = round(zone.zone_bottom + (zone.zone_top - zone.zone_bottom) * 0.6, 2)
        return entry
    else:  # SUPPLY
        # For supply, enter slightly below midpoint (price is rising into zone)
        # Enter at lower 40% of zone — gives room to rise to top before SL
        entry = round(zone.zone_top - (zone.zone_top - zone.zone_bottom) * 0.6, 2)
        return entry


def compute_atr(data: pd.DataFrame, period: int = 14) -> float:
    """
    Calculate ATR using Wilder's smoothing method.
    Returns single float (most recent ATR value).
    """
    if len(data) < period + 1:
        # Fallback: use simple average of high-low range
        return round(float(np.mean(data['high'] - data['low'])), 2)

    high = data['high'].values
    low = data['low'].values
    close = data['close'].values

    # True Range calculation
    tr = np.zeros(len(data))
    tr[0] = high[0] - low[0]
    for i in range(1, len(data)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    # Wilder's smoothing (EMA with alpha = 1/period)
    atr = np.zeros(len(data))
    atr[period - 1] = np.mean(tr[:period])  # Initial SMA seed
    for i in range(period, len(data)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return round(float(atr[-1]), 2)


def calculate_stop_loss(zone: Zone, atr_value: float,
                        atr_multiplier: float = 1.5,
                        max_sl_pct: float = 2.0) -> float:
    """
    SL beyond zone extreme + ATR buffer, capped at max %.

    PROFESSIONAL LOGIC:
    - DEMAND: SL = zone_bottom - (ATR * multiplier)
      Price must break the ENTIRE zone + buffer to prove zone invalid
    - SUPPLY: SL = zone_top + (ATR * multiplier)
    
    The ATR buffer accounts for stop-hunt wicks that sweep below zones
    before reversing. Wider buffer = fewer false SL hits.
    """
    entry = calculate_entry(zone)

    if zone.zone_type == "DEMAND":
        raw_sl = zone.zone_bottom - (atr_value * atr_multiplier)
        # Cap: SL cannot be more than max_sl_pct below entry
        max_sl_distance = entry * (max_sl_pct / 100.0)
        capped_sl = max(raw_sl, entry - max_sl_distance)
        return round(capped_sl, 2)
    else:  # SUPPLY
        raw_sl = zone.zone_top + (atr_value * atr_multiplier)
        # Cap: SL cannot be more than max_sl_pct above entry
        max_sl_distance = entry * (max_sl_pct / 100.0)
        capped_sl = min(raw_sl, entry + max_sl_distance)
        return round(capped_sl, 2)


def validate_sl_distance(entry: float, stop_loss: float,
                         max_sl_pct: float = 2.0) -> bool:
    """Check if stop loss distance is within acceptable range."""
    if entry == 0:
        return False
    sl_distance_pct = abs(entry - stop_loss) / entry * 100
    return sl_distance_pct <= max_sl_pct


def get_confirmation_entry(confirmation, entry_method: str = 'CLOSE') -> float:
    """
    Return entry price from a ConfirmationSignal.
    'CLOSE': confirmation candle close (live trading).
    'NEXT_OPEN': same value — caller must substitute next candle's open for backtesting.
    """
    return confirmation.entry_price
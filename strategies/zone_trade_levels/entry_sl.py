"""
Entry and Stop Loss calculation for zone trading.
Entry at zone edge, SL with ATR buffer + cap enforcement.
"""

import pandas as pd
import numpy as np
from strategies.zone_models import Zone


def calculate_entry(zone: Zone) -> float:
    """
    Entry at zone edge.
    DEMAND: Entry = zone_top (buy when price drops to top of demand zone)
    SUPPLY: Entry = zone_bottom (sell when price rallies to bottom of supply)
    """
    if zone.zone_type == "DEMAND":
        return round(zone.zone_top, 2)
    else:  # SUPPLY
        return round(zone.zone_bottom, 2)


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
                        atr_multiplier: float = 1.0,
                        max_sl_pct: float = 1.5) -> float:
    """
    SL beyond zone extreme + ATR buffer, capped at max %.

    DEMAND: SL = zone_bottom - (ATR * multiplier), capped at max_sl_pct from entry
    SUPPLY: SL = zone_top + (ATR * multiplier), capped at max_sl_pct from entry
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
                         max_sl_pct: float = 1.5) -> bool:
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
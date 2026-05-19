"""
Legacy Compatibility - Stub functions for old zone_scanner.py.

These functions provide backward compatibility with the old detection API.
They will be removed when zone_scanner.py is rewritten in Plan 6.
"""

import pandas as pd
from typing import List, Optional
from strategies.zone_models import Zone


def detect_demand_zone(data: pd.DataFrame, idx: int, threshold: float,
                       max_base_candles: int) -> Optional[Zone]:
    """Legacy stub - returns None. Old scanner called this per-candle."""
    return None


def detect_supply_zone(data: pd.DataFrame, idx: int, threshold: float,
                       max_base_candles: int) -> Optional[Zone]:
    """Legacy stub - returns None. Old scanner called this per-candle."""
    return None
"""
Zone Models
-----------
Data classes for Supply & Demand zone representation.
"""

from dataclasses import dataclass


@dataclass
class Zone:
    """Represents a Supply or Demand zone"""
    zone_type: str  # "DEMAND" or "SUPPLY"
    zone_top: float
    zone_bottom: float
    base_candles: int
    leg_out_pct: float  # Leg-out candle body as % of price
    is_fresh: bool
    score: int
    freshness_score: int
    legout_score: int
    base_score: int
    formed_at_index: int
    formed_at_time: str = ""
    entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    reasoning: str = ""
    symbol: str = ""

    @property
    def zone_height(self) -> float:
        return self.zone_top - self.zone_bottom

    @property
    def zone_height_pct(self) -> float:
        if self.zone_bottom == 0:
            return 0
        return (self.zone_height / self.zone_bottom) * 100
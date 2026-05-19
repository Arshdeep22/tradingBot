"""
Zone Models — Professional-grade data classes for supply/demand zones.

Supports all 4 zone patterns:
- DBR (Drop-Base-Rally): Bearish leg-in → base → bullish leg-out → DEMAND zone
- RBD (Rally-Base-Drop): Bullish leg-in → base → bearish leg-out → SUPPLY zone  
- RBR (Rally-Base-Rally): Bullish leg-in → base → bullish leg-out → DEMAND zone (continuation)
- DBD (Drop-Base-Drop): Bearish leg-in → base → bearish leg-out → SUPPLY zone (continuation)

This module is the foundation for the zone trading system (Plan 1).
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Zone:
    """
    Represents a professional supply or demand zone with full quality metrics.
    
    A zone is formed by the pattern: Leg-In → Base → Leg-Out
    The base candles define the zone boundaries (zone_top, zone_bottom).
    """
    
    # ─── Core Identification ───────────────────────────────────────────
    zone_type: str          # "DEMAND" or "SUPPLY"
    pattern: str            # "DBR", "RBD", "RBR", "DBD"
    zone_top: float         # Highest HIGH of base candles
    zone_bottom: float      # Lowest LOW of base candles
    
    # ─── Formation Details ─────────────────────────────────────────────
    base_candles: int       # Number of candles in the base (1-5)
    formed_at_index: int    # Index in dataframe where base starts
    formed_at_time: str     # Timestamp of formation
    
    # ─── Leg-Out Quality Metrics ───────────────────────────────────────
    leg_out_count: int          # Number of consecutive large leg-out candles (1-5)
    leg_out_body_pct: float     # Average body % of leg-out candles (body/close * 100)
    leg_out_body_ratio: float   # Body / Total Range of leg-out (0-1, higher = less wicky)
    leg_out_volume_ratio: float # Volume of leg-out / 20-candle average volume
    has_gap: bool               # True if there's a price gap after base

    # ─── Leg-In Quality Metrics ────────────────────────────────────────
    leg_in_body_pct: float      # Body % of leg-in candle(s)
    leg_in_candle_count: int    # How many candles form the leg-in (1-3)

    # ─── Freshness & Age ───────────────────────────────────────────────
    is_fresh: bool = True       # True if zone never tested (strict: wick-based)
    age_candles: int = 0        # Number of candles since formation
    mean_body_pct: float = 0.0  # Mean body_pct of entire dataset — for size multiple scoring
    
    # ─── Scoring (filled later by scorer - Plan 3) ─────────────────────
    score: int = 0              # Total score (0-60)
    departure_score: int = 0   # Dimension 1: Leg-out quality (0-10)
    base_score: int = 0        # Dimension 2: Base tightness (0-10)
    freshness_score: int = 0   # Dimension 3: Never tested (0-10)
    arrival_score: int = 0     # Dimension 4: Leg-in quality (0-10)
    time_score: int = 0        # Dimension 5: Time/age factor (0-10)
    trend_score: int = 0       # Dimension 6: Trend alignment (0-10)
    
    # ─── Trade Levels (filled later - Plan 5) ──────────────────────────
    entry: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0     # Partial profit target (1:1)
    target_2: float = 0.0     # Final target (1:3 or opposing zone)
    position_size: int = 0
    
    # ─── Metadata ──────────────────────────────────────────────────────
    symbol: str = ""
    timeframe: str = ""
    reasoning: str = ""

    # ─── Confirmation Candle (Phase 2) ─────────────────────────────────
    confirmation_pattern: str = ""       # e.g. "HAMMER", "BULLISH_ENGULFING", "NONE"
    confirmation_strength: int = 0       # 0-5; 0 = not checked / no pattern
    confirmation_available: bool = False # True when price is within check_pct of zone edge
    
    # ─── Computed Properties ───────────────────────────────────────────
    @property
    def zone_height(self) -> float:
        """Absolute height of the zone in price units."""
        return self.zone_top - self.zone_bottom
    
    @property
    def zone_height_pct(self) -> float:
        """Zone height as a percentage of zone_bottom price."""
        if self.zone_bottom == 0:
            return 0
        return (self.zone_height / self.zone_bottom) * 100
    
    @property
    def midpoint(self) -> float:
        """Midpoint price of the zone."""
        return (self.zone_top + self.zone_bottom) / 2
    
    @property
    def is_demand(self) -> bool:
        """True if this is a demand (buy) zone."""
        return self.zone_type == "DEMAND"
    
    @property
    def is_supply(self) -> bool:
        """True if this is a supply (sell) zone."""
        return self.zone_type == "SUPPLY"
    
    @property
    def is_reversal(self) -> bool:
        """True if this is a reversal pattern (DBR or RBD)."""
        return self.pattern in ("DBR", "RBD")
    
    @property
    def is_continuation(self) -> bool:
        """True if this is a continuation pattern (RBR or DBD)."""
        return self.pattern in ("RBR", "DBD")
    
    def __repr__(self) -> str:
        fresh_marker = "🟢" if self.is_fresh else "🔴"
        return (
            f"Zone({self.zone_type} {self.pattern} {fresh_marker} "
            f"[{self.zone_bottom:.2f}-{self.zone_top:.2f}] "
            f"score={self.score} leg_out={self.leg_out_count}x "
            f"base={self.base_candles} gap={'Y' if self.has_gap else 'N'})"
        )


@dataclass
class ZoneAnalysis:
    """Container for zone analysis results for a symbol."""
    symbol: str
    timeframe: str
    zones: list = field(default_factory=list)
    demand_zones: list = field(default_factory=list)
    supply_zones: list = field(default_factory=list)
    current_price: float = 0.0
    nearest_demand: Optional[Zone] = None
    nearest_supply: Optional[Zone] = None
    signal: str = "NEUTRAL"  # "BUY", "SELL", "NEUTRAL"
    confidence: int = 0
    reasoning: str = ""

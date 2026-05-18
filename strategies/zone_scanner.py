"""
Supply & Demand Zone Scanner Strategy
--------------------------------------
Detects supply and demand zones, scores them, and generates trade signals.

This is the main orchestrator that delegates to:
- zone_models.py: Zone dataclass
- zone_detection.py: Zone detection algorithms
- zone_scoring.py: Scoring, trade levels, reasoning
- zone_mtf.py: Multi-timeframe confirmation

Scoring:
- Freshness: 40 points (zone never tested)
- Leg-out Strength: 30 points (big exciting candle)
- Base Candles: 30 points (1-2 candles = max)

Only zones scoring >= 80 are considered tradeable.
"""

import pandas as pd
from typing import List
import logging

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.zone_models import Zone
from strategies.zone_detection import detect_demand_zone, detect_supply_zone, check_freshness
from strategies.zone_scoring import score_zone, calculate_trade_levels, generate_reasoning
from strategies.zone_mtf import multi_timeframe_confirm

logger = logging.getLogger(__name__)


class ZoneScanner(BaseStrategy):
    """
    Supply & Demand Zone Scanner

    Detects zones, scores them, and presents the best opportunities.
    """

    def __init__(self, timeframe: str = "15m",
                 min_score: int = 80,
                 rr_ratio: float = 3.0,
                 leg_out_exciting_pct: float = 1.5,
                 leg_out_stronger_pct: float = 1.0,
                 leg_out_strong_pct: float = 0.5,
                 max_base_candles: int = 5):
        super().__init__(name="Supply Demand Zones", timeframe=timeframe)
        self.min_score = min_score
        self.rr_ratio = rr_ratio
        self.leg_out_exciting_pct = leg_out_exciting_pct
        self.leg_out_stronger_pct = leg_out_stronger_pct
        self.leg_out_strong_pct = leg_out_strong_pct
        self.max_base_candles = max_base_candles

    def detect_zones(self, data: pd.DataFrame, symbol: str = "") -> List[Zone]:
        """
        Detect all supply and demand zones in the data.

        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol

        Returns:
            List of Zone objects (scored and filtered)
        """
        if data is None or len(data) < 10:
            return []

        data = data.copy().reset_index(drop=True)

        # Calculate ATR(14) for adaptive SL buffer
        atr_val = self._compute_atr(data)

        # Prepare candle body data
        data = self._prepare_body_data(data)

        # Compute adaptive thresholds
        adaptive_strong, adaptive_stronger, adaptive_exciting = self._compute_adaptive_thresholds(data)

        # Mark large candles
        data['is_large'] = data['body_pct'] >= adaptive_strong

        # Scan for zones
        zones = []
        i = 2  # Start from index 2 to have room for leg-in
        while i < len(data) - 1:
            # Look for DEMAND zones
            demand_zone = detect_demand_zone(data, i, adaptive_strong, self.max_base_candles)
            if demand_zone is not None:
                demand_zone.symbol = symbol
                zones.append(demand_zone)

            # Look for SUPPLY zones
            supply_zone = detect_supply_zone(data, i, adaptive_strong, self.max_base_candles)
            if supply_zone is not None:
                supply_zone.symbol = symbol
                zones.append(supply_zone)

            i += 1

        # Check freshness
        zones = check_freshness(zones, data)

        # Score all zones
        zones = [score_zone(z, adaptive_exciting, adaptive_stronger, adaptive_strong) for z in zones]

        # Calculate entry/SL/target
        zones = [calculate_trade_levels(z, self.rr_ratio, atr_val) for z in zones]

        # Generate reasoning
        zones = [generate_reasoning(z) for z in zones]

        # Filter by minimum score
        zones = [z for z in zones if z.score >= self.min_score]

        # Sort by score (highest first)
        zones.sort(key=lambda z: z.score, reverse=True)

        return zones

    def _compute_atr(self, data: pd.DataFrame) -> float:
        """Calculate ATR(14) for adaptive SL buffer."""
        if len(data) <= 14:
            return 0.0
        prev_close = data['Close'].shift(1)
        tr = pd.concat([
            data['High'] - data['Low'],
            (data['High'] - prev_close).abs(),
            (data['Low'] - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(com=13, adjust=False).mean().iloc[-1])

    def _prepare_body_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Add body size columns to the dataframe."""
        data['body'] = abs(data['Close'] - data['Open'])
        data['body_pct'] = (data['body'] / data['Close']) * 100
        data['is_bullish'] = data['Close'] > data['Open']
        data['is_bearish'] = data['Close'] < data['Open']
        return data

    def _compute_adaptive_thresholds(self, data: pd.DataFrame) -> tuple:
        """
        Compute adaptive thresholds based on percentile of body sizes.
        Returns (strong, stronger, exciting) thresholds.
        """
        mean_body = data['body_pct'].mean()
        std_body = data['body_pct'].std()
        adaptive_strong = max(mean_body + std_body, 0.15)
        adaptive_stronger = max(mean_body + 1.5 * std_body, 0.25)
        adaptive_exciting = max(mean_body + 2.0 * std_body, 0.4)
        return adaptive_strong, adaptive_stronger, adaptive_exciting

    def get_trade_setups(self, data: pd.DataFrame, symbol: str) -> List[TradeSetup]:
        """Return one TradeSetup per detected zone (overrides BaseStrategy default)."""
        zones = self.detect_zones(data, symbol)
        setups = []
        for zone in zones:
            setups.append(TradeSetup(
                symbol=symbol,
                side="BUY" if zone.zone_type == "DEMAND" else "SELL",
                entry=zone.entry,
                stop_loss=zone.stop_loss,
                target=zone.target,
                score=zone.score,
                reasoning=zone.reasoning,
            ))
        return setups

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """
        Generate trading signal based on zone detection.
        Returns the highest-scoring zone as a trade signal.
        """
        zones = self.detect_zones(data, symbol)

        if not zones:
            return TradeSignal(Signal.HOLD, symbol, reason="No qualifying zones found")

        # Get the best zone
        best_zone = zones[0]

        if best_zone.zone_type == "DEMAND":
            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=best_zone.entry,
                stop_loss=best_zone.stop_loss,
                target=best_zone.target,
                reason=best_zone.reasoning
            )
        else:
            return TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=best_zone.entry,
                stop_loss=best_zone.stop_loss,
                target=best_zone.target,
                reason=best_zone.reasoning
            )

    def multi_timeframe_scan(self, data_fetcher, symbol: str) -> List[Zone]:
        """
        Multi-timeframe zone analysis:
        1. 15m: Find fresh zones and score them
        2. 5m: Check trend direction (is price moving toward zone?)
        3. 3m: Refine entry/exit/SL levels

        Args:
            data_fetcher: DataFetcher instance
            symbol: Stock symbol

        Returns:
            List of zones with multi-timeframe confirmation
        """
        # Step 1: Find zones on 15m (structure timeframe)
        data_15m = data_fetcher.get_data(symbol, "15m", "5d")
        if data_15m is None or len(data_15m) < 10:
            return []

        zones_15m = self.detect_zones(data_15m, symbol)
        if not zones_15m:
            return []

        # Step 2: Get 5m data for trend confirmation
        data_5m = data_fetcher.get_data(symbol, "5m", "2d")
        if data_5m is None:
            return zones_15m  # Return 15m zones without confirmation

        # Step 3: Get 2m/1m data for entry refinement
        data_3m = data_fetcher.get_data(symbol, "2m", "1d")
        if data_3m is None:
            data_3m = data_fetcher.get_data(symbol, "1m", "1d")

        # Apply multi-timeframe confirmation
        return multi_timeframe_confirm(zones_15m, data_5m, data_3m, self.rr_ratio)

    def get_parameters(self) -> dict:
        """Return strategy parameters"""
        return {
            "name": self.name,
            "timeframe": self.timeframe,
            "min_score": self.min_score,
            "rr_ratio": self.rr_ratio,
            "leg_out_exciting_pct": self.leg_out_exciting_pct,
            "leg_out_stronger_pct": self.leg_out_stronger_pct,
            "leg_out_strong_pct": self.leg_out_strong_pct,
            "max_base_candles": self.max_base_candles
        }
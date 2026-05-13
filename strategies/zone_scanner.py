"""
Supply & Demand Zone Scanner Strategy
--------------------------------------
Detects supply and demand zones, scores them, and generates trade signals.

Scoring:
- Freshness: 40 points (zone never tested)
- Leg-out Strength: 30 points (big exciting candle)
- Base Candles: 30 points (1-2 candles = max)

Only zones scoring >= 80 are considered tradeable.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import logging

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from config.settings import STOP_LOSS_PERCENT, TARGET_PERCENT

logger = logging.getLogger(__name__)


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
        zones = []

        # Calculate candle body sizes
        data['body'] = abs(data['Close'] - data['Open'])
        data['body_pct'] = (data['body'] / data['Close']) * 100
        data['is_bullish'] = data['Close'] > data['Open']
        data['is_bearish'] = data['Close'] < data['Open']

        # ADAPTIVE THRESHOLDS: Use percentile-based detection
        # A "large" candle is one in the top 20% of body sizes
        mean_body = data['body_pct'].mean()
        std_body = data['body_pct'].std()
        adaptive_strong = max(mean_body + std_body, 0.15)  # At least top ~30%
        adaptive_stronger = max(mean_body + 1.5 * std_body, 0.25)
        adaptive_exciting = max(mean_body + 2.0 * std_body, 0.4)

        # Store adaptive thresholds for scoring
        self._current_strong = adaptive_strong
        self._current_stronger = adaptive_stronger
        self._current_exciting = adaptive_exciting

        # Identify large candles (potential leg-out candles)
        data['is_large'] = data['body_pct'] >= adaptive_strong

        # Scan for zones
        i = 2  # Start from index 2 to have room for leg-in
        while i < len(data) - 1:
            # Look for DEMAND zones: drop → base → rally (leg out UP)
            demand_zone = self._detect_demand_zone(data, i)
            if demand_zone is not None:
                demand_zone.symbol = symbol
                zones.append(demand_zone)

            # Look for SUPPLY zones: rally → base → drop (leg out DOWN)
            supply_zone = self._detect_supply_zone(data, i)
            if supply_zone is not None:
                supply_zone.symbol = symbol
                zones.append(supply_zone)

            i += 1

        # Check freshness for all zones
        zones = self._check_freshness(zones, data)

        # Score all zones
        zones = [self._score_zone(z) for z in zones]

        # Calculate entry/SL/target
        zones = [self._calculate_trade_levels(z) for z in zones]

        # Generate reasoning
        zones = [self._generate_reasoning(z) for z in zones]

        # Filter by minimum score
        zones = [z for z in zones if z.score >= self.min_score]

        # Sort by score (highest first)
        zones.sort(key=lambda z: z.score, reverse=True)

        return zones

    def _detect_demand_zone(self, data: pd.DataFrame, start_idx: int) -> Optional[Zone]:
        """
        Detect a demand zone starting at given index.
        Pattern: Large bearish candle(s) → Small base candle(s) → Large bullish candle (leg out)
        """
        n = len(data)
        threshold = getattr(self, '_current_strong', self.leg_out_strong_pct)

        # Check if current candle is a small base candle
        if data['body_pct'].iloc[start_idx] >= threshold:
            return None  # Not a base candle

        # Look for leg-out (bullish) AFTER the base
        base_start = start_idx
        base_end = start_idx

        # Find consecutive small candles (base)
        for j in range(start_idx, min(start_idx + self.max_base_candles + 1, n)):
            if data['body_pct'].iloc[j] < threshold:
                base_end = j
            else:
                break

        base_candles = base_end - base_start + 1

        if base_candles > self.max_base_candles:
            return None

        # Check for leg-out (large bullish candle after base)
        leg_out_idx = base_end + 1
        if leg_out_idx >= n:
            return None

        if not (data['is_bullish'].iloc[leg_out_idx] and
                data['body_pct'].iloc[leg_out_idx] >= threshold):
            return None

        # Check for leg-in (price was dropping before base)
        if base_start > 0:
            leg_in_idx = base_start - 1
            if not data['is_bearish'].iloc[leg_in_idx]:
                return None  # No drop before base

        # Define zone boundaries
        zone_top = data['High'].iloc[base_start:base_end + 1].max()
        zone_bottom = data['Low'].iloc[base_start:base_end + 1].min()

        # Leg-out candle body percentage
        leg_out_pct = data['body_pct'].iloc[leg_out_idx]

        # Get formation time
        formed_time = ""
        if hasattr(data, 'index') and hasattr(data.index, 'strftime'):
            try:
                formed_time = str(data.index[base_start])
            except Exception:
                formed_time = str(base_start)

        return Zone(
            zone_type="DEMAND",
            zone_top=round(zone_top, 2),
            zone_bottom=round(zone_bottom, 2),
            base_candles=base_candles,
            leg_out_pct=round(leg_out_pct, 3),
            is_fresh=True,  # Will be checked later
            score=0,
            freshness_score=0,
            legout_score=0,
            base_score=0,
            formed_at_index=base_start,
            formed_at_time=formed_time
        )

    def _detect_supply_zone(self, data: pd.DataFrame, start_idx: int) -> Optional[Zone]:
        """
        Detect a supply zone starting at given index.
        Pattern: Large bullish candle(s) → Small base candle(s) → Large bearish candle (leg out)
        """
        n = len(data)
        threshold = getattr(self, '_current_strong', self.leg_out_strong_pct)

        # Check if current candle is a small base candle
        if data['body_pct'].iloc[start_idx] >= threshold:
            return None

        # Look for leg-out (bearish) AFTER the base
        base_start = start_idx
        base_end = start_idx

        # Find consecutive small candles (base)
        for j in range(start_idx, min(start_idx + self.max_base_candles + 1, n)):
            if data['body_pct'].iloc[j] < threshold:
                base_end = j
            else:
                break

        base_candles = base_end - base_start + 1

        if base_candles > self.max_base_candles:
            return None

        # Check for leg-out (large bearish candle after base)
        leg_out_idx = base_end + 1
        if leg_out_idx >= n:
            return None

        if not (data['is_bearish'].iloc[leg_out_idx] and
                data['body_pct'].iloc[leg_out_idx] >= threshold):
            return None

        # Check for leg-in (price was rallying before base)
        if base_start > 0:
            leg_in_idx = base_start - 1
            if not data['is_bullish'].iloc[leg_in_idx]:
                return None  # No rally before base

        # Define zone boundaries
        zone_top = data['High'].iloc[base_start:base_end + 1].max()
        zone_bottom = data['Low'].iloc[base_start:base_end + 1].min()

        # Leg-out candle body percentage
        leg_out_pct = data['body_pct'].iloc[leg_out_idx]

        # Get formation time
        formed_time = ""
        if hasattr(data, 'index') and hasattr(data.index, 'strftime'):
            try:
                formed_time = str(data.index[base_start])
            except Exception:
                formed_time = str(base_start)

        return Zone(
            zone_type="SUPPLY",
            zone_top=round(zone_top, 2),
            zone_bottom=round(zone_bottom, 2),
            base_candles=base_candles,
            leg_out_pct=round(leg_out_pct, 3),
            is_fresh=True,
            score=0,
            freshness_score=0,
            legout_score=0,
            base_score=0,
            formed_at_index=base_start,
            formed_at_time=formed_time
        )

    def _check_freshness(self, zones: List[Zone], data: pd.DataFrame) -> List[Zone]:
        """Check if zones are fresh (never tested after formation)"""
        fresh_zones = []

        for zone in zones:
            is_fresh = True
            # Check all candles AFTER zone formation
            for i in range(zone.formed_at_index + zone.base_candles + 1, len(data)):
                if zone.zone_type == "DEMAND":
                    # Stale only if candle closes BELOW zone_bottom (broke through)
                    # A wick into the zone that closes back above = test-and-hold (still fresh)
                    candle_close = data['Close'].iloc[i]
                    if candle_close < zone.zone_bottom:
                        is_fresh = False
                        break
                elif zone.zone_type == "SUPPLY":
                    # Stale only if candle closes ABOVE zone_top (broke through)
                    candle_close = data['Close'].iloc[i]
                    if candle_close > zone.zone_top:
                        is_fresh = False
                        break

            zone.is_fresh = is_fresh
            if is_fresh:
                fresh_zones.append(zone)

        return fresh_zones

    def _score_zone(self, zone: Zone) -> Zone:
        """Score a zone based on the scoring criteria"""

        # 1. Freshness Score (max 40)
        zone.freshness_score = 40 if zone.is_fresh else 0

        # 2. Leg-out Strength Score (max 30) - Use adaptive thresholds
        exciting_threshold = getattr(self, '_current_exciting', self.leg_out_exciting_pct)
        stronger_threshold = getattr(self, '_current_stronger', self.leg_out_stronger_pct)
        strong_threshold = getattr(self, '_current_strong', self.leg_out_strong_pct)

        if zone.leg_out_pct >= exciting_threshold:
            zone.legout_score = 30  # Strongest/Exciting
        elif zone.leg_out_pct >= stronger_threshold:
            zone.legout_score = 20  # Stronger
        elif zone.leg_out_pct >= strong_threshold:
            zone.legout_score = 10  # Strong
        else:
            zone.legout_score = 0  # Weak

        # 3. Base Candles Score (max 30)
        if zone.base_candles <= 2:
            zone.base_score = 30
        elif zone.base_candles <= 4:
            zone.base_score = 20
        elif zone.base_candles == 5:
            zone.base_score = 10
        else:
            zone.base_score = 0

        # Total Score
        zone.score = zone.freshness_score + zone.legout_score + zone.base_score

        return zone

    def _calculate_trade_levels(self, zone: Zone) -> Zone:
        """Calculate entry, stop loss, and target for a zone"""

        if zone.zone_type == "DEMAND":
            # Buy at top of demand zone
            zone.entry = zone.zone_top
            # SL below bottom of zone (with 0.4% buffer — wider to survive 15m wicks)
            zone.stop_loss = round(zone.zone_bottom * (1 - 0.004), 2)
            # Target = Entry + 3 * Risk
            risk = zone.entry - zone.stop_loss
            zone.target = round(zone.entry + (self.rr_ratio * risk), 2)

        elif zone.zone_type == "SUPPLY":
            # Sell at bottom of supply zone
            zone.entry = zone.zone_bottom
            # SL above top of zone (with 0.4% buffer — wider to survive 15m wicks)
            zone.stop_loss = round(zone.zone_top * (1 + 0.004), 2)
            # Target = Entry - 3 * Risk
            risk = zone.stop_loss - zone.entry
            zone.target = round(zone.entry - (self.rr_ratio * risk), 2)

        return zone

    def _generate_reasoning(self, zone: Zone) -> Zone:
        """Generate human-readable reasoning for the zone"""

        # Leg-out description
        if zone.legout_score == 30:
            leg_desc = f"EXCITING leg-out candle ({zone.leg_out_pct:.1f}% body)"
        elif zone.legout_score == 20:
            leg_desc = f"STRONGER leg-out candle ({zone.leg_out_pct:.1f}% body)"
        else:
            leg_desc = f"STRONG leg-out candle ({zone.leg_out_pct:.1f}% body)"

        # Base description
        if zone.base_score == 30:
            base_desc = f"Very tight base ({zone.base_candles} candles)"
        elif zone.base_score == 20:
            base_desc = f"Compact base ({zone.base_candles} candles)"
        else:
            base_desc = f"Wider base ({zone.base_candles} candles)"

        # Freshness description
        fresh_desc = "FRESH zone (never tested)" if zone.is_fresh else "Zone has been tested"

        # Zone type description
        if zone.zone_type == "DEMAND":
            type_desc = "DEMAND zone (Buy opportunity)"
            action = "BUY"
        else:
            type_desc = "SUPPLY zone (Sell opportunity)"
            action = "SELL"

        # Risk/Reward
        risk = abs(zone.entry - zone.stop_loss)
        reward = abs(zone.target - zone.entry)
        rr = reward / risk if risk > 0 else 0

        zone.reasoning = (
            f"{type_desc} | Score: {zone.score}/100\n"
            f"• {fresh_desc} (+{zone.freshness_score} pts)\n"
            f"• {leg_desc} (+{zone.legout_score} pts)\n"
            f"• {base_desc} (+{zone.base_score} pts)\n"
            f"• Zone: {zone.zone_bottom} - {zone.zone_top}\n"
            f"• {action} @ {zone.entry} | SL: {zone.stop_loss} | Target: {zone.target}\n"
            f"• Risk:Reward = 1:{rr:.1f}"
        )

        return zone

    def get_trade_setups(self, data: pd.DataFrame, symbol: str):
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

        # Step 2: Check 5m for trend confirmation
        data_5m = data_fetcher.get_data(symbol, "5m", "2d")
        if data_5m is None:
            return zones_15m  # Return 15m zones without confirmation

        # Step 3: Check 2m/1m for entry refinement (3m not supported by yfinance)
        data_3m = data_fetcher.get_data(symbol, "2m", "1d")
        if data_3m is None:
            data_3m = data_fetcher.get_data(symbol, "1m", "1d")

        confirmed_zones = []
        for zone in zones_15m:
            # Check trend on 5m
            trend = self._check_trend_5m(data_5m, zone)

            # Reject zones that trade against the 5m trend
            if zone.zone_type == "DEMAND" and trend == "DOWN":
                continue
            if zone.zone_type == "SUPPLY" and trend == "UP":
                continue

            # Refine on 3m
            refined_zone = self._refine_on_3m(data_3m, zone) if data_3m is not None else zone

            # Check freshness across timeframes
            fresh_on_5m = self._check_fresh_on_timeframe(data_5m, zone)
            fresh_on_3m = self._check_fresh_on_timeframe(data_3m, zone) if data_3m is not None else True

            # Update zone with MTF info
            mtf_fresh = zone.is_fresh and fresh_on_5m and fresh_on_3m

            if mtf_fresh:
                refined_zone.is_fresh = True
                # Bonus reasoning for multi-timeframe confirmation
                trend_text = "BULLISH" if trend == "UP" else "BEARISH" if trend == "DOWN" else "SIDEWAYS"
                refined_zone.reasoning += (
                    f"\n• MTF Confirmed: Fresh on 15m/5m/3m"
                    f"\n• 5m Trend: {trend_text}"
                    f"\n• Entry refined on 3m chart"
                )
                confirmed_zones.append(refined_zone)

        # Sort by score
        confirmed_zones.sort(key=lambda z: z.score, reverse=True)
        return confirmed_zones

    def _check_trend_5m(self, data_5m: pd.DataFrame, zone: Zone) -> str:
        """
        Check 5m trend direction relative to zone.
        Returns: "UP", "DOWN", or "SIDEWAYS"
        """
        if data_5m is None or len(data_5m) < 20:
            return "SIDEWAYS"

        data = data_5m.copy()
        # Use last 20 candles for trend
        recent = data.tail(20)

        # Simple trend: compare EMA 9 vs EMA 20
        ema_fast = recent['Close'].ewm(span=9, adjust=False).mean()
        ema_slow = recent['Close'].ewm(span=20, adjust=False).mean()

        if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
            trend = "UP"
        elif ema_fast.iloc[-1] < ema_slow.iloc[-1]:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"

        # For DEMAND zones, we want price to be coming DOWN toward zone (or UP trend)
        # For SUPPLY zones, we want price to be going UP toward zone (or DOWN trend)
        return trend

    def _refine_on_3m(self, data_3m: pd.DataFrame, zone: Zone) -> Zone:
        """
        Refine entry/SL/target using 3m chart for tighter levels.
        Looks for a more precise zone boundary on 3m.
        """
        if data_3m is None or len(data_3m) < 10:
            return zone

        refined = Zone(
            zone_type=zone.zone_type,
            zone_top=zone.zone_top,
            zone_bottom=zone.zone_bottom,
            base_candles=zone.base_candles,
            leg_out_pct=zone.leg_out_pct,
            is_fresh=zone.is_fresh,
            score=zone.score,
            freshness_score=zone.freshness_score,
            legout_score=zone.legout_score,
            base_score=zone.base_score,
            formed_at_index=zone.formed_at_index,
            formed_at_time=zone.formed_at_time,
            entry=zone.entry,
            stop_loss=zone.stop_loss,
            target=zone.target,
            reasoning=zone.reasoning,
            symbol=zone.symbol
        )

        data = data_3m.copy().reset_index(drop=True)

        # Look for a tighter zone on 3m within the 15m zone range
        data['body'] = abs(data['Close'] - data['Open'])
        data['body_pct'] = (data['body'] / data['Close']) * 100

        # Find candles within the zone
        in_zone = data[
            (data['Low'] >= zone.zone_bottom * 0.999) &
            (data['High'] <= zone.zone_top * 1.001)
        ]

        if len(in_zone) >= 1:
            # Tighter zone from 3m data
            tighter_top = in_zone['High'].max()
            tighter_bottom = in_zone['Low'].min()

            if zone.zone_type == "DEMAND":
                refined.entry = round(tighter_top, 2)
                refined.stop_loss = round(tighter_bottom * (1 - 0.004), 2)
                risk = refined.entry - refined.stop_loss
                refined.target = round(refined.entry + (self.rr_ratio * risk), 2)
            else:
                refined.entry = round(tighter_bottom, 2)
                refined.stop_loss = round(tighter_top * (1 + 0.004), 2)
                risk = refined.stop_loss - refined.entry
                refined.target = round(refined.entry - (self.rr_ratio * risk), 2)

        return refined

    def _check_fresh_on_timeframe(self, data: pd.DataFrame, zone: Zone) -> bool:
        """Check if zone is fresh on a given timeframe's data"""
        if data is None or len(data) < 5:
            return True  # Assume fresh if no data

        data = data.copy().reset_index(drop=True)

        # Check last 20 candles to see if price entered the zone
        recent = data.tail(20)

        for i in range(len(recent)):
            candle_low = recent['Low'].iloc[i]
            candle_high = recent['High'].iloc[i]

            if zone.zone_type == "DEMAND":
                if candle_low <= zone.zone_top and candle_low >= zone.zone_bottom:
                    return False  # Zone was tested
            elif zone.zone_type == "SUPPLY":
                if candle_high >= zone.zone_bottom and candle_high <= zone.zone_top:
                    return False  # Zone was tested

        return True

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

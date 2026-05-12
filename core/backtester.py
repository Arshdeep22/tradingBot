"""
Backtester Module
-----------------
Tests the Supply & Demand Zone strategy on historical data.

Approach:
1. Split data into "zone building" period and "testing" period
2. Detect zones on the building period
3. Simulate forward through testing period to check if zones get triggered
4. Track outcomes: Target Hit, SL Hit, or Pending
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from strategies.zone_scanner import ZoneScanner, Zone

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a simulated trade"""
    zone: Zone
    triggered: bool = False
    trigger_time: str = ""
    trigger_price: float = 0.0
    outcome: str = "PENDING"  # "TARGET_HIT", "SL_HIT", "PENDING"
    exit_time: str = ""
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    rr_achieved: float = 0.0
    candles_to_trigger: int = 0
    candles_to_exit: int = 0


@dataclass 
class BacktestReport:
    """Summary report of a backtest run"""
    symbol: str
    building_start: str
    building_end: str
    testing_start: str
    testing_end: str
    total_zones_found: int
    zones_triggered: int
    targets_hit: int
    sl_hit: int
    pending: int
    win_rate: float
    total_pnl: float
    avg_rr_achieved: float
    max_win: float
    max_loss: float
    trade_results: List[TradeResult] = field(default_factory=list)
    zones: List[Zone] = field(default_factory=list)
    building_data: Optional[pd.DataFrame] = None
    testing_data: Optional[pd.DataFrame] = None


class Backtester:
    """
    Backtests the Supply & Demand Zone strategy.
    
    Usage:
        bt = Backtester()
        report = bt.run(data, split_index, symbol)
    """

    def __init__(self, min_score: int = 80, rr_ratio: float = 3.0):
        self.zone_scanner = ZoneScanner(
            timeframe="15m",
            min_score=min_score,
            rr_ratio=rr_ratio
        )

    def run(self, data: pd.DataFrame, split_date: datetime, 
            symbol: str = "") -> BacktestReport:
        """
        Run backtest on data split at split_date.
        
        Args:
            data: Full OHLCV DataFrame with DatetimeIndex
            split_date: Date to split building/testing periods
            symbol: Stock symbol
            
        Returns:
            BacktestReport with all results
        """
        if data is None or len(data) < 20:
            return self._empty_report(symbol)

        # Split data
        building_data = data[data.index < split_date].copy()
        testing_data = data[data.index >= split_date].copy()

        if len(building_data) < 10 or len(testing_data) < 5:
            return self._empty_report(symbol)

        # Step 1: Detect zones on building period
        zones = self.zone_scanner.detect_zones(building_data.reset_index(drop=True), symbol)

        if not zones:
            return BacktestReport(
                symbol=symbol,
                building_start=str(building_data.index[0]),
                building_end=str(building_data.index[-1]),
                testing_start=str(testing_data.index[0]),
                testing_end=str(testing_data.index[-1]),
                total_zones_found=0,
                zones_triggered=0,
                targets_hit=0,
                sl_hit=0,
                pending=0,
                win_rate=0.0,
                total_pnl=0.0,
                avg_rr_achieved=0.0,
                max_win=0.0,
                max_loss=0.0,
                trade_results=[],
                zones=zones,
                building_data=building_data,
                testing_data=testing_data
            )

        # Step 2: Simulate forward through testing period
        trade_results = []
        for zone in zones:
            result = self._simulate_zone(zone, testing_data)
            trade_results.append(result)

        # Step 3: Calculate statistics
        triggered = [r for r in trade_results if r.triggered]
        targets_hit = [r for r in triggered if r.outcome == "TARGET_HIT"]
        sl_hit = [r for r in triggered if r.outcome == "SL_HIT"]
        pending = [r for r in trade_results if not r.triggered or r.outcome == "PENDING"]

        win_rate = (len(targets_hit) / len(triggered) * 100) if triggered else 0.0
        total_pnl = sum(r.pnl for r in triggered)
        
        rr_values = [r.rr_achieved for r in triggered if r.rr_achieved != 0]
        avg_rr = np.mean(rr_values) if rr_values else 0.0

        pnl_values = [r.pnl for r in triggered]
        max_win = max(pnl_values) if pnl_values else 0.0
        max_loss = min(pnl_values) if pnl_values else 0.0

        return BacktestReport(
            symbol=symbol,
            building_start=str(building_data.index[0]),
            building_end=str(building_data.index[-1]),
            testing_start=str(testing_data.index[0]),
            testing_end=str(testing_data.index[-1]),
            total_zones_found=len(zones),
            zones_triggered=len(triggered),
            targets_hit=len(targets_hit),
            sl_hit=len(sl_hit),
            pending=len(pending),
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_rr_achieved=avg_rr,
            max_win=max_win,
            max_loss=max_loss,
            trade_results=trade_results,
            zones=zones,
            building_data=building_data,
            testing_data=testing_data
        )

    def _simulate_zone(self, zone: Zone, testing_data: pd.DataFrame) -> TradeResult:
        """
        Simulate a single zone through the testing period.
        
        For DEMAND zones: Wait for price to drop to zone_top (entry), then track SL/Target
        For SUPPLY zones: Wait for price to rise to zone_bottom (entry), then track SL/Target
        """
        result = TradeResult(zone=zone)
        
        testing_data_reset = testing_data.reset_index()
        
        triggered = False
        trigger_idx = -1

        for i in range(len(testing_data_reset)):
            candle_high = testing_data_reset['High'].iloc[i]
            candle_low = testing_data_reset['Low'].iloc[i]
            candle_open = testing_data_reset['Open'].iloc[i]

            if not triggered:
                # Check if zone entry is hit
                if zone.zone_type == "DEMAND":
                    # Price must drop to or below zone_top (entry level)
                    if candle_low <= zone.entry:
                        triggered = True
                        trigger_idx = i
                        result.triggered = True
                        result.trigger_price = zone.entry
                        result.candles_to_trigger = i
                        # Get time from index
                        if 'index' in testing_data_reset.columns:
                            result.trigger_time = str(testing_data_reset['index'].iloc[i])
                        elif hasattr(testing_data_reset, 'Datetime'):
                            result.trigger_time = str(testing_data_reset['Datetime'].iloc[i])
                        else:
                            result.trigger_time = f"Candle {i}"
                            
                elif zone.zone_type == "SUPPLY":
                    # Price must rise to or above zone_bottom (entry level)
                    if candle_high >= zone.entry:
                        triggered = True
                        trigger_idx = i
                        result.triggered = True
                        result.trigger_price = zone.entry
                        result.candles_to_trigger = i
                        if 'index' in testing_data_reset.columns:
                            result.trigger_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.trigger_time = f"Candle {i}"
            else:
                # Already triggered - check for SL or Target hit
                if zone.zone_type == "DEMAND":
                    # Check SL first (conservative - if both hit in same candle, count as SL)
                    if candle_low <= zone.stop_loss:
                        result.outcome = "SL_HIT"
                        result.exit_price = zone.stop_loss
                        result.pnl = zone.stop_loss - zone.entry
                        result.pnl_pct = (result.pnl / zone.entry) * 100
                        risk = zone.entry - zone.stop_loss
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break
                    elif candle_high >= zone.target:
                        result.outcome = "TARGET_HIT"
                        result.exit_price = zone.target
                        result.pnl = zone.target - zone.entry
                        result.pnl_pct = (result.pnl / zone.entry) * 100
                        risk = zone.entry - zone.stop_loss
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break

                elif zone.zone_type == "SUPPLY":
                    # For SUPPLY (short): SL is above, Target is below
                    if candle_high >= zone.stop_loss:
                        result.outcome = "SL_HIT"
                        result.exit_price = zone.stop_loss
                        result.pnl = zone.entry - zone.stop_loss  # Negative
                        result.pnl_pct = (result.pnl / zone.entry) * 100
                        risk = zone.stop_loss - zone.entry
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break
                    elif candle_low <= zone.target:
                        result.outcome = "TARGET_HIT"
                        result.exit_price = zone.target
                        result.pnl = zone.entry - zone.target  # Positive for short
                        result.pnl_pct = (result.pnl / zone.entry) * 100
                        risk = zone.stop_loss - zone.entry
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break

        # If triggered but never hit SL or Target
        if triggered and result.outcome == "PENDING":
            result.outcome = "PENDING"
            # Calculate current unrealized P&L based on last candle
            last_close = testing_data_reset['Close'].iloc[-1]
            if zone.zone_type == "DEMAND":
                result.pnl = last_close - zone.entry
            else:
                result.pnl = zone.entry - last_close
            result.pnl_pct = (result.pnl / zone.entry) * 100

        return result

    def _empty_report(self, symbol: str) -> BacktestReport:
        """Return empty report when data is insufficient"""
        return BacktestReport(
            symbol=symbol,
            building_start="N/A",
            building_end="N/A",
            testing_start="N/A",
            testing_end="N/A",
            total_zones_found=0,
            zones_triggered=0,
            targets_hit=0,
            sl_hit=0,
            pending=0,
            win_rate=0.0,
            total_pnl=0.0,
            avg_rr_achieved=0.0,
            max_win=0.0,
            max_loss=0.0,
            trade_results=[],
            zones=[]
        )

    def run_multi_symbol(self, data_dict: dict, split_date: datetime) -> List[BacktestReport]:
        """
        Run backtest across multiple symbols.
        
        Args:
            data_dict: Dict of {symbol: DataFrame}
            split_date: Date to split building/testing
            
        Returns:
            List of BacktestReport objects
        """
        reports = []
        for symbol, data in data_dict.items():
            report = self.run(data, split_date, symbol)
            reports.append(report)
        return reports
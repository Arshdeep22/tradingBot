"""
Backtester Module
-----------------
Tests any trading strategy on historical data.

Approach:
1. Split data into "zone building" period and "testing" period
2. Ask strategy for trade setups on the building period
3. Simulate forward through testing period to check if setups get triggered
4. Track outcomes: Target Hit, SL Hit, or Pending
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import logging

from strategies.zone_scanner import ZoneScanner
from strategies.base_strategy import BaseStrategy, TradeSetup

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Result of a simulated trade"""
    setup: TradeSetup
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
    setups: List[TradeSetup] = field(default_factory=list)
    building_data: Optional[pd.DataFrame] = None
    testing_data: Optional[pd.DataFrame] = None

    @property
    def zones(self):
        """Backward-compat alias for setups (used by older dashboard code)."""
        return self.setups


class Backtester:
    """
    Backtests any strategy that implements BaseStrategy.get_trade_setups().

    Usage:
        bt = Backtester()                         # defaults to ZoneScanner
        bt = Backtester(strategy=MyStrategy())    # any strategy
        report = bt.run(data, split_date, symbol)
    """

    def __init__(self, strategy: BaseStrategy = None, min_score: int = 80, rr_ratio: float = 3.0):
        if strategy is None:
            strategy = ZoneScanner(timeframe="15m", min_score=min_score, rr_ratio=rr_ratio)
        self.strategy = strategy
        self.zone_scanner = strategy  # backward-compat alias used by Test Strategy page
        self.commission_pct = 0.001   # 0.1% per trade (NSE charges + brokerage)
        self.slippage_pct = 0.002     # 0.2% slippage on entry

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

        # Step 1: Get trade setups from strategy on building period
        setups = self.strategy.get_trade_setups(building_data.reset_index(drop=True), symbol)

        if not setups:
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
                setups=[],
                building_data=building_data,
                testing_data=testing_data
            )

        # Step 2: Simulate forward through testing period
        trade_results = []
        for setup in setups:
            result = self._simulate_setup(setup, testing_data)
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
            total_zones_found=len(setups),
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
            setups=setups,
            building_data=building_data,
            testing_data=testing_data
        )

    def _simulate_setup(self, setup: TradeSetup, testing_data: pd.DataFrame) -> TradeResult:
        """
        Simulate a single trade setup through the testing period.

        For BUY setups:  triggered when price drops to entry, exits at SL or target.
        For SELL setups: triggered when price rises to entry, exits at SL or target.

        Applies realistic commission (0.1%) and slippage (0.2%) to every trade.
        """
        result = TradeResult(setup=setup)

        testing_data_reset = testing_data.reset_index()

        is_buy = setup.side == "BUY"

        # Effective entry after slippage (assume worse fill on entry)
        effective_entry = setup.entry * (1 + self.slippage_pct) if is_buy else setup.entry * (1 - self.slippage_pct)

        # Commission cost: charged on entry + exit (both legs)
        commission_cost = setup.entry * self.commission_pct * 2

        triggered = False
        trigger_idx = -1

        for i in range(len(testing_data_reset)):
            candle_high = testing_data_reset['High'].iloc[i]
            candle_low = testing_data_reset['Low'].iloc[i]

            if not triggered:
                # Check if entry is hit
                if is_buy and candle_low <= setup.entry:
                    triggered = True
                elif not is_buy and candle_high >= setup.entry:
                    triggered = True

                if triggered:
                    trigger_idx = i
                    result.triggered = True
                    result.trigger_price = effective_entry
                    result.candles_to_trigger = i
                    if 'index' in testing_data_reset.columns:
                        result.trigger_time = str(testing_data_reset['index'].iloc[i])
                    else:
                        result.trigger_time = f"Candle {i}"
            else:
                # Already triggered — check SL then Target
                if is_buy:
                    if candle_low <= setup.stop_loss:
                        result.outcome = "SL_HIT"
                        result.exit_price = setup.stop_loss
                        raw_pnl = setup.stop_loss - effective_entry
                        result.pnl = raw_pnl - commission_cost
                        result.pnl_pct = (result.pnl / effective_entry) * 100
                        risk = effective_entry - setup.stop_loss
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break
                    elif candle_high >= setup.target:
                        result.outcome = "TARGET_HIT"
                        result.exit_price = setup.target
                        raw_pnl = setup.target - effective_entry
                        result.pnl = raw_pnl - commission_cost
                        result.pnl_pct = (result.pnl / effective_entry) * 100
                        risk = effective_entry - setup.stop_loss
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break
                else:  # SELL
                    if candle_high >= setup.stop_loss:
                        result.outcome = "SL_HIT"
                        result.exit_price = setup.stop_loss
                        raw_pnl = effective_entry - setup.stop_loss  # negative
                        result.pnl = raw_pnl - commission_cost
                        result.pnl_pct = (result.pnl / effective_entry) * 100
                        risk = setup.stop_loss - effective_entry
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break
                    elif candle_low <= setup.target:
                        result.outcome = "TARGET_HIT"
                        result.exit_price = setup.target
                        raw_pnl = effective_entry - setup.target  # positive for short
                        result.pnl = raw_pnl - commission_cost
                        result.pnl_pct = (result.pnl / effective_entry) * 100
                        risk = setup.stop_loss - effective_entry
                        result.rr_achieved = result.pnl / risk if risk > 0 else 0
                        result.candles_to_exit = i - trigger_idx
                        if 'index' in testing_data_reset.columns:
                            result.exit_time = str(testing_data_reset['index'].iloc[i])
                        else:
                            result.exit_time = f"Candle {i}"
                        break

        # If triggered but never hit SL or Target — unrealized P&L
        if triggered and result.outcome == "PENDING":
            last_close = testing_data_reset['Close'].iloc[-1]
            result.pnl = (last_close - effective_entry if is_buy else effective_entry - last_close) - commission_cost
            result.pnl_pct = (result.pnl / effective_entry) * 100

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
            setups=[]
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

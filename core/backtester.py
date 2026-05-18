"""
Backtester Module
-----------------
Tests any trading strategy on historical data.

Delegates trade simulation to core/trade_simulator.py and uses
models from core/backtester_models.py.

Approach:
1. Split data into "zone building" period and "testing" period
2. Ask strategy for trade setups on the building period
3. Simulate forward through testing period to check if setups get triggered
4. Track outcomes: Target Hit, SL Hit, Expired, or Cancelled
"""

import pandas as pd
import numpy as np
from typing import List
from datetime import datetime
import logging

from strategies.zone_scanner import ZoneScanner
from strategies.base_strategy import BaseStrategy, TradeSetup
from .backtester_models import TradeResult, BacktestReport
from .trade_simulator import simulate_setup

logger = logging.getLogger(__name__)

# 3 trading days on 15m timeframe = ~75 bars (25 bars/day × 3)
DEFAULT_MAX_HOLDING_BARS = 75


class Backtester:
    """
    Backtests any strategy that implements BaseStrategy.get_trade_setups().

    Usage:
        bt = Backtester()                         # defaults to ZoneScanner
        bt = Backtester(strategy=MyStrategy())    # any strategy
        report = bt.run(data, split_date, symbol)
    """

    def __init__(self, strategy: BaseStrategy = None, min_score: int = 80,
                 rr_ratio: float = 3.0, max_holding_bars: int = DEFAULT_MAX_HOLDING_BARS):
        if strategy is None:
            strategy = ZoneScanner(timeframe="15m", min_score=min_score, rr_ratio=rr_ratio)
        self.strategy = strategy
        self.zone_scanner = strategy  # backward-compat alias used by Test Strategy page
        self.commission_pct = 0.001   # 0.1% per trade (NSE charges + brokerage)
        self.slippage_pct = 0.002     # 0.2% slippage on entry
        self.max_holding_bars = max_holding_bars

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
                expired=0,
                cancelled=0,
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
            result = simulate_setup(
                setup, testing_data, self.max_holding_bars,
                self.commission_pct, self.slippage_pct
            )
            trade_results.append(result)

        # Step 3: Calculate statistics
        report = self._build_report(
            symbol, building_data, testing_data, setups, trade_results
        )
        return report

    def _build_report(self, symbol: str, building_data: pd.DataFrame,
                      testing_data: pd.DataFrame, setups: List[TradeSetup],
                      trade_results: List[TradeResult]) -> BacktestReport:
        """Calculate statistics and build the BacktestReport."""
        triggered = [r for r in trade_results if r.triggered]
        targets_hit = [r for r in triggered if r.outcome == "TARGET_HIT"]
        sl_hit = [r for r in triggered if r.outcome == "SL_HIT"]
        expired = [r for r in triggered if r.outcome == "EXPIRED"]
        cancelled = [r for r in trade_results if r.outcome == "CANCELLED"]

        # Win rate: TARGET_HIT and profitable EXPIRED are wins
        resolved = [r for r in triggered if r.outcome in ("TARGET_HIT", "SL_HIT", "EXPIRED")]
        wins = len(targets_hit) + len([r for r in expired if r.pnl > 0])
        win_rate = (wins / len(resolved) * 100) if resolved else 0.0

        # P&L only from resolved trades
        total_pnl = sum(r.pnl for r in resolved)

        rr_values = [r.rr_achieved for r in resolved if r.rr_achieved != 0]
        avg_rr = np.mean(rr_values) if rr_values else 0.0

        pnl_values = [r.pnl for r in resolved]
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
            expired=len(expired),
            cancelled=len(cancelled),
            pending=len(cancelled),  # backward compat
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

    def _empty_report(self, symbol: str) -> BacktestReport:
        """Return empty report when data is insufficient."""
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
            expired=0,
            cancelled=0,
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
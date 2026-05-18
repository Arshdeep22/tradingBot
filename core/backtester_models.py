"""
Backtester Models
-----------------
Data classes for backtest results and reports.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

from strategies.base_strategy import TradeSetup


@dataclass
class TradeResult:
    """Result of a simulated trade"""
    setup: TradeSetup
    triggered: bool = False
    trigger_time: str = ""
    trigger_price: float = 0.0
    outcome: str = "CANCELLED"  # "TARGET_HIT", "SL_HIT", "EXPIRED", "CANCELLED"
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
    expired: int
    cancelled: int
    pending: int  # kept for backward compat
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
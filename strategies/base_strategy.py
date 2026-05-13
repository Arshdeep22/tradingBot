"""
Base Strategy - Abstract class that all strategies must implement.
To create a new strategy:
1. Create a new file in the strategies/ folder
2. Inherit from BaseStrategy
3. Implement generate_signal() and get_parameters()
4. Register it in strategies/__init__.py STRATEGY_REGISTRY
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, TYPE_CHECKING
import pandas as pd


class Signal(Enum):
    """Trading signals"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSignal:
    """Represents a trading signal with metadata"""

    def __init__(self, signal: Signal, symbol: str, price: float = 0.0,
                 stop_loss: float = 0.0, target: float = 0.0, reason: str = ""):
        self.signal = signal
        self.symbol = symbol
        self.price = price
        self.stop_loss = stop_loss
        self.target = target
        self.reason = reason

    def __repr__(self):
        return (f"TradeSignal({self.signal.value}, {self.symbol}, "
                f"price={self.price}, SL={self.stop_loss}, Target={self.target})")


@dataclass
class TradeSetup:
    """
    Generic trade opportunity returned by any strategy.
    Used by the Backtester and bot_runner — strategies never return Zone objects directly.
    """
    symbol: str
    side: str           # "BUY" or "SELL"
    entry: float
    stop_loss: float
    target: float
    score: int = 0      # confidence 0-100 (optional, used for ranking)
    reasoning: str = ""


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Every strategy must implement:
    - generate_signal(): Returns BUY/SELL/HOLD for the most recent bar
    - get_parameters(): Returns dict of tunable parameters

    Optionally override:
    - get_trade_setups(): Returns ALL current setups (default wraps generate_signal into one)
      Override this when your strategy can detect multiple opportunities per symbol per scan.
    """

    def __init__(self, name: str, timeframe: str = "15m"):
        self.name = name
        self.timeframe = timeframe

    @abstractmethod
    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """
        Analyze market data and generate a trading signal.

        Args:
            data: DataFrame with OHLCV data (columns: Open, High, Low, Close, Volume)
            symbol: Stock symbol

        Returns:
            TradeSignal with BUY, SELL, or HOLD signal
        """
        pass

    @abstractmethod
    def get_parameters(self) -> dict:
        """Return strategy parameters for logging/display"""
        pass

    def get_trade_setups(self, data: pd.DataFrame, symbol: str) -> List[TradeSetup]:
        """
        Return all current trade setups for a symbol.

        Default implementation wraps generate_signal() into a single TradeSetup.
        Override this in strategies that can detect multiple setups per scan
        (e.g. ZoneScanner returns one TradeSetup per zone).

        Returns:
            List of TradeSetup objects (empty list = no opportunity)
        """
        signal = self.generate_signal(data, symbol)
        if signal.signal == Signal.HOLD or not signal.price:
            return []
        return [TradeSetup(
            symbol=symbol,
            side="BUY" if signal.signal == Signal.BUY else "SELL",
            entry=signal.price,
            stop_loss=signal.stop_loss or 0.0,
            target=signal.target or 0.0,
            reasoning=signal.reason or "",
        )]

    def __repr__(self):
        return f"Strategy({self.name}, timeframe={self.timeframe})"
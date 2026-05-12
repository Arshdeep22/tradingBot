"""
Base Strategy - Abstract class that all strategies must implement.
To create a new strategy:
1. Create a new file in the strategies/ folder
2. Inherit from BaseStrategy
3. Implement the generate_signal() method
"""

from abc import ABC, abstractmethod
from enum import Enum
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


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Every strategy must implement:
    - name: Strategy name
    - generate_signal(): Returns BUY/SELL/HOLD signal based on data
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

    def __repr__(self):
        return f"Strategy({self.name}, timeframe={self.timeframe})"
"""
Broker Interface Module
-----------------------
Abstract broker interface that can be implemented by:
- PaperBroker (for paper trading / simulation)
- ZerodhaBroker (for live trading via Kite Connect)
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Order:
    """Represents a trade order"""

    def __init__(self, order_id: str, symbol: str, order_type: str,
                 side: str, quantity: int, price: float,
                 stop_loss: float = 0.0, target: float = 0.0,
                 status: str = "PENDING"):
        self.order_id = order_id
        self.symbol = symbol
        self.order_type = order_type  # MARKET, LIMIT
        self.side = side  # BUY, SELL
        self.quantity = quantity
        self.price = price
        self.stop_loss = stop_loss
        self.target = target
        self.status = status  # PENDING, EXECUTED, CANCELLED, REJECTED

    def __repr__(self):
        return (f"Order({self.order_id}, {self.side} {self.quantity} {self.symbol} "
                f"@ {self.price}, status={self.status})")


class Position:
    """Represents an open position"""

    def __init__(self, symbol: str, side: str, quantity: int,
                 entry_price: float, current_price: float = 0.0,
                 stop_loss: float = 0.0, target: float = 0.0):
        self.symbol = symbol
        self.side = side  # BUY (long) or SELL (short)
        self.quantity = quantity
        self.entry_price = entry_price
        self.current_price = current_price
        self.stop_loss = stop_loss
        self.target = target

    @property
    def pnl(self) -> float:
        """Calculate unrealized P&L"""
        if self.side == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - self.current_price) * self.quantity

    @property
    def pnl_percent(self) -> float:
        """Calculate P&L percentage"""
        if self.entry_price == 0:
            return 0.0
        if self.side == "BUY":
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.current_price) / self.entry_price) * 100

    def __repr__(self):
        return (f"Position({self.side} {self.quantity} {self.symbol} "
                f"@ {self.entry_price}, PnL={self.pnl:.2f})")


class BrokerInterface(ABC):
    """
    Abstract broker interface.
    All broker implementations must inherit from this class.
    """

    @abstractmethod
    def place_order(self, symbol: str, side: str, quantity: int,
                    price: float, order_type: str = "MARKET",
                    stop_loss: float = 0.0, target: float = 0.0) -> Optional[Order]:
        """Place a new order"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        pass

    @abstractmethod
    def get_positions(self) -> list:
        """Get all open positions"""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        pass

    @abstractmethod
    def close_position(self, symbol: str, price: float = 0.0) -> Optional[Order]:
        """Close an existing position"""
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """Get available balance"""
        pass

    @abstractmethod
    def get_portfolio_value(self) -> float:
        """Get total portfolio value (balance + positions)"""
        pass
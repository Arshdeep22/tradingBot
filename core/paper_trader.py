"""
Paper Trader Module
-------------------
Simulates order execution for paper trading.
Implements BrokerInterface for seamless switching to live trading later.
"""

import uuid
from datetime import datetime
from typing import Optional
import logging

from core.broker_interface import BrokerInterface, Order, Position
from config.settings import INITIAL_CAPITAL, MAX_POSITION_SIZE, MAX_OPEN_POSITIONS

logger = logging.getLogger(__name__)


class PaperTrader(BrokerInterface):
    """
    Paper trading broker - simulates real trading without actual money.
    All orders are executed immediately at the given price (market orders).
    """

    def __init__(self, initial_capital: float = None):
        self.initial_capital = initial_capital or INITIAL_CAPITAL
        self.balance = self.initial_capital
        self.positions: dict = {}  # symbol -> Position
        self.orders: list = []  # Order history
        self.closed_trades: list = []  # Completed trades for P&L tracking

    def place_order(self, symbol: str, side: str, quantity: int,
                    price: float, order_type: str = "MARKET",
                    stop_loss: float = 0.0, target: float = 0.0) -> Optional[Order]:
        """
        Place a paper trade order.
        For paper trading, MARKET orders execute immediately.
        """
        order_id = str(uuid.uuid4())[:8]

        # Validate order
        if side == "BUY":
            cost = price * quantity
            if cost > self.balance:
                logger.warning(f"Insufficient balance. Need {cost}, have {self.balance}")
                order = Order(order_id, symbol, order_type, side, quantity,
                              price, stop_loss, target, status="REJECTED")
                self.orders.append(order)
                return order

            # Check position limits
            if len(self.positions) >= MAX_OPEN_POSITIONS:
                logger.warning(f"Max open positions ({MAX_OPEN_POSITIONS}) reached")
                order = Order(order_id, symbol, order_type, side, quantity,
                              price, stop_loss, target, status="REJECTED")
                self.orders.append(order)
                return order

            # Check position size limit
            max_allowed = self.initial_capital * MAX_POSITION_SIZE
            if cost > max_allowed:
                logger.warning(f"Position size {cost} exceeds max allowed {max_allowed}")
                order = Order(order_id, symbol, order_type, side, quantity,
                              price, stop_loss, target, status="REJECTED")
                self.orders.append(order)
                return order

            # Execute BUY order
            self.balance -= cost
            self.positions[symbol] = Position(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                entry_price=price,
                current_price=price,
                stop_loss=stop_loss,
                target=target
            )

            order = Order(order_id, symbol, order_type, side, quantity,
                          price, stop_loss, target, status="EXECUTED")
            self.orders.append(order)

            logger.info(f"BUY Order Executed: {quantity} {symbol} @ {price} | "
                        f"SL: {stop_loss} | Target: {target} | Balance: {self.balance:.2f}")
            return order

        elif side == "SELL":
            # Close existing position
            if symbol not in self.positions:
                logger.warning(f"No position found for {symbol} to sell")
                order = Order(order_id, symbol, order_type, side, quantity,
                              price, stop_loss, target, status="REJECTED")
                self.orders.append(order)
                return order

            position = self.positions[symbol]
            proceeds = price * position.quantity
            self.balance += proceeds

            # Record closed trade
            pnl = (price - position.entry_price) * position.quantity
            closed_trade = {
                "symbol": symbol,
                "side": position.side,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "exit_price": price,
                "pnl": pnl,
                "pnl_percent": ((price - position.entry_price) / position.entry_price) * 100,
                "entry_time": datetime.now().isoformat(),
                "exit_time": datetime.now().isoformat(),
                "stop_loss": position.stop_loss,
                "target": position.target
            }
            self.closed_trades.append(closed_trade)

            # Remove position
            del self.positions[symbol]

            order = Order(order_id, symbol, order_type, side, position.quantity,
                          price, status="EXECUTED")
            self.orders.append(order)

            logger.info(f"SELL Order Executed: {position.quantity} {symbol} @ {price} | "
                        f"PnL: {pnl:.2f} ({closed_trade['pnl_percent']:.2f}%) | "
                        f"Balance: {self.balance:.2f}")
            return order

        return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order (paper trading executes immediately, so rarely used)"""
        for order in self.orders:
            if order.order_id == order_id and order.status == "PENDING":
                order.status = "CANCELLED"
                logger.info(f"Order {order_id} cancelled")
                return True
        return False

    def get_positions(self) -> list:
        """Get all open positions"""
        return list(self.positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol"""
        return self.positions.get(symbol)

    def close_position(self, symbol: str, price: float = 0.0) -> Optional[Order]:
        """Close an existing position at given price"""
        if symbol in self.positions:
            position = self.positions[symbol]
            return self.place_order(symbol, "SELL", position.quantity, price)
        return None

    def get_balance(self) -> float:
        """Get available cash balance"""
        return self.balance

    def get_portfolio_value(self) -> float:
        """Get total portfolio value (cash + positions value)"""
        positions_value = sum(
            pos.current_price * pos.quantity for pos in self.positions.values()
        )
        return self.balance + positions_value

    def update_positions(self, prices: dict):
        """
        Update current prices for all open positions.
        Also checks stop loss and target hits.

        Args:
            prices: Dict of symbol -> current_price
        """
        symbols_to_close = []

        for symbol, position in self.positions.items():
            if symbol in prices:
                position.current_price = prices[symbol]

                # Check stop loss hit
                if position.stop_loss > 0 and position.current_price <= position.stop_loss:
                    logger.info(f"STOP LOSS HIT for {symbol} @ {position.current_price}")
                    symbols_to_close.append((symbol, position.stop_loss))

                # Check target hit
                elif position.target > 0 and position.current_price >= position.target:
                    logger.info(f"TARGET HIT for {symbol} @ {position.current_price}")
                    symbols_to_close.append((symbol, position.target))

        # Close positions that hit SL/Target
        for symbol, price in symbols_to_close:
            self.close_position(symbol, price)

    def get_trade_history(self) -> list:
        """Get all closed trades"""
        return self.closed_trades

    def get_summary(self) -> dict:
        """Get portfolio summary"""
        total_trades = len(self.closed_trades)
        winning_trades = len([t for t in self.closed_trades if t['pnl'] > 0])
        losing_trades = len([t for t in self.closed_trades if t['pnl'] < 0])

        total_pnl = sum(t['pnl'] for t in self.closed_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        return {
            "initial_capital": self.initial_capital,
            "current_balance": self.balance,
            "portfolio_value": self.get_portfolio_value(),
            "total_pnl": total_pnl,
            "total_pnl_percent": (total_pnl / self.initial_capital) * 100,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "open_positions": len(self.positions)
        }
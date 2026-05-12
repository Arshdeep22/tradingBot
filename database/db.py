"""
Database Module
---------------
SQLite database for storing trade history and performance metrics.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Ensure database directory exists
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "trades.db")


class DatabaseManager:
    """Manages SQLite database for trade storage"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._create_tables()

    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables(self):
        """Create required tables if they don't exist"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL,
                target REAL,
                pnl REAL,
                pnl_percent REAL,
                strategy TEXT,
                reason TEXT,
                status TEXT DEFAULT 'OPEN',
                entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                exit_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Pending orders table (limit orders waiting for price to hit entry)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                stop_loss REAL,
                target REAL,
                strategy TEXT,
                reason TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                executed_at TIMESTAMP
            )
        """)

        # Portfolio snapshots table (for tracking equity curve)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                balance REAL,
                portfolio_value REAL,
                open_positions INTEGER,
                total_pnl REAL
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    # ============================================================
    # PENDING ORDERS
    # ============================================================

    def save_pending_order(self, symbol: str, side: str, quantity: int,
                           entry_price: float, stop_loss: float = 0.0,
                           target: float = 0.0, strategy: str = "",
                           reason: str = "", expires_at: str = None) -> int:
        """
        Save a pending (limit) order that will execute when price hits entry.

        Returns:
            Order ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO pending_orders (symbol, side, quantity, entry_price, stop_loss,
                                       target, strategy, reason, status, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
        """, (symbol, side, quantity, entry_price, stop_loss, target,
              strategy, reason, expires_at))

        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Pending order saved: ID={order_id}, {side} {quantity} {symbol} @ {entry_price}")
        return order_id

    def get_pending_orders(self) -> list:
        """Get all pending orders"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM pending_orders 
            WHERE status = 'PENDING' 
            ORDER BY created_at DESC
        """)
        orders = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return orders

    def execute_pending_order(self, order_id: int) -> dict:
        """Mark a pending order as executed and create a trade"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get the pending order
        cursor.execute("SELECT * FROM pending_orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()

        if order is None:
            conn.close()
            return None

        order_dict = dict(order)

        # Mark as executed
        cursor.execute("""
            UPDATE pending_orders 
            SET status = 'EXECUTED', executed_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), order_id))

        # Create the actual trade
        cursor.execute("""
            INSERT INTO trades (symbol, side, quantity, entry_price, stop_loss,
                              target, strategy, reason, status, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (order_dict['symbol'], order_dict['side'], order_dict['quantity'],
              order_dict['entry_price'], order_dict['stop_loss'], order_dict['target'],
              order_dict['strategy'], order_dict['reason'], datetime.now().isoformat()))

        conn.commit()
        conn.close()

        logger.info(f"Pending order {order_id} executed: {order_dict['side']} {order_dict['symbol']} @ {order_dict['entry_price']}")
        return order_dict

    def cancel_pending_order(self, order_id: int):
        """Cancel a pending order"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE pending_orders SET status = 'CANCELLED' WHERE id = ?
        """, (order_id,))

        conn.commit()
        conn.close()
        logger.info(f"Pending order {order_id} cancelled")

    def expire_old_orders(self, max_age_days: int = 3):
        """Expire pending orders older than max_age_days"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE pending_orders 
            SET status = 'EXPIRED' 
            WHERE status = 'PENDING' 
            AND created_at < datetime('now', ?)
        """, (f'-{max_age_days} days',))

        expired_count = cursor.rowcount
        conn.commit()
        conn.close()

        if expired_count > 0:
            logger.info(f"Expired {expired_count} old pending orders")

    # ============================================================
    # TRADES
    # ============================================================

    def save_trade(self, symbol: str, side: str, quantity: int,
                   entry_price: float, stop_loss: float = 0.0,
                   target: float = 0.0, strategy: str = "",
                   reason: str = "") -> int:
        """
        Save a new trade to the database.

        Returns:
            Trade ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO trades (symbol, side, quantity, entry_price, stop_loss,
                              target, strategy, reason, status, entry_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
        """, (symbol, side, quantity, entry_price, stop_loss, target,
              strategy, reason, datetime.now().isoformat()))

        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Trade saved: ID={trade_id}, {side} {quantity} {symbol} @ {entry_price}")
        return trade_id

    def close_trade(self, symbol: str, exit_price: float,
                    pnl: float = 0.0, reason: str = ""):
        """Close an open trade"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Find the open trade for this symbol
        cursor.execute("""
            SELECT id, entry_price, quantity, side FROM trades
            WHERE symbol = ? AND status = 'OPEN'
            ORDER BY entry_time DESC LIMIT 1
        """, (symbol,))

        trade = cursor.fetchone()
        if trade is None:
            logger.warning(f"No open trade found for {symbol}")
            conn.close()
            return

        trade_id = trade['id']
        entry_price = trade['entry_price']
        quantity = trade['quantity']
        side = trade['side']

        # Calculate PnL if not provided
        if pnl == 0.0:
            if side == "BUY":
                pnl = (exit_price - entry_price) * quantity
            else:  # SELL (short)
                pnl = (entry_price - exit_price) * quantity

        pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        if side == "SELL":
            pnl_percent = -pnl_percent

        cursor.execute("""
            UPDATE trades
            SET exit_price = ?, pnl = ?, pnl_percent = ?,
                status = 'CLOSED', exit_time = ?, reason = reason || ' | Exit: ' || ?
            WHERE id = ?
        """, (exit_price, pnl, pnl_percent, datetime.now().isoformat(), reason, trade_id))

        conn.commit()
        conn.close()

        logger.info(f"Trade closed: ID={trade_id}, {symbol} @ {exit_price}, PnL={pnl:.2f}")

    def get_all_trades(self) -> list:
        """Get all trades (open and closed)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades ORDER BY entry_time DESC")
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def get_open_trades(self) -> list:
        """Get all open trades"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC")
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def get_closed_trades(self) -> list:
        """Get all closed trades"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC")
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def get_performance_metrics(self) -> dict:
        """Calculate performance metrics from trade history"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trades WHERE status = 'CLOSED'")
        trades = cursor.fetchall()
        conn.close()

        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0
            }

        total_trades = len(trades)
        pnls = [trade['pnl'] for trade in trades]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]

        total_pnl = sum(pnls)
        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0

        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        # Calculate max drawdown
        cumulative_pnl = []
        running_total = 0
        for pnl in pnls:
            running_total += pnl
            cumulative_pnl.append(running_total)

        peak = 0
        max_drawdown = 0
        for value in cumulative_pnl:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return {
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            "max_profit": round(max(pnls), 2) if pnls else 0,
            "max_loss": round(min(pnls), 2) if pnls else 0,
            "avg_win": round(sum(winning_trades) / len(winning_trades), 2) if winning_trades else 0,
            "avg_loss": round(sum(losing_trades) / len(losing_trades), 2) if losing_trades else 0,
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown, 2)
        }

    def save_portfolio_snapshot(self, balance: float, portfolio_value: float,
                                 open_positions: int, total_pnl: float):
        """Save a portfolio snapshot for equity curve tracking"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO portfolio_snapshots (balance, portfolio_value, open_positions, total_pnl)
            VALUES (?, ?, ?, ?)
        """, (balance, portfolio_value, open_positions, total_pnl))

        conn.commit()
        conn.close()

    def get_portfolio_history(self) -> list:
        """Get portfolio value history for equity curve"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp ASC")
        snapshots = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return snapshots

    def get_trades_by_strategy(self, strategy: str) -> list:
        """Get trades filtered by strategy name"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM trades WHERE strategy = ? ORDER BY entry_time DESC
        """, (strategy,))
        trades = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return trades

    def clear_all_trades(self):
        """Clear all trades (use with caution!)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM trades")
        cursor.execute("DELETE FROM portfolio_snapshots")
        cursor.execute("DELETE FROM pending_orders")

        conn.commit()
        conn.close()
        logger.warning("All trades cleared from database")
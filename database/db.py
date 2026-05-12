"""
Database Manager - Facade combining all database operations.
Uses mixins for modularity: trades, orders, metrics.
Supports SQLite (local) and Supabase (cloud) automatically.
"""
from database.base import BaseDB
from database.trades import TradesMixin
from database.orders import OrdersMixin
from database.metrics import MetricsMixin


class DatabaseManager(BaseDB, TradesMixin, OrdersMixin, MetricsMixin):
    """
    Unified database manager.

    - Locally: uses SQLite (database/trades.db)
    - On Streamlit Cloud: uses Supabase (auto-detected from secrets)

    Usage:
        db = DatabaseManager()
        db.save_trade(...)
        db.get_all_trades()
    """
    pass
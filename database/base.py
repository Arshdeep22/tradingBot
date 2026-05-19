"""Database Base - Connection and table setup for SQLite and Supabase."""
import os
import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "trades.db")


def get_supabase_config():
    """Get Supabase config from Streamlit secrets, .streamlit/secrets.toml, or env vars."""
    # 1. Streamlit runtime (dashboard)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'supabase' in st.secrets:
            return {'url': st.secrets['supabase']['url'], 'key': st.secrets['supabase']['key']}
    except Exception:
        pass

    # 2. .streamlit/secrets.toml (local terminal — bot_runner.py, backtester, etc.)
    try:
        import tomllib
        secrets_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".streamlit", "secrets.toml"
        )
        if os.path.exists(secrets_path):
            with open(secrets_path, "rb") as f:
                secrets = tomllib.load(f)
            sb = secrets.get("supabase", {})
            if sb.get("url") and sb.get("key"):
                return {'url': sb["url"], 'key': sb["key"]}
    except Exception:
        pass

    # 3. Environment variables (GitHub Actions)
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_KEY', '')
    if url and key:
        return {'url': url, 'key': key}

    return None


class BaseDB:
    """Base database class with connection logic."""

    def __init__(self, db_path=None, force_sqlite=False):
        self.db_path = db_path or DB_PATH
        self.use_supabase = False
        self.supabase_client = None

        if not force_sqlite:
            config = get_supabase_config()
            if config:
                try:
                    from supabase import create_client
                    self.supabase_client = create_client(config['url'], config['key'])
                    self.use_supabase = True
                    logger.info("Connected to Supabase")
                except Exception as e:
                    logger.warning(f"Supabase failed: {e}. Using SQLite.")

        if not self.use_supabase:
            self._create_tables_sqlite()
            self._run_sqlite_migrations()
            logger.info(f"Using SQLite: {self.db_path}")
        else:
            self._warn_supabase_schema()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_tables_sqlite(self):
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity INTEGER NOT NULL, entry_price REAL NOT NULL,
            exit_price REAL, stop_loss REAL, target REAL,
            pnl REAL, pnl_percent REAL,
            strategy TEXT, reason TEXT,
            status TEXT DEFAULT 'OPEN',
            entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            exit_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS pending_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL, side TEXT NOT NULL,
            quantity INTEGER NOT NULL, entry_price REAL NOT NULL,
            stop_loss REAL, target REAL,
            strategy TEXT, reason TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP, executed_at TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            balance REAL, portfolio_value REAL,
            open_positions INTEGER, total_pnl REAL)""")
        conn.commit()
        conn.close()

    def _warn_supabase_schema(self):
        """Check if management columns exist on Supabase and warn if not."""
        _mgmt_cols = {"current_sl", "breakeven_applied", "base_candles"}
        try:
            res = self.supabase_client.table("trades").select(
                "current_sl,breakeven_applied,base_candles"
            ).limit(1).execute()
            _ = res.data  # no error = columns exist
        except Exception:
            logger.warning(
                "Supabase trades table is missing bot_runner management columns. "
                "Run the ALTER TABLE statements from database/supabase_setup.sql "
                "in your Supabase SQL Editor."
            )
        """Add new columns to existing tables without dropping data."""
        new_trade_columns = [
            ("current_sl", "REAL"),
            ("breakeven_applied", "INTEGER DEFAULT 0"),
            ("partial_taken", "INTEGER DEFAULT 0"),
            ("high_since_entry", "REAL DEFAULT 0.0"),
            ("low_since_entry", "REAL DEFAULT 0.0"),
            ("base_candles", "INTEGER DEFAULT 2"),
            ("entry_candle_index", "INTEGER DEFAULT 0"),
            ("trail_method", "TEXT DEFAULT 'ATR'"),
        ]
        conn = self._get_connection()
        c = conn.cursor()
        c.execute("PRAGMA table_info(trades)")
        existing = {row["name"] for row in c.fetchall()}
        for col_name, col_def in new_trade_columns:
            if col_name not in existing:
                c.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_def}")
                logger.info(f"Migration: added trades.{col_name}")
        conn.commit()
        conn.close()
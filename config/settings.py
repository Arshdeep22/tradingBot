"""
Trading Bot Configuration Settings
"""

# ============== GENERAL SETTINGS ==============
BOT_NAME = "TradingBot"
LOG_LEVEL = "INFO"
LOG_FILE = "logs/bot.log"

# ============== TRADING SETTINGS ==============
# Symbols to trade (NSE stocks - append .NS for Yahoo Finance)
# Nifty 50 Companies
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS",
    "LT.NS", "HCLTECH.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS", "DMART.NS", "ULTRACEMCO.NS",
    "WIPRO.NS", "ONGC.NS", "NTPC.NS", "TATAMOTORS.NS", "JSWSTEEL.NS",
    "M&M.NS", "POWERGRID.NS", "TATASTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS",
    "COALINDIA.NS", "HINDALCO.NS", "BAJAJFINSV.NS", "TECHM.NS", "HDFCLIFE.NS",
    "INDUSINDBK.NS", "DRREDDY.NS", "DIVISLAB.NS", "CIPLA.NS", "GRASIM.NS",
    "SBILIFE.NS", "BPCL.NS", "BRITANNIA.NS", "NESTLEIND.NS", "TATACONSUM.NS",
    "APOLLOHOSP.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "UPL.NS", "LTIM.NS"
]

# Default watchlist (subset for quick scanning)
SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]

# Timeframes supported: 1m, 3m, 5m, 15m, 30m, 1h, 1d
DEFAULT_TIMEFRAME = "15m"
SUPPORTED_TIMEFRAMES = ["3m", "5m", "15m"]

# ============== PAPER TRADING SETTINGS ==============
INITIAL_CAPITAL = 100000  # Starting capital in INR
MAX_POSITION_SIZE = 0.1   # Max 10% of capital per trade

# ============== RISK MANAGEMENT ==============
# Per-trade SL/TP: keep in ALL modes — these are strategy mechanics, not risk controls.
# Without them, win/loss signals are meaningless and the learning loop breaks.
STOP_LOSS_PERCENT = 1.0   # 1% stop loss (per-trade, strategy-level)
TARGET_PERCENT = 2.0      # 2% target (per-trade, strategy-level)
TRAILING_STOP = False

# ============== PAPER TRADING MODE ==============
# PAPER_TRADING_MODE=True  → relaxed aggregate limits for maximum learning throughput
# PAPER_TRADING_MODE=False → strict risk controls for real money
# To go live: add GitHub Actions secret PAPER_TRADING_MODE=false (no code change needed)
import os as _os
PAPER_TRADING_MODE = _os.environ.get("PAPER_TRADING_MODE", "true").lower() not in ("false", "0", "no")

MAX_OPEN_POSITIONS = 12 if PAPER_TRADING_MODE else 5     # Paper: 12 slots; Real: 5
MAX_DAILY_LOSS_PCT = 50.0 if PAPER_TRADING_MODE else 1.5  # Paper: effectively off; Real: 1.5%

# ============== DATA SETTINGS ==============
DATA_SOURCE = "yfinance"  # Options: "yfinance", "zerodha"
LOOKBACK_PERIOD = "5d"    # How much historical data to fetch

# ============== DATABASE ==============
DATABASE_URL = "sqlite:///database/trades.db"

# ============== BROKER SETTINGS ==============
BROKER = "paper"  # Options: "paper", "zerodha"

# Zerodha settings (for future use)
ZERODHA_API_KEY = ""
ZERODHA_API_SECRET = ""
ZERODHA_ACCESS_TOKEN = ""

# ============== STRATEGY SETTINGS ==============
ACTIVE_STRATEGY = "Supply & Demand Zones"  # Must match a key in strategies.STRATEGY_REGISTRY

# EMA Crossover Strategy Settings
EMA_FAST_PERIOD = 9
EMA_SLOW_PERIOD = 21

# ============== SCHEDULE SETTINGS ==============
# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# NSE Trading Holidays 2026 (dates when exchange is closed)
from datetime import date as _date
NSE_HOLIDAYS_2026 = {
    _date(2026, 1, 26),   # Republic Day
    _date(2026, 2, 26),   # Mahashivratri
    _date(2026, 3, 20),   # Holi
    _date(2026, 4, 3),    # Good Friday
    _date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    _date(2026, 4, 30),   # Ram Navami
    _date(2026, 5, 1),    # Maharashtra Day
    _date(2026, 8, 15),   # Independence Day
    _date(2026, 8, 27),   # Ganesh Chaturthi
    _date(2026, 10, 2),   # Gandhi Jayanti
    _date(2026, 10, 21),  # Dussehra
    _date(2026, 11, 5),   # Diwali Laxmi Puja
    _date(2026, 11, 6),   # Diwali Balipratipada
    _date(2026, 11, 25),  # Guru Nanak Jayanti
    _date(2026, 12, 25),  # Christmas
}

# How often to check for signals (in seconds)
CHECK_INTERVAL = 60  # Check every 60 seconds
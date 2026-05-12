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
MAX_OPEN_POSITIONS = 5    # Maximum simultaneous positions

# ============== RISK MANAGEMENT ==============
STOP_LOSS_PERCENT = 1.0   # 1% stop loss
TARGET_PERCENT = 2.0      # 2% target (1:2 risk-reward)
TRAILING_STOP = False     # Enable/disable trailing stop

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
ACTIVE_STRATEGY = "ema_crossover"

# EMA Crossover Strategy Settings
EMA_FAST_PERIOD = 9
EMA_SLOW_PERIOD = 21

# ============== SCHEDULE SETTINGS ==============
# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# How often to check for signals (in seconds)
CHECK_INTERVAL = 60  # Check every 60 seconds
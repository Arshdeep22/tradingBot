"""
Trading Bot - Main Entry Point
================================
Start the trading bot with paper trading.

Usage:
    python main.py              # Run in continuous mode (during market hours)
    python main.py --once       # Run one cycle only
    python main.py --backtest   # Run without market hour check
"""

import sys
import os
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import (
    BOT_NAME, LOG_LEVEL, LOG_FILE,
    SYMBOLS, DEFAULT_TIMEFRAME, INITIAL_CAPITAL,
    ACTIVE_STRATEGY
)
from strategies.ema_crossover import EMACrossoverStrategy
from core.paper_trader import PaperTrader
from core.engine import TradingEngine


def setup_logging():
    """Configure logging for the bot"""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Configure logging
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_strategy(strategy_name: str):
    """Get strategy instance by name"""
    strategies = {
        "ema_crossover": EMACrossoverStrategy(timeframe=DEFAULT_TIMEFRAME),
    }

    if strategy_name not in strategies:
        print(f"Unknown strategy: {strategy_name}")
        print(f"Available strategies: {list(strategies.keys())}")
        sys.exit(1)

    return strategies[strategy_name]


def main():
    """Main function to start the trading bot"""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Print banner
    print("=" * 60)
    print(f"  {BOT_NAME} - Paper Trading Mode")
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"  Strategy: {ACTIVE_STRATEGY}")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Timeframe: {DEFAULT_TIMEFRAME}")
    print(f"  Capital: INR {INITIAL_CAPITAL:,.2f}")
    print("=" * 60)
    print()

    # Initialize components
    strategy = get_strategy(ACTIVE_STRATEGY)
    broker = PaperTrader(initial_capital=INITIAL_CAPITAL)

    # Create trading engine
    engine = TradingEngine(
        strategy=strategy,
        broker=broker,
        symbols=SYMBOLS,
        timeframe=DEFAULT_TIMEFRAME
    )

    # Parse command line arguments
    continuous = True
    if "--once" in sys.argv:
        continuous = False
        logger.info("Running in single-cycle mode")
    elif "--backtest" in sys.argv:
        # Override market hours check for backtesting
        engine.is_market_hours = lambda: True
        logger.info("Running in backtest mode (ignoring market hours)")

    # Start the engine
    try:
        engine.start(continuous=continuous)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        engine.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        engine.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
"""
Trading Engine Module
---------------------
Main trading loop that:
1. Fetches market data
2. Runs strategy to generate signals
3. Executes trades via broker
4. Monitors open positions (SL/Target)
"""

import time
import logging
from datetime import datetime

from core.data_fetcher import DataFetcher
from core.paper_trader import PaperTrader
from core.broker_interface import BrokerInterface
from strategies.base_strategy import BaseStrategy, Signal
from database.db import DatabaseManager
from config.settings import (
    SYMBOLS, DEFAULT_TIMEFRAME, CHECK_INTERVAL,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    MAX_POSITION_SIZE, INITIAL_CAPITAL
)

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine that orchestrates the entire trading process.
    """

    def __init__(self, strategy: BaseStrategy, broker: BrokerInterface = None,
                 symbols: list = None, timeframe: str = None):
        self.strategy = strategy
        self.broker = broker or PaperTrader()
        self.symbols = symbols or SYMBOLS
        self.timeframe = timeframe or DEFAULT_TIMEFRAME
        self.data_fetcher = DataFetcher()
        self.db = DatabaseManager()
        self.is_running = False

        logger.info(f"Trading Engine initialized")
        logger.info(f"Strategy: {self.strategy.name}")
        logger.info(f"Symbols: {self.symbols}")
        logger.info(f"Timeframe: {self.timeframe}")

    def is_market_hours(self) -> bool:
        """Check if current time is within market hours (IST)"""
        now = datetime.now()
        market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
        market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)

        # Check if it's a weekday (Monday=0 to Friday=4)
        if now.weekday() > 4:
            return False

        return market_open <= now <= market_close

    def calculate_quantity(self, price: float) -> int:
        """Calculate order quantity based on position sizing rules"""
        max_amount = INITIAL_CAPITAL * MAX_POSITION_SIZE
        available = self.broker.get_balance()
        amount_to_use = min(max_amount, available)

        quantity = int(amount_to_use / price)
        return max(1, quantity)

    def run_once(self):
        """Run one iteration of the trading loop"""
        logger.info(f"--- Running trading cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")

        for symbol in self.symbols:
            try:
                # Step 1: Fetch data
                data = self.data_fetcher.get_data(symbol, self.timeframe)
                if data is None:
                    logger.warning(f"No data for {symbol}, skipping")
                    continue

                # Step 2: Generate signal
                signal = self.strategy.generate_signal(data, symbol)
                logger.info(f"{symbol}: {signal}")

                # Step 3: Execute trade based on signal
                if signal.signal == Signal.BUY:
                    # Check if we already have a position
                    existing_position = self.broker.get_position(symbol)
                    if existing_position is None:
                        quantity = self.calculate_quantity(signal.price)
                        order = self.broker.place_order(
                            symbol=symbol,
                            side="BUY",
                            quantity=quantity,
                            price=signal.price,
                            stop_loss=signal.stop_loss,
                            target=signal.target
                        )
                        if order and order.status == "EXECUTED":
                            # Save to database
                            self.db.save_trade(
                                symbol=symbol,
                                side="BUY",
                                quantity=quantity,
                                entry_price=signal.price,
                                stop_loss=signal.stop_loss,
                                target=signal.target,
                                strategy=self.strategy.name,
                                reason=signal.reason
                            )
                    else:
                        logger.info(f"Already have position in {symbol}, skipping BUY")

                elif signal.signal == Signal.SELL:
                    # Close position if exists
                    existing_position = self.broker.get_position(symbol)
                    if existing_position is not None:
                        order = self.broker.close_position(symbol, signal.price)
                        if order and order.status == "EXECUTED":
                            # Update trade in database
                            pnl = (signal.price - existing_position.entry_price) * existing_position.quantity
                            self.db.close_trade(
                                symbol=symbol,
                                exit_price=signal.price,
                                pnl=pnl,
                                reason=signal.reason
                            )

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)

        # Step 4: Update open positions (check SL/Target)
        self._check_stop_loss_target()

    def _check_stop_loss_target(self):
        """Check if any open positions have hit SL or Target"""
        positions = self.broker.get_positions()
        if not positions:
            return

        # Get current prices for all positions
        prices = {}
        for position in positions:
            price = self.data_fetcher.get_current_price(position.symbol)
            if price > 0:
                prices[position.symbol] = price

        # Update positions (PaperTrader handles SL/Target internally)
        if isinstance(self.broker, PaperTrader):
            self.broker.update_positions(prices)

            # Update database for any closed trades
            for trade in self.broker.closed_trades:
                self.db.close_trade(
                    symbol=trade['symbol'],
                    exit_price=trade['exit_price'],
                    pnl=trade['pnl'],
                    reason="SL/Target Hit"
                )

    def start(self, continuous: bool = True):
        """
        Start the trading engine.

        Args:
            continuous: If True, runs in a loop. If False, runs once.
        """
        logger.info("=" * 50)
        logger.info(f"Starting Trading Engine - {self.strategy.name}")
        logger.info(f"Capital: {INITIAL_CAPITAL} | Symbols: {len(self.symbols)}")
        logger.info("=" * 50)

        self.is_running = True

        if not continuous:
            self.run_once()
            return

        try:
            while self.is_running:
                if self.is_market_hours():
                    self.run_once()
                else:
                    logger.info("Market is closed. Waiting...")

                # Print summary
                if isinstance(self.broker, PaperTrader):
                    summary = self.broker.get_summary()
                    logger.info(f"Portfolio: {summary['portfolio_value']:.2f} | "
                                f"PnL: {summary['total_pnl']:.2f} | "
                                f"Win Rate: {summary['win_rate']:.1f}%")

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Trading Engine stopped by user")
            self.stop()

    def stop(self):
        """Stop the trading engine"""
        self.is_running = False
        logger.info("Trading Engine stopped")

        # Print final summary
        if isinstance(self.broker, PaperTrader):
            summary = self.broker.get_summary()
            logger.info("=" * 50)
            logger.info("FINAL SUMMARY")
            logger.info(f"Initial Capital: {summary['initial_capital']:.2f}")
            logger.info(f"Portfolio Value: {summary['portfolio_value']:.2f}")
            logger.info(f"Total PnL: {summary['total_pnl']:.2f} ({summary['total_pnl_percent']:.2f}%)")
            logger.info(f"Total Trades: {summary['total_trades']}")
            logger.info(f"Win Rate: {summary['win_rate']:.1f}%")
            logger.info(f"Open Positions: {summary['open_positions']}")
            logger.info("=" * 50)
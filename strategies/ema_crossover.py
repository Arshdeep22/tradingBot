"""
EMA Crossover Strategy
-----------------------
Default strategy for the trading bot.

Rules:
- BUY: When fast EMA (9) crosses above slow EMA (21)
- SELL: When fast EMA (9) crosses below slow EMA (21)
- Stop Loss: 1% below entry price
- Target: 2% above entry price (1:2 risk-reward)
"""

import pandas as pd

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal
from config.settings import (
    EMA_FAST_PERIOD, EMA_SLOW_PERIOD,
    STOP_LOSS_PERCENT, TARGET_PERCENT
)


class EMACrossoverStrategy(BaseStrategy):
    """
    EMA Crossover Strategy

    Generates BUY signal when fast EMA crosses above slow EMA.
    Generates SELL signal when fast EMA crosses below slow EMA.
    """

    def __init__(self, fast_period: int = None, slow_period: int = None,
                 timeframe: str = "15m"):
        super().__init__(name="EMA Crossover", timeframe=timeframe)
        self.fast_period = fast_period or EMA_FAST_PERIOD
        self.slow_period = slow_period or EMA_SLOW_PERIOD

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """
        Generate trading signal based on EMA crossover.

        Args:
            data: DataFrame with OHLCV data
            symbol: Stock symbol

        Returns:
            TradeSignal
        """
        if data is None or len(data) < self.slow_period + 2:
            return TradeSignal(Signal.HOLD, symbol, reason="Insufficient data")

        # Calculate EMAs using pandas built-in ewm
        data = data.copy()
        data['ema_fast'] = data['Close'].ewm(span=self.fast_period, adjust=False).mean()
        data['ema_slow'] = data['Close'].ewm(span=self.slow_period, adjust=False).mean()

        # Drop NaN rows
        data = data.dropna()

        if len(data) < 2:
            return TradeSignal(Signal.HOLD, symbol, reason="Not enough data after EMA calculation")

        # Get last two rows to detect crossover
        current = data.iloc[-1]
        previous = data.iloc[-2]

        current_price = current['Close']

        # Bullish crossover: fast EMA crosses above slow EMA
        if (previous['ema_fast'] <= previous['ema_slow'] and
                current['ema_fast'] > current['ema_slow']):

            stop_loss = current_price * (1 - STOP_LOSS_PERCENT / 100)
            target = current_price * (1 + TARGET_PERCENT / 100)

            return TradeSignal(
                signal=Signal.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=round(stop_loss, 2),
                target=round(target, 2),
                reason=f"EMA {self.fast_period} crossed above EMA {self.slow_period}"
            )

        # Bearish crossover: fast EMA crosses below slow EMA
        elif (previous['ema_fast'] >= previous['ema_slow'] and
              current['ema_fast'] < current['ema_slow']):

            return TradeSignal(
                signal=Signal.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=0,
                target=0,
                reason=f"EMA {self.fast_period} crossed below EMA {self.slow_period}"
            )

        # No crossover - hold
        return TradeSignal(Signal.HOLD, symbol, price=current_price,
                           reason="No crossover detected")

    def get_parameters(self) -> dict:
        """Return strategy parameters"""
        return {
            "name": self.name,
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "timeframe": self.timeframe,
            "stop_loss_percent": STOP_LOSS_PERCENT,
            "target_percent": TARGET_PERCENT
        }
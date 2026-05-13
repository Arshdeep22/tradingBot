"""
RSI Reversal Strategy
---------------------
Buys when RSI is oversold and the last candle is a bullish reversal.
Sells when RSI is overbought and the last candle is a bearish reversal.

Signal conditions:
  BUY:  RSI(period) <= oversold_level AND last candle closes bullish (close > open)
  SELL: RSI(period) >= overbought_level AND last candle closes bearish (close < open)

Risk levels:
  Stop Loss: 1x ATR(14) from entry price
  Target:    rr_ratio x risk

How to add your own strategy:
1. Copy this file → strategies/my_strategy.py
2. Inherit BaseStrategy, implement generate_signal() and get_parameters()
3. Add one line in strategies/__init__.py: "My Strategy": MyStrategy
"""

import pandas as pd
from typing import List

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, adjust=False).mean()


class RSIReversalStrategy(BaseStrategy):
    """
    RSI Reversal strategy — trades mean-reversion at extreme RSI levels.

    Parameters:
        rsi_period     — lookback for RSI calculation (default 14)
        oversold_level — RSI threshold to buy (default 30)
        overbought_level — RSI threshold to sell (default 70)
        atr_period     — ATR lookback for SL sizing (default 14)
        rr_ratio       — reward:risk multiplier for target (default 2.0)
        timeframe      — candle timeframe (default "15m")
    """

    def __init__(self, rsi_period: int = 14, oversold_level: float = 30,
                 overbought_level: float = 70, atr_period: int = 14,
                 rr_ratio: float = 2.0, timeframe: str = "15m"):
        super().__init__("RSI Reversal", timeframe)
        self.rsi_period = rsi_period
        self.oversold_level = oversold_level
        self.overbought_level = overbought_level
        self.atr_period = atr_period
        self.rr_ratio = rr_ratio

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """Return the single best signal (most recent bar)."""
        setups = self.get_trade_setups(data, symbol)
        if not setups:
            return TradeSignal(Signal.HOLD, symbol, reason="No RSI reversal signal")
        best = setups[0]
        return TradeSignal(
            signal=Signal.BUY if best.side == "BUY" else Signal.SELL,
            symbol=symbol,
            price=best.entry,
            stop_loss=best.stop_loss,
            target=best.target,
            reason=best.reasoning,
        )

    def get_trade_setups(self, data: pd.DataFrame, symbol: str) -> List[TradeSetup]:
        """
        Scan recent bars for RSI reversal setups. Returns a list so the
        backtester can find all setups across the building period.
        """
        if data is None or len(data) < max(self.rsi_period, self.atr_period) + 5:
            return []

        data = data.copy().reset_index(drop=True)
        rsi = _rsi(data['Close'], self.rsi_period)
        atr = _atr(data['High'], data['Low'], data['Close'], self.atr_period)

        setups = []

        # Scan all bars (backtester uses the building period; live uses last bar)
        for i in range(self.rsi_period + 1, len(data)):
            rsi_val = rsi.iloc[i]
            atr_val = atr.iloc[i]
            if atr_val <= 0:
                continue

            candle_close = data['Close'].iloc[i]
            candle_open = data['Open'].iloc[i]
            is_bullish = candle_close > candle_open
            is_bearish = candle_close < candle_open

            if rsi_val <= self.oversold_level and is_bullish:
                entry = round(candle_close, 2)
                sl = round(entry - atr_val, 2)
                risk = entry - sl
                if risk <= 0:
                    continue
                target = round(entry + self.rr_ratio * risk, 2)
                setups.append(TradeSetup(
                    symbol=symbol,
                    side="BUY",
                    entry=entry,
                    stop_loss=sl,
                    target=target,
                    score=min(100, int((self.oversold_level - rsi_val) * 3 + 50)),
                    reasoning=(
                        f"RSI Reversal BUY | RSI={rsi_val:.1f} (oversold ≤{self.oversold_level}) "
                        f"| Bullish candle | ATR={atr_val:.2f} | R:R=1:{self.rr_ratio}"
                    ),
                ))

            elif rsi_val >= self.overbought_level and is_bearish:
                entry = round(candle_close, 2)
                sl = round(entry + atr_val, 2)
                risk = sl - entry
                if risk <= 0:
                    continue
                target = round(entry - self.rr_ratio * risk, 2)
                setups.append(TradeSetup(
                    symbol=symbol,
                    side="SELL",
                    entry=entry,
                    stop_loss=sl,
                    target=target,
                    score=min(100, int((rsi_val - self.overbought_level) * 3 + 50)),
                    reasoning=(
                        f"RSI Reversal SELL | RSI={rsi_val:.1f} (overbought ≥{self.overbought_level}) "
                        f"| Bearish candle | ATR={atr_val:.2f} | R:R=1:{self.rr_ratio}"
                    ),
                ))

        # Sort by score (highest confidence first)
        setups.sort(key=lambda s: s.score, reverse=True)
        return setups

    def get_parameters(self) -> dict:
        return {
            "name": self.name,
            "timeframe": self.timeframe,
            "rsi_period": self.rsi_period,
            "oversold_level": self.oversold_level,
            "overbought_level": self.overbought_level,
            "atr_period": self.atr_period,
            "rr_ratio": self.rr_ratio,
        }

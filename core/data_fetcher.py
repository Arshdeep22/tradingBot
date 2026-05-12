"""
Data Fetcher Module
-------------------
Fetches market data from various sources.
Currently supports: yfinance
Future: Zerodha Kite Connect
"""

import yfinance as yf
import pandas as pd
import logging

from config.settings import DATA_SOURCE, LOOKBACK_PERIOD

logger = logging.getLogger(__name__)


class DataFetcher:
    """Fetches OHLCV market data"""

    def __init__(self, source: str = None):
        self.source = source or DATA_SOURCE

    def get_data(self, symbol: str, timeframe: str = "15m",
                 period: str = None) -> pd.DataFrame:
        """
        Fetch OHLCV data for a symbol.

        Args:
            symbol: Stock symbol (e.g., "RELIANCE.NS")
            timeframe: Candle timeframe (1m, 3m, 5m, 15m, 30m, 1h, 1d)
            period: Lookback period (1d, 5d, 1mo, etc.)

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
        """
        if self.source == "yfinance":
            return self._fetch_yfinance(symbol, timeframe, period)
        elif self.source == "zerodha":
            return self._fetch_zerodha(symbol, timeframe, period)
        else:
            raise ValueError(f"Unknown data source: {self.source}")

    def _fetch_yfinance(self, symbol: str, timeframe: str = "15m",
                        period: str = None) -> pd.DataFrame:
        """Fetch data from Yahoo Finance"""
        period = period or LOOKBACK_PERIOD

        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=timeframe)

            if data.empty:
                logger.warning(f"No data received for {symbol} ({timeframe})")
                return None

            # Keep only OHLCV columns
            data = data[['Open', 'High', 'Low', 'Close', 'Volume']]

            logger.info(f"Fetched {len(data)} candles for {symbol} ({timeframe})")
            return data

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    def _fetch_zerodha(self, symbol: str, timeframe: str = "15m",
                       period: str = None) -> pd.DataFrame:
        """
        Fetch data from Zerodha Kite Connect.
        To be implemented when Zerodha is integrated.
        """
        raise NotImplementedError("Zerodha data fetcher not yet implemented. "
                                  "Please use 'yfinance' as data source.")

    def get_current_price(self, symbol: str) -> float:
        """Get the current market price of a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if data is not None and not data.empty:
                return float(data['Close'].iloc[-1])
            return 0.0
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return 0.0

    def get_multiple_symbols_data(self, symbols: list, timeframe: str = "15m",
                                   period: str = None) -> dict:
        """
        Fetch data for multiple symbols.

        Args:
            symbols: List of stock symbols
            timeframe: Candle timeframe
            period: Lookback period

        Returns:
            Dictionary with symbol as key and DataFrame as value
        """
        data_dict = {}
        for symbol in symbols:
            data = self.get_data(symbol, timeframe, period)
            if data is not None:
                data_dict[symbol] = data
        return data_dict
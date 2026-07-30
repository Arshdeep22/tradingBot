"""Market-data tool — wraps `core.data_fetcher.DataFetcher` with tracing.

Two modes:
  * live-ish (calls yfinance): used by paper/live modes and as a fallback in
    backtest mode when a cached window isn't available.
  * cached  (an in-memory DataFrame the runner pre-loads for a backtest):
    lets the LLM be called per-bar without re-hitting the API.
"""
from __future__ import annotations

from typing import Optional

try:
    import pandas as pd  # type: ignore
except ImportError:  # pragma: no cover
    pd = None  # type: ignore

from trading_agent.tools.base import ToolBase, ToolError, traced_action


class MarketDataTool(ToolBase):
    tool_name = "market_data"

    def __init__(self, db=None, cached: Optional[dict] = None):
        super().__init__(db=db)
        # `cached` maps symbol -> full DataFrame (for backtest mode).
        self._cached = cached or {}
        # Lazy: don't import DataFetcher unless actually needed.
        self._fetcher = None

    # ── cache management (used by TradingAgentRunner during backtest) ──────
    def set_cache(self, symbol: str, df) -> None:
        self._cached[symbol] = df

    def clear_cache(self) -> None:
        self._cached.clear()

    # ── tool actions ───────────────────────────────────────────────────────
    @traced_action("get_bars")
    def get_bars(self, symbol: str, timeframe: str = "15m",
                 lookback: int = 100,
                 up_to_index: Optional[int] = None) -> dict:
        """Return the most recent `lookback` OHLCV bars for `symbol`.

        In backtest mode with a cached DataFrame, `up_to_index` slices the
        DataFrame at that position (so the LLM only sees bars up to "now"
        and there's no lookahead leakage).
        """
        if symbol in self._cached:
            df = self._cached[symbol]
            if up_to_index is not None:
                df = df.iloc[: up_to_index + 1]
            df = df.tail(lookback)
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "source": "cache",
                "rows": len(df),
                "df": df,
            }

        # Live fetch — lazy-import to avoid pulling yfinance in tests.
        if self._fetcher is None:
            from core.data_fetcher import DataFetcher
            self._fetcher = DataFetcher()
        df = self._fetcher.get_data(symbol, timeframe=timeframe)
        if df is None or (hasattr(df, "empty") and df.empty):
            raise ToolError(f"no market data returned for {symbol}")
        df = df.tail(lookback)
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "source": "yfinance",
            "rows": len(df),
            "df": df,
        }

    @traced_action("get_current_price")
    def get_current_price(self, symbol: str) -> Optional[float]:
        if symbol in self._cached:
            df = self._cached[symbol]
            if df is None or len(df) == 0:
                return None
            return float(df.iloc[-1]["close"])
        if self._fetcher is None:
            from core.data_fetcher import DataFetcher
            self._fetcher = DataFetcher()
        price = self._fetcher.get_current_price(symbol)
        if price is None:
            raise ToolError(f"no current price for {symbol}")
        return float(price)
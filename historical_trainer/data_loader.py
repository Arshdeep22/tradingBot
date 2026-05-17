"""
Data fetching for historical training.
"""

import logging
from datetime import datetime, timezone

from core.data_fetcher import DataFetcher
from .constants import DATA_PERIOD

logger = logging.getLogger(__name__)


def fetch_all_data(symbols: list, progress_cb=None) -> dict:
    """
    Fetch 60 days of 15m OHLCV data for every symbol.
    Reports per-symbol progress via optional callback.
    """
    fetcher = DataFetcher()
    data_dict = {}
    ts_prefix = lambda: datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    for i, sym in enumerate(symbols):
        pct = 2 + (i / max(len(symbols), 1)) * 10
        try:
            df = fetcher.get_data(sym, timeframe="15m", period=DATA_PERIOD)
            if df is not None and len(df) >= 50:
                data_dict[sym] = df
                msg = f"[{ts_prefix()}] Fetching ({i+1}/{len(symbols)}): {sym} — {len(df)} bars ✓"
            else:
                bars = len(df) if df is not None else 0
                msg = f"[{ts_prefix()}] Fetching ({i+1}/{len(symbols)}): {sym} — only {bars} bars, skipped"
                logger.warning(msg)
        except Exception as e:
            msg = f"[{ts_prefix()}] Fetching ({i+1}/{len(symbols)}): {sym} — ERROR: {e}"
            logger.error(msg)
        logger.info(msg)
        if progress_cb:
            progress_cb(pct, msg)

    logger.info(f"Fetch complete: {len(data_dict)}/{len(symbols)} symbols with ≥50 bars")
    return data_dict
"""
Market data helper — fetches VIX and Nifty via yfinance and returns a MarketConditions object.

This is the data-layer bridge between the live market and market_conditions.py.
Called at the start of each scan to gate/adjust all trades accordingly.
"""

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

from strategies.market_conditions import MarketConditions, evaluate_market_conditions

logger = logging.getLogger(__name__)

_NIFTY_TICKER = "^NSEI"
_VIX_TICKER = "^INDIAVIX"


def _fetch_nifty_intraday() -> pd.DataFrame:
    """Fetch today's Nifty 50 intraday data (5m candles, last 2 days)."""
    try:
        df = yf.download(_NIFTY_TICKER, period="2d", interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"Failed to fetch Nifty data: {e}")
        return pd.DataFrame()


def _fetch_vix() -> Optional[float]:
    """Fetch latest India VIX value."""
    try:
        df = yf.download(_VIX_TICKER, period="5d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        return float(df["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Failed to fetch VIX: {e}")
        return None


def fetch_market_conditions(
    config: Optional[dict] = None,
    is_news_day: bool = False,
) -> MarketConditions:
    """
    Fetch live VIX + Nifty data and evaluate market regime.

    Args:
        config: Strategy config dict (passes VIX/Nifty thresholds to evaluator)
        is_news_day: Manual flag for RBI/Budget/Election days

    Returns:
        MarketConditions with regime, can_trade, multipliers set
    """
    nifty_data = _fetch_nifty_intraday()
    vix = _fetch_vix()

    conditions = evaluate_market_conditions(
        nifty_data=nifty_data,
        vix=vix,
        is_news_day=is_news_day,
        config=config or {},
    )

    if not conditions.can_trade:
        logger.warning(f"Market conditions block trading: {conditions.skip_reason}")
    elif conditions.regime.value != "NORMAL":
        logger.info(
            f"Market regime: {conditions.regime.value} | "
            f"VIX={vix:.1f if vix else 'N/A'} | "
            f"Nifty={conditions.nifty_change_pct:+.2f}% | "
            f"SL×{conditions.sl_multiplier} Size×{conditions.size_multiplier}"
        )

    return conditions

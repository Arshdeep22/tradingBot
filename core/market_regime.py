"""
Market Regime Detector
-----------------------
Classifies current market as: trending_up, trending_down, ranging, volatile.
Uses Nifty 50 index (^NSEI) and India VIX (^INDIAVIX) from yfinance.
All calculations are pure pandas/numpy — no extra dependencies needed.
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class RegimeResult:
    regime: str          # trending_up | trending_down | ranging | volatile
    nifty_direction: str # e.g. "+0.8%"
    adx: float
    vix: float
    best_strategy: str
    description: str

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "nifty_direction": self.nifty_direction,
            "adx": self.adx,
            "vix": self.vix,
            "best_strategy": self.best_strategy,
            "description": self.description,
        }


def _compute_adx(df: pd.DataFrame, period: int = 14) -> float:
    """Compute ADX from OHLC DataFrame. Returns latest ADX value."""
    if len(df) < period * 2:
        return 25.0

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    up_move = high - prev_high
    down_move = prev_low - low

    dm_plus = up_move.where((up_move > 0) & (up_move > down_move), 0.0)
    dm_minus = down_move.where((down_move > 0) & (down_move > up_move), 0.0)

    # Wilder's smoothing via EWM (alpha = 1/period)
    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    smooth_dmp = dm_plus.ewm(alpha=alpha, adjust=False).mean()
    smooth_dmm = dm_minus.ewm(alpha=alpha, adjust=False).mean()

    di_plus = 100.0 * smooth_dmp / atr.replace(0, np.nan)
    di_minus = 100.0 * smooth_dmm / atr.replace(0, np.nan)

    denom = (di_plus + di_minus).replace(0, np.nan)
    dx = 100.0 * (di_plus - di_minus).abs() / denom
    adx = dx.ewm(alpha=alpha, adjust=False).mean()

    valid = adx.dropna()
    return float(valid.iloc[-1]) if len(valid) > 0 else 25.0


_FALLBACK = RegimeResult(
    regime="ranging",
    nifty_direction="0.0%",
    adx=25.0,
    vix=15.0,
    best_strategy="Supply & Demand Zones",
    description="Could not fetch regime data — defaulting to Supply & Demand Zones",
)


def detect_regime() -> RegimeResult:
    """
    Detect current market regime using Nifty 50 index and India VIX.
    Returns RegimeResult with regime classification and recommended strategy.
    """
    try:
        nifty = yf.download("^NSEI", period="30d", interval="1d",
                            progress=False, auto_adjust=True)
        vix_data = yf.download("^INDIAVIX", period="5d", interval="1d",
                               progress=False, auto_adjust=True)
    except Exception as e:
        logger.warning(f"Failed to fetch regime data: {e}")
        return _FALLBACK

    if nifty is None or len(nifty) < 20:
        logger.warning("Insufficient Nifty data for regime detection")
        return _FALLBACK

    # 5-day direction
    nifty_close = nifty["Close"].squeeze()
    five_day_return = (nifty_close.iloc[-1] - nifty_close.iloc[-6]) / nifty_close.iloc[-6] * 100
    direction_str = f"{five_day_return:+.1f}%"

    adx = _compute_adx(nifty)

    vix = 15.0
    try:
        if vix_data is not None and len(vix_data) > 0:
            vix = float(vix_data["Close"].squeeze().iloc[-1])
    except Exception:
        pass

    # Regime classification
    if vix > 20:
        regime = "volatile"
        best_strategy = "Supply & Demand Zones"
        desc = (f"High VIX={vix:.1f} — fearful market. "
                "Use only high-quality zones (score 85+); reduce position sizes.")
    elif adx >= 25:
        if five_day_return > 0:
            regime = "trending_up"
            best_strategy = "EMA Crossover"
            desc = (f"ADX={adx:.1f} strong uptrend (Nifty {direction_str}). "
                    "EMA crossover and demand zones both effective.")
        else:
            regime = "trending_down"
            best_strategy = "Supply & Demand Zones"
            desc = (f"ADX={adx:.1f} strong downtrend (Nifty {direction_str}). "
                    "Supply zones and RSI oversold bounces effective.")
    else:
        regime = "ranging"
        best_strategy = "RSI Reversal"
        desc = (f"ADX={adx:.1f} — ranging market (Nifty {direction_str}). "
                "RSI reversal and tight supply/demand zones work best.")

    logger.info(f"Market regime: {regime} | ADX={adx:.1f} | VIX={vix:.1f} | "
                f"Nifty={direction_str} | Best strategy: {best_strategy}")

    return RegimeResult(
        regime=regime,
        nifty_direction=direction_str,
        adx=round(adx, 1),
        vix=round(vix, 1),
        best_strategy=best_strategy,
        description=desc,
    )

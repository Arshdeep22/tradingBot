"""
Market Condition Filters for Zone Trading Strategy.

Evaluates external market state (VIX, Nifty trend, gap, news days) and returns
trading adjustments (SL multiplier, size multiplier, hard stops).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class MarketRegime(Enum):
    NORMAL = "NORMAL"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"        # VIX 20-25
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"  # VIX > 25
    STRONG_TREND_UP = "STRONG_TREND_UP"        # Nifty > +2% intraday
    STRONG_TREND_DOWN = "STRONG_TREND_DOWN"    # Nifty < -2% intraday
    GAP_DAY = "GAP_DAY"                        # Open gap > 1%
    NEWS_DAY = "NEWS_DAY"                      # RBI / Budget / Election day


@dataclass
class MarketConditions:
    regime: MarketRegime = MarketRegime.NORMAL
    nifty_change_pct: float = 0.0   # Intraday % move of Nifty
    vix: Optional[float] = None     # India VIX value
    gap_pct: float = 0.0            # Today's open gap vs prev close
    is_news_day: bool = False
    sl_multiplier: float = 1.0      # Scale SL ATR multiplier
    size_multiplier: float = 1.0    # Scale position size
    can_trade: bool = True
    skip_reason: str = ""


# ─── Data helpers ─────────────────────────────────────────────────────────────

def compute_gap_pct(today_open: float, prev_close: float) -> float:
    """Gap at open as a signed percentage of previous close."""
    if prev_close == 0:
        return 0.0
    return (today_open - prev_close) / prev_close * 100


def compute_intraday_move_pct(nifty_data: pd.DataFrame) -> float:
    """High-to-low range of today's session as % of the day's open."""
    if nifty_data.empty:
        return 0.0
    day_open = nifty_data.iloc[0]["open"]
    if day_open == 0:
        return 0.0
    day_high = nifty_data["high"].max()
    day_low = nifty_data["low"].min()
    return (day_high - day_low) / day_open * 100


# ─── Main evaluator ───────────────────────────────────────────────────────────

def evaluate_market_conditions(
    nifty_data: pd.DataFrame,
    vix: Optional[float] = None,
    is_news_day: bool = False,
    config: Optional[dict] = None,
) -> MarketConditions:
    """
    Evaluate overall market state and return trading adjustments.

    Priority order (highest → lowest):
      1. News day
      2. Extreme VIX (> 25)
      3. High VIX (20-25)
      4. Strong Nifty trend (> 2%)
      5. Gap day (> 1%)
      6. Normal
    """
    cfg = config or {}
    vix_high = cfg.get("vix_high_threshold", 20.0)
    vix_extreme = cfg.get("vix_extreme_threshold", 25.0)
    strong_move = cfg.get("nifty_strong_move_pct", 2.0)
    gap_thresh = cfg.get("gap_threshold_pct", 1.0)
    news_can_trade = cfg.get("news_day_can_trade", False)
    news_size_mult = cfg.get("news_day_size_multiplier", 0.5)
    high_vix_sl = cfg.get("high_vix_sl_multiplier", 1.5)
    high_vix_size = cfg.get("high_vix_size_multiplier", 0.7)

    gap_pct = 0.0
    if not nifty_data.empty and len(nifty_data) >= 2:
        gap_pct = compute_gap_pct(
            nifty_data.iloc[0]["open"],
            nifty_data.iloc[-1]["close"] if len(nifty_data) == 1 else nifty_data.iloc[0]["open"],
        )

    nifty_move = compute_intraday_move_pct(nifty_data)

    # Determine signed trend direction from first vs latest close
    nifty_change_pct = 0.0
    if not nifty_data.empty and len(nifty_data) >= 2:
        first_open = nifty_data.iloc[0]["open"]
        last_close = nifty_data.iloc[-1]["close"]
        if first_open != 0:
            nifty_change_pct = (last_close - first_open) / first_open * 100

    mc = MarketConditions(
        nifty_change_pct=nifty_change_pct,
        vix=vix,
        gap_pct=gap_pct,
        is_news_day=is_news_day,
    )

    # ── Rule 1: News day ──────────────────────────────────────────────────
    if is_news_day:
        mc.regime = MarketRegime.NEWS_DAY
        if news_can_trade:
            mc.size_multiplier = news_size_mult
            mc.skip_reason = ""
        else:
            mc.can_trade = False
            mc.skip_reason = "Adverse news day — RBI/Budget/Election"
        return mc

    # ── Rule 2: Extreme VIX ───────────────────────────────────────────────
    if vix is not None and vix > vix_extreme:
        mc.regime = MarketRegime.EXTREME_VOLATILITY
        mc.can_trade = False
        mc.skip_reason = f"Extreme volatility — VIX {vix:.1f} > {vix_extreme}"
        return mc

    # ── Rule 3: High VIX ──────────────────────────────────────────────────
    if vix is not None and vix > vix_high:
        mc.regime = MarketRegime.HIGH_VOLATILITY
        mc.sl_multiplier = high_vix_sl
        mc.size_multiplier = high_vix_size
        return mc

    # ── Rule 4: Strong intraday trend ─────────────────────────────────────
    if abs(nifty_change_pct) > strong_move:
        mc.regime = (
            MarketRegime.STRONG_TREND_UP
            if nifty_change_pct > 0
            else MarketRegime.STRONG_TREND_DOWN
        )
        mc.size_multiplier = 0.8
        return mc

    # ── Rule 5: Gap day ───────────────────────────────────────────────────
    if abs(gap_pct) > gap_thresh:
        mc.regime = MarketRegime.GAP_DAY
        return mc

    # ── Rule 6: Normal ────────────────────────────────────────────────────
    return mc


# ─── Counter-trend helper ─────────────────────────────────────────────────────

def is_counter_trend_to_market(zone, conditions: MarketConditions) -> bool:
    """
    Returns True when a zone's direction opposes a strong market trend,
    making the trade statistically unfavourable.
    """
    if conditions.regime == MarketRegime.STRONG_TREND_UP and zone.is_supply:
        return True
    if conditions.regime == MarketRegime.STRONG_TREND_DOWN and zone.is_demand:
        return True
    return False

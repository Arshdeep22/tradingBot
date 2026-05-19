"""
Risk Management Checks for Zone Trading Strategy.

Provides pre-trade risk validation including:
- Trading hours check
- Position limits
- Daily loss limits
- Trade frequency limits
- Market condition filters (VIX, trend, gap, news day)
"""

from datetime import datetime, time
from typing import Optional, Tuple
import logging

from strategies.market_conditions import MarketConditions, MarketRegime, is_counter_trend_to_market

logger = logging.getLogger(__name__)


def parse_time(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def is_trading_time(config: dict) -> bool:
    """
    Check if current time is within allowed trading hours.

    Uses config keys:
    - 'trading_start': e.g. '09:45'
    - 'no_new_trades_after': e.g. '14:30'
    """
    now = datetime.now().time()
    start = parse_time(config.get("trading_start", "09:15"))
    end = parse_time(config.get("no_new_trades_after", "15:00"))
    return start <= now <= end


def can_take_new_trade(
    config: dict,
    open_positions: int = 0,
    daily_pnl_pct: float = 0.0,
    trades_today: int = 0,
    consecutive_losses: int = 0,
) -> Tuple[bool, str]:
    """
    Check all risk limits before taking a new trade.

    Args:
        config: Strategy configuration dict
        open_positions: Current number of open positions
        daily_pnl_pct: Today's P&L as percentage of capital (negative = loss)
        trades_today: Number of trades already taken today
        consecutive_losses: Current streak of consecutive losses

    Returns:
        (can_trade, reason): True if trade allowed, else False with reason
    """
    # 1. Trading time check
    if not is_trading_time(config):
        return False, (
            f"Outside trading hours "
            f"({config.get('trading_start', '09:15')} - "
            f"{config.get('no_new_trades_after', '15:00')})"
        )

    # 2. Max open positions
    max_positions = config.get("max_open_positions", 5)
    if open_positions >= max_positions:
        return False, f"Max open positions reached ({max_positions})"

    # 3. Daily loss limit
    max_daily_loss = config.get("max_daily_loss_pct", 3.0)
    if daily_pnl_pct <= -max_daily_loss:
        return False, f"Daily loss limit hit ({max_daily_loss}%)"

    # 4. Max trades per day
    max_trades = config.get("max_trades_per_day", 3)
    if trades_today >= max_trades:
        return False, f"Max trades per day reached ({max_trades})"

    # 5. Hard stop after 2 consecutive losses — guide standard, not configurable
    if consecutive_losses >= 2:
        return False, "Hard stop: 2 consecutive losses today — no new trades"

    # 6. Hard 3:00 PM cutoff — no new entries regardless of soft no_new_trades_after
    if datetime.now().time() >= parse_time("15:00"):
        return False, "No new trades after 3:00 PM"

    return True, "All risk checks passed"


def check_pre_trade(
    zone,
    config: dict,
    open_positions: int = 0,
    daily_pnl_pct: float = 0.0,
    trades_today: int = 0,
    consecutive_losses: int = 0,
    market_conditions: Optional[MarketConditions] = None,
) -> Tuple[bool, str]:
    """
    Full pre-trade gate: existing risk limits + market condition filters.

    Returns (can_trade, reason).
    """
    # 1-5. Existing risk checks
    allowed, reason = can_take_new_trade(
        config,
        open_positions=open_positions,
        daily_pnl_pct=daily_pnl_pct,
        trades_today=trades_today,
        consecutive_losses=consecutive_losses,
    )
    if not allowed:
        return False, reason

    if market_conditions is None:
        return True, "All risk checks passed"

    # 6. Gap-day: enforce 30-min wait from market open (09:15 NSE)
    if market_conditions.regime == MarketRegime.GAP_DAY:
        now = datetime.now().time()
        gap_clear_time = parse_time(config.get("gap_day_start", "09:45"))
        if now < gap_clear_time:
            return False, (
                f"Gap day ({market_conditions.gap_pct:+.1f}%) — "
                f"waiting until {gap_clear_time.strftime('%H:%M')} for price to settle"
            )

    # 7. Hard stop from market conditions
    if not market_conditions.can_trade:
        return False, market_conditions.skip_reason

    # 8. Counter-trend block in strong trend regime
    if is_counter_trend_to_market(zone, market_conditions):
        return False, (
            f"Counter-trend zone blocked — market regime: {market_conditions.regime.value}"
        )

    return True, "All risk checks passed"


def apply_market_condition_multipliers(
    stop_loss_atr: float,
    position_size: int,
    market_conditions: Optional[MarketConditions],
) -> Tuple[float, int]:
    """
    Scale SL ATR and position size by market condition multipliers.

    Returns (adjusted_sl_atr, adjusted_position_size).
    """
    if market_conditions is None:
        return stop_loss_atr, position_size
    adjusted_sl = stop_loss_atr * market_conditions.sl_multiplier
    adjusted_size = max(1, int(position_size * market_conditions.size_multiplier))
    return adjusted_sl, adjusted_size
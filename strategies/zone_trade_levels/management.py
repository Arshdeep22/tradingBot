"""
Post-entry trade management: breakeven, trailing stops, time-based exit.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple
import pandas as pd


class TrailMethod(Enum):
    SWING = "SWING"   # SL below each new higher low (longs) / above lower high (shorts)
    ATR   = "ATR"     # SL = price ± (2 × ATR)
    EMA   = "EMA"     # SL at EMA(21) close


class TradeAction(Enum):
    NONE         = "NONE"
    PARTIAL_EXIT = "PARTIAL_EXIT"   # Close part of the position; trade continues
    FULL_EXIT    = "FULL_EXIT"      # Close entire position; trade is done


@dataclass
class TradeEvent:
    action: TradeAction = TradeAction.NONE
    reason: str = ""
    quantity_to_close: int = 0      # Shares to close (0 = all remaining)


@dataclass
class ActiveTrade:
    """Runtime state of a live trade — separate from ZoneSignal which is pre-entry."""
    zone_id: str
    symbol: str
    direction: str              # "BUY" or "SELL"
    entry_price: float
    initial_sl: float
    current_sl: float
    target_1: float             # 1:1 R:R (partial profit + breakeven trigger)
    target_2: float             # Final target
    position_size: int
    base_candles: int           # From zone, used for time-based exit
    entry_candle_index: int     # DataFrame index at entry

    breakeven_applied: bool = False
    partial_taken: bool = False
    trail_method: TrailMethod = TrailMethod.ATR

    @property
    def risk(self) -> float:
        if self.direction == "BUY":
            return self.entry_price - self.initial_sl
        return self.initial_sl - self.entry_price


def check_breakeven(trade: ActiveTrade, current_price: float) -> Tuple["ActiveTrade", TradeEvent]:
    """
    At 1:1 R:R reached: signal to close 50% of position and move SL to breakeven.
    Only triggers once — breakeven_applied flag prevents repeat.
    Returns (updated_trade, TradeEvent).
    """
    if trade.breakeven_applied:
        return trade, TradeEvent()

    at_target = (
        (trade.direction == "BUY"  and current_price >= trade.target_1) or
        (trade.direction == "SELL" and current_price <= trade.target_1)
    )

    if at_target:
        trade.current_sl = trade.entry_price
        trade.breakeven_applied = True
        trade.partial_taken = True

        if trade.position_size <= 1:
            return trade, TradeEvent(
                action=TradeAction.FULL_EXIT,
                reason="1:1 R:R — no shares to split",
                quantity_to_close=trade.position_size,
            )

        qty_to_close = max(1, trade.position_size // 2)
        return trade, TradeEvent(
            action=TradeAction.PARTIAL_EXIT,
            reason="1:1 R:R reached — taking 50% profit, SL moved to breakeven",
            quantity_to_close=qty_to_close,
        )

    return trade, TradeEvent()


def trail_swing(trade: ActiveTrade, data: pd.DataFrame, lookback: int = 3) -> ActiveTrade:
    """
    SL below the most recent swing low (BUY) or above swing high (SELL).
    Only ratchets in the favourable direction — never widens SL.
    """
    if len(data) < lookback:
        return trade

    recent = data.iloc[-lookback:]

    if trade.direction == "BUY":
        new_sl = recent["low"].min()
        if new_sl > trade.current_sl:
            trade.current_sl = round(new_sl, 2)
    else:
        new_sl = recent["high"].max()
        if new_sl < trade.current_sl:
            trade.current_sl = round(new_sl, 2)

    return trade


def trail_atr(
    trade: ActiveTrade,
    current_price: float,
    atr: float,
    multiplier: float = 2.0,
) -> ActiveTrade:
    """
    SL = current_price ∓ (multiplier × ATR). Ratchet-only.
    """
    if trade.direction == "BUY":
        new_sl = current_price - (multiplier * atr)
        if new_sl > trade.current_sl:
            trade.current_sl = round(new_sl, 2)
    else:
        new_sl = current_price + (multiplier * atr)
        if new_sl < trade.current_sl:
            trade.current_sl = round(new_sl, 2)

    return trade


def trail_ema(trade: ActiveTrade, data: pd.DataFrame, period: int = 21) -> ActiveTrade:
    """
    SL at EMA(period) of close. Ratchet-only.
    """
    if len(data) < period:
        return trade

    ema = data["close"].ewm(span=period, adjust=False).mean().iloc[-1]

    if trade.direction == "BUY":
        if ema > trade.current_sl:
            trade.current_sl = round(ema, 2)
    else:
        if ema < trade.current_sl:
            trade.current_sl = round(ema, 2)

    return trade


def apply_trailing_stop(trade: ActiveTrade, data: pd.DataFrame, atr: float) -> ActiveTrade:
    """
    Dispatcher — routes to the correct trail method.
    Only activates trailing AFTER breakeven is applied (i.e., at > 1:1 R:R).
    """
    if not trade.breakeven_applied:
        return trade

    if trade.trail_method == TrailMethod.SWING:
        return trail_swing(trade, data)
    elif trade.trail_method == TrailMethod.ATR:
        return trail_atr(trade, data.iloc[-1]["close"], atr)
    else:
        return trail_ema(trade, data)


def check_time_exit(
    trade: ActiveTrade,
    current_candle_index: int,
    current_price: float,
) -> Tuple[bool, str]:
    """
    Exit if trade hasn't moved meaningfully after (2 × base_candles) candles.
    "Meaningful" = at least 20% of initial risk distance in our direction.
    """
    candles_elapsed = current_candle_index - trade.entry_candle_index
    if candles_elapsed < 2 * trade.base_candles:
        return False, ""

    move = (
        current_price - trade.entry_price
        if trade.direction == "BUY"
        else trade.entry_price - current_price
    )

    if move < trade.risk * 0.20:
        return True, f"Time exit: no meaningful move after {candles_elapsed} candles"

    return False, ""


def update_open_trade(
    trade: ActiveTrade,
    data: pd.DataFrame,
    atr: float,
    current_price: float,
    current_candle_index: int,
) -> Tuple[ActiveTrade, TradeEvent]:
    """
    Per-candle update. Returns (updated_trade, TradeEvent).

    TradeEvent.action:
      NONE         → trade continues, nothing to execute
      PARTIAL_EXIT → close TradeEvent.quantity_to_close shares, trade continues
      FULL_EXIT    → close all remaining shares, trade is done
    """
    # 1. SL hit → full exit
    if trade.direction == "BUY" and current_price <= trade.current_sl:
        return trade, TradeEvent(TradeAction.FULL_EXIT, "SL hit", trade.position_size)
    if trade.direction == "SELL" and current_price >= trade.current_sl:
        return trade, TradeEvent(TradeAction.FULL_EXIT, "SL hit", trade.position_size)

    # 2. Breakeven + partial profit
    trade, event = check_breakeven(trade, current_price)
    if event.action != TradeAction.NONE:
        return trade, event

    # 3. Trailing stop (only after breakeven)
    trade = apply_trailing_stop(trade, data, atr)

    # 4. Time-based exit → full exit
    should_exit, reason = check_time_exit(trade, current_candle_index, current_price)
    if should_exit:
        return trade, TradeEvent(TradeAction.FULL_EXIT, reason, trade.position_size)

    # 5. Final target hit → full exit of remaining position
    if trade.direction == "BUY" and current_price >= trade.target_2:
        return trade, TradeEvent(TradeAction.FULL_EXIT, "Target reached", trade.position_size)
    if trade.direction == "SELL" and current_price <= trade.target_2:
        return trade, TradeEvent(TradeAction.FULL_EXIT, "Target reached", trade.position_size)

    return trade, TradeEvent()

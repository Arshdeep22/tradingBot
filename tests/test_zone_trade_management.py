"""
Tests for post-entry trade management: breakeven, trailing stops, time exit.
"""

import pandas as pd
import pytest

from strategies.zone_trade_levels.management import (
    ActiveTrade, TrailMethod, TradeAction, TradeEvent,
    check_breakeven, trail_swing, trail_atr, trail_ema,
    apply_trailing_stop, check_time_exit, update_open_trade,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_trade(
    direction="BUY",
    entry=100.0,
    sl=95.0,
    target_1=105.0,
    target_2=115.0,
    base_candles=5,
    entry_candle_index=0,
    trail_method=TrailMethod.ATR,
    breakeven_applied=False,
) -> ActiveTrade:
    return ActiveTrade(
        zone_id="Z1",
        symbol="TEST",
        direction=direction,
        entry_price=entry,
        initial_sl=sl,
        current_sl=sl,
        target_1=target_1,
        target_2=target_2,
        position_size=10,
        base_candles=base_candles,
        entry_candle_index=entry_candle_index,
        trail_method=trail_method,
        breakeven_applied=breakeven_applied,
    )


def make_candles(highs, lows, closes=None) -> pd.DataFrame:
    closes = closes or [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame({"high": highs, "low": lows, "close": closes})


# ---------------------------------------------------------------------------
# ActiveTrade.risk property
# ---------------------------------------------------------------------------

def test_risk_buy():
    t = make_trade(direction="BUY", entry=100, sl=95)
    assert t.risk == 5.0


def test_risk_sell():
    t = make_trade(direction="SELL", entry=100, sl=105)
    assert t.risk == 5.0


# ---------------------------------------------------------------------------
# check_breakeven
# ---------------------------------------------------------------------------

def test_breakeven_buy_triggers_at_target_1():
    t = make_trade(direction="BUY", entry=100, sl=95, target_1=105)
    t, event = check_breakeven(t, current_price=105.0)
    assert t.current_sl == 100.0
    assert t.breakeven_applied is True
    assert event.action == TradeAction.PARTIAL_EXIT


def test_breakeven_sell_triggers_at_target_1():
    t = make_trade(direction="SELL", entry=100, sl=105, target_1=95)
    t, event = check_breakeven(t, current_price=95.0)
    assert t.current_sl == 100.0
    assert t.breakeven_applied is True
    assert event.action == TradeAction.PARTIAL_EXIT


def test_breakeven_not_triggered_before_target():
    t = make_trade(direction="BUY", entry=100, sl=95, target_1=105)
    t, event = check_breakeven(t, current_price=103.0)
    assert t.current_sl == 95.0
    assert t.breakeven_applied is False
    assert event.action == TradeAction.NONE


def test_breakeven_only_applied_once():
    t = make_trade(direction="BUY", entry=100, sl=95, target_1=105)
    t, _ = check_breakeven(t, current_price=106.0)
    assert t.current_sl == 100.0
    # Simulate price retreating and then calling again — SL must not move
    t.current_sl = 102.0  # manually advanced by trailing
    t, event = check_breakeven(t, current_price=106.0)
    assert t.current_sl == 102.0  # unchanged
    assert event.action == TradeAction.NONE


# ---------------------------------------------------------------------------
# trail_swing
# ---------------------------------------------------------------------------

def test_trail_swing_buy_advances_sl():
    t = make_trade(direction="BUY", entry=100, sl=95)
    data = make_candles(highs=[101, 102, 103], lows=[98, 99, 100])
    t = trail_swing(t, data, lookback=3)
    # swing low of last 3 = min(98, 99, 100) = 98
    assert t.current_sl == 98.0


def test_trail_swing_buy_does_not_widen_sl():
    t = make_trade(direction="BUY", entry=100, sl=99)
    data = make_candles(highs=[101, 102, 103], lows=[97, 96, 98])
    t = trail_swing(t, data, lookback=3)
    assert t.current_sl == 99.0  # new swing low 96 < current_sl 99 → no change


def test_trail_swing_sell_advances_sl():
    t = make_trade(direction="SELL", entry=100, sl=105)
    data = make_candles(highs=[103, 102, 101], lows=[98, 97, 96])
    t = trail_swing(t, data, lookback=3)
    # swing high of last 3 = max(103, 102, 101) = 103 < current_sl 105 → advances
    assert t.current_sl == 103.0


def test_trail_swing_insufficient_data():
    t = make_trade(direction="BUY", entry=100, sl=95)
    data = make_candles(highs=[101], lows=[98])
    t = trail_swing(t, data, lookback=3)
    assert t.current_sl == 95.0  # unchanged


# ---------------------------------------------------------------------------
# trail_atr
# ---------------------------------------------------------------------------

def test_trail_atr_buy_advances_sl():
    t = make_trade(direction="BUY", entry=100, sl=90)
    t = trail_atr(t, current_price=110.0, atr=3.0, multiplier=2.0)
    # new_sl = 110 - 6 = 104 > current_sl 90 → advances
    assert t.current_sl == 104.0


def test_trail_atr_buy_does_not_widen():
    t = make_trade(direction="BUY", entry=100, sl=108)
    t = trail_atr(t, current_price=110.0, atr=3.0, multiplier=2.0)
    # new_sl = 104 < current_sl 108 → no change
    assert t.current_sl == 108.0


def test_trail_atr_sell_advances_sl():
    t = make_trade(direction="SELL", entry=100, sl=110)
    t = trail_atr(t, current_price=90.0, atr=3.0, multiplier=2.0)
    # new_sl = 90 + 6 = 96 < current_sl 110 → advances
    assert t.current_sl == 96.0


# ---------------------------------------------------------------------------
# trail_ema
# ---------------------------------------------------------------------------

def test_trail_ema_buy_uses_ema():
    t = make_trade(direction="BUY", entry=100, sl=90)
    closes = [100] * 21 + [102]  # stable then slightly up
    data = make_candles(highs=closes, lows=closes, closes=closes)
    t = trail_ema(t, data, period=21)
    # EMA should be near 100, which is > initial_sl 90
    assert t.current_sl > 90.0


def test_trail_ema_insufficient_data():
    t = make_trade(direction="BUY", entry=100, sl=90)
    data = make_candles(highs=[101, 102], lows=[99, 100], closes=[100, 101])
    t = trail_ema(t, data, period=21)
    assert t.current_sl == 90.0


# ---------------------------------------------------------------------------
# apply_trailing_stop (dispatcher)
# ---------------------------------------------------------------------------

def test_trailing_not_applied_before_breakeven():
    t = make_trade(direction="BUY", entry=100, sl=90, breakeven_applied=False)
    data = make_candles(highs=[105, 106, 107], lows=[102, 103, 104])
    original_sl = t.current_sl
    t = apply_trailing_stop(t, data, atr=2.0)
    assert t.current_sl == original_sl


def test_trailing_applied_after_breakeven_atr():
    t = make_trade(direction="BUY", entry=100, sl=90, trail_method=TrailMethod.ATR)
    t.breakeven_applied = True
    t.current_sl = 100.0  # at breakeven
    data = make_candles(highs=[110], lows=[108], closes=[110])
    t = apply_trailing_stop(t, data, atr=2.0)
    # new_sl = 110 - 4 = 106 > 100 → advances
    assert t.current_sl == 106.0


# ---------------------------------------------------------------------------
# check_time_exit
# ---------------------------------------------------------------------------

def test_time_exit_fires_when_stale():
    t = make_trade(direction="BUY", entry=100, sl=95, base_candles=5, entry_candle_index=0)
    # No meaningful move after 10 candles (2 × 5)
    should_exit, reason = check_time_exit(t, current_candle_index=10, current_price=100.5)
    assert should_exit is True
    assert "10 candles" in reason


def test_time_exit_does_not_fire_before_limit():
    t = make_trade(direction="BUY", entry=100, sl=95, base_candles=5, entry_candle_index=0)
    should_exit, _ = check_time_exit(t, current_candle_index=9, current_price=100.5)
    assert should_exit is False


def test_time_exit_does_not_fire_if_meaningful_move():
    t = make_trade(direction="BUY", entry=100, sl=95, base_candles=5, entry_candle_index=0)
    # risk=5, 20% threshold=1.0; price moved +2 → meaningful
    should_exit, _ = check_time_exit(t, current_candle_index=10, current_price=102.0)
    assert should_exit is False


def test_time_exit_sell_direction():
    t = make_trade(direction="SELL", entry=100, sl=105, base_candles=5, entry_candle_index=0)
    # price barely moved down — stale
    should_exit, reason = check_time_exit(t, current_candle_index=10, current_price=99.8)
    assert should_exit is True


# ---------------------------------------------------------------------------
# update_open_trade (orchestrator)
# ---------------------------------------------------------------------------

def make_data_for_update():
    return make_candles(
        highs=[101, 102, 103],
        lows=[99, 100, 101],
        closes=[100, 101, 102],
    )


def test_update_exits_on_sl_hit_buy():
    t = make_trade(direction="BUY", entry=100, sl=95)
    data = make_data_for_update()
    t, event = update_open_trade(t, data, atr=1.0, current_price=94.0, current_candle_index=1)
    assert event.action == TradeAction.FULL_EXIT
    assert event.reason == "SL hit"


def test_update_exits_on_sl_hit_sell():
    t = make_trade(direction="SELL", entry=100, sl=105)
    data = make_data_for_update()
    t, event = update_open_trade(t, data, atr=1.0, current_price=106.0, current_candle_index=1)
    assert event.action == TradeAction.FULL_EXIT
    assert event.reason == "SL hit"


def test_update_exits_on_target_hit_buy():
    t = make_trade(
        direction="BUY", entry=100, sl=95,
        target_1=105, target_2=115,
        breakeven_applied=True,
    )
    data = make_data_for_update()
    t, event = update_open_trade(t, data, atr=1.0, current_price=116.0, current_candle_index=1)
    assert event.action == TradeAction.FULL_EXIT
    assert event.reason == "Target reached"


def test_update_applies_breakeven_mid_trade():
    t = make_trade(direction="BUY", entry=100, sl=95, target_1=105, target_2=115)
    data = make_data_for_update()
    t, event = update_open_trade(t, data, atr=1.0, current_price=106.0, current_candle_index=1)
    assert event.action == TradeAction.PARTIAL_EXIT
    assert t.breakeven_applied is True
    assert t.current_sl == 100.0


def test_update_no_exit_mid_trade():
    t = make_trade(direction="BUY", entry=100, sl=95, target_1=105, target_2=115)
    data = make_data_for_update()
    t, event = update_open_trade(t, data, atr=1.0, current_price=102.0, current_candle_index=1)
    assert event.action == TradeAction.NONE

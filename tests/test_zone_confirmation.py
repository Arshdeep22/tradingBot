"""
Unit tests for zone entry confirmation candle patterns (Plan 11).
"""

import pytest
import pandas as pd
from strategies.zone_trade_levels.confirmation import (
    is_bullish_engulfing, is_hammer,
    is_bearish_engulfing, is_shooting_star,
    is_morning_star, is_evening_star,
    detect_demand_confirmation, detect_supply_confirmation,
    ConfirmationSignal,
)
from strategies.zone_trade_levels.entry_sl import get_confirmation_entry


def candle(open_, high, low, close) -> pd.Series:
    return pd.Series({'open': open_, 'high': high, 'low': low, 'close': close})


def df_from_candles(*candles) -> pd.DataFrame:
    return pd.DataFrame([c for c in candles])


DEFAULT_CONFIG = {
    'min_hammer_wick_ratio': 2.0,
    'allow_morning_star': True,
    'min_confirmation_strength': 3,
}


# ---------------------------------------------------------------------------
# is_bullish_engulfing
# ---------------------------------------------------------------------------

class TestBullishEngulfing:
    def test_valid_engulfing(self):
        prev = candle(110, 112, 108, 109)   # bearish
        curr = candle(107, 115, 106, 114)   # bullish, engulfs
        assert is_bullish_engulfing(prev, curr)

    def test_prev_must_be_bearish(self):
        prev = candle(108, 112, 107, 111)   # bullish
        curr = candle(107, 115, 106, 114)
        assert not is_bullish_engulfing(prev, curr)

    def test_curr_must_be_bullish(self):
        prev = candle(110, 112, 108, 109)   # bearish
        curr = candle(114, 115, 106, 107)   # bearish
        assert not is_bullish_engulfing(prev, curr)

    def test_must_fully_engulf(self):
        prev = candle(110, 112, 108, 109)   # bearish, body 109–110
        curr = candle(109, 113, 108, 110)   # bullish but doesn't fully engulf
        # curr body 109–110, prev body 109–110 — equal counts as engulf
        assert is_bullish_engulfing(prev, curr)

    def test_partial_engulf_fails(self):
        prev = candle(112, 114, 107, 108)   # bearish, body 108–112
        curr = candle(109, 113, 108, 111)   # bullish, body 109–111 < 108–112
        assert not is_bullish_engulfing(prev, curr)


# ---------------------------------------------------------------------------
# is_hammer
# ---------------------------------------------------------------------------

class TestHammer:
    def test_valid_hammer(self):
        # Body 99–100, lower wick 94–99 = 5, body = 1, ratio = 5×
        c = candle(99, 100.5, 94, 100)
        assert is_hammer(c, min_wick_ratio=2.0)

    def test_close_must_be_above_midpoint(self):
        # Midpoint = (100.5 + 94) / 2 = 97.25 — close below midpoint
        c = candle(97.5, 100.5, 94, 97)
        assert not is_hammer(c, min_wick_ratio=2.0)

    def test_lower_wick_too_small(self):
        # Body 98–100 = 2, lower wick = 97–98 = 1, ratio 0.5× < 2×
        c = candle(98, 101, 97, 100)
        assert not is_hammer(c, min_wick_ratio=2.0)

    def test_doji_returns_false(self):
        c = candle(100, 102, 98, 100)   # body = 0
        assert not is_hammer(c)


# ---------------------------------------------------------------------------
# is_bearish_engulfing
# ---------------------------------------------------------------------------

class TestBearishEngulfing:
    def test_valid(self):
        prev = candle(108, 113, 107, 111)   # bullish
        curr = candle(112, 114, 105, 106)   # bearish, engulfs
        assert is_bearish_engulfing(prev, curr)

    def test_prev_must_be_bullish(self):
        prev = candle(111, 113, 107, 108)   # bearish
        curr = candle(112, 114, 105, 106)
        assert not is_bearish_engulfing(prev, curr)

    def test_curr_must_be_bearish(self):
        prev = candle(108, 113, 107, 111)   # bullish
        curr = candle(105, 115, 104, 114)   # bullish
        assert not is_bearish_engulfing(prev, curr)


# ---------------------------------------------------------------------------
# is_shooting_star
# ---------------------------------------------------------------------------

class TestShootingStar:
    def test_valid_shooting_star(self):
        # Body 100–101 = 1, upper wick 101–105 = 4, close < midpoint
        c = candle(101, 105, 99.5, 100)
        assert is_shooting_star(c, min_wick_ratio=2.0)

    def test_close_must_be_below_midpoint(self):
        # Midpoint = (105 + 99.5) / 2 = 102.25 — close above midpoint
        c = candle(101, 105, 99.5, 103)
        assert not is_shooting_star(c, min_wick_ratio=2.0)

    def test_upper_wick_too_small(self):
        c = candle(100, 101.5, 98, 100.2)
        assert not is_shooting_star(c, min_wick_ratio=2.0)


# ---------------------------------------------------------------------------
# is_morning_star
# ---------------------------------------------------------------------------

class TestMorningStar:
    def _valid_df(self):
        return df_from_candles(
            candle(110, 112, 105, 106),   # [0] bearish, large body
            candle(105, 106, 104, 105.2), # [1] tiny doji
            candle(105, 113, 104, 111),   # [2] bullish, closes above midpoint of [0]
        )

    def test_valid_morning_star(self):
        assert is_morning_star(self._valid_df())

    def test_requires_3_candles(self):
        df = df_from_candles(candle(110, 112, 105, 106), candle(105, 106, 104, 105.2))
        assert not is_morning_star(df)

    def test_first_candle_must_be_bearish(self):
        df = df_from_candles(
            candle(105, 112, 104, 111),   # bullish
            candle(110, 111, 109, 110.2),
            candle(110, 116, 109, 115),
        )
        assert not is_morning_star(df)

    def test_last_candle_must_close_above_midpoint(self):
        df = df_from_candles(
            candle(110, 112, 105, 106),
            candle(105, 106, 104, 105.2),
            candle(106, 108, 105, 107),   # closes at 107, midpoint of [0] is (110+106)/2=108
        )
        assert not is_morning_star(df)


# ---------------------------------------------------------------------------
# is_evening_star
# ---------------------------------------------------------------------------

class TestEveningStar:
    def test_valid_evening_star(self):
        df = df_from_candles(
            candle(100, 110, 99, 109),    # bullish, large body
            candle(109, 111, 108, 109.2), # tiny doji
            candle(109, 110, 102, 103),   # bearish, closes below midpoint of [0]
        )
        assert is_evening_star(df)

    def test_requires_3_candles(self):
        df = df_from_candles(candle(100, 110, 99, 109), candle(109, 111, 108, 109.2))
        assert not is_evening_star(df)


# ---------------------------------------------------------------------------
# detect_demand_confirmation
# ---------------------------------------------------------------------------

class TestDetectDemandConfirmation:
    def _base_data(self):
        # Price drops into demand zone (zone_top=100, zone_bottom=97)
        return df_from_candles(
            candle(103, 105, 102, 104),
            candle(102, 104, 99, 100),    # prev: bearish, enters zone
            candle(99,  105, 98, 103),    # curr: bullish engulfing, low inside zone
        )

    def test_detects_bullish_engulfing(self):
        data = self._base_data()
        sig = detect_demand_confirmation(data, zone_top=100, zone_bottom=97, config=DEFAULT_CONFIG)
        assert sig.confirmed
        assert sig.pattern == "BULLISH_ENGULFING"
        assert sig.strength == 5

    def test_entry_price_is_close_of_curr_candle(self):
        data = self._base_data()
        sig = detect_demand_confirmation(data, zone_top=100, zone_bottom=97, config=DEFAULT_CONFIG)
        assert sig.entry_price == 103.0

    def test_no_signal_when_price_above_zone(self):
        data = df_from_candles(
            candle(105, 107, 104, 106),
            candle(104, 106, 103, 105),   # low > zone_top=100, not in zone
        )
        sig = detect_demand_confirmation(data, zone_top=100, zone_bottom=97, config=DEFAULT_CONFIG)
        assert not sig.confirmed
        assert sig.pattern == "NONE"

    def test_detects_hammer(self):
        data = df_from_candles(
            candle(105, 107, 104, 106),
            candle(99.5, 101, 94, 100),   # hammer inside zone (body=0.5, lower wick=5.5)
        )
        sig = detect_demand_confirmation(data, zone_top=101, zone_bottom=97, config=DEFAULT_CONFIG)
        assert sig.confirmed
        assert sig.pattern == "HAMMER"

    def test_insufficient_data_returns_no_signal(self):
        data = df_from_candles(candle(99, 102, 98, 101))
        sig = detect_demand_confirmation(data, zone_top=102, zone_bottom=97, config=DEFAULT_CONFIG)
        assert not sig.confirmed

    def test_min_strength_filter(self):
        # Bullish close = strength 3; set min_strength=4 → should not confirm
        data = df_from_candles(
            candle(105, 107, 104, 106),
            candle(100, 102, 99, 101),    # enters zone, closes bullish above zone_top=100
        )
        config = {**DEFAULT_CONFIG, 'min_confirmation_strength': 4}
        sig = detect_demand_confirmation(data, zone_top=100, zone_bottom=97, config=config)
        assert not sig.confirmed


# ---------------------------------------------------------------------------
# detect_supply_confirmation
# ---------------------------------------------------------------------------

class TestDetectSupplyConfirmation:
    def test_detects_bearish_engulfing(self):
        data = df_from_candles(
            candle(97, 99, 96, 98),
            candle(98, 103, 97, 102),     # prev: bullish, enters supply zone
            candle(103, 105, 96, 97),     # curr: bearish engulfing
        )
        sig = detect_supply_confirmation(data, zone_top=105, zone_bottom=102, config=DEFAULT_CONFIG)
        assert sig.confirmed
        assert sig.pattern == "BEARISH_ENGULFING"

    def test_no_signal_when_price_below_zone(self):
        data = df_from_candles(
            candle(97, 99, 96, 98),
            candle(96, 98, 95, 97),       # high < zone_bottom=100
        )
        sig = detect_supply_confirmation(data, zone_top=105, zone_bottom=100, config=DEFAULT_CONFIG)
        assert not sig.confirmed

    def test_detects_shooting_star(self):
        data = df_from_candles(
            candle(100, 102, 99, 101),
            candle(101.5, 107, 100.5, 101),  # shooting star inside zone (body=0.5, upper wick=5.5)
        )
        sig = detect_supply_confirmation(data, zone_top=108, zone_bottom=100, config=DEFAULT_CONFIG)
        assert sig.confirmed
        assert sig.pattern == "SHOOTING_STAR"


# ---------------------------------------------------------------------------
# get_confirmation_entry
# ---------------------------------------------------------------------------

class TestGetConfirmationEntry:
    def test_returns_close_price(self):
        sig = ConfirmationSignal("HAMMER", 5, True, 102.50, 5)
        assert get_confirmation_entry(sig) == 102.50

    def test_next_open_returns_same_value(self):
        sig = ConfirmationSignal("HAMMER", 5, True, 102.50, 5)
        assert get_confirmation_entry(sig, entry_method='NEXT_OPEN') == 102.50

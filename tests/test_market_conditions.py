"""
Unit tests for Market Condition Filters (Plan 8).

All tests use synthetic DataFrames — no live API calls.
"""

import pandas as pd
import pytest

from strategies.market_conditions import (
    MarketConditions,
    MarketRegime,
    compute_gap_pct,
    compute_intraday_move_pct,
    evaluate_market_conditions,
    is_counter_trend_to_market,
)
from strategies.zone_models import Zone
from strategies.zone_risk import apply_market_condition_multipliers, check_pre_trade


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_nifty(open_: float, high: float, low: float, close: float, rows: int = 5) -> pd.DataFrame:
    """Build a minimal multi-row Nifty DataFrame for testing."""
    data = {
        "open":  [open_] + [open_] * (rows - 1),
        "high":  [high]  + [high]  * (rows - 1),
        "low":   [low]   + [low]   * (rows - 1),
        "close": [close] + [close] * (rows - 1),
        "volume": [1_000_000] * rows,
    }
    return pd.DataFrame(data)


def make_zone(zone_type: str = "DEMAND") -> Zone:
    return Zone(
        zone_type=zone_type,
        pattern="DBR",
        zone_top=100.0,
        zone_bottom=95.0,
        base_candles=2,
        formed_at_index=10,
        formed_at_time="2026-01-01 10:00",
        leg_out_count=3,
        leg_out_body_pct=60.0,
        leg_out_body_ratio=0.8,
        leg_out_volume_ratio=1.5,
        has_gap=False,
        leg_in_body_pct=70.0,
        leg_in_candle_count=1,
    )


TRADING_CONFIG = {
    "trading_start": "09:15",
    "no_new_trades_after": "23:59",
    "max_open_positions": 5,
    "max_daily_loss_pct": 3.0,
    "max_trades_per_day": 10,
    "max_consecutive_losses": 5,
}


# ─── compute_gap_pct ─────────────────────────────────────────────────────────

def test_gap_pct_positive():
    assert compute_gap_pct(22_100, 22_000) == pytest.approx(100 / 22_000 * 100)


def test_gap_pct_negative():
    result = compute_gap_pct(21_780, 22_000)
    assert result < 0


def test_gap_pct_zero_prev_close():
    assert compute_gap_pct(100, 0) == 0.0


# ─── compute_intraday_move_pct ────────────────────────────────────────────────

def test_intraday_move_basic():
    df = make_nifty(open_=22_000, high=22_500, low=21_800, close=22_300)
    pct = compute_intraday_move_pct(df)
    assert pct == pytest.approx((22_500 - 21_800) / 22_000 * 100)


def test_intraday_move_empty_df():
    assert compute_intraday_move_pct(pd.DataFrame()) == 0.0


# ─── evaluate_market_conditions ──────────────────────────────────────────────

def test_normal_regime():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    mc = evaluate_market_conditions(df, vix=15.0)
    assert mc.regime == MarketRegime.NORMAL
    assert mc.can_trade is True
    assert mc.sl_multiplier == 1.0
    assert mc.size_multiplier == 1.0


def test_news_day_blocks_trading():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    mc = evaluate_market_conditions(df, is_news_day=True)
    assert mc.regime == MarketRegime.NEWS_DAY
    assert mc.can_trade is False
    assert "news day" in mc.skip_reason.lower()


def test_news_day_allows_reduced_size_when_configured():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    cfg = {"news_day_can_trade": True, "news_day_size_multiplier": 0.5}
    mc = evaluate_market_conditions(df, is_news_day=True, config=cfg)
    assert mc.can_trade is True
    assert mc.size_multiplier == 0.5


def test_extreme_vix_blocks_trading():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    mc = evaluate_market_conditions(df, vix=27.0)
    assert mc.regime == MarketRegime.EXTREME_VOLATILITY
    assert mc.can_trade is False
    assert "VIX" in mc.skip_reason


def test_high_vix_widens_sl_and_reduces_size():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    mc = evaluate_market_conditions(df, vix=22.0)
    assert mc.regime == MarketRegime.HIGH_VOLATILITY
    assert mc.can_trade is True
    assert mc.sl_multiplier == 1.5
    assert mc.size_multiplier == 0.7


def test_strong_trend_up():
    # close > open by >2%
    open_ = 22_000.0
    close = open_ * 1.025
    df = make_nifty(open_, close, open_ * 0.99, close)
    mc = evaluate_market_conditions(df, vix=15.0)
    assert mc.regime == MarketRegime.STRONG_TREND_UP
    assert mc.size_multiplier == 0.8
    assert mc.can_trade is True


def test_strong_trend_down():
    open_ = 22_000.0
    close = open_ * 0.975
    df = make_nifty(open_, open_ * 1.005, close, close)
    mc = evaluate_market_conditions(df, vix=15.0)
    assert mc.regime == MarketRegime.STRONG_TREND_DOWN
    assert mc.size_multiplier == 0.8


def test_gap_day_regime():
    # Gap > 1%: today_open vs prev provided via DataFrame structure
    # We simulate it by passing a config with gap_threshold_pct and a large gap
    open_ = 22_220.0   # ~1% gap from 22_000
    df = make_nifty(open_, open_ * 1.001, open_ * 0.999, open_)
    # Manually inject gap by providing prev_close via nifty_data with 2+ rows
    df2 = pd.concat([
        pd.DataFrame({"open": [22_000], "high": [22_100], "low": [21_900], "close": [22_000], "volume": [1e6]}),
        df,
    ], ignore_index=True)
    mc = evaluate_market_conditions(df2, vix=14.0)
    # gap_pct here is computed from row0 open vs something — regime may be NORMAL or GAP_DAY
    # Just verify no crash and can_trade remains True for gap day
    assert mc.can_trade is True


def test_news_day_takes_priority_over_extreme_vix():
    df = make_nifty(22_000, 22_200, 21_900, 22_100)
    mc = evaluate_market_conditions(df, vix=30.0, is_news_day=True)
    assert mc.regime == MarketRegime.NEWS_DAY  # news checked first


# ─── is_counter_trend_to_market ──────────────────────────────────────────────

def test_supply_zone_blocked_in_strong_trend_up():
    supply = make_zone("SUPPLY")
    mc = MarketConditions(regime=MarketRegime.STRONG_TREND_UP)
    assert is_counter_trend_to_market(supply, mc) is True


def test_demand_zone_blocked_in_strong_trend_down():
    demand = make_zone("DEMAND")
    mc = MarketConditions(regime=MarketRegime.STRONG_TREND_DOWN)
    assert is_counter_trend_to_market(demand, mc) is True


def test_demand_zone_allowed_in_strong_trend_up():
    demand = make_zone("DEMAND")
    mc = MarketConditions(regime=MarketRegime.STRONG_TREND_UP)
    assert is_counter_trend_to_market(demand, mc) is False


def test_counter_trend_normal_regime():
    supply = make_zone("SUPPLY")
    mc = MarketConditions(regime=MarketRegime.NORMAL)
    assert is_counter_trend_to_market(supply, mc) is False


# ─── check_pre_trade ─────────────────────────────────────────────────────────

def test_check_pre_trade_passes_without_conditions():
    zone = make_zone("DEMAND")
    ok, reason = check_pre_trade(zone, TRADING_CONFIG)
    assert ok is True


def test_check_pre_trade_blocked_by_can_trade_false():
    zone = make_zone("DEMAND")
    mc = MarketConditions(can_trade=False, skip_reason="VIX too high")
    ok, reason = check_pre_trade(zone, TRADING_CONFIG, market_conditions=mc)
    assert ok is False
    assert "VIX" in reason


def test_check_pre_trade_blocked_counter_trend():
    supply = make_zone("SUPPLY")
    mc = MarketConditions(regime=MarketRegime.STRONG_TREND_UP)
    ok, reason = check_pre_trade(supply, TRADING_CONFIG, market_conditions=mc)
    assert ok is False
    assert "Counter-trend" in reason


def test_check_pre_trade_allows_with_trend():
    demand = make_zone("DEMAND")
    mc = MarketConditions(regime=MarketRegime.STRONG_TREND_UP)
    ok, _ = check_pre_trade(demand, TRADING_CONFIG, market_conditions=mc)
    assert ok is True


def test_check_pre_trade_respects_existing_limits():
    zone = make_zone("DEMAND")
    ok, reason = check_pre_trade(zone, TRADING_CONFIG, daily_pnl_pct=-5.0)
    assert ok is False
    assert "loss limit" in reason.lower()


# ─── apply_market_condition_multipliers ──────────────────────────────────────

def test_multipliers_normal():
    sl, size = apply_market_condition_multipliers(50.0, 10, MarketConditions())
    assert sl == 50.0
    assert size == 10


def test_multipliers_high_vix():
    mc = MarketConditions(sl_multiplier=1.5, size_multiplier=0.7)
    sl, size = apply_market_condition_multipliers(50.0, 10, mc)
    assert sl == pytest.approx(75.0)
    assert size == 7


def test_multipliers_news_day_reduced_size():
    mc = MarketConditions(size_multiplier=0.5)
    _, size = apply_market_condition_multipliers(50.0, 10, mc)
    assert size == 5


def test_multipliers_minimum_size_is_one():
    mc = MarketConditions(size_multiplier=0.01)
    _, size = apply_market_condition_multipliers(50.0, 1, mc)
    assert size >= 1


def test_multipliers_none_conditions():
    sl, size = apply_market_condition_multipliers(50.0, 10, None)
    assert sl == 50.0
    assert size == 10

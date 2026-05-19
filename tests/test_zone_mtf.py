"""Tests for the Multi-Timeframe System (Plan 4)."""
import pandas as pd
import numpy as np
import pytest

from strategies.zone_models import Zone
from strategies.zone_mtf.trend import (
    find_swing_highs, find_swing_lows, get_ema_bias,
    detect_trend, _classify_structure,
)
from strategies.zone_mtf.confluence import find_zone_confluence, _zones_overlap, _same_type
from strategies.zone_mtf.entry_refinement import assess_arrival_on_entry_tf, check_freshness_on_entry_tf
from strategies.zone_mtf.orchestrator import apply_trend_filter, multi_timeframe_analysis, DEFAULT_MTF_CONFIG
from strategies.zone_mtf import multi_timeframe_confirm


def _uptrend(n=80):
    np.random.seed(42)
    # Gentle trend + strong oscillations = clear HH/HL structure
    prices = [100.0 + i * 0.4 + 5.0 * np.sin(i * 0.25) for i in range(n)]
    close = np.array(prices)
    high = close + np.random.uniform(0.2, 0.8, n)
    low = close - np.random.uniform(0.2, 0.8, n)
    open_ = close - np.random.uniform(-0.3, 0.3, n)
    vol = np.random.randint(1000, 5000, n)
    return pd.DataFrame({
        'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': vol,
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol,
    })


def _downtrend(n=80):
    np.random.seed(42)
    prices = [200.0 - i * 0.4 + 5.0 * np.sin(i * 0.25) for i in range(n)]
    close = np.array(prices)
    high = close + np.random.uniform(0.2, 0.8, n)
    low = close - np.random.uniform(0.2, 0.8, n)
    open_ = close - np.random.uniform(-0.3, 0.3, n)
    vol = np.random.randint(1000, 5000, n)
    return pd.DataFrame({
        'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': vol,
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol,
    })


def _sideways(n=80):
    np.random.seed(42)
    # Pure oscillation, no trend
    prices = [150.0 + 5.0 * np.sin(i * 0.25) for i in range(n)]
    close = np.array(prices)
    high = close + np.random.uniform(0.2, 0.8, n)
    low = close - np.random.uniform(0.2, 0.8, n)
    open_ = close - np.random.uniform(-0.3, 0.3, n)
    vol = np.random.randint(1000, 5000, n)
    return pd.DataFrame({
        'Open': open_, 'High': high, 'Low': low, 'Close': close, 'Volume': vol,
        'open': open_, 'high': high, 'low': low, 'close': close, 'volume': vol,
    })


def _zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0, is_fresh=True, score=45):
    return Zone(
        zone_type=zone_type, pattern="DBR" if zone_type == "DEMAND" else "RBD",
        zone_top=zone_top, zone_bottom=zone_bottom, base_candles=2,
        formed_at_index=10, formed_at_time="2024-01-01 10:00",
        leg_out_count=2, leg_out_body_pct=1.5, leg_out_body_ratio=0.75,
        leg_out_volume_ratio=1.8, has_gap=False, leg_in_body_pct=1.0,
        leg_in_candle_count=1, is_fresh=is_fresh, age_candles=20, score=score,
        departure_score=8, base_score=8, freshness_score=10 if is_fresh else 0,
        arrival_score=5, time_score=8, trend_score=5,
    )


# ─── Swing Detection ─────────────────────────────────────────────────

class TestSwingDetection:
    def test_find_swing_highs_basic(self):
        swings = find_swing_highs(_uptrend(30), window=3)
        assert len(swings) > 0
        assert all(isinstance(s[0], int) and isinstance(s[1], float) for s in swings)

    def test_find_swing_lows_basic(self):
        swings = find_swing_lows(_uptrend(30), window=3)
        assert len(swings) > 0

    def test_swing_highs_insufficient_data(self):
        assert find_swing_highs(pd.DataFrame({'high': [100, 101]}), window=5) == []

    def test_swing_lows_insufficient_data(self):
        assert find_swing_lows(pd.DataFrame({'low': [100, 99]}), window=5) == []

    def test_none_data(self):
        assert find_swing_highs(None) == []
        assert find_swing_lows(None) == []

    def test_swing_high_is_local_max(self):
        data = pd.DataFrame({'high': [10, 11, 15, 11, 10, 11, 20, 11, 10, 11, 18, 11, 10]})
        swings = find_swing_highs(data, window=2)
        assert len(swings) >= 2
        for idx, price in swings:
            assert data['high'].iloc[idx] == price


# ─── EMA Bias ─────────────────────────────────────────────────────────

class TestEMABias:
    def test_uptrend(self):
        assert get_ema_bias(_uptrend(60)) == "UP"

    def test_downtrend(self):
        assert get_ema_bias(_downtrend(60)) == "DOWN"

    def test_insufficient(self):
        assert get_ema_bias(pd.DataFrame({'close': [100, 101]})) == "SIDEWAYS"

    def test_none(self):
        assert get_ema_bias(None) == "SIDEWAYS"


# ─── Structure Classification ─────────────────────────────────────────

class TestStructure:
    def test_hh_hl(self):
        assert _classify_structure(
            [(5, 100.0), (15, 105.0), (25, 110.0)],
            [(10, 95.0), (20, 98.0), (30, 101.0)]
        ) == "UP"

    def test_lh_ll(self):
        assert _classify_structure(
            [(5, 110.0), (15, 105.0), (25, 100.0)],
            [(10, 101.0), (20, 98.0), (30, 95.0)]
        ) == "DOWN"

    def test_mixed(self):
        # HH but LL = mixed = SIDEWAYS
        assert _classify_structure(
            [(5, 100.0), (15, 105.0), (25, 108.0)],
            [(10, 95.0), (20, 98.0), (30, 96.0)]
        ) == "SIDEWAYS"

    def test_insufficient(self):
        assert _classify_structure([(5, 100.0)], [(10, 95.0)]) == "SIDEWAYS"


# ─── detect_trend (combined) ──────────────────────────────────────────

class TestDetectTrend:
    def test_uptrend(self):
        assert detect_trend(_uptrend(), lookback=60) == "UP"

    def test_downtrend(self):
        assert detect_trend(_downtrend(), lookback=60) == "DOWN"

    def test_sideways(self):
        assert detect_trend(_sideways(), lookback=60) == "SIDEWAYS"

    def test_insufficient(self):
        assert detect_trend(pd.DataFrame({'high': [1], 'low': [1], 'close': [1]}), lookback=50) == "SIDEWAYS"

    def test_none(self):
        assert detect_trend(None) == "SIDEWAYS"

    def test_valid_return(self):
        assert detect_trend(_uptrend(60)) in ("UP", "DOWN", "SIDEWAYS")


# ─── Zone Confluence ──────────────────────────────────────────────────

class TestConfluence:
    def test_overlap_true(self):
        assert _zones_overlap(_zone(zone_top=105, zone_bottom=100), _zone(zone_top=107, zone_bottom=103))

    def test_overlap_false(self):
        assert not _zones_overlap(_zone(zone_top=105, zone_bottom=100), _zone(zone_top=115, zone_bottom=110))

    def test_contained(self):
        assert _zones_overlap(_zone(zone_top=103, zone_bottom=102), _zone(zone_top=105, zone_bottom=100))

    def test_same_type(self):
        assert _same_type(_zone("DEMAND"), _zone("DEMAND"))
        assert not _same_type(_zone("DEMAND"), _zone("SUPPLY"))

    def test_empty_zones(self):
        assert find_zone_confluence([], _uptrend()) == []

    def test_none_data(self):
        zones = [_zone()]
        assert find_zone_confluence(zones, None) == zones


# ─── Entry Refinement ─────────────────────────────────────────────────

class TestEntryRefinement:
    def test_arrival_slow(self):
        n = 30
        close = np.linspace(100, 105, n)
        open_ = close.copy()
        open_[:20] = close[:20] - 2.0
        open_[20:] = close[20:] - 0.2
        data = pd.DataFrame({'open': open_, 'high': close + 0.5, 'low': close - 2.5, 'close': close})
        assert assess_arrival_on_entry_tf(_zone(), data) >= 7

    def test_arrival_fast(self):
        n = 30
        close = np.linspace(100, 105, n)
        open_ = close.copy()
        open_[:20] = close[:20] - 0.2
        open_[20:] = close[20:] - 5.0
        data = pd.DataFrame({'open': open_, 'high': close + 0.5, 'low': close - 5.5, 'close': close})
        assert assess_arrival_on_entry_tf(_zone(), data) <= 3

    def test_arrival_none(self):
        assert assess_arrival_on_entry_tf(_zone(), None) == 5

    def test_arrival_insufficient(self):
        data = pd.DataFrame({'open': [100, 101], 'close': [101, 102]})
        assert assess_arrival_on_entry_tf(_zone(), data) == 5

    def test_freshness_demand_fresh(self):
        z = _zone("DEMAND", zone_top=100.0, zone_bottom=98.0)
        data = pd.DataFrame({
            'open': [105, 104, 103, 104, 105],
            'high': [106, 105, 104, 105, 106],
            'low': [104, 103, 102, 103, 104],
            'close': [104, 103, 103, 104, 105],
        })
        assert check_freshness_on_entry_tf(z, data) is True

    def test_freshness_demand_tested(self):
        z = _zone("DEMAND", zone_top=100.0, zone_bottom=98.0)
        data = pd.DataFrame({
            'open': [105, 104, 103, 104, 105],
            'high': [106, 105, 104, 105, 106],
            'low': [104, 103, 99.5, 103, 104],
            'close': [104, 103, 103, 104, 105],
        })
        assert check_freshness_on_entry_tf(z, data) is False

    def test_freshness_supply_fresh(self):
        z = _zone("SUPPLY", zone_top=110.0, zone_bottom=108.0)
        data = pd.DataFrame({
            'open': [105, 104, 103, 104, 105],
            'high': [106, 105, 107, 105, 106],
            'low': [104, 103, 102, 103, 104],
            'close': [104, 103, 103, 104, 105],
        })
        assert check_freshness_on_entry_tf(z, data) is True

    def test_freshness_supply_tested(self):
        z = _zone("SUPPLY", zone_top=110.0, zone_bottom=108.0)
        data = pd.DataFrame({
            'open': [105, 104, 103, 104, 105],
            'high': [106, 105, 109.0, 105, 106],
            'low': [104, 103, 102, 103, 104],
            'close': [104, 103, 103, 104, 105],
        })
        assert check_freshness_on_entry_tf(z, data) is False

    def test_freshness_none(self):
        assert check_freshness_on_entry_tf(_zone(), None) is True


# ─── Trend Filter ─────────────────────────────────────────────────────

class TestTrendFilter:
    def test_strict_removes_demand_in_downtrend(self):
        zones = [_zone("DEMAND"), _zone("SUPPLY")]
        result = apply_trend_filter(zones, "DOWN", strict=True)
        assert len(result) == 1 and result[0].zone_type == "SUPPLY"

    def test_strict_removes_supply_in_uptrend(self):
        zones = [_zone("DEMAND"), _zone("SUPPLY")]
        result = apply_trend_filter(zones, "UP", strict=True)
        assert len(result) == 1 and result[0].zone_type == "DEMAND"

    def test_strict_sideways_keeps_all(self):
        zones = [_zone("DEMAND"), _zone("SUPPLY")]
        assert len(apply_trend_filter(zones, "SIDEWAYS", strict=True)) == 2

    def test_lenient_keeps_all(self):
        zones = [_zone("DEMAND"), _zone("SUPPLY")]
        assert len(apply_trend_filter(zones, "DOWN", strict=False)) == 2

    def test_empty(self):
        assert apply_trend_filter([], "UP", strict=True) == []


# ─── MTF Orchestrator ─────────────────────────────────────────────────

class TestOrchestrator:
    def test_no_trading_data(self):
        assert multi_timeframe_analysis(_uptrend(), None, _uptrend(30)) == []

    def test_empty_trading_data(self):
        assert multi_timeframe_analysis(_uptrend(), pd.DataFrame(), None) == []

    def test_graceful_no_higher_tf(self):
        result = multi_timeframe_analysis(None, _uptrend(100), None)
        assert isinstance(result, list)

    def test_graceful_no_entry_tf(self):
        result = multi_timeframe_analysis(_uptrend(), _uptrend(100), None)
        assert isinstance(result, list)

    def test_config_defaults(self):
        assert 'trend_tf' in DEFAULT_MTF_CONFIG
        assert 'zone_tf' in DEFAULT_MTF_CONFIG
        assert 'entry_tf' in DEFAULT_MTF_CONFIG
        assert 'trend_lookback' in DEFAULT_MTF_CONFIG
        assert 'strict_trend_filter' in DEFAULT_MTF_CONFIG


# ─── Legacy Compat ────────────────────────────────────────────────────

class TestLegacy:
    def test_import(self):
        from strategies.zone_mtf import multi_timeframe_confirm
        assert callable(multi_timeframe_confirm)

    def test_empty_zones(self):
        assert multi_timeframe_confirm([], None, None, 3.0) == []

    def test_returns_list(self):
        zones = [_zone("DEMAND", is_fresh=True)]
        result = multi_timeframe_confirm(zones, _uptrend(30), None, 3.0)
        assert isinstance(result, list)

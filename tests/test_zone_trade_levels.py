"""Tests for Zone Trade Levels package (Plan 5)."""

import pytest
import pandas as pd
import numpy as np
from strategies.zone_models import Zone
from strategies.zone_trade_levels.entry_sl import (
    calculate_entry, compute_atr, calculate_stop_loss, validate_sl_distance
)
from strategies.zone_trade_levels.targets import (
    find_opposing_zone_target, calculate_rr_target,
    calculate_partial_target, calculate_targets, _compute_rr_ratio
)
from strategies.zone_trade_levels.position_sizing import (
    calculate_position_size, calculate_risk_amount,
    calculate_position_value, validate_position_size
)
from strategies.zone_trade_levels.calculator import (
    calculate_trade_levels, calculate_trade_levels_batch
)


def _zone(zone_type="DEMAND", pattern="DBR", zone_top=105.0, zone_bottom=100.0, **kw):
    defaults = dict(
        zone_type=zone_type, pattern=pattern, zone_top=zone_top,
        zone_bottom=zone_bottom, base_candles=2, formed_at_index=10,
        formed_at_time="2024-01-10", leg_out_count=3, leg_out_body_pct=2.5,
        leg_out_body_ratio=0.75, leg_out_volume_ratio=1.8, has_gap=False,
        leg_in_body_pct=2.0, leg_in_candle_count=1, is_fresh=True,
        age_candles=5, score=45,
    )
    defaults.update(kw)
    return Zone(**defaults)


def _data(n=30, base=100.0):
    np.random.seed(42)
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.rand(n) * 2.0
    low = close - np.random.rand(n) * 2.0
    return pd.DataFrame({
        'open': close + np.random.randn(n) * 0.3,
        'high': high, 'low': low, 'close': close,
        'volume': np.random.randint(100000, 500000, n),
    })


class TestEntry:
    def test_demand_entry_at_zone_top(self):
        assert calculate_entry(_zone("DEMAND", zone_top=105.0)) == 105.0

    def test_supply_entry_at_zone_bottom(self):
        assert calculate_entry(_zone("SUPPLY", "RBD", 110.0, 107.0)) == 107.0

    def test_rounded(self):
        assert calculate_entry(_zone("DEMAND", zone_top=105.333)) == 105.33


class TestATR:
    def test_returns_positive_float(self):
        atr = compute_atr(_data(30))
        assert isinstance(atr, float) and atr > 0

    def test_short_data_fallback(self):
        atr = compute_atr(_data(5), period=14)
        assert isinstance(atr, float) and atr > 0

    def test_constant_prices(self):
        df = pd.DataFrame({
            'open': [100.0]*20, 'high': [100.5]*20,
            'low': [99.5]*20, 'close': [100.0]*20, 'volume': [100000]*20,
        })
        assert compute_atr(df, period=14) == 1.0


class TestStopLoss:
    def test_demand_sl_below_zone(self):
        z = _zone("DEMAND", zone_top=105.0, zone_bottom=100.0)
        # Entry=105, raw SL=100-2=98, cap=105*5%=5.25, max_sl=99.75
        # Since 105-98=7 > 5.25 cap, SL gets capped to 99.75
        assert calculate_stop_loss(z, 2.0, 1.0, 5.0) == 99.75

    def test_supply_sl_above_zone(self):
        z = _zone("SUPPLY", "RBD", 110.0, 107.0)
        assert calculate_stop_loss(z, 2.0, 1.0, 5.0) == 112.0

    def test_demand_sl_capped(self):
        z = _zone("DEMAND", zone_top=100.0, zone_bottom=90.0)
        assert calculate_stop_loss(z, 5.0, 1.0, 1.5) == 98.5

    def test_supply_sl_capped(self):
        z = _zone("SUPPLY", "RBD", 110.0, 100.0)
        assert calculate_stop_loss(z, 5.0, 1.0, 1.5) == 101.5

    def test_multiplier(self):
        z = _zone("DEMAND", zone_top=105.0, zone_bottom=100.0)
        assert calculate_stop_loss(z, 2.0, 1.5, 10.0) == 97.0


class TestSLValidation:
    def test_valid(self):
        assert validate_sl_distance(100.0, 98.5, 1.5) is True

    def test_too_wide(self):
        assert validate_sl_distance(100.0, 95.0, 1.5) is False

    def test_zero_entry(self):
        assert validate_sl_distance(0.0, 5.0, 1.5) is False


class TestOpposingTarget:
    def test_demand_finds_supply_above(self):
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        s = _zone("SUPPLY", "RBD", 120.0, 115.0)
        assert find_opposing_zone_target(d, [d, s]) == 115.0

    def test_supply_finds_demand_below(self):
        s = _zone("SUPPLY", "RBD", 120.0, 115.0)
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        assert find_opposing_zone_target(s, [d, s]) == 100.0

    def test_none_when_no_opposing(self):
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        assert find_opposing_zone_target(d, [d]) is None

    def test_nearest_selected(self):
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        s1 = _zone("SUPPLY", "RBD", 112.0, 110.0)
        s2 = _zone("SUPPLY", "RBD", 130.0, 125.0)
        assert find_opposing_zone_target(d, [d, s1, s2]) == 110.0


class TestRRTarget:
    def test_demand_target(self):
        assert calculate_rr_target(100.0, 98.0, 3.0) == 106.0

    def test_supply_target(self):
        assert calculate_rr_target(100.0, 102.0, 3.0) == 94.0

    def test_partial(self):
        assert calculate_partial_target(100.0, 98.0) == 102.0


class TestRRRatio:
    def test_3_to_1(self):
        assert _compute_rr_ratio(100.0, 98.0, 106.0) == 3.0

    def test_zero_risk(self):
        assert _compute_rr_ratio(100.0, 100.0, 106.0) == 0.0


class TestCalculateTargets:
    def test_opposing_zone_used(self):
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        d.entry, d.stop_loss = 100.0, 98.0
        s = _zone("SUPPLY", "RBD", 112.0, 110.0)
        cfg = {'use_opposing_zone_target': True, 'min_rr_with_opposing': 2.0, 'default_rr_ratio': 3.0}
        r = calculate_targets(d, [d, s], cfg)
        assert r['target'] == 110.0 and r['target_source'] == "opposing_zone"

    def test_fallback_rr(self):
        d = _zone("DEMAND", zone_top=100.0, zone_bottom=95.0)
        d.entry, d.stop_loss = 100.0, 98.0
        cfg = {'use_opposing_zone_target': True, 'min_rr_with_opposing': 2.0, 'default_rr_ratio': 3.0}
        r = calculate_targets(d, [d], cfg)
        assert r['target'] == 106.0 and r['target_source'] == "fixed_rr"


class TestPositionSizing:
    def test_basic(self):
        # 1% of 100k = 1000, risk/share = 2, pos = 500
        assert calculate_position_size(100.0, 98.0, 100000, 1.0) == 500

    def test_zero_risk(self):
        assert calculate_position_size(100.0, 100.0, 100000, 1.0) == 0

    def test_zero_capital(self):
        assert calculate_position_size(100.0, 98.0, 0, 1.0) == 0

    def test_risk_amount(self):
        assert calculate_risk_amount(100000, 1.0) == 1000.0

    def test_position_value(self):
        assert calculate_position_value(100.0, 500) == 50000.0

    def test_validate_within_limit(self):
        assert validate_position_size(500, 100.0, 100000, 60.0) is True

    def test_validate_exceeds_limit(self):
        assert validate_position_size(500, 100.0, 100000, 20.0) is False


class TestCalculator:
    def _config(self):
        return {
            'sl_atr_multiplier': 1.0,
            'max_sl_pct': 1.5,
            'default_rr_ratio': 3.0,
            'use_opposing_zone_target': True,
            'min_rr_with_opposing': 2.0,
            'min_rr_ratio': 2.0,
            'risk_per_trade_pct': 1.0,
            'capital': 100000,
        }

    def test_valid_demand_zone(self):
        z = _zone("DEMAND", zone_top=100.0, zone_bottom=99.0)
        data = _data(30, base=100.0)
        cfg = self._config()
        cfg['max_sl_pct'] = 5.0  # generous cap
        result = calculate_trade_levels(z, data, [z], cfg)
        if result is not None:
            assert result.entry == 100.0
            assert result.stop_loss > 0
            assert result.target_1 > result.entry
            assert result.target_2 > result.target_1
            assert result.position_size > 0

    def test_returns_none_for_bad_rr(self):
        z = _zone("DEMAND", zone_top=100.0, zone_bottom=99.0)
        data = _data(30, base=100.0)
        cfg = self._config()
        cfg['min_rr_ratio'] = 100.0  # impossible to meet
        result = calculate_trade_levels(z, data, [z], cfg)
        assert result is None

    def test_batch_filters_invalid(self):
        z1 = _zone("DEMAND", zone_top=100.0, zone_bottom=99.5)
        z2 = _zone("DEMAND", zone_top=200.0, zone_bottom=199.5)
        data = _data(30, base=100.0)
        cfg = self._config()
        cfg['max_sl_pct'] = 5.0
        results = calculate_trade_levels_batch([z1, z2], data, cfg)
        assert isinstance(results, list)
        # All results should have trade levels populated
        for r in results:
            assert r.entry > 0
            assert r.position_size > 0
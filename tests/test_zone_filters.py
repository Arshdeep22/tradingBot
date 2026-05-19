"""
Tests for zone quality filters (Plan 2 - Part B).

Tests individual filter functions and the apply_all_filters orchestrator.
"""

import pandas as pd
import pytest

from strategies.zone_models import Zone
from strategies.zone_filters import (
    filter_zone_width,
    filter_distance_from_price,
    filter_sl_cap,
    filter_freshness,
    filter_minimum_leg_out,
    filter_overlapping_zones,
    apply_all_filters,
    DEFAULT_FILTER_CONFIG,
)


def _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
               formed_at_index=0, base_candles=1, leg_out_count=1,
               is_fresh=True, leg_out_body_ratio=0.8):
    """Helper to create a Zone for testing."""
    return Zone(
        zone_type=zone_type,
        pattern="DBR" if zone_type == "DEMAND" else "RBD",
        zone_top=zone_top,
        zone_bottom=zone_bottom,
        base_candles=base_candles,
        formed_at_index=formed_at_index,
        formed_at_time="2024-01-01",
        leg_out_count=leg_out_count,
        leg_out_body_pct=1.5,
        leg_out_body_ratio=leg_out_body_ratio,
        leg_out_volume_ratio=1.5,
        has_gap=False,
        leg_in_body_pct=1.2,
        leg_in_candle_count=1,
        is_fresh=is_fresh,
    )


def _make_data(last_close=100.5):
    """Create a minimal DataFrame with specified last close price."""
    data = pd.DataFrame({
        "open": [100.0, 100.5],
        "high": [101.0, 101.5],
        "low": [99.5, 100.0],
        "close": [100.5, last_close],
        "volume": [1000, 1000],
    })
    return data


class TestFilterZoneWidth:
    """Tests for zone width filter."""

    def test_normal_width_passes(self):
        """Zone with ~1% width passes default filter."""
        zone = _make_zone(zone_top=101.0, zone_bottom=100.0)
        # width = 1/100.5 * 100 ≈ 0.995%
        assert filter_zone_width(zone, max_pct=1.5, min_pct=0.1) is True

    def test_too_wide_rejected(self):
        """Zone > 1.5% width is rejected."""
        zone = _make_zone(zone_top=102.0, zone_bottom=100.0)
        # width = 2/101 * 100 ≈ 1.98%
        assert filter_zone_width(zone, max_pct=1.5, min_pct=0.1) is False

    def test_too_narrow_rejected(self):
        """Zone < 0.1% width is rejected."""
        zone = _make_zone(zone_top=100.05, zone_bottom=100.0)
        # width = 0.05/100.025 * 100 ≈ 0.05%
        assert filter_zone_width(zone, max_pct=1.5, min_pct=0.1) is False

    def test_exact_boundary_passes(self):
        """Zone at exactly max width passes (<=)."""
        # 1.5% of midpoint 100 = 1.5 → zone_top=100.75, zone_bottom=99.25
        zone = _make_zone(zone_top=100.75, zone_bottom=99.25)
        assert filter_zone_width(zone, max_pct=1.5, min_pct=0.1) is True

    def test_zero_midpoint_rejected(self):
        """Zone with zero midpoint is rejected."""
        zone = _make_zone(zone_top=0.0, zone_bottom=0.0)
        assert filter_zone_width(zone, max_pct=1.5, min_pct=0.1) is False


class TestFilterDistanceFromPrice:
    """Tests for distance from current price filter."""

    def test_close_zone_passes(self):
        """Zone near current price passes."""
        zone = _make_zone(zone_top=101.0, zone_bottom=100.0)
        # midpoint=100.5, price=101.0, distance=0.5/101*100≈0.5%
        assert filter_distance_from_price(zone, 101.0, max_distance_pct=3.0) is True

    def test_far_zone_rejected(self):
        """Zone too far from current price is rejected."""
        zone = _make_zone(zone_top=101.0, zone_bottom=100.0)
        # midpoint=100.5, price=110.0, distance=9.5/110*100≈8.6%
        assert filter_distance_from_price(zone, 110.0, max_distance_pct=3.0) is False

    def test_zero_price_rejected(self):
        """Zero current price is handled gracefully."""
        zone = _make_zone(zone_top=101.0, zone_bottom=100.0)
        assert filter_distance_from_price(zone, 0.0, max_distance_pct=3.0) is False

    def test_exact_boundary_passes(self):
        """Zone at exactly 3% distance passes."""
        zone = _make_zone(zone_top=101.0, zone_bottom=100.0)
        # midpoint = 100.5
        # distance = |price - 100.5| / price * 100 = 3.0
        # price = 100.5 / (1 - 0.03) = 103.608...
        assert filter_distance_from_price(zone, 103.0, max_distance_pct=3.0) is True


class TestFilterSlCap:
    """Tests for stop-loss cap filter."""

    def test_small_sl_passes(self):
        """SL within 1.5% passes."""
        zone = _make_zone()
        assert filter_sl_cap(zone, entry=100.0, stop_loss=99.0, max_sl_pct=1.5) is True

    def test_large_sl_rejected(self):
        """SL > 1.5% is rejected."""
        zone = _make_zone()
        assert filter_sl_cap(zone, entry=100.0, stop_loss=97.0, max_sl_pct=1.5) is False

    def test_zero_entry_rejected(self):
        """Zero entry price is handled."""
        zone = _make_zone()
        assert filter_sl_cap(zone, entry=0.0, stop_loss=99.0, max_sl_pct=1.5) is False


class TestFilterFreshness:
    """Tests for freshness filter."""

    def test_fresh_zone_passes(self):
        """Fresh zone passes."""
        zone = _make_zone(is_fresh=True)
        assert filter_freshness(zone) is True

    def test_tested_zone_rejected(self):
        """Non-fresh zone is rejected."""
        zone = _make_zone(is_fresh=False)
        assert filter_freshness(zone) is False


class TestFilterMinimumLegOut:
    """Tests for minimum leg-out body ratio filter."""

    def test_strong_leg_out_passes(self):
        """Strong leg-out (ratio >= 0.60) passes."""
        zone = _make_zone(leg_out_body_ratio=0.75)
        assert filter_minimum_leg_out(zone, min_body_ratio=0.60) is True

    def test_weak_leg_out_rejected(self):
        """Weak leg-out (ratio < 0.60) is rejected."""
        zone = _make_zone(leg_out_body_ratio=0.45)
        assert filter_minimum_leg_out(zone, min_body_ratio=0.60) is False

    def test_exact_boundary_passes(self):
        """Ratio exactly at threshold passes."""
        zone = _make_zone(leg_out_body_ratio=0.60)
        assert filter_minimum_leg_out(zone, min_body_ratio=0.60) is True


class TestFilterOverlappingZones:
    """Tests for overlapping zone filter."""

    def test_no_overlap_all_kept(self):
        """Non-overlapping zones are all kept."""
        zone1 = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                           formed_at_index=0)
        zone2 = _make_zone(zone_type="DEMAND", zone_top=106.0, zone_bottom=105.0,
                           formed_at_index=5)
        result = filter_overlapping_zones([zone1, zone2])
        assert len(result) == 2

    def test_overlapping_same_type_newer_kept(self):
        """Overlapping zones of same type: newer one is kept."""
        zone1 = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                           formed_at_index=0)
        zone2 = _make_zone(zone_type="DEMAND", zone_top=101.5, zone_bottom=100.5,
                           formed_at_index=5)
        # These heavily overlap (50% of each zone's width overlaps)
        result = filter_overlapping_zones([zone1, zone2], overlap_threshold_pct=1.0)
        assert len(result) == 1
        assert result[0].formed_at_index == 5  # Newer kept

    def test_different_types_not_compared(self):
        """Overlapping zones of different types are both kept."""
        zone1 = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                           formed_at_index=0)
        zone2 = _make_zone(zone_type="SUPPLY", zone_top=101.5, zone_bottom=100.5,
                           formed_at_index=5)
        result = filter_overlapping_zones([zone1, zone2])
        assert len(result) == 2

    def test_empty_list(self):
        """Empty list returns empty."""
        assert filter_overlapping_zones([]) == []

    def test_result_sorted_by_index(self):
        """Result is sorted by formed_at_index ascending."""
        zone1 = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                           formed_at_index=10)
        zone2 = _make_zone(zone_type="DEMAND", zone_top=106.0, zone_bottom=105.0,
                           formed_at_index=5)
        result = filter_overlapping_zones([zone1, zone2])
        assert result[0].formed_at_index == 5
        assert result[1].formed_at_index == 10


class TestApplyAllFilters:
    """Tests for the apply_all_filters orchestrator."""

    def test_good_zone_passes_all(self):
        """A high-quality zone passes all filters."""
        zone = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                          is_fresh=True, leg_out_body_ratio=0.8)
        data = _make_data(last_close=101.5)
        result = apply_all_filters([zone], data)
        assert len(result) == 1

    def test_stale_zone_rejected(self):
        """Non-fresh zone is rejected by freshness filter."""
        zone = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                          is_fresh=False, leg_out_body_ratio=0.8)
        data = _make_data(last_close=101.5)
        result = apply_all_filters([zone], data)
        assert len(result) == 0

    def test_too_wide_zone_rejected(self):
        """Too wide zone is rejected."""
        zone = _make_zone(zone_type="DEMAND", zone_top=103.0, zone_bottom=100.0,
                          is_fresh=True, leg_out_body_ratio=0.8)
        # width = 3/101.5 * 100 ≈ 2.96% > 1.5%
        data = _make_data(last_close=101.5)
        result = apply_all_filters([zone], data)
        assert len(result) == 0

    def test_too_far_zone_rejected(self):
        """Zone too far from current price is rejected."""
        zone = _make_zone(zone_type="DEMAND", zone_top=91.0, zone_bottom=90.0,
                          is_fresh=True, leg_out_body_ratio=0.8)
        # midpoint=90.5, price=101.5, distance=11/101.5*100≈10.8% > 3%
        data = _make_data(last_close=101.5)
        result = apply_all_filters([zone], data)
        assert len(result) == 0

    def test_weak_leg_out_rejected(self):
        """Weak leg-out zone is rejected."""
        zone = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                          is_fresh=True, leg_out_body_ratio=0.3)
        data = _make_data(last_close=101.5)
        result = apply_all_filters([zone], data)
        assert len(result) == 0

    def test_custom_config(self):
        """Custom config overrides defaults."""
        # Zone with 2% width would normally fail default max_zone_width_pct=1.5
        zone = _make_zone(zone_type="DEMAND", zone_top=102.0, zone_bottom=100.0,
                          is_fresh=True, leg_out_body_ratio=0.8)
        data = _make_data(last_close=101.0)
        # Allow wider zones
        config = {"max_zone_width_pct": 3.0}
        result = apply_all_filters([zone], data, config=config)
        assert len(result) == 1

    def test_empty_zones_returns_empty(self):
        """Empty zones list returns empty."""
        data = _make_data(last_close=100.0)
        result = apply_all_filters([], data)
        assert result == []

    def test_overlapping_zones_deduplicated(self):
        """Overlapping zones are deduplicated (newer kept)."""
        zone1 = _make_zone(zone_type="DEMAND", zone_top=101.0, zone_bottom=100.0,
                           formed_at_index=0, is_fresh=True, leg_out_body_ratio=0.8)
        zone2 = _make_zone(zone_type="DEMAND", zone_top=101.3, zone_bottom=100.3,
                           formed_at_index=5, is_fresh=True, leg_out_body_ratio=0.8)
        data = _make_data(last_close=101.0)
        result = apply_all_filters([zone1, zone2], data)
        # These overlap significantly, only newer (index 5) should remain
        assert len(result) == 1
        assert result[0].formed_at_index == 5
"""
Tests for zone freshness checking (Plan 2 - Part A).

Tests the strict wick-based freshness logic:
- Fresh zones: price never entered
- Tested zones: wick entered but didn't close through
- Broken zones: price closed through (removed entirely)
"""

import pandas as pd
import pytest

from strategies.zone_models import Zone
from strategies.zone_detection.freshness import check_freshness


def _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
               formed_at_index=0, base_candles=1, leg_out_count=1):
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
        leg_out_body_ratio=0.8,
        leg_out_volume_ratio=1.5,
        has_gap=False,
        leg_in_body_pct=1.2,
        leg_in_candle_count=1,
    )


def _make_data(prices):
    """
    Create a simple OHLC DataFrame from a list of (open, high, low, close) tuples.
    """
    data = pd.DataFrame(prices, columns=["open", "high", "low", "close"])
    data["volume"] = 1000
    return data


class TestDemandZoneFreshness:
    """Tests for DEMAND zone freshness."""

    def test_demand_fresh_price_stays_above(self):
        """Demand zone stays fresh if price never enters."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # Zone forms at index 0, base=1, leg_out=1, so check starts at index 3
        # All candles after formation stay above zone_top (105)
        data = _make_data([
            (100, 105, 100, 103),   # index 0: formation base
            (103, 108, 103, 107),   # index 1: leg out
            (107, 110, 106, 109),   # index 2: leg out continuation
            (109, 112, 108, 111),   # index 3: first check - above zone
            (111, 115, 110, 114),   # index 4: above zone
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is True

    def test_demand_tested_wick_enters_zone(self):
        """Demand zone is tested when a wick enters (low <= zone_top)."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # Check starts at index 3. A candle's low dips to 104 (inside zone)
        data = _make_data([
            (100, 105, 100, 103),   # index 0
            (103, 108, 103, 107),   # index 1
            (107, 110, 106, 109),   # index 2
            (109, 112, 104, 110),   # index 3: low=104 enters zone (<=105)
            (110, 113, 109, 112),   # index 4
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is False

    def test_demand_broken_close_below_bottom(self):
        """Demand zone is broken when price closes below zone_bottom."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # A candle closes at 98, below zone_bottom (100) → zone broken
        data = _make_data([
            (100, 105, 100, 103),   # index 0
            (103, 108, 103, 107),   # index 1
            (107, 110, 106, 109),   # index 2
            (109, 110, 97, 98),     # index 3: close=98 < zone_bottom=100
        ])
        result = check_freshness([zone], data)
        assert len(result) == 0  # Zone removed entirely

    def test_demand_age_candles_calculated(self):
        """age_candles is set to number of candles after formation."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        data = _make_data([
            (100, 105, 100, 103),   # index 0
            (103, 108, 103, 107),   # index 1
            (107, 110, 106, 109),   # index 2
            (109, 112, 108, 111),   # index 3
            (111, 115, 110, 114),   # index 4
            (114, 118, 113, 117),   # index 5
        ])
        result = check_freshness([zone], data)
        assert result[0].age_candles == 3  # indices 3, 4, 5


class TestSupplyZoneFreshness:
    """Tests for SUPPLY zone freshness."""

    def test_supply_fresh_price_stays_below(self):
        """Supply zone stays fresh if price never enters."""
        zone = _make_zone(zone_type="SUPPLY", zone_top=110.0, zone_bottom=105.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # All candles stay below zone_bottom (105)
        data = _make_data([
            (108, 110, 105, 107),   # index 0
            (107, 107, 102, 103),   # index 1
            (103, 104, 100, 101),   # index 2
            (101, 103, 99, 100),    # index 3: high=103 < zone_bottom=105
            (100, 102, 98, 101),    # index 4: high=102 < zone_bottom=105
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is True

    def test_supply_tested_wick_enters_zone(self):
        """Supply zone is tested when a wick enters (high >= zone_bottom)."""
        zone = _make_zone(zone_type="SUPPLY", zone_top=110.0, zone_bottom=105.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # A candle's high reaches 106 (inside zone: >= zone_bottom=105)
        data = _make_data([
            (108, 110, 105, 107),   # index 0
            (107, 107, 102, 103),   # index 1
            (103, 104, 100, 101),   # index 2
            (101, 106, 99, 102),    # index 3: high=106 >= zone_bottom=105
            (102, 103, 98, 100),    # index 4
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is False

    def test_supply_broken_close_above_top(self):
        """Supply zone is broken when price closes above zone_top."""
        zone = _make_zone(zone_type="SUPPLY", zone_top=110.0, zone_bottom=105.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        # A candle closes at 112, above zone_top (110) → zone broken
        data = _make_data([
            (108, 110, 105, 107),   # index 0
            (107, 107, 102, 103),   # index 1
            (103, 104, 100, 101),   # index 2
            (101, 113, 100, 112),   # index 3: close=112 > zone_top=110
        ])
        result = check_freshness([zone], data)
        assert len(result) == 0  # Zone removed entirely


class TestEdgeCases:
    """Edge case tests for freshness checking."""

    def test_empty_zones_list(self):
        """Empty zones list returns empty list."""
        data = _make_data([(100, 105, 99, 103)])
        result = check_freshness([], data)
        assert result == []

    def test_empty_dataframe(self):
        """Empty DataFrame returns empty list."""
        zone = _make_zone()
        data = pd.DataFrame()
        result = check_freshness([zone], data)
        assert result == []

    def test_zone_just_formed_no_subsequent_candles(self):
        """Zone formed at end of data is fresh (no candles to check)."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=3, base_candles=1, leg_out_count=1)
        # Only 5 candles total, check_start = 3+1+1+1 = 6, which is out of bounds
        data = _make_data([
            (95, 100, 95, 98),
            (98, 102, 97, 100),
            (100, 103, 99, 102),
            (102, 105, 100, 103),
            (103, 108, 103, 107),
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is True
        assert result[0].age_candles == 0

    def test_multiple_zones_mixed_results(self):
        """Multiple zones: some fresh, some tested, some broken."""
        # Zone 1: demand at 100-105, stays fresh
        zone1 = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                           formed_at_index=0, base_candles=1, leg_out_count=1)
        # Zone 2: supply at 120-125, gets broken
        zone2 = _make_zone(zone_type="SUPPLY", zone_top=125.0, zone_bottom=120.0,
                           formed_at_index=0, base_candles=1, leg_out_count=1)
        # Price goes to 130 (breaks supply zone)
        data = _make_data([
            (100, 105, 100, 103),   # index 0
            (103, 110, 103, 108),   # index 1
            (108, 115, 107, 114),   # index 2
            (114, 130, 113, 128),   # index 3: close=128 > supply zone_top=125
        ])
        result = check_freshness([zone1, zone2], data)
        # zone1 should survive (price stays above), zone2 broken
        assert len(result) == 1
        assert result[0].zone_type == "DEMAND"
        assert result[0].is_fresh is True

    def test_demand_exact_boundary_touch(self):
        """Demand zone: low exactly at zone_top counts as tested."""
        zone = _make_zone(zone_type="DEMAND", zone_top=105.0, zone_bottom=100.0,
                          formed_at_index=0, base_candles=1, leg_out_count=1)
        data = _make_data([
            (100, 105, 100, 103),
            (103, 108, 103, 107),
            (107, 110, 106, 109),
            (109, 112, 105, 110),   # low exactly at zone_top → tested
        ])
        result = check_freshness([zone], data)
        assert len(result) == 1
        assert result[0].is_fresh is False
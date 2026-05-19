"""
Tests for the Professional 6-Dimension Zone Scoring System (Plan 3).

Tests each dimension individually and the full scoring pipeline.
"""

import pandas as pd
import pytest

from strategies.zone_models import Zone
from strategies.zone_scoring import (
    score_departure,
    score_base,
    score_freshness,
    score_arrival,
    score_time,
    score_trend,
    score_zone,
    score_zones,
    generate_reasoning,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_zone(**kwargs) -> Zone:
    """Create a Zone with sensible defaults, overridable via kwargs."""
    defaults = dict(
        zone_type="DEMAND",
        pattern="DBR",
        zone_top=105.0,
        zone_bottom=100.0,
        base_candles=2,
        formed_at_index=10,
        formed_at_time="2026-05-19 09:30:00",
        leg_out_count=2,
        leg_out_body_pct=1.5,
        leg_out_body_ratio=0.75,
        leg_out_volume_ratio=2.0,
        has_gap=False,
        leg_in_body_pct=1.2,
        leg_in_candle_count=1,
        is_fresh=True,
        age_candles=30,
    )
    defaults.update(kwargs)
    return Zone(**defaults)


def _make_ohlc_data(n: int = 100, body_size: float = 1.0) -> pd.DataFrame:
    """Create a simple OHLC DataFrame with controllable body sizes."""
    data = {
        "open": [100.0 + i * 0.1 for i in range(n)],
        "close": [100.0 + i * 0.1 + body_size for i in range(n)],
        "high": [100.0 + i * 0.1 + body_size + 0.5 for i in range(n)],
        "low": [100.0 + i * 0.1 - 0.3 for i in range(n)],
        "volume": [1000] * n,
    }
    return pd.DataFrame(data)


def _make_arrival_data(overall_body: float = 1.0, recent_body: float = 0.3) -> pd.DataFrame:
    """Create data where last 5 candles have different body size than overall."""
    n = 50
    opens = [100.0 + i * 0.1 for i in range(n)]
    closes_normal = [o + overall_body for o in opens[:-5]]
    closes_recent = [opens[-5 + i] + recent_body for i in range(5)]
    closes = closes_normal + closes_recent
    data = {
        "open": opens,
        "close": closes,
        "high": [max(o, c) + 0.2 for o, c in zip(opens, closes)],
        "low": [min(o, c) - 0.2 for o, c in zip(opens, closes)],
        "volume": [1000] * n,
    }
    return pd.DataFrame(data)


# ─── Dimension 1: Departure Strength ─────────────────────────────────────────


class TestScoreDeparture:
    """Tests for score_departure()."""

    def test_gap_gives_10(self):
        zone = _make_zone(has_gap=True, leg_out_count=1, leg_out_body_ratio=0.5, leg_out_volume_ratio=1.0)
        assert score_departure(zone) == 10

    def test_three_candles_high_vol_gives_10(self):
        zone = _make_zone(has_gap=False, leg_out_count=3, leg_out_body_ratio=0.8, leg_out_volume_ratio=2.0)
        assert score_departure(zone) == 10

    def test_three_candles_no_vol_gives_10(self):
        # 3+ consecutive large candles = 10 regardless of volume
        zone = _make_zone(has_gap=False, leg_out_count=3, leg_out_body_ratio=0.8, leg_out_volume_ratio=0.0)
        assert score_departure(zone) == 10

    def test_two_candles_high_vol_gives_8(self):
        zone = _make_zone(has_gap=False, leg_out_count=2, leg_out_body_ratio=0.75, leg_out_volume_ratio=1.8)
        assert score_departure(zone) == 8

    def test_two_candles_no_vol_gives_8(self):
        # 2 strong candles = 8 regardless of volume
        zone = _make_zone(has_gap=False, leg_out_count=2, leg_out_body_ratio=0.75, leg_out_volume_ratio=0.0)
        assert score_departure(zone) == 8

    def test_one_candle_high_vol_gives_6(self):
        zone = _make_zone(has_gap=False, leg_out_count=1, leg_out_body_ratio=0.72, leg_out_volume_ratio=1.6)
        assert score_departure(zone) == 6

    def test_one_candle_no_vol_gives_5(self):
        zone = _make_zone(has_gap=False, leg_out_count=1, leg_out_body_ratio=0.75, leg_out_volume_ratio=1.0)
        assert score_departure(zone) == 5

    def test_one_candle_decent_body_gives_4(self):
        zone = _make_zone(has_gap=False, leg_out_count=1, leg_out_body_ratio=0.65, leg_out_volume_ratio=1.0)
        assert score_departure(zone) == 4

    def test_weak_departure_gives_2(self):
        zone = _make_zone(has_gap=False, leg_out_count=1, leg_out_body_ratio=0.4, leg_out_volume_ratio=0.8)
        assert score_departure(zone) == 2


# ─── Dimension 2: Base Quality ────────────────────────────────────────────────


class TestScoreBase:
    """Tests for score_base()."""

    def test_one_candle_gives_10(self):
        zone = _make_zone(base_candles=1)
        assert score_base(zone) == 10

    def test_two_candles_gives_8(self):
        zone = _make_zone(base_candles=2)
        assert score_base(zone) == 8

    def test_three_candles_gives_6(self):
        zone = _make_zone(base_candles=3)
        assert score_base(zone) == 6

    def test_four_candles_gives_4(self):
        zone = _make_zone(base_candles=4)
        assert score_base(zone) == 4

    def test_five_candles_gives_4(self):
        zone = _make_zone(base_candles=5)
        assert score_base(zone) == 4

    def test_six_candles_gives_2(self):
        zone = _make_zone(base_candles=6)
        assert score_base(zone) == 2


# ─── Dimension 3: Freshness ──────────────────────────────────────────────────


class TestScoreFreshness:
    """Tests for score_freshness()."""

    def test_fresh_recent_gives_10(self):
        zone = _make_zone(is_fresh=True, age_candles=20)
        assert score_freshness(zone) == 10

    def test_fresh_at_boundary_50_gives_10(self):
        zone = _make_zone(is_fresh=True, age_candles=50)
        assert score_freshness(zone) == 10

    def test_fresh_under_100_gives_10(self):
        zone = _make_zone(is_fresh=True, age_candles=75)
        assert score_freshness(zone) == 10

    def test_fresh_over_100_gives_7(self):
        zone = _make_zone(is_fresh=True, age_candles=150)
        assert score_freshness(zone) == 7

    def test_not_fresh_gives_0(self):
        zone = _make_zone(is_fresh=False, age_candles=10)
        assert score_freshness(zone) == 0


# ─── Dimension 4: Arrival Quality ────────────────────────────────────────────


class TestScoreArrival:
    """Tests for score_arrival()."""

    def test_very_slow_approach_gives_10(self):
        # recent bodies are < 50% of overall average
        data = _make_arrival_data(overall_body=2.0, recent_body=0.5)
        zone = _make_zone()
        assert score_arrival(zone, data) == 10

    def test_slow_approach_gives_8(self):
        # recent bodies ~60% of overall
        data = _make_arrival_data(overall_body=2.0, recent_body=1.2)
        zone = _make_zone()
        assert score_arrival(zone, data) == 8

    def test_moderate_approach_gives_7(self):
        # recent bodies ~80% of overall
        data = _make_arrival_data(overall_body=2.0, recent_body=1.6)
        zone = _make_zone()
        assert score_arrival(zone, data) == 7

    def test_average_approach_gives_5(self):
        # recent bodies ≈ overall
        data = _make_arrival_data(overall_body=2.0, recent_body=2.2)
        zone = _make_zone()
        assert score_arrival(zone, data) == 5

    def test_fast_approach_gives_3(self):
        # recent bodies > 150% of overall
        data = _make_arrival_data(overall_body=1.0, recent_body=1.8)
        zone = _make_zone()
        assert score_arrival(zone, data) == 3

    def test_crashing_approach_gives_2(self):
        # recent bodies > 200% of overall
        data = _make_arrival_data(overall_body=1.0, recent_body=2.5)
        zone = _make_zone()
        assert score_arrival(zone, data) == 2

    def test_insufficient_data_gives_5(self):
        data = pd.DataFrame({"open": [1, 2], "close": [2, 3], "high": [3, 4], "low": [0, 1]})
        zone = _make_zone()
        assert score_arrival(zone, data) == 5

    def test_none_data_gives_5(self):
        zone = _make_zone()
        assert score_arrival(zone, None) == 5


# ─── Dimension 5: Time/Age ────────────────────────────────────────────────────


class TestScoreTime:
    """Tests for score_time()."""

    def test_very_recent_gives_10(self):
        zone = _make_zone(age_candles=5)
        assert score_time(zone) == 10

    def test_boundary_20_gives_10(self):
        zone = _make_zone(age_candles=20)
        assert score_time(zone) == 10

    def test_recent_gives_8(self):
        zone = _make_zone(age_candles=35)
        assert score_time(zone) == 8

    def test_moderate_gives_6(self):
        zone = _make_zone(age_candles=80)
        assert score_time(zone) == 6

    def test_aging_gives_4(self):
        zone = _make_zone(age_candles=130)
        assert score_time(zone) == 4

    def test_old_gives_2(self):
        zone = _make_zone(age_candles=200)
        assert score_time(zone) == 2

    def test_ancient_gives_1(self):
        zone = _make_zone(age_candles=210)
        assert score_time(zone) == 1


# ─── Dimension 6: Trend Alignment ────────────────────────────────────────────


class TestScoreTrend:
    """Tests for score_trend()."""

    def test_demand_in_uptrend_gives_10(self):
        zone = _make_zone(zone_type="DEMAND")
        assert score_trend(zone, "UPTREND") == 10

    def test_supply_in_downtrend_gives_10(self):
        zone = _make_zone(zone_type="SUPPLY", pattern="RBD")
        assert score_trend(zone, "DOWNTREND") == 10

    def test_demand_in_downtrend_gives_3(self):
        zone = _make_zone(zone_type="DEMAND")
        assert score_trend(zone, "DOWNTREND") == 3

    def test_supply_in_uptrend_gives_3(self):
        zone = _make_zone(zone_type="SUPPLY", pattern="RBD")
        assert score_trend(zone, "UPTREND") == 3

    def test_sideways_gives_5(self):
        zone = _make_zone(zone_type="DEMAND")
        assert score_trend(zone, "SIDEWAYS") == 5

    def test_none_trend_gives_5(self):
        zone = _make_zone(zone_type="DEMAND")
        assert score_trend(zone, None) == 5

    def test_case_insensitive(self):
        zone = _make_zone(zone_type="DEMAND")
        assert score_trend(zone, "uptrend") == 10


# ─── Full Scorer ──────────────────────────────────────────────────────────────


class TestScoreZone:
    """Tests for score_zone() orchestrator."""

    def test_populates_all_dimensions(self):
        zone = _make_zone(
            leg_out_count=2, leg_out_body_ratio=0.8, leg_out_volume_ratio=2.0,
            has_gap=False, base_candles=1, is_fresh=True, age_candles=10,
        )
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "UPTREND")

        assert scored.departure_score == 8
        assert scored.base_score == 10
        assert scored.freshness_score == 10
        assert scored.time_score == 10
        assert scored.trend_score == 10
        # arrival depends on data, just check it's in range
        assert 0 <= scored.arrival_score <= 10
        # total is sum
        expected_total = (
            scored.departure_score + scored.base_score + scored.freshness_score
            + scored.arrival_score + scored.time_score + scored.trend_score
        )
        assert scored.score == expected_total

    def test_score_range_0_to_60(self):
        zone = _make_zone()
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "SIDEWAYS")
        assert 0 <= scored.score <= 60

    def test_perfect_zone_near_max(self):
        """A perfect zone should score close to 60."""
        zone = _make_zone(
            has_gap=True, base_candles=1, is_fresh=True, age_candles=5,
            zone_type="DEMAND",
        )
        # Make data with very small recent bodies (slow arrival)
        data = _make_arrival_data(overall_body=2.0, recent_body=0.4)
        scored = score_zone(zone, data, "UPTREND")
        assert scored.score >= 55  # Should be near-perfect

    def test_weak_zone_low_score(self):
        """A weak zone should score low."""
        zone = _make_zone(
            has_gap=False, leg_out_count=1, leg_out_body_ratio=0.4,
            leg_out_volume_ratio=0.8, base_candles=6,
            is_fresh=False, age_candles=200,
            zone_type="DEMAND",
        )
        data = _make_arrival_data(overall_body=1.0, recent_body=2.5)
        scored = score_zone(zone, data, "DOWNTREND")
        assert scored.score <= 20  # Should be very low


class TestScoreZones:
    """Tests for score_zones() batch scorer."""

    def test_returns_sorted_by_score(self):
        zone_a = _make_zone(has_gap=True, base_candles=1, is_fresh=True, age_candles=5)
        zone_b = _make_zone(has_gap=False, leg_out_count=1, leg_out_body_ratio=0.4,
                            leg_out_volume_ratio=0.8, base_candles=6,
                            is_fresh=False, age_candles=200)
        data = _make_ohlc_data()
        scored = score_zones([zone_b, zone_a], data, "UPTREND")
        assert scored[0].score >= scored[1].score

    def test_empty_list(self):
        data = _make_ohlc_data()
        assert score_zones([], data) == []


# ─── Reasoning Generator ─────────────────────────────────────────────────────


class TestGenerateReasoning:
    """Tests for generate_reasoning()."""

    def test_populates_reasoning_field(self):
        zone = _make_zone()
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "UPTREND")
        result = generate_reasoning(scored)
        assert result.reasoning != ""
        assert "DEMAND" in result.reasoning
        assert "DBR" in result.reasoning
        assert "/60" in result.reasoning

    def test_contains_all_dimensions(self):
        zone = _make_zone()
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "SIDEWAYS")
        result = generate_reasoning(scored)
        assert "Departure" in result.reasoning
        assert "Base" in result.reasoning
        assert "Freshness" in result.reasoning
        assert "Arrival" in result.reasoning
        assert "Time" in result.reasoning
        assert "Trend" in result.reasoning

    def test_supply_zone_reasoning(self):
        zone = _make_zone(zone_type="SUPPLY", pattern="RBD")
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "DOWNTREND")
        result = generate_reasoning(scored)
        assert "SUPPLY" in result.reasoning
        assert "RBD" in result.reasoning

    def test_score_shown_in_reasoning(self):
        zone = _make_zone()
        data = _make_ohlc_data()
        scored = score_zone(zone, data, "SIDEWAYS")
        result = generate_reasoning(scored)
        assert f"{scored.score}/60" in result.reasoning

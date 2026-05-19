"""Integration test: full pipeline end-to-end verification (Plan 7).

data → detect → freshness → filter → score → trade levels → signal
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import pytest

from strategies.zone_models import Zone
from strategies.zone_scanner import ProfessionalZoneScanner, DEFAULT_CONFIG
from strategies.base_strategy import Signal, TradeSignal, TradeSetup


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_dbr_data(n=80):
    """OHLCV data with a clear DBR demand zone pattern (leg-in → base → leg-out)."""
    np.random.seed(10)
    dates = pd.date_range("2024-01-01", periods=n, freq="15min")
    o, h, l, c, v = [], [], [], [], []
    p = 100.0
    for i in range(n):
        if i == 5:                          # large bearish leg-in
            op, cl = p, p - 2.0
            hi, lo, vol = op + 0.1, cl - 0.1, 600000
        elif 6 <= i <= 7:                   # tight base
            op, cl = p, p + np.random.uniform(-0.05, 0.05)
            hi, lo, vol = max(op, cl) + 0.05, min(op, cl) - 0.05, 80000
        elif 8 <= i <= 10:                  # strong bullish leg-out
            op, cl = p, p + 2.0
            hi, lo, vol = cl + 0.1, op - 0.05, 700000
        else:
            op, cl = p, p + np.random.randn() * 0.2
            hi, lo, vol = max(op, cl) + 0.15, min(op, cl) - 0.15, 200000
        o.append(op); h.append(hi); l.append(lo); c.append(cl); v.append(int(vol))
        p = cl
    return pd.DataFrame(
        {"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=dates
    )


def _relaxed_scanner(**overrides):
    """Scanner with very permissive settings to maximise zone survival through filters."""
    return ProfessionalZoneScanner(
        min_score_to_trade=0, max_sl_pct=5.0, min_rr_ratio=1.0,
        max_distance_from_cmp=20.0, min_zone_width_pct=0.01,
        max_zone_width_pct=5.0, min_body_ratio=0.4, min_legin_multiplier=0.4,
        **overrides,
    )


# ─── Full Pipeline ────────────────────────────────────────────────────────────

class TestFullPipeline:
    """End-to-end pipeline runs without errors and returns correct types."""

    def test_pipeline_returns_list(self):
        """detect_and_score never raises; always returns a list."""
        scanner = ProfessionalZoneScanner()
        assert isinstance(scanner.detect_and_score(_make_dbr_data(), "TEST"), list)

    def test_detected_zones_have_all_fields(self):
        """Any zones produced have every required field populated correctly."""
        scanner = _relaxed_scanner()
        for zone in scanner.detect_and_score(_make_dbr_data(), "TEST"):
            assert zone.zone_type in ("DEMAND", "SUPPLY")
            assert zone.pattern in ("DBR", "RBD", "RBR", "DBD")
            assert zone.zone_top > zone.zone_bottom
            assert 0 <= zone.score <= 60
            for s in (zone.departure_score, zone.base_score, zone.freshness_score,
                      zone.arrival_score, zone.time_score, zone.trend_score):
                assert 0 <= s <= 10
            assert zone.entry > 0 and zone.stop_loss > 0
            assert zone.target_1 > 0 and zone.target_2 > 0
            assert zone.position_size > 0
            assert zone.reasoning != ""
            assert zone.symbol == "TEST"

    def test_score_equals_sum_of_dimensions(self):
        """zone.score == sum of all 6 dimension scores."""
        for zone in _relaxed_scanner().detect_and_score(_make_dbr_data(), "TEST"):
            expected = (zone.departure_score + zone.base_score + zone.freshness_score
                        + zone.arrival_score + zone.time_score + zone.trend_score)
            assert zone.score == expected

    def test_zones_sorted_descending(self):
        """detect_and_score returns zones highest-score first."""
        zones = _relaxed_scanner().detect_and_score(_make_dbr_data(), "TEST")
        scores = [z.score for z in zones]
        assert scores == sorted(scores, reverse=True)


# ─── Strategy Interface ───────────────────────────────────────────────────────

class TestStrategyInterface:
    """ProfessionalZoneScanner satisfies BaseStrategy contract."""

    def test_generate_signal_returns_trade_signal(self):
        scanner = ProfessionalZoneScanner()
        result = scanner.generate_signal(_make_dbr_data(), "TEST")
        assert isinstance(result, TradeSignal)
        assert result.symbol == "TEST"
        assert result.signal in (Signal.BUY, Signal.SELL, Signal.HOLD)

    def test_generate_signal_hold_on_empty(self):
        result = ProfessionalZoneScanner().generate_signal(pd.DataFrame(), "EMPTY")
        assert result.signal == Signal.HOLD

    def test_get_trade_setups_returns_list(self):
        setups = ProfessionalZoneScanner().get_trade_setups(_make_dbr_data(), "TEST")
        assert isinstance(setups, list)

    def test_trade_setups_valid_fields(self):
        """Each TradeSetup from relaxed scanner has valid entry/sl/target."""
        for setup in _relaxed_scanner().get_trade_setups(_make_dbr_data(), "TEST"):
            assert isinstance(setup, TradeSetup)
            assert setup.symbol == "TEST"
            assert setup.side in ("BUY", "SELL")
            assert setup.entry > 0 and setup.stop_loss > 0 and setup.target > 0

    def test_get_parameters_contains_keys(self):
        params = ProfessionalZoneScanner().get_parameters()
        assert isinstance(params, dict)
        assert params["name"] == "Professional Zone Scanner"
        assert "timeframe" in params
        assert "min_score_to_trade" in params


# ─── Edge Cases ───────────────────────────────────────────────────────────────

class TestEmptyDataGraceful:
    """Every pipeline stage handles absent or insufficient data gracefully."""

    def test_none_data_returns_empty(self):
        assert ProfessionalZoneScanner().detect_and_score(None, "X") == []

    def test_empty_df_returns_empty(self):
        assert ProfessionalZoneScanner().detect_and_score(pd.DataFrame(), "X") == []

    def test_short_data_returns_empty(self):
        data = pd.DataFrame({
            "Open": [100]*5, "High": [101]*5, "Low": [99]*5,
            "Close": [100]*5, "Volume": [1000]*5,
        })
        assert ProfessionalZoneScanner().detect_and_score(data, "X") == []

    def test_generate_signal_none_returns_hold(self):
        assert ProfessionalZoneScanner().generate_signal(None, "X").signal == Signal.HOLD

    def test_get_trade_setups_empty_returns_list(self):
        assert ProfessionalZoneScanner().get_trade_setups(pd.DataFrame(), "X") == []


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_all_tests():
    print("\n" + "=" * 60)
    print("  ZONE INTEGRATION TEST SUITE (Plan 7)")
    print("=" * 60)
    suites = [TestFullPipeline, TestStrategyInterface, TestEmptyDataGraceful]
    passed = failed = 0
    for suite in suites:
        inst = suite()
        for name in [m for m in dir(inst) if m.startswith("test_")]:
            try:
                getattr(inst, name)()
                print(f"  [PASS] {suite.__name__}.{name}")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] {suite.__name__}.{name}: {e}")
                failed += 1
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

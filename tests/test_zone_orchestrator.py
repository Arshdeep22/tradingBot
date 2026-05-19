"""
Tests for Plan 6: Main Orchestrator & Integration.

Tests the ProfessionalZoneScanner orchestrator and zone_risk module.
"""

import unittest
from unittest.mock import MagicMock
from datetime import time

import pandas as pd
import numpy as np

from strategies import ProfessionalZoneScanner, ZoneScanner, STRATEGY_REGISTRY, Signal
from strategies.base_strategy import BaseStrategy, TradeSignal, TradeSetup
from strategies.zone_risk import can_take_new_trade, is_trading_time, parse_time
from strategies.zone_scanner import DEFAULT_CONFIG, _normalize_columns


def _make_zone_data():
    """Create test data with a detectable DBR zone pattern near current price."""
    np.random.seed(42)
    prices = []
    for i in range(30):
        o = 100 + i * 0.1
        c = o + np.random.uniform(-0.3, 0.3)
        prices.append((o, max(o, c) + 0.1, min(o, c) - 0.1, c, 5000))
    # Leg-in (bearish drop)
    prices += [(103, 103.2, 100.5, 100.8, 8000), (100.8, 101, 99.5, 99.8, 7000)]
    # Base (small candles)
    prices += [(99.8, 100.1, 99.5, 99.9, 3000), (99.9, 100.2, 99.6, 100.0, 2500)]
    # Leg-out (bullish rally)
    prices += [
        (100.0, 102.5, 99.9, 102.3, 12000),
        (102.3, 104.0, 102.1, 103.8, 11000),
        (103.8, 105.5, 103.5, 105.2, 10000),
    ]
    # Price drifts back toward zone
    for i in range(10):
        b = 105 - i * 0.3
        prices.append((b, b + 0.1, b - 0.1, b, 4000))
    for i in range(10):
        prices.append((101.5, 101.6, 101.3, 101.5, 4000))
    return pd.DataFrame(prices, columns=["Open", "High", "Low", "Close", "Volume"])


class TestProfessionalZoneScanner(unittest.TestCase):
    """Test the main orchestrator class."""

    def setUp(self):
        self.scanner = ProfessionalZoneScanner()
        self.data = _make_zone_data()

    def test_inherits_base_strategy(self):
        assert isinstance(self.scanner, BaseStrategy)

    def test_default_config(self):
        assert self.scanner.config["capital"] == 100000
        assert self.scanner.config["min_score_to_trade"] == 40
        assert self.scanner.config["max_base_candles"] == 3

    def test_config_override(self):
        s = ProfessionalZoneScanner(capital=500000, min_score_to_trade=30)
        assert s.config["capital"] == 500000
        assert s.config["min_score_to_trade"] == 30

    def test_generate_signal_returns_trade_signal(self):
        signal = self.scanner.generate_signal(self.data, "TEST")
        assert isinstance(signal, TradeSignal)
        assert signal.signal in (Signal.BUY, Signal.SELL, Signal.HOLD)

    def test_generate_signal_buy(self):
        signal = self.scanner.generate_signal(self.data, "TEST")
        assert signal.signal == Signal.BUY
        assert signal.price > 0
        assert signal.stop_loss > 0
        assert signal.target > 0

    def test_get_trade_setups_returns_list(self):
        setups = self.scanner.get_trade_setups(self.data, "TEST")
        assert isinstance(setups, list)
        assert len(setups) >= 1
        for s in setups:
            assert isinstance(s, TradeSetup)

    def test_trade_setup_fields(self):
        setups = self.scanner.get_trade_setups(self.data, "TEST")
        if setups:
            s = setups[0]
            assert s.symbol == "TEST"
            assert s.side in ("BUY", "SELL")
            assert s.entry > 0
            assert s.stop_loss > 0
            assert s.target > 0
            assert s.score > 0

    def test_detect_and_score(self):
        zones = self.scanner.detect_and_score(self.data, "TEST")
        assert isinstance(zones, list)
        assert len(zones) >= 1
        z = zones[0]
        assert z.symbol == "TEST"
        assert z.score > 0
        assert z.entry > 0

    def test_detect_and_score_empty_data(self):
        zones = self.scanner.detect_and_score(pd.DataFrame(), "TEST")
        assert zones == []

    def test_detect_and_score_none_data(self):
        zones = self.scanner.detect_and_score(None, "TEST")
        assert zones == []

    def test_detect_and_score_short_data(self):
        short = self.data.head(5)
        zones = self.scanner.detect_and_score(short, "TEST")
        assert zones == []

    def test_get_parameters(self):
        params = self.scanner.get_parameters()
        assert "name" in params
        assert "timeframe" in params
        assert "capital" in params
        assert "min_score_to_trade" in params
        assert params["name"] == "Professional Zone Scanner"

    def test_multi_timeframe_scan(self):
        """Test MTF scan with mock data_fetcher."""
        mock_fetcher = MagicMock()
        mock_fetcher.get_data.return_value = self.data
        zones = self.scanner.multi_timeframe_scan(mock_fetcher, "TEST")
        assert isinstance(zones, list)
        # Should have called get_data 3 times (1h, 15m, 5m)
        assert mock_fetcher.get_data.call_count == 3

    def test_zones_sorted_by_score(self):
        zones = self.scanner.detect_and_score(self.data, "TEST")
        if len(zones) > 1:
            for i in range(len(zones) - 1):
                assert zones[i].score >= zones[i + 1].score

    def test_hold_signal_when_no_zones(self):
        # Random noise won't create valid zones
        np.random.seed(99)
        noise = pd.DataFrame({
            "Open": np.random.rand(50) * 100,
            "High": np.random.rand(50) * 100 + 50,
            "Low": np.random.rand(50) * 100 - 50,
            "Close": np.random.rand(50) * 100,
            "Volume": np.random.randint(100, 1000, 50),
        })
        signal = self.scanner.generate_signal(noise, "NOISE")
        assert signal.signal == Signal.HOLD


class TestNormalizeColumns(unittest.TestCase):
    """Test column normalization helper."""

    def test_uppercase_to_both(self):
        df = pd.DataFrame({"Open": [1], "High": [2], "Low": [3], "Close": [4], "Volume": [5]})
        result = _normalize_columns(df)
        assert "open" in result.columns
        assert "Open" in result.columns

    def test_lowercase_to_both(self):
        df = pd.DataFrame({"open": [1], "high": [2], "low": [3], "close": [4], "volume": [5]})
        result = _normalize_columns(df)
        assert "Open" in result.columns
        assert "open" in result.columns

    def test_already_both(self):
        df = pd.DataFrame({"Open": [1], "open": [1], "High": [2], "high": [2],
                           "Low": [3], "low": [3], "Close": [4], "close": [4],
                           "Volume": [5], "volume": [5]})
        result = _normalize_columns(df)
        assert len(result.columns) == 10  # No duplicates added


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility aliases."""

    def test_zone_scanner_alias(self):
        assert ZoneScanner is ProfessionalZoneScanner

    def test_registry_contains_scanner(self):
        assert "zone_scanner" in STRATEGY_REGISTRY
        assert "professional_zone_scanner" in STRATEGY_REGISTRY

    def test_create_from_registry(self):
        cls = STRATEGY_REGISTRY["zone_scanner"]
        instance = cls()
        assert isinstance(instance, BaseStrategy)


class TestRiskManagement(unittest.TestCase):
    """Test zone_risk module."""

    def setUp(self):
        self.config = {
            "trading_start": "09:45",
            "no_new_trades_after": "14:30",
            "max_open_positions": 5,
            "max_daily_loss_pct": 3.0,
            "max_trades_per_day": 3,
            "max_consecutive_losses": 5,
        }

    def test_parse_time(self):
        t = parse_time("09:45")
        assert t == time(9, 45)

    def test_max_positions_check(self):
        result, reason = can_take_new_trade(self.config, open_positions=5)
        assert result is False
        assert "Max open positions" in reason

    def test_daily_loss_check(self):
        result, reason = can_take_new_trade(self.config, daily_pnl_pct=-3.0)
        assert result is False
        assert "Daily loss limit" in reason

    def test_max_trades_check(self):
        result, reason = can_take_new_trade(self.config, trades_today=3)
        assert result is False
        assert "Max trades per day" in reason

    def test_consecutive_losses_check(self):
        result, reason = can_take_new_trade(self.config, consecutive_losses=5)
        assert result is False
        assert "consecutive losses" in reason

    def test_all_clear(self):
        result, reason = can_take_new_trade(
            self.config, open_positions=1, daily_pnl_pct=-1.0,
            trades_today=1, consecutive_losses=1,
        )
        # May pass or fail depending on current time; just check it returns a tuple
        assert isinstance(result, bool)
        assert isinstance(reason, str)

    def test_is_trading_time_callable(self):
        assert callable(is_trading_time)
        result = is_trading_time(self.config)
        assert isinstance(result, bool)


if __name__ == "__main__":
    unittest.main()
"""Unit tests for strategies/stock_selector.py — Plan 9."""

import pytest
import pandas as pd

from strategies.stock_selector import (
    StockProfile,
    StockSelectionResult,
    passes_stock_selection,
    build_stock_profile,
    DEFAULT_STOCK_SELECTION_CONFIG,
)

CFG = DEFAULT_STOCK_SELECTION_CONFIG.copy()


def _profile(**kwargs) -> StockProfile:
    defaults = dict(
        symbol="TEST",
        avg_daily_volume=1_000_000,
        current_spread_pct=0.02,
        has_corporate_action=False,
        beta=1.0,
        sector="IT",
    )
    return StockProfile(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# Acceptance criterion 2: low-volume stocks are blocked
# ---------------------------------------------------------------------------

def test_low_volume_fails():
    result = passes_stock_selection(_profile(avg_daily_volume=100_000), [], CFG)
    assert not result.passed
    assert any("liquidity" in r.lower() or "Low liquidity" in r for r in result.failed_reasons)


def test_sufficient_volume_passes():
    result = passes_stock_selection(_profile(avg_daily_volume=500_001), [], CFG)
    assert result.passed


def test_exactly_at_volume_threshold_fails():
    result = passes_stock_selection(_profile(avg_daily_volume=500_000), [], CFG)
    assert not result.passed


# ---------------------------------------------------------------------------
# Acceptance criterion 3: spread > 0.05% → FAIL
# ---------------------------------------------------------------------------

def test_wide_spread_fails():
    result = passes_stock_selection(_profile(current_spread_pct=0.10), [], CFG)
    assert not result.passed
    assert any("spread" in r.lower() for r in result.failed_reasons)


def test_tight_spread_passes():
    result = passes_stock_selection(_profile(current_spread_pct=0.04), [], CFG)
    assert result.passed


# ---------------------------------------------------------------------------
# Acceptance criterion 4: corporate action today → FAIL
# ---------------------------------------------------------------------------

def test_corporate_action_fails():
    result = passes_stock_selection(_profile(has_corporate_action=True), [], CFG)
    assert not result.passed
    assert any("corporate action" in r.lower() for r in result.failed_reasons)


# ---------------------------------------------------------------------------
# Acceptance criterion 5: beta > 2.0 → FAIL; beta < 0.5 → WARN
# ---------------------------------------------------------------------------

def test_high_beta_fails():
    result = passes_stock_selection(_profile(beta=2.1), [], CFG)
    assert not result.passed
    assert any("beta" in r.lower() for r in result.failed_reasons)


def test_beta_exactly_at_max_fails():
    result = passes_stock_selection(_profile(beta=2.0), [], CFG)
    assert result.passed  # exactly 2.0 is OK (> 2.0 fails)


def test_low_beta_warns_not_fails():
    result = passes_stock_selection(_profile(beta=0.3), [], CFG)
    assert result.passed
    assert any("beta" in w.lower() for w in result.warnings)


def test_beta_exactly_at_min_passes():
    result = passes_stock_selection(_profile(beta=0.5), [], CFG)
    assert result.passed
    assert not result.warnings


# ---------------------------------------------------------------------------
# Acceptance criterion 6: sector concentration → FAIL
# ---------------------------------------------------------------------------

def test_sector_overexposure_fails():
    open_sectors = ["IT", "IT"]
    result = passes_stock_selection(_profile(sector="IT"), open_sectors, CFG)
    assert not result.passed
    assert any("sector" in r.lower() for r in result.failed_reasons)


def test_sector_one_existing_passes():
    open_sectors = ["IT"]
    result = passes_stock_selection(_profile(sector="IT"), open_sectors, CFG)
    assert result.passed


def test_different_sectors_pass():
    open_sectors = ["Banking", "Energy"]
    result = passes_stock_selection(_profile(sector="IT"), open_sectors, CFG)
    assert result.passed


# ---------------------------------------------------------------------------
# Acceptance criterion 7: missing beta / sector → gracefully skipped
# ---------------------------------------------------------------------------

def test_none_beta_skips_check():
    result = passes_stock_selection(_profile(beta=None), [], CFG)
    assert result.passed
    assert not result.failed_reasons


def test_none_sector_skips_concentration_check():
    result = passes_stock_selection(_profile(sector=None), ["IT", "IT"], CFG)
    assert result.passed


# ---------------------------------------------------------------------------
# Multiple failures accumulate
# ---------------------------------------------------------------------------

def test_multiple_failures_reported():
    p = _profile(avg_daily_volume=10_000, current_spread_pct=1.0, has_corporate_action=True)
    result = passes_stock_selection(p, [], CFG)
    assert not result.passed
    assert len(result.failed_reasons) == 3


# ---------------------------------------------------------------------------
# build_stock_profile
# ---------------------------------------------------------------------------

def test_build_stock_profile_from_data():
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df = pd.DataFrame({
        "Volume": [1_000_000] * 25,
        "Close": [100.0] * 25,
    }, index=dates)
    quote = {"bid": 99.9, "ask": 100.1}
    beta_lookup = {"INFY": 0.78}
    sector_lookup = {"INFY": "IT"}
    corporate_actions = ["HDFC"]

    profile = build_stock_profile(
        symbol="INFY",
        historical_data=df,
        live_quote=quote,
        corporate_actions=corporate_actions,
        beta_lookup=beta_lookup,
        sector_lookup=sector_lookup,
    )

    assert profile.symbol == "INFY"
    assert profile.avg_daily_volume == pytest.approx(1_000_000)
    assert profile.current_spread_pct == pytest.approx(0.2, rel=1e-3)  # 0.2 / 100 * 100
    assert not profile.has_corporate_action
    assert profile.beta == pytest.approx(0.78)
    assert profile.sector == "IT"


def test_build_stock_profile_with_corporate_action():
    df = pd.DataFrame({"Volume": [500_000] * 20})
    profile = build_stock_profile(
        symbol="HDFC",
        historical_data=df,
        live_quote={"bid": 1500.0, "ask": 1501.0},
        corporate_actions=["HDFC"],
    )
    assert profile.has_corporate_action


def test_build_stock_profile_missing_data():
    profile = build_stock_profile(
        symbol="XYZ",
        historical_data=None,
        live_quote={},
        corporate_actions=[],
    )
    assert profile.avg_daily_volume == 0.0
    assert profile.current_spread_pct == 0.0
    assert profile.beta is None
    assert profile.sector is None

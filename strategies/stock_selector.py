"""
Stock Selection Filters — Plan 9.

Quality gates applied once per instrument before zone logic runs.
Catches low-liquidity, wide-spread, earnings-day, volatile, and sector-overexposed stocks.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_STOCK_SELECTION_CONFIG = {
    "min_avg_daily_volume": 500_000,       # 5 lakh shares
    "max_spread_pct": 0.05,                # 0.05% bid-ask spread
    "min_beta": 0.5,
    "max_beta": 2.0,
    "max_same_sector_positions": 2,
    "skip_if_no_beta": False,
    "beta_file": "data/nse_stock_beta.json",
    "sector_file": "data/nse_stock_sectors.json",
    "corporate_actions_file": "data/corporate_actions.json",
}


@dataclass
class StockProfile:
    symbol: str
    avg_daily_volume: float            # 20-day average daily volume in shares
    current_spread_pct: float          # (ask - bid) / mid_price * 100
    has_corporate_action: bool         # Results, dividend, bonus, rights today
    beta: Optional[float] = None       # Beta vs Nifty 50 (1-year)
    sector: Optional[str] = None       # NSE sector classification


@dataclass
class StockSelectionResult:
    passed: bool
    symbol: str
    failed_reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        parts = [f"{self.symbol}: {status}"]
        if self.failed_reasons:
            parts.append(f"  Reasons: {'; '.join(self.failed_reasons)}")
        if self.warnings:
            parts.append(f"  Warnings: {'; '.join(self.warnings)}")
        return "\n".join(parts)


def passes_stock_selection(
    profile: StockProfile,
    open_position_sectors: list,
    config: dict,
) -> StockSelectionResult:
    """
    Returns StockSelectionResult indicating whether the stock passes all quality gates.

    Checks in order: liquidity → spread → corporate action → beta → sector concentration.
    """
    cfg = {**DEFAULT_STOCK_SELECTION_CONFIG, **config}
    failed: list[str] = []
    warnings: list[str] = []

    # 1. Liquidity
    min_vol = cfg["min_avg_daily_volume"]
    if profile.avg_daily_volume <= min_vol:
        failed.append(
            f"Low liquidity: {profile.avg_daily_volume:,.0f} < {min_vol:,.0f} shares"
        )

    # 2. Spread
    max_spread = cfg["max_spread_pct"]
    if profile.current_spread_pct > max_spread:
        failed.append(
            f"Wide spread: {profile.current_spread_pct:.4f}% > {max_spread:.4f}%"
        )

    # 3. Corporate action
    if profile.has_corporate_action:
        failed.append("Corporate action today — zone thesis invalid")

    # 4. Beta
    if profile.beta is not None:
        min_beta = cfg["min_beta"]
        max_beta = cfg["max_beta"]
        if profile.beta > max_beta:
            failed.append(
                f"High beta ({profile.beta:.2f}) — too volatile, SL likely to be hit"
            )
        elif profile.beta < min_beta:
            warnings.append(
                f"Low beta ({profile.beta:.2f}) — slow moves, harder to hit targets"
            )
    elif not cfg.get("skip_if_no_beta", False):
        logger.debug("%s: beta unknown — skipping beta check", profile.symbol)

    # 5. Sector concentration
    if profile.sector is not None:
        count = sum(1 for s in open_position_sectors if s == profile.sector)
        max_sector = cfg["max_same_sector_positions"]
        if count >= max_sector:
            failed.append(
                f"Sector overexposure: already {count} open in {profile.sector}"
            )
    else:
        logger.debug("%s: sector unknown — skipping sector concentration check", profile.symbol)

    passed = len(failed) == 0
    result = StockSelectionResult(
        passed=passed, symbol=profile.symbol,
        failed_reasons=failed, warnings=warnings,
    )
    if not passed:
        logger.info("Stock selection REJECTED %s: %s", profile.symbol, "; ".join(failed))
    elif warnings:
        logger.info("Stock selection WARN %s: %s", profile.symbol, "; ".join(warnings))
    return result


def build_stock_profile(
    symbol: str,
    historical_data: pd.DataFrame,
    live_quote: dict,
    corporate_actions: list,
    beta_lookup: Optional[dict] = None,
    sector_lookup: Optional[dict] = None,
) -> StockProfile:
    """
    Builds StockProfile from available data sources.

    avg_daily_volume: mean of last 20 daily volumes
    current_spread_pct: (ask - bid) / mid * 100
    has_corporate_action: symbol in corporate_actions list
    beta / sector: from lookup dicts if provided
    """
    # Average daily volume — last 20 days
    avg_vol = 0.0
    if historical_data is not None and not historical_data.empty:
        vol_col = "Volume" if "Volume" in historical_data.columns else "volume"
        if vol_col in historical_data.columns:
            avg_vol = float(historical_data[vol_col].tail(20).mean())

    # Bid-ask spread
    spread_pct = 0.0
    if live_quote:
        bid = live_quote.get("bid", 0)
        ask = live_quote.get("ask", 0)
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid * 100

    has_action = symbol in (corporate_actions or [])
    beta = beta_lookup.get(symbol) if beta_lookup else None
    sector = sector_lookup.get(symbol) if sector_lookup else None

    return StockProfile(
        symbol=symbol,
        avg_daily_volume=avg_vol,
        current_spread_pct=spread_pct,
        has_corporate_action=has_action,
        beta=beta,
        sector=sector,
    )


def load_reference_data(config: dict) -> tuple[dict, dict, list]:
    """
    Loads beta_lookup, sector_lookup, and corporate_actions from JSON files.
    Returns empty defaults if files are missing.
    """
    cfg = {**DEFAULT_STOCK_SELECTION_CONFIG, **config}

    def _load(path_key: str, default):
        path = Path(cfg[path_key])
        if not path.exists():
            logger.warning("Reference file not found: %s", path)
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Failed to load %s: %s", path, e)
            return default

    beta_lookup = _load("beta_file", {})
    sector_lookup = _load("sector_file", {})
    corporate_actions = _load("corporate_actions_file", [])
    return beta_lookup, sector_lookup, corporate_actions

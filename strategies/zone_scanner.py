"""
Professional Supply & Demand Zone Scanner — Main orchestrator.

Pipeline: 1H trend → 15m detection → freshness → filters → scoring → trade levels → signals.
"""

import logging
from typing import List, Optional

import pandas as pd

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.zone_models import Zone
from strategies.zone_detection import detect_zones, check_freshness
from strategies.zone_filters import apply_all_filters
from strategies.zone_scoring import score_zones, generate_reasoning
from strategies.zone_mtf import multi_timeframe_analysis, detect_trend
from strategies.zone_trade_levels import calculate_trade_levels_batch
from strategies.market_conditions import MarketConditions, is_counter_trend_to_market
from strategies.stock_selector import (
    StockProfile, passes_stock_selection, DEFAULT_STOCK_SELECTION_CONFIG,
    build_stock_profile, load_reference_data,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    **DEFAULT_STOCK_SELECTION_CONFIG,
    "enable_stock_selection": True,
    # Detection
    "max_base_candles": 3, "min_body_ratio": 0.60,
    "min_volume_ratio": 1.5, "min_legin_multiplier": 0.8,
    "detect_dbr": True, "detect_rbd": True, "detect_rbr": True, "detect_dbd": True,
    # Filters
    "max_zone_width_pct": 1.5, "min_zone_width_pct": 0.1, "max_distance_from_cmp": 3.0,
    # Scoring
    "min_score_to_trade": 40,
    # MTF
    "trend_tf": "1h", "zone_tf": "15m", "entry_tf": "5m", "strict_trend_filter": False,
    # Trade Levels
    "sl_atr_multiplier": 1.0, "max_sl_pct": 1.5,
    "default_rr_ratio": 3.0, "min_rr_ratio": 2.0,
    "risk_per_trade_pct": 1.0, "capital": 100000,
    # Risk Management
    "trading_start": "09:45", "no_new_trades_after": "14:30",
    "gap_day_start": "09:45",
    "max_open_positions": 5, "max_daily_loss_pct": 3.0,
    "max_trades_per_day": 3, "max_consecutive_losses": 5,
    # Market Conditions (VIX / Nifty)
    "enable_market_conditions": True,
    "is_news_day": False,
    "vix_high_threshold": 20.0, "vix_extreme_threshold": 25.0,
    "nifty_strong_move_pct": 2.0, "gap_threshold_pct": 1.0,
    "high_vix_sl_multiplier": 1.5, "high_vix_size_multiplier": 0.7,
    "news_day_can_trade": False, "news_day_size_multiplier": 0.5,
    # Confirmation candle
    "check_confirmation": True,
    "confirmation_check_pct": 0.5,
    "require_confirmation": False,
    "min_confirmation_strength": 3,
}


def _normalize_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure DataFrame has both capitalized and lowercase column aliases."""
    df = data.copy()
    col_map = {"open": "Open", "high": "High", "low": "Low",
               "close": "Close", "volume": "Volume"}
    for lower, upper in col_map.items():
        if upper in df.columns and lower not in df.columns:
            df[lower] = df[upper]
        elif lower in df.columns and upper not in df.columns:
            df[upper] = df[lower]
    return df


class ProfessionalZoneScanner(BaseStrategy):
    """Professional Supply & Demand Zone Scanner with full pipeline."""

    def __init__(self, **kwargs):
        super().__init__(name="Professional Zone Scanner", timeframe="15m")
        self.config = {**DEFAULT_CONFIG, **kwargs}

    def generate_signal(self, data: pd.DataFrame, symbol: str) -> TradeSignal:
        """BaseStrategy interface — returns BUY/SELL/HOLD signal."""
        zones = self.detect_and_score(data, symbol)
        if not zones:
            return TradeSignal(Signal.HOLD, symbol, reason="No qualified zones")

        best = zones[0]
        if best.zone_type == "DEMAND":
            signal = Signal.BUY
        elif best.zone_type == "SUPPLY":
            signal = Signal.SELL
        else:
            signal = Signal.HOLD

        return TradeSignal(
            signal=signal, symbol=symbol,
            price=best.entry if best.entry else best.midpoint,
            stop_loss=best.stop_loss,
            target=best.target_2 if best.target_2 else best.target_1,
            reason=best.reasoning or f"{best.pattern} zone, score={best.score}/60",
        )

    def get_trade_setups(
        self,
        data: pd.DataFrame,
        symbol: str,
        live_quote: Optional[dict] = None,
        open_position_sectors: Optional[List[str]] = None,
        market_conditions: Optional[MarketConditions] = None,
    ) -> List[TradeSetup]:
        """One TradeSetup per qualified zone."""
        if market_conditions and not market_conditions.can_trade:
            logger.info(f"Skipping {symbol}: {market_conditions.skip_reason}")
            return []

        stock_profile: Optional[StockProfile] = None
        if self.config.get("enable_stock_selection", True):
            beta_lookup, sector_lookup, corporate_actions = load_reference_data(self.config)
            stock_profile = build_stock_profile(
                symbol=symbol,
                historical_data=data,
                live_quote=live_quote or {},
                corporate_actions=corporate_actions,
                beta_lookup=beta_lookup,
                sector_lookup=sector_lookup,
            )
        zones = self.detect_and_score(
            data, symbol,
            stock_profile=stock_profile,
            open_position_sectors=open_position_sectors or [],
        )

        setups = []
        for zone in zones:
            if zone.score < self.config["min_score_to_trade"]:
                continue
            if not zone.entry or not zone.stop_loss:
                continue
            target = zone.target_2 if zone.target_2 else zone.target_1
            if not target:
                continue
            # Block counter-trend zones if market has a strong directional move
            if market_conditions and is_counter_trend_to_market(zone, market_conditions):
                logger.debug(f"Skipping counter-trend {zone.zone_type} zone for {symbol}")
                continue

            setups.append(TradeSetup(
                symbol=symbol,
                side="BUY" if zone.zone_type == "DEMAND" else "SELL",
                entry=zone.entry, stop_loss=zone.stop_loss, target=target,
                score=zone.score,
                reasoning=zone.reasoning or f"{zone.pattern} score={zone.score}",
            ))
        return setups

    def detect_and_score(self, data: pd.DataFrame, symbol: str,
                         trend: str = "SIDEWAYS",
                         stock_profile: Optional[StockProfile] = None,
                         open_position_sectors: Optional[List[str]] = None) -> List[Zone]:
        """Full single-TF pipeline: detect → freshness → filter → score → trade levels."""
        if data is None or len(data) < 10:
            return []

        if stock_profile:
            result = passes_stock_selection(
                stock_profile, open_position_sectors or [], self.config
            )
            if not result.passed:
                return []

        data = _normalize_columns(data)

        zones = detect_zones(data, self.config)
        if not zones:
            return []
        for z in zones:
            z.symbol = symbol

        zones = check_freshness(zones, data)
        if not zones:
            return []

        zones = apply_all_filters(zones, data, self.config)
        if not zones:
            return []

        trend_label = self._resolve_trend(data, trend)
        zones = score_zones(zones, data, trend_label)
        zones = [generate_reasoning(z) for z in zones]
        zones = calculate_trade_levels_batch(zones, data, self.config)
        zones = [z for z in zones if z.score >= self.config["min_score_to_trade"]]
        zones.sort(key=lambda z: z.score, reverse=True)
        return zones

    def multi_timeframe_scan(
        self,
        data_fetcher,
        symbol: str,
        stock_profile: Optional[StockProfile] = None,
        open_position_sectors: Optional[List[str]] = None,
        market_conditions: Optional[MarketConditions] = None,
    ) -> List[Zone]:
        """Full 3-TF analysis using data_fetcher."""
        if market_conditions and not market_conditions.can_trade:
            logger.info(f"Skipping MTF scan for {symbol}: {market_conditions.skip_reason}")
            return []

        if stock_profile:
            result = passes_stock_selection(
                stock_profile, open_position_sectors or [], self.config
            )
            if not result.passed:
                return []

        trend_tf = self.config["trend_tf"]
        zone_tf = self.config["zone_tf"]
        entry_tf = self.config["entry_tf"]

        data_higher = data_fetcher.get_data(symbol, trend_tf, "10d")
        data_trading = data_fetcher.get_data(symbol, zone_tf, "5d")
        data_entry = data_fetcher.get_data(symbol, entry_tf, "2d")

        if data_higher is not None:
            data_higher = _normalize_columns(data_higher)
        if data_trading is not None:
            data_trading = _normalize_columns(data_trading)
        if data_entry is not None:
            data_entry = _normalize_columns(data_entry)

        zones = multi_timeframe_analysis(
            data_higher=data_higher, data_trading=data_trading,
            data_entry=data_entry, config=self.config,
        )

        # Filter counter-trend zones if market has a strong directional bias
        if market_conditions:
            zones = [z for z in zones if not is_counter_trend_to_market(z, market_conditions)]

        if zones and data_trading is not None:
            zones = calculate_trade_levels_batch(zones, data_trading, self.config)
        for z in zones:
            z.symbol = symbol
        zones = [generate_reasoning(z) for z in zones]
        zones = [z for z in zones if z.score >= self.config["min_score_to_trade"]]
        zones.sort(key=lambda z: z.score, reverse=True)
        return zones

    def get_parameters(self) -> dict:
        """Return all config for display/logging."""
        return {"name": self.name, "timeframe": self.timeframe, **self.config}

    def _resolve_trend(self, data: pd.DataFrame, trend: str) -> str:
        """Convert trend to scoring format or auto-detect from data."""
        if trend != "SIDEWAYS":
            return {"UP": "UPTREND", "DOWN": "DOWNTREND"}.get(trend, trend)
        if len(data) >= 50:
            detected = detect_trend(data, lookback=50)
            return {"UP": "UPTREND", "DOWN": "DOWNTREND"}.get(detected, "SIDEWAYS")
        return "SIDEWAYS"


# Backward compatibility alias
ZoneScanner = ProfessionalZoneScanner

"""
Strategies Package
------------------
Trading strategies for the bot.

Module structure:
- base_strategy.py: Base class for all strategies
- zone_models.py: Zone dataclass
- zone_detection/: Zone detection package (config, preparation, components, detector, freshness)
- zone_filters.py: Zone quality filters
- zone_scoring/: 6-dimension scoring system
- zone_mtf/: Multi-timeframe analysis (trend, confluence, entry refinement)
- zone_trade_levels/: Entry, SL, targets, position sizing
- zone_risk.py: Risk management checks
- zone_scanner.py: Main ProfessionalZoneScanner strategy (orchestrator)
"""

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.zone_models import Zone
from strategies.zone_detection import detect_zones, DEFAULT_CONFIG
from strategies.zone_scanner import ProfessionalZoneScanner
from strategies.stock_selector import (
    StockProfile, StockSelectionResult,
    passes_stock_selection, build_stock_profile, load_reference_data,
    DEFAULT_STOCK_SELECTION_CONFIG,
)

# Backward compatibility alias
ZoneScanner = ProfessionalZoneScanner

# Strategy registry for dynamic loading
STRATEGY_REGISTRY = {
    "zone_scanner": ProfessionalZoneScanner,
    "professional_zone_scanner": ProfessionalZoneScanner,
}

__all__ = [
    "BaseStrategy",
    "Signal",
    "TradeSignal",
    "TradeSetup",
    "Zone",
    "detect_zones",
    "DEFAULT_CONFIG",
    "ProfessionalZoneScanner",
    "ZoneScanner",
    "STRATEGY_REGISTRY",
    # Plan 9 — stock selection
    "StockProfile",
    "StockSelectionResult",
    "passes_stock_selection",
    "build_stock_profile",
    "load_reference_data",
    "DEFAULT_STOCK_SELECTION_CONFIG",
]
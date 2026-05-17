"""
Strategies package.

Currently focused exclusively on Supply & Demand Zone strategy.
"""
from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.zone_scanner import ZoneScanner

# Registry maps display name → strategy class.
STRATEGY_REGISTRY = {
    "Supply & Demand Zones": ZoneScanner,
}

__all__ = [
    'BaseStrategy', 'Signal', 'TradeSignal', 'TradeSetup',
    'ZoneScanner',
    'STRATEGY_REGISTRY',
]
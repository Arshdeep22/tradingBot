"""
Strategies package.

To add a new strategy:
1. Create strategies/my_strategy.py — inherit BaseStrategy, implement generate_signal() + get_parameters()
2. Import it here and add one entry to STRATEGY_REGISTRY
"""
from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.ema_crossover import EMACrossoverStrategy
from strategies.zone_scanner import ZoneScanner
from strategies.rsi_reversal import RSIReversalStrategy

# Registry maps display name → strategy class.
# All entries appear automatically in the Test Strategy dropdown and can be set
# as ACTIVE_STRATEGY in config/settings.py.
STRATEGY_REGISTRY = {
    "Supply & Demand Zones": ZoneScanner,
    "EMA Crossover": EMACrossoverStrategy,
    "RSI Reversal": RSIReversalStrategy,
}

__all__ = [
    'BaseStrategy', 'Signal', 'TradeSignal', 'TradeSetup',
    'ZoneScanner', 'EMACrossoverStrategy', 'RSIReversalStrategy',
    'STRATEGY_REGISTRY',
]

"""
Strategies Package
------------------
Trading strategies for the bot.

Module structure:
- zone_models.py: Zone dataclass
- zone_detection.py: Zone detection algorithms  
- zone_scoring.py: Scoring, trade levels, reasoning
- zone_mtf.py: Multi-timeframe confirmation
- zone_scanner.py: Main ZoneScanner strategy (orchestrator)
- base_strategy.py: Base class for all strategies
"""

from strategies.base_strategy import BaseStrategy, Signal, TradeSignal, TradeSetup
from strategies.zone_scanner import ZoneScanner
from strategies.zone_models import Zone
# Strategies package
from strategies.base_strategy import BaseStrategy, Signal, TradeSignal
from strategies.ema_crossover import EMACrossoverStrategy

__all__ = ['BaseStrategy', 'Signal', 'TradeSignal', 'EMACrossoverStrategy']
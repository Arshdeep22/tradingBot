"""
Historical Walk-Forward Trainer
--------------------------------
Simulates the full trading loop on up to 60 days of real historical 15-minute
data to bootstrap strategy learning before live trading begins.

Each trading day is one iteration:
  1. Build data = all 15m bars from dataset start -> 11:02 AM IST on day D
  2. Run strategies on build data -> find setups (Zone + EMA + RSI)
  3. Test data = 15m bars from 11:02 AM -> 3:30 PM IST on day D only
  4. Simulate each setup bar-by-bar -> TARGET, SL, or EXPIRED

Every 5 days:   mini-optimizer updates params (no Claude -- pure win-rate grid)
Every 10 days:  Claude synthesis call (starting day 10) for pattern insights
Final:          comprehensive Claude summary saved to strategy_memory.json + strategy_weights.json

Callable as library:  from historical_trainer import run_training
Callable as CLI:      python -m historical_trainer [--quick] [--no-ai]
"""

import sys
import os
import logging

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.makedirs("logs", exist_ok=True)
os.makedirs("reports/training", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/historical_trainer.log", mode="a"),
    ],
)

from .runner import run_training, main  # noqa: E402

__all__ = ["run_training", "main"]
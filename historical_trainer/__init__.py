"""
Historical Walk-Forward Trainer
--------------------------------
Simulates the full Professional Zone Scanner pipeline on up to 60 days of real
historical 15-minute data to bootstrap strategy learning before live trading begins.

Strategy: Professional Zone Scanner with 6-dimension scoring (0-60):
  - Departure (leg-out quality, 0-10)
  - Base (tightness, 0-10)
  - Freshness (untested zone, 0-10)
  - Arrival (leg-in quality, 0-10)
  - Time (zone age, 0-10)
  - Trend (HTF alignment, 0-10)

Each trading day is one iteration:
  1. Build data = all 15m bars from dataset start -> 11:02 AM IST on day D
  2. Run ProfessionalZoneScanner on build data -> detect, score, filter zones
  3. Test data = 15m bars over next 3 trading days
  4. Simulate each setup bar-by-bar -> TARGET_HIT, SL_HIT, or EXPIRED

Every 5 days:   mini-optimizer runs param grid (composite: WR + RR + P&L)
Every 10 days:  Claude synthesis call (starting day 10) for pattern insights
Final:          comprehensive Claude summary saved to strategy_memory.json

Key tunable parameters:
  - min_score_to_trade (threshold out of 60)
  - default_rr_ratio, min_rr_ratio
  - sl_atr_multiplier, max_sl_pct
  - max_base_candles

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
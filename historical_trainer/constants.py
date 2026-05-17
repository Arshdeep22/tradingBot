"""
Constants for the Historical Walk-Forward Trainer.
Grids, time constants, symbol lists.
"""

from itertools import product
from config.settings import NIFTY_50

# ── Grid search parameter combinations (Zone Scanner only) ────────────────────
ZONE_GRID       = list(product([70, 75, 80], [2.0, 2.5, 3.0], [3, 4, 5]))
QUICK_ZONE_GRID = list(product([70, 75, 80], [2.0, 3.0], [4]))

# ── Backtesting parameters ────────────────────────────────────────────────────
TEST_DAYS   = 15
DATA_PERIOD = "60d"

# ── Time constants (UTC equivalents of IST times) ─────────────────────────────
# 11:02 AM IST = 5:32 UTC  (split point for each day)
SPLIT_UTC_H, SPLIT_UTC_M = 5, 32
# 3:30 PM IST  = 10:00 UTC (end of NSE market)
EOD_UTC_H, EOD_UTC_M = 10, 0

# ── Symbol lists for training ─────────────────────────────────────────────────
# Top 10/20 Nifty symbols (balance of speed vs. coverage)
TRAINING_SYMBOLS_QUICK = NIFTY_50[:10]
TRAINING_SYMBOLS_FULL  = NIFTY_50[:20]
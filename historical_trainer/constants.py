"""
Constants for the Historical Walk-Forward Trainer (v3).
Grids, time constants, symbol lists.

KEY CHANGES (v3):
- Default SL multiplier raised to 1.8 (was 1.5) — fewer stop hunts
- Default max_sl_pct raised to 2.5% (was 2.0%) — wider risk allowance
- Default RR target lowered to 1.8 (was 2.0) — more achievable targets
- min_rr_ratio lowered to 1.2 (was 1.5) — don't reject valid setups
- Grid focuses on sweet spots found in previous runs
- max_distance_from_cmp widened to 4.0% — see more zone candidates
"""

from itertools import product
from config.settings import NIFTY_50

# ── Grid search parameter combinations (Professional Zone Scanner) ─────────────
# Params: (min_score_to_trade, default_rr_ratio, min_rr_ratio, sl_atr_multiplier, max_sl_pct, max_base_candles)
#
# v3: Focused on what worked in previous runs:
# - Week 2 winners had scores 47-51, trending regime, RR ~1.0-1.1
# - SL needs to be wider to avoid stop-hunts (1.5-2.0x ATR)
# - RR targets of 1.5-2.0 are realistic (3.0 never gets hit)
ZONE_GRID = list(product(
    [35, 38, 42],        # min_score_to_trade (lower = more trades for learning)
    [1.5, 1.8, 2.0],    # default_rr_ratio (realistic targets)
    [1.0, 1.2],          # min_rr_ratio (don't reject good setups)
    [1.5, 1.8, 2.0],    # sl_atr_multiplier (wider = fewer false SL hits)
    [2.5, 3.0],          # max_sl_pct (allow wider SL for large-cap)
    [3, 4],              # max_base_candles (3 = tight, 4 = more opportunities)
))

# Quick grid: fewer combinations for faster iteration
QUICK_ZONE_GRID = list(product(
    [35, 38, 42],        # min_score_to_trade
    [1.5, 1.8],          # default_rr_ratio
    [1.2],               # min_rr_ratio
    [1.8],               # sl_atr_multiplier
    [2.5],               # max_sl_pct
    [3],                 # max_base_candles
))

# ── Default Zone Scanner parameters (v3: wider SL, lower RR, more realistic) ───
DEFAULT_ZONE_PARAMS = {
    "min_score_to_trade": 38,       # Was 42 — too restrictive, caused 0 trades
    "default_rr_ratio": 1.8,        # Was 2.0 — 1.8 is more achievable on 15m
    "min_rr_ratio": 1.2,            # Was 1.5 — was rejecting valid setups
    "sl_atr_multiplier": 1.8,       # Was 1.5 — wider to avoid stop-hunts
    "max_sl_pct": 2.5,              # Was 2.0 — large-cap stocks need more room
    "max_base_candles": 3,          # Keep tight bases
    "min_body_ratio": 0.55,         # Was 0.60 — slightly more lenient
    "min_volume_ratio": 1.3,        # Was 1.5 — allow slightly lower volume
    "max_zone_width_pct": 2.0,      # Was 1.5 — allow wider zones
    "max_distance_from_cmp": 4.0,   # Was 3.0 — see more candidates
}

# ── Backtesting parameters ────────────────────────────────────────────────────
TEST_DAYS = 30  # Lookback for grid search evaluation
DATA_PERIOD = "60d"

# ── Time constants (UTC equivalents of IST times) ─────────────────────────────
# 11:02 AM IST = 5:32 UTC  (split point for each day)
SPLIT_UTC_H, SPLIT_UTC_M = 5, 32
# 3:30 PM IST  = 10:00 UTC (end of NSE market)
EOD_UTC_H, EOD_UTC_M = 10, 0

# ── Symbol lists for training ─────────────────────────────────────────────────
# Top 10/20 Nifty symbols (balance of speed vs. coverage)
TRAINING_SYMBOLS_QUICK = NIFTY_50[:10]
TRAINING_SYMBOLS_FULL = NIFTY_50[:20]
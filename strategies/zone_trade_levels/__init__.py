"""
Zone Trade Levels Package.
Calculates professional entry, stop loss, targets, and position sizing.
"""

from strategies.zone_trade_levels.entry_sl import (
    calculate_entry, calculate_stop_loss, compute_atr, validate_sl_distance,
    get_confirmation_entry,
)
from strategies.zone_trade_levels.confirmation import (
    ConfirmationSignal,
    detect_demand_confirmation, detect_supply_confirmation,
    is_bullish_engulfing, is_hammer,
    is_bearish_engulfing, is_shooting_star,
    is_morning_star, is_evening_star,
)
from strategies.zone_trade_levels.targets import (
    find_opposing_zone_target, calculate_rr_target,
    calculate_partial_target, calculate_targets,
)
from strategies.zone_trade_levels.position_sizing import (
    calculate_position_size, calculate_risk_amount,
    calculate_position_value, validate_position_size,
)
from strategies.zone_trade_levels.calculator import (
    calculate_trade_levels, calculate_trade_levels_batch
)
from strategies.zone_trade_levels.management import (
    TrailMethod, ActiveTrade, TradeAction, TradeEvent,
    check_breakeven, trail_swing, trail_atr, trail_ema,
    apply_trailing_stop, check_time_exit, update_open_trade,
)

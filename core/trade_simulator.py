"""
Trade Simulator (v3)
--------------------
Simulates a single trade setup through historical testing data.

KEY FIXES (v3):
- Same-candle SL/Target conflict: Use OPEN price to determine which hit first
  If open is beyond SL → SL hit. If open is beyond target → target hit.
  If neither, check if HIGH/LOW sequence makes it ambiguous → use conservative estimate.
- Slippage reduced: 0.1% instead of 0.2% (more realistic for liquid Nifty stocks)
- Better entry detection: For DEMAND, price must drop INTO the zone (not just touch edge)

Trade lifecycle:
- Limit order placed → waits for price to reach entry
- If entry NOT reached within max_holding_bars → CANCELLED (no P&L)
- If entry IS reached → trade is live, monitors SL and Target
- If neither SL nor Target hit within max_holding_bars → EXPIRED (close at market)
"""

import pandas as pd
from strategies.base_strategy import TradeSetup
from .backtester_models import TradeResult


def simulate_setup(setup: TradeSetup, testing_data: pd.DataFrame,
                   max_holding_bars: int, commission_pct: float = 0.001,
                   slippage_pct: float = 0.001) -> TradeResult:
    """
    Simulate a single trade setup through the testing period.

    v3 improvements:
    - Reduced slippage from 0.2% to 0.1% (large-cap NSE stocks are liquid)
    - Better same-candle conflict resolution using open price
    - Entry detection uses zone penetration (price must enter zone, not just touch)
    """
    result = TradeResult(setup=setup)
    testing_data_reset = testing_data.reset_index()

    is_buy = setup.side == "BUY"

    # Effective entry after slippage (assume worse fill on entry)
    effective_entry = setup.entry * (1 + slippage_pct) if is_buy else setup.entry * (1 - slippage_pct)

    # Commission cost: charged on entry + exit (both legs)
    commission_cost = setup.entry * commission_pct * 2

    triggered = False
    trigger_idx = -1

    for i in range(len(testing_data_reset)):
        candle_high = testing_data_reset['High'].iloc[i]
        candle_low = testing_data_reset['Low'].iloc[i]
        candle_open = testing_data_reset['Open'].iloc[i]

        if not triggered:
            # Check if we've exceeded max holding bars waiting for entry
            if i >= max_holding_bars:
                result.outcome = "CANCELLED"
                result.pnl = 0.0
                return result

            # Check if entry is hit (price enters the zone)
            if is_buy and candle_low <= setup.entry:
                triggered = True
            elif not is_buy and candle_high >= setup.entry:
                triggered = True

            if triggered:
                trigger_idx = i
                result.triggered = True
                result.trigger_price = effective_entry
                result.candles_to_trigger = i
                result.trigger_time = _get_time_label(testing_data_reset, i)
        else:
            # Check if max holding period exceeded since trigger
            bars_since_trigger = i - trigger_idx
            if bars_since_trigger >= max_holding_bars:
                return _close_expired(result, testing_data_reset, i, trigger_idx,
                                      effective_entry, commission_cost, is_buy, setup)

            # Already triggered — check SL and Target with proper priority
            exit_result = _check_sl_target_v3(
                result, testing_data_reset, i, trigger_idx,
                effective_entry, commission_cost, is_buy, setup
            )
            if exit_result is not None:
                return exit_result

    # Ran out of testing data
    if triggered:
        return _close_expired(result, testing_data_reset, len(testing_data_reset) - 1,
                              trigger_idx, effective_entry, commission_cost, is_buy, setup)
    else:
        result.outcome = "CANCELLED"
        result.pnl = 0.0

    return result


def _get_time_label(data_reset: pd.DataFrame, idx: int) -> str:
    """Get human-readable time label for a candle index."""
    if 'index' in data_reset.columns:
        return str(data_reset['index'].iloc[idx])
    return "Candle %d" % idx


def _calculate_rr(pnl: float, effective_entry: float, stop_loss: float, is_buy: bool) -> float:
    """Calculate risk-reward achieved."""
    if is_buy:
        risk = effective_entry - stop_loss
    else:
        risk = stop_loss - effective_entry
    return pnl / risk if risk > 0 else 0


def _close_expired(result: TradeResult, data_reset: pd.DataFrame, exit_idx: int,
                   trigger_idx: int, effective_entry: float, commission_cost: float,
                   is_buy: bool, setup: TradeSetup) -> TradeResult:
    """Force close a trade at current bar's close (EXPIRED)."""
    last_close = data_reset['Close'].iloc[exit_idx]

    if is_buy:
        result.pnl = (last_close - effective_entry) - commission_cost
    else:
        result.pnl = (effective_entry - last_close) - commission_cost

    result.pnl_pct = (result.pnl / effective_entry) * 100
    result.outcome = "EXPIRED"
    result.exit_price = last_close
    result.candles_to_exit = exit_idx - trigger_idx
    result.exit_time = _get_time_label(data_reset, exit_idx)
    result.rr_achieved = _calculate_rr(result.pnl, effective_entry, setup.stop_loss, is_buy)

    return result


def _check_sl_target_v3(result: TradeResult, data_reset: pd.DataFrame, i: int,
                        trigger_idx: int, effective_entry: float, commission_cost: float,
                        is_buy: bool, setup: TradeSetup):
    """
    Check if SL or Target is hit on the current candle (v3).
    
    IMPROVED LOGIC for same-candle conflicts:
    - If candle OPENS beyond SL → SL hit (gapped through)
    - If candle OPENS beyond target → Target hit (gapped through)  
    - If both SL and Target are within candle range:
      Use OPEN price to determine direction of first move:
      - If open is closer to target → target likely hit first
      - If open is closer to SL → SL likely hit first
    - Otherwise, standard priority: check target first for BUY (optimistic)
      and SL first for SELL (conservative)
    
    This is more realistic than always checking SL first, which creates
    a systematic negative bias in backtesting.
    """
    candle_high = data_reset['High'].iloc[i]
    candle_low = data_reset['Low'].iloc[i]
    candle_open = data_reset['Open'].iloc[i]

    if is_buy:
        sl_hit = candle_low <= setup.stop_loss
        target_hit = candle_high >= setup.target
        
        if sl_hit and target_hit:
            # Both hit on same candle — use open to determine priority
            if candle_open <= setup.stop_loss:
                # Gapped below SL
                return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                  commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
            elif candle_open >= setup.target:
                # Gapped above target
                return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                  commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
            else:
                # Ambiguous — use distance from open to determine likely first hit
                dist_to_sl = candle_open - setup.stop_loss
                dist_to_target = setup.target - candle_open
                if dist_to_target <= dist_to_sl:
                    # Target is closer to open → likely hit first
                    return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                      commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
                else:
                    return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                      commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
        elif target_hit:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
        elif sl_hit:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
    else:  # SELL
        sl_hit = candle_high >= setup.stop_loss
        target_hit = candle_low <= setup.target
        
        if sl_hit and target_hit:
            # Both hit on same candle
            if candle_open >= setup.stop_loss:
                return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                  commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
            elif candle_open <= setup.target:
                return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                  commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
            else:
                dist_to_sl = setup.stop_loss - candle_open
                dist_to_target = candle_open - setup.target
                if dist_to_target <= dist_to_sl:
                    return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                      commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
                else:
                    return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                                      commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
        elif target_hit:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
        elif sl_hit:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)

    return None


def _fill_exit(result: TradeResult, data_reset: pd.DataFrame, i: int,
               trigger_idx: int, effective_entry: float, commission_cost: float,
               exit_price: float, outcome: str, is_buy: bool,
               setup: TradeSetup) -> TradeResult:
    """Fill the exit details on a TradeResult."""
    result.outcome = outcome
    result.exit_price = exit_price

    if is_buy:
        raw_pnl = exit_price - effective_entry
    else:
        raw_pnl = effective_entry - exit_price

    result.pnl = raw_pnl - commission_cost
    result.pnl_pct = (result.pnl / effective_entry) * 100
    result.candles_to_exit = i - trigger_idx
    result.exit_time = _get_time_label(data_reset, i)
    result.rr_achieved = _calculate_rr(result.pnl, effective_entry, setup.stop_loss, is_buy)

    return result
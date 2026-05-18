"""
Trade Simulator
---------------
Simulates a single trade setup through historical testing data.
Handles entry triggering, stop loss, target hits, expiry, and cancellation.

Trade lifecycle:
- Limit order placed → waits for price to reach entry
- If entry NOT reached within max_holding_bars → CANCELLED (no P&L)
- If entry IS reached → trade is live, monitors SL and Target
- If neither SL nor Target hit within max_holding_bars from trigger → EXPIRED (close at market)
"""

import pandas as pd
from strategies.base_strategy import TradeSetup
from .backtester_models import TradeResult


def simulate_setup(setup: TradeSetup, testing_data: pd.DataFrame,
                   max_holding_bars: int, commission_pct: float = 0.001,
                   slippage_pct: float = 0.002) -> TradeResult:
    """
    Simulate a single trade setup through the testing period.

    For BUY setups:  triggered when price drops to entry, exits at SL or target.
    For SELL setups: triggered when price rises to entry, exits at SL or target.

    Applies realistic commission and slippage to every trade.

    Args:
        setup: The trade setup to simulate
        testing_data: OHLCV data for the testing period
        max_holding_bars: Maximum bars to hold before expiry
        commission_pct: Commission percentage per trade leg (default 0.1%)
        slippage_pct: Slippage percentage on entry (default 0.2%)

    Returns:
        TradeResult with outcome details
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

        if not triggered:
            # Check if we've exceeded max holding bars waiting for entry
            if i >= max_holding_bars:
                result.outcome = "CANCELLED"
                result.pnl = 0.0
                return result

            # Check if entry is hit
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

            # Already triggered — check SL then Target
            exit_result = _check_sl_target(
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


def _check_sl_target(result: TradeResult, data_reset: pd.DataFrame, i: int,
                     trigger_idx: int, effective_entry: float, commission_cost: float,
                     is_buy: bool, setup: TradeSetup):
    """
    Check if SL or Target is hit on the current candle.
    Returns TradeResult if exit occurred, None otherwise.
    """
    candle_high = data_reset['High'].iloc[i]
    candle_low = data_reset['Low'].iloc[i]

    if is_buy:
        if candle_low <= setup.stop_loss:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
        elif candle_high >= setup.target:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.target, "TARGET_HIT", is_buy, setup)
    else:  # SELL
        if candle_high >= setup.stop_loss:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.stop_loss, "SL_HIT", is_buy, setup)
        elif candle_low <= setup.target:
            return _fill_exit(result, data_reset, i, trigger_idx, effective_entry,
                              commission_cost, setup.target, "TARGET_HIT", is_buy, setup)

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
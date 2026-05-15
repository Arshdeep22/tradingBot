"""
Bot Runner - GitHub Actions Compatible
========================================
This script runs on a schedule (via GitHub Actions) to:
1. Check pending orders → execute if price hits entry
2. Monitor open trades → close if SL or Target hit
3. Scan for new zones → create pending orders automatically

Designed to run as a cron job every 5 minutes during market hours.
No need to keep your laptop on!

Usage:
    python bot_runner.py                    # Full cycle (check orders + monitor + scan)
    python bot_runner.py --check-only       # Only check pending orders & monitor trades
    python bot_runner.py --scan-only        # Only scan for new zones
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import DatabaseManager
from core.data_fetcher import DataFetcher
from strategies.zone_scanner import ZoneScanner
from strategies import STRATEGY_REGISTRY
from config.settings import (
    INITIAL_CAPITAL, SYMBOLS, NIFTY_50,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    MAX_OPEN_POSITIONS, MAX_DAILY_LOSS_PCT, NSE_HOLIDAYS_2026,
    ACTIVE_STRATEGY, PAPER_TRADING_MODE,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot_runner.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

# Initialize components
db = DatabaseManager()
data_fetcher = DataFetcher()

# Instantiate the active strategy from the registry
# Load AI-optimized params from strategy memory if available, else use defaults
try:
    from core.llm_advisor import StrategyMemory
    _mem = StrategyMemory()
    if _mem.best_params:
        _lp = _mem.live_params()
        logger.info(f"Loaded AI-optimized params: score={_lp['min_score']}, rr={_lp['rr_ratio']}, base={_lp['max_base_candles']} (backtest WR: {_mem.best_win_rate:.1f}%)")
    else:
        _lp = {"min_score": 80, "rr_ratio": 3.0, "max_base_candles": 5}
        logger.info("No AI memory found — using default params: score=80, rr=3.0, base=5")
except Exception as _e:
    _lp = {"min_score": 80, "rr_ratio": 3.0, "max_base_candles": 5}
    logger.warning(f"Could not load strategy memory ({_e}) — using defaults")

# Regime-aware strategy selection:
# 1. Best performing strategy over last 5 days (data-driven)
# 2. Regime recommendation (market-condition-driven)
# 3. ACTIVE_STRATEGY from settings (fallback)
_selected_strategy = ACTIVE_STRATEGY
try:
    from core.market_regime import detect_regime
    from core.learning_journal import LearningJournal
    _regime = detect_regime()
    _journal_best = LearningJournal().best_strategy_last_n_days(5)
    if _journal_best:
        _selected_strategy = _journal_best
        logger.info(f"Strategy selected by 5-day journal performance: {_selected_strategy}")
    elif _regime.best_strategy:
        _selected_strategy = _regime.best_strategy
        logger.info(f"Strategy selected by regime ({_regime.regime}): {_selected_strategy}")
    logger.info(f"Regime: {_regime.regime} | ADX={_regime.adx} | VIX={_regime.vix} | Nifty={_regime.nifty_direction}")
except Exception as _e:
    logger.warning(f"Regime/journal selection failed ({_e}) — using {_selected_strategy}")

StrategyClass = STRATEGY_REGISTRY.get(_selected_strategy, ZoneScanner)

if _selected_strategy == "Supply & Demand Zones":
    strategy = StrategyClass(
        min_score=_lp["min_score"],
        rr_ratio=_lp["rr_ratio"],
        max_base_candles=_lp["max_base_candles"],
    )
else:
    strategy = StrategyClass()

zone_scanner = strategy  # backward-compat alias used in older code paths
logger.info(f"Active strategy: {_selected_strategy} ({StrategyClass.__name__})")

# In paper trading mode, scan from the full Nifty 50 (up to 20 symbols)
# In real money mode, use the default 5-stock watchlist
_scan_pool = NIFTY_50[:20] if PAPER_TRADING_MODE else SYMBOLS

# ── Paper mode: run all 3 strategies in parallel with regime-adaptive slot budgets ──

ZONE_PROXIMITY_PCT = 1.5  # % from zone entry → execute immediately as OPEN trade

_REGIME_HEURISTICS = {
    "trending_up":   {"Supply & Demand Zones": 3, "EMA Crossover": 6, "RSI Reversal": 3},
    "trending_down": {"Supply & Demand Zones": 3, "EMA Crossover": 6, "RSI Reversal": 3},
    "ranging":       {"Supply & Demand Zones": 4, "EMA Crossover": 2, "RSI Reversal": 6},
    "volatile":      {"Supply & Demand Zones": 6, "EMA Crossover": 3, "RSI Reversal": 3},
    "unknown":       {"Supply & Demand Zones": 4, "EMA Crossover": 4, "RSI Reversal": 4},
}


def _get_strategy_slots() -> dict:
    """Return per-strategy slot counts based on current regime + learned weights."""
    regime_name = "unknown"
    try:
        regime_name = _regime.regime
    except Exception:
        pass
    weights_path = ".streamlit/strategy_weights.json"
    if os.path.exists(weights_path):
        try:
            with open(weights_path) as _f:
                learned = json.load(_f)
            if regime_name in learned:
                return learned[regime_name]
        except Exception:
            pass
    return _REGIME_HEURISTICS.get(regime_name, _REGIME_HEURISTICS["unknown"])


_paper_strategies = {_selected_strategy: strategy}
if PAPER_TRADING_MODE:
    for _sname, _scls in STRATEGY_REGISTRY.items():
        if _sname not in _paper_strategies:
            _paper_strategies[_sname] = _scls()
    logger.info(f"Paper mode: {len(_paper_strategies)} strategies with regime-adaptive slots")


def is_market_hours() -> bool:
    """Check if current time is within Indian market hours (IST)"""
    # GitHub Actions runs in UTC, so convert to IST (UTC+5:30)
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)

    # Check weekday (Monday=0 to Friday=4)
    if ist_now.weekday() > 4:
        logger.info(f"Weekend - Market closed. IST: {ist_now.strftime('%Y-%m-%d %H:%M:%S')}")
        return False

    # Check NSE holidays
    if ist_now.date() in NSE_HOLIDAYS_2026:
        logger.info(f"NSE Holiday - Market closed. IST: {ist_now.strftime('%Y-%m-%d')}")
        return False

    market_open = ist_now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    market_close = ist_now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)

    is_open = market_open <= ist_now <= market_close
    if not is_open:
        logger.info(f"Market closed. IST: {ist_now.strftime('%H:%M')} (Open: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d})")

    return is_open


def check_pending_orders():
    """
    Check all pending orders against current market prices.
    Execute orders where price has reached the entry level.
    """
    pending_orders = db.get_pending_orders()

    if not pending_orders:
        logger.info("No pending orders to check")
        return 0

    logger.info(f"Checking {len(pending_orders)} pending orders...")
    executed_count = 0

    for order in pending_orders:
        symbol = order['symbol']
        entry_price = order['entry_price']
        side = order['side']

        try:
            current_price = data_fetcher.get_current_price(symbol)
            if current_price <= 0:
                logger.warning(f"Could not get price for {symbol}")
                continue

            should_execute = False

            if side == "BUY":
                # For BUY (demand zone): execute when price drops TO or BELOW entry
                if current_price <= entry_price:
                    should_execute = True
                    logger.info(f"🟢 BUY TRIGGERED: {symbol} | Price: ₹{current_price:.2f} <= Entry: ₹{entry_price:.2f}")

            elif side == "SELL":
                # For SELL (supply zone): execute when price rises TO or ABOVE entry
                if current_price >= entry_price:
                    should_execute = True
                    logger.info(f"🔴 SELL TRIGGERED: {symbol} | Price: ₹{current_price:.2f} >= Entry: ₹{entry_price:.2f}")

            if should_execute:
                # Check position limits
                open_trades = db.get_open_trades()
                if len(open_trades) >= MAX_OPEN_POSITIONS:
                    logger.warning(f"Max positions ({MAX_OPEN_POSITIONS}) reached. Skipping {symbol}")
                    continue

                # Execute the order
                db.execute_pending_order(order['id'])
                executed_count += 1
                logger.info(f"✅ Order #{order['id']} EXECUTED: {side} {order['quantity']} {symbol} @ ₹{entry_price:.2f}")
            else:
                logger.info(f"⏳ {symbol}: Current ₹{current_price:.2f} | Entry ₹{entry_price:.2f} | Waiting...")

        except Exception as e:
            logger.error(f"Error checking order for {symbol}: {e}")

    return executed_count


def monitor_open_trades():
    """
    Monitor open trades for Stop Loss and Target hits.
    Close trades that hit SL or Target.
    """
    open_trades = db.get_open_trades()

    if not open_trades:
        logger.info("No open trades to monitor")
        return 0

    logger.info(f"Monitoring {len(open_trades)} open trades...")
    closed_count = 0

    for trade in open_trades:
        symbol = trade['symbol']
        entry_price = trade['entry_price']
        stop_loss = trade['stop_loss']
        target = trade['target']
        side = trade['side']
        quantity = trade['quantity']

        try:
            current_price = data_fetcher.get_current_price(symbol)
            if current_price <= 0:
                logger.warning(f"Could not get price for {symbol}")
                continue

            should_close = False
            close_reason = ""
            exit_price = current_price

            if side == "BUY":
                # Check Stop Loss (price drops below SL)
                if stop_loss > 0 and current_price <= stop_loss:
                    should_close = True
                    close_reason = "STOP LOSS HIT"
                    exit_price = stop_loss
                    logger.info(f"🛑 SL HIT: {symbol} | Price: ₹{current_price:.2f} <= SL: ₹{stop_loss:.2f}")

                # Check Target (price rises above target)
                elif target > 0 and current_price >= target:
                    should_close = True
                    close_reason = "TARGET HIT"
                    exit_price = target
                    logger.info(f"🎯 TARGET HIT: {symbol} | Price: ₹{current_price:.2f} >= Target: ₹{target:.2f}")

            elif side == "SELL":
                # Check Stop Loss (price rises above SL)
                if stop_loss > 0 and current_price >= stop_loss:
                    should_close = True
                    close_reason = "STOP LOSS HIT"
                    exit_price = stop_loss
                    logger.info(f"🛑 SL HIT: {symbol} | Price: ₹{current_price:.2f} >= SL: ₹{stop_loss:.2f}")

                # Check Target (price drops below target)
                elif target > 0 and current_price <= target:
                    should_close = True
                    close_reason = "TARGET HIT"
                    exit_price = target
                    logger.info(f"🎯 TARGET HIT: {symbol} | Price: ₹{current_price:.2f} <= Target: ₹{target:.2f}")

            if should_close:
                # Calculate PnL
                if side == "BUY":
                    pnl = (exit_price - entry_price) * quantity
                else:
                    pnl = (entry_price - exit_price) * quantity

                db.close_trade(symbol=symbol, exit_price=exit_price, pnl=pnl, reason=close_reason)
                closed_count += 1
                logger.info(f"✅ Trade CLOSED: {symbol} | PnL: ₹{pnl:.2f} | Reason: {close_reason}")
            else:
                # Trailing stop: move SL to breakeven after 1:1 R is reached
                risk = abs(entry_price - stop_loss) if stop_loss > 0 else 0
                if risk > 0 and stop_loss != entry_price:
                    if side == "BUY" and current_price >= entry_price + risk:
                        if stop_loss < entry_price:
                            db.update_trade_stop_loss(trade['id'], entry_price)
                            logger.info(
                                f"🔒 Breakeven: {symbol} | SL moved to entry ₹{entry_price:.2f} "
                                f"(price reached 1:1 R at ₹{entry_price + risk:.2f})"
                            )
                    elif side == "SELL" and current_price <= entry_price - risk:
                        if stop_loss > entry_price:
                            db.update_trade_stop_loss(trade['id'], entry_price)
                            logger.info(
                                f"🔒 Breakeven: {symbol} | SL moved to entry ₹{entry_price:.2f} "
                                f"(price reached 1:1 R at ₹{entry_price - risk:.2f})"
                            )

                # Calculate unrealized PnL for logging
                if side == "BUY":
                    unrealized_pnl = (current_price - entry_price) * quantity
                else:
                    unrealized_pnl = (entry_price - current_price) * quantity
                logger.info(f"📊 {symbol}: ₹{current_price:.2f} | Entry: ₹{entry_price:.2f} | Unrealized: ₹{unrealized_pnl:.2f}")

        except Exception as e:
            logger.error(f"Error monitoring {symbol}: {e}")

    return closed_count


def auto_scan_zones():
    """
    Scan for new trade setups across all strategies and create orders.
    Paper mode: all 3 strategies run in parallel with regime-adaptive slot budgets.
    Real mode: single selected strategy only.
    """
    from collections import defaultdict

    pending_orders = db.get_pending_orders()
    open_trades = db.get_open_trades()

    # Overall gate: in paper mode count only OPEN trades so we always place 12 fresh orders daily
    if PAPER_TRADING_MODE:
        total_active = len(open_trades)
    else:
        total_active = len(open_trades) + len(pending_orders)

    if total_active >= MAX_OPEN_POSITIONS:
        logger.info(f"Max open positions reached ({total_active}/{MAX_OPEN_POSITIONS}). Skipping scan.")
        return 0

    # Determine per-strategy slot budgets
    run_strategies = list(_paper_strategies.items()) if PAPER_TRADING_MODE else [(_selected_strategy, strategy)]
    strat_weights = _get_strategy_slots() if PAPER_TRADING_MODE else {_selected_strategy: MAX_OPEN_POSITIONS}
    strat_count = defaultdict(int)
    for o in pending_orders:
        strat_count[o.get('strategy', '')] += 1
    for t in open_trades:
        strat_count[t.get('strategy', '')] += 1
    strat_slots = {
        name: max(0, strat_weights.get(name, 4) - strat_count[name])
        for name, _ in run_strategies
    }
    logger.info(f"Scanning for setups... strategy slots: {dict(strat_slots)}")

    active_symbols = {o['symbol'] for o in pending_orders} | {t['symbol'] for t in open_trades}
    symbols_to_scan = [s for s in _scan_pool if s not in active_symbols]

    if not symbols_to_scan:
        logger.info("All watched symbols already have active orders/trades")
        return 0

    # Pre-fetch data once per symbol — reused across all strategies
    symbol_data = {}
    for symbol in symbols_to_scan:
        try:
            data = data_fetcher.get_data(symbol, period="5d", interval="15m")
            if data is not None and len(data) > 0:
                symbol_data[symbol] = data
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")

    new_orders = 0

    # Each strategy independently scans all available symbols up to its slot budget
    for strat_name, strat_instance in run_strategies:
        if strat_slots.get(strat_name, 0) <= 0:
            logger.info(f"{strat_name}: quota full, skipping")
            continue
        strat_new = 0

        for symbol, data in symbol_data.items():
            if strat_new >= strat_slots.get(strat_name, 0):
                break
            if symbol in active_symbols:
                continue

            try:
                setups = strat_instance.get_trade_setups(data, symbol)
                if not setups:
                    continue
                best = setups[0]
                risk_per_share = abs(best.entry - best.stop_loss)
                quantity = max(1, int(INITIAL_CAPITAL * 0.01 / max(risk_per_share, 0.01)))

                # Zone strategy in paper mode: if price is already at zone, execute immediately
                if PAPER_TRADING_MODE and strat_name == "Supply & Demand Zones":
                    try:
                        current_price = data_fetcher.get_current_price(symbol)
                        if current_price > 0:
                            proximity = abs(current_price - best.entry) / best.entry * 100
                            if proximity <= ZONE_PROXIMITY_PCT:
                                trade_id = db.save_trade(
                                    symbol=symbol, side=best.side, quantity=quantity,
                                    entry_price=current_price,
                                    stop_loss=best.stop_loss, target=best.target,
                                    strategy=strat_name, reason=best.reasoning,
                                )
                                active_symbols.add(symbol)
                                strat_new += 1
                                new_orders += 1
                                logger.info(
                                    f"⚡ IMMEDIATE Zone: #{trade_id} | {best.side} {symbol} "
                                    f"@ ₹{current_price:.2f} (zone {proximity:.1f}% away)"
                                )
                                continue
                    except Exception as _pe:
                        logger.warning(f"Proximity check failed for {symbol}: {_pe}")

                # Standard: create pending order (EMA/RSI execute on next 5-min cycle)
                order_id = db.save_pending_order(
                    symbol=symbol, side=best.side, quantity=quantity,
                    entry_price=best.entry, stop_loss=best.stop_loss,
                    target=best.target, strategy=strat_name, reason=best.reasoning,
                )
                active_symbols.add(symbol)
                strat_new += 1
                new_orders += 1
                logger.info(f"📋 {strat_name}: #{order_id} | {best.side} {symbol} @ ₹{best.entry:.2f} (Score: {best.score})")

            except Exception as e:
                logger.error(f"Error scanning {symbol} with {strat_name}: {e}")

        if strat_new:
            logger.info(f"{strat_name}: placed {strat_new} new orders this cycle")

    return new_orders


def print_summary():
    """Print current portfolio summary"""
    metrics = db.get_performance_metrics()
    open_trades = db.get_open_trades()
    pending_orders = db.get_pending_orders()

    logger.info("=" * 60)
    logger.info("📊 PORTFOLIO SUMMARY")
    logger.info(f"   💰 Capital: ₹{INITIAL_CAPITAL:,.0f}")
    logger.info(f"   📈 Total P&L: ₹{metrics['total_pnl']:,.2f}")
    logger.info(f"   🏆 Win Rate: {metrics['win_rate']:.1f}%")
    logger.info(f"   📊 Total Trades: {metrics['total_trades']}")
    logger.info(f"   📍 Open Positions: {len(open_trades)}")
    logger.info(f"   ⏳ Pending Orders: {len(pending_orders)}")
    logger.info("=" * 60)


def main():
    """Main bot runner - called by GitHub Actions"""
    os.makedirs("logs", exist_ok=True)

    logger.info("=" * 60)
    logger.info(f"🤖 Bot Runner Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # Parse arguments
    check_only = "--check-only" in sys.argv
    scan_only = "--scan-only" in sys.argv
    force = "--force" in sys.argv  # Skip market hours check

    # Check market hours (unless forced)
    if not force and not is_market_hours():
        logger.info("Market is closed. Exiting.")
        # Expire stale pending orders even when market is closed
        db.expire_old_orders(max_age_days=3)
        return

    logger.info("✅ Market is OPEN - Running bot cycle")

    # Expire stale pending orders (3 days in all modes)
    db.expire_old_orders(max_age_days=3)

    if not scan_only:
        # Step 1: Check pending orders
        logger.info("\n--- STEP 1: Checking Pending Orders ---")
        executed = check_pending_orders()
        logger.info(f"Orders executed: {executed}")

        # Step 2: Monitor open trades
        logger.info("\n--- STEP 2: Monitoring Open Trades ---")
        closed = monitor_open_trades()
        logger.info(f"Trades closed: {closed}")

    if not check_only:
        # Daily loss circuit breaker: halt new orders if daily loss >= 1% of capital
        try:
            from datetime import timezone
            ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
            today_str = ist_now.strftime("%Y-%m-%d")
            today_trades = db.get_closed_trades_for_date(today_str)
            daily_pnl = sum(t.get("pnl", 0) for t in today_trades)
            daily_loss_limit = INITIAL_CAPITAL * MAX_DAILY_LOSS_PCT / 100
            if daily_pnl <= -daily_loss_limit:
                logger.warning(
                    f"🚨 Daily loss limit hit: ₹{daily_pnl:.2f} <= -₹{daily_loss_limit:.2f} "
                    f"({MAX_DAILY_LOSS_PCT}% of ₹{INITIAL_CAPITAL:,.0f}). Halting new orders."
                )
                print_summary()
                logger.info("\n🤖 Bot Runner cycle complete!")
                return
        except Exception as _e:
            logger.warning(f"Could not check daily P&L ({_e}) — proceeding with scan")

        # Step 3: Auto-scan for new zones
        logger.info("\n--- STEP 3: Auto-Scanning for Zones ---")
        new_orders = auto_scan_zones()
        logger.info(f"New pending orders: {new_orders}")

    # Print summary
    print_summary()

    logger.info("\n🤖 Bot Runner cycle complete!")


if __name__ == "__main__":
    main()
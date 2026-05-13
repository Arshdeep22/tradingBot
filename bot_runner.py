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
    ACTIVE_STRATEGY,
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
StrategyClass = STRATEGY_REGISTRY.get(ACTIVE_STRATEGY, ZoneScanner)

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

if ACTIVE_STRATEGY == "Supply & Demand Zones":
    strategy = StrategyClass(
        min_score=_lp["min_score"],
        rr_ratio=_lp["rr_ratio"],
        max_base_candles=_lp["max_base_candles"],
    )
else:
    strategy = StrategyClass()

zone_scanner = strategy  # backward-compat alias used in older code paths
logger.info(f"Active strategy: {ACTIVE_STRATEGY} ({StrategyClass.__name__})")


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
    Automatically scan for new trade setups and create pending orders.
    Only runs if we have fewer than MAX_OPEN_POSITIONS pending + open.
    """
    # Check how many orders/trades we already have
    pending_orders = db.get_pending_orders()
    open_trades = db.get_open_trades()
    total_active = len(pending_orders) + len(open_trades)

    if total_active >= MAX_OPEN_POSITIONS:
        logger.info(f"Already have {total_active} active orders/trades (max: {MAX_OPEN_POSITIONS}). Skipping scan.")
        return 0

    slots_available = MAX_OPEN_POSITIONS - total_active
    logger.info(f"Scanning for setups... ({slots_available} slots available)")

    # Get symbols that don't already have pending orders or open trades
    active_symbols = set()
    for order in pending_orders:
        active_symbols.add(order['symbol'])
    for trade in open_trades:
        active_symbols.add(trade['symbol'])

    # Scan a subset of symbols (to stay within API limits)
    symbols_to_scan = [s for s in SYMBOLS if s not in active_symbols][:10]

    if not symbols_to_scan:
        logger.info("All watched symbols already have active orders/trades")
        return 0

    new_orders = 0

    for symbol in symbols_to_scan:
        if new_orders >= slots_available:
            break

        try:
            data = data_fetcher.get_data(symbol, period="5d", interval="15m")
            if data is None or len(data) == 0:
                logger.warning(f"No data for {symbol} — skipping")
                continue

            setups = strategy.get_trade_setups(data, symbol)

            if setups:
                best = setups[0]  # Highest scoring setup
                logger.info(f"🎯 Setup found: {symbol} - {best.side} (Score: {best.score})")

                # Calculate quantity (1% risk per trade)
                risk_per_share = abs(best.entry - best.stop_loss)
                if risk_per_share > 0:
                    risk_amount = INITIAL_CAPITAL * 0.01  # 1% of capital
                    quantity = max(1, int(risk_amount / risk_per_share))
                else:
                    quantity = 1

                # Create pending order
                order_id = db.save_pending_order(
                    symbol=symbol,
                    side=best.side,
                    quantity=quantity,
                    entry_price=best.entry,
                    stop_loss=best.stop_loss,
                    target=best.target,
                    strategy=ACTIVE_STRATEGY,
                    reason=best.reasoning
                )

                logger.info(f"📋 Pending order created: #{order_id} | {best.side} {symbol} @ ₹{best.entry:.2f}")
                new_orders += 1

        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")

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
        # Still expire old orders even when market is closed
        db.expire_old_orders(max_age_days=3)
        return

    logger.info("✅ Market is OPEN - Running bot cycle")

    # Expire old pending orders
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
"""
AI Trade Runner
---------------
Runs at 11:00 AM IST via GitHub Actions.
Scans all Nifty 50 stocks, asks Claude for the top 10 trade setups,
and places the top 5 as pending orders tagged with strategy="AI Recommendations".

Also saves reports/YYYY-MM-DD_recommendations.json so the EOD report
can compare what was recommended vs. what succeeded.

Usage:
    python ai_trade_runner.py           # Runs only during market hours
    python ai_trade_runner.py --force   # Skip market hours check (for testing)
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import DatabaseManager
from core.ai_recommender import create_llm_from_env, scan_nifty50_zones, get_ai_recommendations
from config.settings import (
    INITIAL_CAPITAL, MAX_OPEN_POSITIONS,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
    NSE_HOLIDAYS_2026,
)

TOP_N_ORDERS = 5  # How many AI recommendations to auto-place as pending orders

os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/ai_trade_runner.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

db = DatabaseManager()


def ist_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)


def is_market_hours() -> bool:
    now = ist_now()
    if now.weekday() > 4:
        logger.info(f"Weekend — market closed. IST: {now.strftime('%Y-%m-%d %H:%M')}")
        return False
    if now.date() in NSE_HOLIDAYS_2026:
        logger.info(f"NSE holiday — market closed. IST: {now.strftime('%Y-%m-%d')}")
        return False
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)
    if not (market_open <= now <= market_close):
        logger.info(f"Market closed. IST: {now.strftime('%H:%M')}")
        return False
    return True


def _active_symbols() -> set:
    """Symbols that already have a pending order or open trade."""
    active = set()
    for order in db.get_pending_orders():
        active.add(order["symbol"])
    for trade in db.get_open_trades():
        active.add(trade["symbol"])
    return active


def place_orders(selected_setups: list, ai_recs: list) -> list:
    """
    Create pending orders for the selected setups.
    Returns list of dicts describing what was placed.
    """
    active = _active_symbols()
    open_trades = db.get_open_trades()
    pending_orders = db.get_pending_orders()
    total_active = len(open_trades) + len(pending_orders)
    slots = MAX_OPEN_POSITIONS - total_active

    if slots <= 0:
        logger.warning(f"No slots available ({total_active}/{MAX_OPEN_POSITIONS} active). Skipping order placement.")
        return []

    placed = []
    for setup, rec in selected_setups:
        if len(placed) >= slots:
            logger.info(f"Filled available slots ({slots}). Stopping.")
            break
        if setup.symbol in active:
            logger.info(f"Skipping {setup.symbol} — already has active order/trade")
            continue

        risk = abs(setup.entry - setup.stop_loss)
        quantity = max(1, int((INITIAL_CAPITAL * 0.01) / max(risk, 0.01)))
        order_id = db.save_pending_order(
            symbol=setup.symbol,
            side=setup.side,
            quantity=quantity,
            entry_price=setup.entry,
            stop_loss=setup.stop_loss,
            target=setup.target,
            strategy="AI Recommendations",
            reason=setup.reasoning,
        )
        active.add(setup.symbol)
        prob = rec.get("win_probability", 0) if rec else 0
        logger.info(
            f"Pending order #{order_id}: {setup.side} {setup.symbol} "
            f"@ ₹{setup.entry:.2f} | SL ₹{setup.stop_loss:.2f} | "
            f"Target ₹{setup.target:.2f} | AI prob {prob}%"
        )
        placed.append({
            "order_id": order_id,
            "symbol": setup.symbol,
            "side": setup.side,
            "entry": setup.entry,
            "stop_loss": setup.stop_loss,
            "target": setup.target,
            "quantity": quantity,
            "win_probability": prob,
        })

    return placed


def save_recommendations_log(today: str, all_setups: list, ai_output: dict,
                              display_items: list, placed: list):
    """Save morning recommendations to reports/YYYY-MM-DD_recommendations.json."""
    placed_symbols = {p["symbol"] for p in placed}

    recs_log = []
    for i, (setup, rec) in enumerate(display_items):
        recs_log.append({
            "rank": i + 1,
            "symbol": setup.symbol,
            "side": setup.side,
            "entry": setup.entry,
            "stop_loss": setup.stop_loss,
            "target": setup.target,
            "zone_score": setup.score,
            "win_probability": rec.get("win_probability", 0) if rec else 0,
            "conviction": rec.get("conviction", "N/A") if rec else "N/A",
            "reasoning": rec.get("reasoning", []) if rec else [],
            "risks": rec.get("risks", "") if rec else "",
            "entry_advice": rec.get("entry_advice", "") if rec else "",
            "order_placed": setup.symbol in placed_symbols,
        })

    payload = {
        "date": today,
        "scan_time_ist": ist_now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_setups_found": len(all_setups),
        "total_candidates_sent_to_ai": min(20, len(all_setups)),
        "ai_available": ai_output is not None,
        "market_context": ai_output.get("market_context", "") if ai_output else "",
        "top10_recommendations": recs_log,
        "orders_placed": placed,
    }

    path = f"reports/{today}_recommendations.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Recommendations saved to {path}")


def main():
    force = "--force" in sys.argv

    logger.info("=" * 60)
    logger.info(f"AI Trade Runner started at {ist_now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    logger.info("=" * 60)

    if not force and not is_market_hours():
        logger.info("Market is closed. Exiting.")
        return

    today = ist_now().strftime("%Y-%m-%d")

    # Step 1: Scan zones
    logger.info("\n--- STEP 1: Scanning Nifty 50 for zones ---")
    all_setups = scan_nifty50_zones(min_score=75)

    if not all_setups:
        logger.warning("No qualifying zones found. Exiting.")
        return

    candidates = all_setups[:20]

    # Step 2: Get AI recommendations
    logger.info(f"\n--- STEP 2: Asking AI to rank {len(candidates)} candidates ---")
    ai_output = None
    try:
        llm = create_llm_from_env()
        ai_output = get_ai_recommendations(candidates, llm)
    except KeyError as e:
        logger.warning(f"AICORE env var missing ({e}) — falling back to zone score ranking")
    except Exception as e:
        logger.warning(f"AI call failed ({e}) — falling back to zone score ranking")

    # Step 3: Build display list (same logic as the Streamlit page)
    display_items = []
    if ai_output and "recommendations" in ai_output:
        logger.info(f"AI returned {len(ai_output['recommendations'])} recommendations")
        recs = sorted(ai_output["recommendations"], key=lambda r: r.get("rank", 99))
        used_ids = set()
        for rec in recs[:10]:
            cid = rec.get("id", -1)
            if isinstance(cid, int) and 0 <= cid < len(candidates):
                display_items.append((candidates[cid], rec))
                used_ids.add(cid)
        for i, s in enumerate(candidates):
            if len(display_items) >= 10:
                break
            if i not in used_ids:
                display_items.append((s, None))
    else:
        logger.info("Using top 10 by zone score (no AI output)")
        display_items = [(s, None) for s in candidates[:10]]

    logger.info(f"Top 10 recommendations built ({len(display_items)} items)")

    # Step 4: Place top 5 as pending orders
    logger.info(f"\n--- STEP 3: Placing top {TOP_N_ORDERS} as pending orders ---")
    selected = display_items[:TOP_N_ORDERS]
    placed = place_orders(selected, [rec for _, rec in selected])

    logger.info(f"Orders placed: {len(placed)}/{TOP_N_ORDERS}")

    # Step 5: Save recommendations log
    save_recommendations_log(today, all_setups, ai_output, display_items, placed)

    logger.info("=" * 60)
    logger.info(f"AI Trade Runner complete. Placed {len(placed)} pending orders.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

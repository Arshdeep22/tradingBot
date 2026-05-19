"""
Bot Runner — per-candle trade management loop.

Reads open trades from the DB, fetches current price, and applies the
management rules from zone_trade_levels/management.py (breakeven, trailing
stops, time-based exit, target hits) every poll cycle.

Usage (blocking):
    runner = BotRunner(db, data_fetcher)
    runner.run_forever()           # blocks; Ctrl-C to stop

Usage (async, inside an existing event loop):
    runner = BotRunner(db, data_fetcher)
    await runner.run_loop()
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional

from core.data_fetcher import DataFetcher
from strategies.zone_trade_levels.entry_sl import compute_atr
from strategies.zone_trade_levels.management import (
    ActiveTrade, TradeAction, TrailMethod, update_open_trade,
)

logger = logging.getLogger(__name__)


@dataclass
class BotEvent:
    trade_id: int
    symbol: str
    action: str       # mirrors TradeAction.value
    reason: str
    price: float


class BotRunner:
    """
    Polls open trades and applies post-entry management rules.

    Args:
        db: DatabaseManager instance (must have get_open_trades_with_management_state,
            update_trade_management_state, close_trade_by_id, record_partial_exit)
        data_fetcher: DataFetcher instance
        interval_seconds: How often to poll (default 60s)
    """

    def __init__(self, db, data_fetcher: DataFetcher, interval_seconds: int = 60):
        self.db = db
        self.data_fetcher = data_fetcher
        self.interval_seconds = interval_seconds
        self.running = False
        self._events: List[BotEvent] = []   # last N events for dashboard display

    # ── Public API ─────────────────────────────────────────────────────────

    def run_once(self) -> List[BotEvent]:
        """
        Single management cycle over all open trades.
        Returns list of BotEvents (actions taken this cycle).
        """
        events: List[BotEvent] = []
        open_trades = self.db.get_open_trades_with_management_state()

        for trade in open_trades:
            try:
                event = self._process_trade(trade)
                if event:
                    events.append(event)
                    self._events = (events + self._events)[:50]  # keep last 50
            except Exception as e:
                logger.error(f"BotRunner error on {trade.get('symbol')}: {e}")

        return events

    def run_forever(self):
        """Blocking loop. Use Ctrl-C to stop."""
        import time
        self.running = True
        logger.info(f"BotRunner started — polling every {self.interval_seconds}s")
        try:
            while self.running:
                self.run_once()
                time.sleep(self.interval_seconds)
        except KeyboardInterrupt:
            logger.info("BotRunner stopped by user")
        finally:
            self.running = False

    async def run_loop(self):
        """Async version of run_forever — for use inside an existing event loop."""
        self.running = True
        logger.info(f"BotRunner async started — polling every {self.interval_seconds}s")
        while self.running:
            self.run_once()
            await asyncio.sleep(self.interval_seconds)

    def stop(self):
        self.running = False

    def recent_events(self, n: int = 20) -> List[BotEvent]:
        return self._events[:n]

    # ── Internal ───────────────────────────────────────────────────────────

    def _process_trade(self, trade: dict) -> Optional[BotEvent]:
        """Run one trade through the management pipeline. Returns BotEvent if action taken."""
        symbol = trade["symbol"]
        current_price = self.data_fetcher.get_current_price(symbol)
        if not current_price:
            return None

        data = self.data_fetcher.get_data(symbol, "5m", period="1d")
        if data is None or len(data) < 14:
            return None

        # Normalise column names to lowercase
        data.columns = [c.lower() for c in data.columns]
        atr = compute_atr(data)
        current_index = len(data) - 1

        active = self._db_to_active_trade(trade)
        updated, event = update_open_trade(active, data, atr, current_price, current_index)

        if event.action == TradeAction.NONE:
            # Still update tracking fields (high/low watermarks may have changed)
            self.db.update_trade_management_state(
                trade_id=trade["id"],
                current_sl=updated.current_sl,
                breakeven_applied=updated.breakeven_applied,
                partial_taken=updated.partial_taken,
                high_since_entry=max(trade.get("high_since_entry") or 0, current_price)
                if updated.direction == "BUY"
                else trade.get("high_since_entry") or current_price,
                low_since_entry=min(trade.get("low_since_entry") or current_price, current_price)
                if updated.direction == "SELL"
                else trade.get("low_since_entry") or current_price,
            )
            return None

        # Something happened — apply it
        return self._apply_event(trade, updated, event, current_price)

    def _apply_event(self, trade: dict, active: ActiveTrade,
                     event, current_price: float) -> BotEvent:
        tid = trade["id"]
        symbol = trade["symbol"]

        if event.action == TradeAction.FULL_EXIT:
            self.db.close_trade_by_id(tid, current_price, reason=event.reason)
            logger.info(f"[{symbol}] FULL EXIT @ {current_price:.2f} — {event.reason}")

        elif event.action == TradeAction.PARTIAL_EXIT:
            new_qty = max(1, trade["quantity"] - event.quantity_to_close)
            ep = trade["entry_price"]
            partial_pnl = (
                (current_price - ep) * event.quantity_to_close
                if trade["side"] == "BUY"
                else (ep - current_price) * event.quantity_to_close
            )
            self.db.record_partial_exit(tid, new_qty, round(partial_pnl, 2))
            # Move SL to breakeven
            self.db.update_trade_management_state(
                trade_id=tid,
                current_sl=active.current_sl,
                breakeven_applied=True,
                partial_taken=True,
                high_since_entry=trade.get("high_since_entry") or current_price,
                low_since_entry=trade.get("low_since_entry") or current_price,
            )
            logger.info(f"[{symbol}] PARTIAL EXIT {event.quantity_to_close} shares "
                        f"@ {current_price:.2f} — {event.reason}")

        else:
            # BREAKEVEN_APPLIED or trailing stop update — just persist new SL
            self.db.update_trade_management_state(
                trade_id=tid,
                current_sl=active.current_sl,
                breakeven_applied=active.breakeven_applied,
                partial_taken=active.partial_taken,
                high_since_entry=trade.get("high_since_entry") or current_price,
                low_since_entry=trade.get("low_since_entry") or current_price,
            )
            logger.info(f"[{symbol}] SL updated to {active.current_sl:.2f} — {event.reason}")

        return BotEvent(
            trade_id=tid,
            symbol=symbol,
            action=event.action.value,
            reason=event.reason,
            price=current_price,
        )

    def _db_to_active_trade(self, t: dict) -> ActiveTrade:
        """Reconstruct ActiveTrade from a DB trade record dict."""
        return ActiveTrade(
            zone_id=str(t["id"]),
            symbol=t["symbol"],
            direction=t["side"],
            entry_price=float(t["entry_price"]),
            initial_sl=float(t["stop_loss"]),
            current_sl=float(t.get("current_sl") or t["stop_loss"]),
            target_1=float(t["target"]),   # partial target (1:1)
            target_2=float(t["target"]),   # final target — same unless two targets stored
            position_size=int(t["quantity"]),
            base_candles=int(t.get("base_candles") or 2),
            entry_candle_index=int(t.get("entry_candle_index") or 0),
            breakeven_applied=bool(t.get("breakeven_applied")),
            partial_taken=bool(t.get("partial_taken")),
            trail_method=TrailMethod(t.get("trail_method") or "ATR"),
        )

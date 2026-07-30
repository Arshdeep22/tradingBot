"""Broker tool — abstract fills. Ships with an in-process paper broker.

Live broker (Zerodha Kite) is intentionally left as a future adapter — the
same `BrokerTool` interface is used so the agent code doesn't change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from trading_agent.tools.base import ToolBase, ToolError, traced_action


@dataclass
class OpenPosition:
    trade_id: int
    symbol: str
    side: str            # "BUY" | "SELL"
    quantity: int
    entry_price: float
    stop_loss: Optional[float]
    target: Optional[float]


class PaperBroker:
    """Zero-slippage, instant-fill simulator. Keeps state in memory only —
    persistence goes through `trading_agent_trades` (owned by the agent)."""

    def __init__(self, starting_capital: float):
        self.capital = float(starting_capital)
        self.starting_capital = float(starting_capital)
        self.positions: dict[int, OpenPosition] = {}
        self.closed_trades: list[dict] = []
        self._realized_pnl = 0.0

    def open(self, *, trade_id: int, symbol: str, side: str,
             quantity: int, entry_price: float,
             stop_loss: Optional[float], target: Optional[float]) -> OpenPosition:
        pos = OpenPosition(
            trade_id=trade_id, symbol=symbol, side=side, quantity=quantity,
            entry_price=entry_price, stop_loss=stop_loss, target=target,
        )
        self.positions[trade_id] = pos
        return pos

    def close(self, trade_id: int, exit_price: float,
              reason: str = "") -> dict[str, Any]:
        pos = self.positions.pop(trade_id, None)
        if pos is None:
            raise ToolError(f"unknown trade_id={trade_id}")
        if pos.side == "BUY":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity
        self.capital += pnl
        self._realized_pnl += pnl
        record = {
            "trade_id": trade_id,
            "symbol": pos.symbol,
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "reason": reason,
        }
        self.closed_trades.append(record)
        return record

    def check_stops(self, symbol: str, high: float,
                    low: float) -> list[tuple[int, float, str]]:
        """Return [(trade_id, fill_price, reason), ...] for positions whose
        stop or target was touched by this bar. Priority: stop before target
        (conservative: assume worst-case ordering intra-bar)."""
        hits: list[tuple[int, float, str]] = []
        for tid, pos in list(self.positions.items()):
            if pos.symbol != symbol:
                continue
            if pos.side == "BUY":
                if pos.stop_loss is not None and low <= pos.stop_loss:
                    hits.append((tid, pos.stop_loss, "stop_loss"))
                    continue
                if pos.target is not None and high >= pos.target:
                    hits.append((tid, pos.target, "target"))
                    continue
            else:  # SELL / short
                if pos.stop_loss is not None and high >= pos.stop_loss:
                    hits.append((tid, pos.stop_loss, "stop_loss"))
                    continue
                if pos.target is not None and low <= pos.target:
                    hits.append((tid, pos.target, "target"))
                    continue
        return hits

    def mark_to_market(self, prices: dict[str, float]) -> float:
        """Return capital + unrealised PnL at the given per-symbol prices."""
        unreal = 0.0
        for pos in self.positions.values():
            p = prices.get(pos.symbol)
            if p is None:
                continue
            if pos.side == "BUY":
                unreal += (p - pos.entry_price) * pos.quantity
            else:
                unreal += (pos.entry_price - p) * pos.quantity
        return self.capital + unreal


class BrokerTool(ToolBase):
    """Traced wrapper over `PaperBroker` (later: real broker)."""

    tool_name = "broker"

    def __init__(self, db=None, starting_capital: float = 100_000.0,
                 mode: str = "backtest"):
        super().__init__(db=db)
        self._mode = mode
        # For now, backtest + paper both use PaperBroker. `live` will get its
        # own adapter later — same public methods.
        if mode == "live":
            raise NotImplementedError("live broker not implemented yet")
        self.broker = PaperBroker(starting_capital=starting_capital)

    # ── public tool actions ────────────────────────────────────────────────
    @traced_action("open_position")
    def open_position(self, *, trade_id: int, symbol: str, side: str,
                      quantity: int, entry_price: float,
                      stop_loss: Optional[float] = None,
                      target: Optional[float] = None) -> dict:
        pos = self.broker.open(
            trade_id=trade_id, symbol=symbol, side=side,
            quantity=quantity, entry_price=entry_price,
            stop_loss=stop_loss, target=target,
        )
        return {
            "trade_id": pos.trade_id, "symbol": pos.symbol, "side": pos.side,
            "quantity": pos.quantity, "entry_price": pos.entry_price,
            "capital_after": self.broker.capital,
        }

    @traced_action("close_position")
    def close_position(self, trade_id: int, exit_price: float,
                       reason: str = "") -> dict:
        return self.broker.close(trade_id, exit_price, reason=reason)

    @traced_action("check_stops")
    def check_stops(self, symbol: str, high: float, low: float) -> list:
        return self.broker.check_stops(symbol, high, low)

    @traced_action("snapshot")
    def snapshot(self, prices: dict[str, float]) -> dict:
        equity = self.broker.mark_to_market(prices)
        return {
            "capital": self.broker.capital,
            "equity": equity,
            "starting_capital": self.broker.starting_capital,
            "open_positions": len(self.broker.positions),
            "closed_trades": len(self.broker.closed_trades),
            "realized_pnl": round(self.broker._realized_pnl, 2),
        }
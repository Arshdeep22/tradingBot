"""Risk tool — sizing + guard-rails.

Called by the trading agent BEFORE it lets a proposed order go to the
broker. Traces every check so the optimizer can see exactly which
risk rule vetoed a trade.
"""
from __future__ import annotations

from typing import Any, Optional

from trading_agent.tools.base import ToolBase, traced_action


class RiskTool(ToolBase):
    tool_name = "risk"

    def __init__(self, db=None, params: Optional[dict] = None):
        super().__init__(db=db)
        self._params = params or {}

    @traced_action("size_position")
    def size_position(self, *, capital: float, entry: float,
                      stop_loss: float, side: str) -> dict[str, Any]:
        """Return `{ok, quantity, risk_rupees, reason}` for the proposed trade."""
        max_risk_pct = self._params.get("max_risk_pct_per_trade", 1.0)
        capital_floor = self._params.get("capital_floor_rupees", 0.0)

        if capital <= capital_floor:
            return {
                "ok": False, "quantity": 0, "risk_rupees": 0.0,
                "reason": f"capital {capital:.0f} at/below floor {capital_floor:.0f}",
            }

        risk_per_share = abs(entry - stop_loss)
        if risk_per_share <= 0:
            return {
                "ok": False, "quantity": 0, "risk_rupees": 0.0,
                "reason": "entry == stop_loss (would be zero-risk)",
            }

        risk_budget = capital * (max_risk_pct / 100.0)
        qty = int(risk_budget // risk_per_share)
        if qty <= 0:
            return {
                "ok": False, "quantity": 0, "risk_rupees": 0.0,
                "reason": f"risk_per_share {risk_per_share:.2f} exceeds budget {risk_budget:.2f}",
            }

        return {
            "ok": True,
            "quantity": qty,
            "risk_rupees": round(qty * risk_per_share, 2),
            "reason": f"sized {qty} @ {max_risk_pct:.2f}% of {capital:.0f}",
        }

    @traced_action("can_open_new")
    def can_open_new(self, *, open_positions: int,
                     trades_today: int) -> dict[str, Any]:
        """Portfolio-level check: are we allowed to open ANOTHER trade now?"""
        max_conc = self._params.get("max_concurrent_positions", 3)
        max_per_day = self._params.get("max_trades_per_day", 3)
        if open_positions >= max_conc:
            return {"ok": False,
                    "reason": f"open_positions={open_positions} >= max {max_conc}"}
        if trades_today >= max_per_day:
            return {"ok": False,
                    "reason": f"trades_today={trades_today} >= max {max_per_day}"}
        return {"ok": True, "reason": "under limits"}